from __future__ import annotations

import select
import socket
import socketserver
import threading
from collections import deque
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from .models import ActivityRecord, AppConfig, RouteTarget, display_process_name
from .platform.windows_process import resolve_client_process
from .policy import PolicyEngine
from .upstream import normalize_upstream_protocol, socks5_connect


MAX_HEADER = 65536


def _read_header(sock: socket.socket) -> tuple[bytes, bytes]:
    data = bytearray()
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(8192)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > MAX_HEADER:
            raise ValueError("请求头超过 64 KiB")
    marker = data.find(b"\r\n\r\n")
    if marker < 0:
        return bytes(data), b""
    end = marker + 4
    return bytes(data[:end]), bytes(data[end:])


def _parse_authority(value: str, default_port: int) -> tuple[str, int]:
    value = value.strip()
    if value.startswith("["):
        end = value.find("]")
        host = value[1:end]
        port = int(value[end + 2 :]) if len(value) > end + 1 and value[end + 1] == ":" else default_port
        return host, port
    if value.count(":") == 1:
        host, raw_port = value.rsplit(":", 1)
        return host, int(raw_port)
    return value, default_port


def _parse_request(header: bytes) -> tuple[str, str, int, bytes]:
    text = header.decode("iso-8859-1")
    lines = text.split("\r\n")
    method, target, version = lines[0].split(" ", 2)
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" in line:
            name, value = line.split(":", 1)
            headers[name.strip().lower()] = value.strip()
    if method.upper() == "CONNECT":
        host, port = _parse_authority(target, 443)
        return method.upper(), host, port, header
    parsed = urlsplit(target)
    authority = parsed.netloc or headers.get("host", "")
    default_port = 443 if parsed.scheme.lower() == "https" else 80
    host, port = _parse_authority(authority, default_port)
    if not host:
        raise ValueError("请求缺少目标主机")
    origin = parsed.path or "/"
    if parsed.query:
        origin += "?" + parsed.query
    lines[0] = f"{method} {origin} {version}"
    lines = [line for line in lines if not line.lower().startswith("proxy-connection:")]
    rewritten = "\r\n".join(lines).encode("iso-8859-1")
    return method.upper(), host, port, rewritten


def _relay(left: socket.socket, right: socket.socket, timeout: float = 180.0) -> None:
    peers = {left: right, right: left}
    readers = {left, right}
    while readers:
        readable, _, exceptional = select.select(list(readers), [], list(readers), timeout)
        if exceptional or not readable:
            return
        for source in readable:
            target = peers[source]
            try:
                data = source.recv(65536)
            except OSError:
                data = b""
            if not data:
                readers.discard(source)
                # A FIN only closes one direction. Propagate the half-close and
                # keep draining the peer so late HTTP responses are not cut off.
                try:
                    target.shutdown(socket.SHUT_WR)
                except OSError:
                    pass
                continue
            try:
                target.sendall(data)
            except OSError:
                return


def _prepare_relay_socket(sock: socket.socket) -> None:
    sock.settimeout(None)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    except OSError:
        pass


def _connect_succeeded(response: bytes) -> bool:
    try:
        status = int(response.split(b"\r\n", 1)[0].split(b" ", 2)[1])
    except (IndexError, ValueError):
        return False
    return 200 <= status < 300


class _ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True
    block_on_close = False
    request_queue_size = 128


class SplitProxyGateway:
    def __init__(self, config: AppConfig, on_activity: Callable[[ActivityRecord], None] | None = None):
        self.config = config
        self.policy = PolicyEngine(config)
        self.on_activity = on_activity
        self.activities: deque[ActivityRecord] = deque(maxlen=2000)
        self._server: _ThreadingTCPServer | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()

    @property
    def running(self) -> bool:
        return self._server is not None

    def update_config(self, config: AppConfig) -> None:
        with self._lock:
            self.config = config
            self.policy.update(config)

    def start(self) -> None:
        if self.running:
            return
        gateway = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self) -> None:
                gateway._handle(self.request, self.client_address, self.server.server_address)

        self._server = _ThreadingTCPServer((self.config.listen_host, self.config.listen_port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, name="routeweaver-gateway", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        server, thread = self._server, self._thread
        self._server = None
        self._thread = None
        if server:
            server.shutdown()
            server.server_close()
        if thread and thread.is_alive():
            thread.join(timeout=2.0)

    def _record(self, record: ActivityRecord) -> None:
        self.activities.append(record)
        if self.on_activity:
            self.on_activity(record)

    def _handle(self, client: socket.socket, client_address: tuple[str, int], server_address: tuple[str, int]) -> None:
        client.settimeout(20.0)
        upstream: socket.socket | None = None
        process = ""
        host = ""
        port = 0
        decision = None
        response_started = False
        try:
            _, process = resolve_client_process(client_address[0], client_address[1], server_address[0], server_address[1])
            header, remainder = _read_header(client)
            if not header:
                return
            method, host, port, direct_header = _parse_request(header)
            with self._lock:
                config = self.config
                decision = self.policy.decide(process, host)
            if decision.target is RouteTarget.VPN:
                protocol = normalize_upstream_protocol(config.upstream_protocol)
                if protocol == "http":
                    upstream = socket.create_connection((config.upstream_host, config.upstream_port), timeout=15.0)
                    if method == "CONNECT":
                        # Do not pipeline the client's TLS ClientHello before the
                        # proxy has accepted CONNECT. Some local VPN proxies
                        # intermittently reset such optimistic tunnels.
                        upstream.sendall(header)
                        response, response_extra = _read_header(upstream)
                        if not response:
                            raise OSError("VPN 上游未响应 CONNECT")
                        client.sendall(response + response_extra)
                        response_started = True
                        if not _connect_succeeded(response):
                            status_line = response.split(b"\r\n", 1)[0]
                            raise OSError(status_line.decode("iso-8859-1", "replace"))
                        if remainder:
                            upstream.sendall(remainder)
                    else:
                        upstream.sendall(header + remainder)
                else:
                    upstream = socks5_connect(
                        config.upstream_host, config.upstream_port, host, port, timeout=15.0,
                    )
                    if method == "CONNECT":
                        client.sendall(b"HTTP/1.1 200 Connection Established\r\nProxy-Agent: RouteWeaver/1.1\r\n\r\n")
                        response_started = True
                        if remainder:
                            upstream.sendall(remainder)
                    else:
                        upstream.sendall(direct_header + remainder)
                _prepare_relay_socket(client)
                _prepare_relay_socket(upstream)
                _relay(client, upstream)
            else:
                upstream = socket.create_connection((host, port), timeout=15.0)
                if method == "CONNECT":
                    client.sendall(b"HTTP/1.1 200 Connection Established\r\nProxy-Agent: RouteWeaver/1.0\r\n\r\n")
                    response_started = True
                    if remainder:
                        upstream.sendall(remainder)
                else:
                    upstream.sendall(direct_header + remainder)
                _prepare_relay_socket(client)
                _prepare_relay_socket(upstream)
                _relay(client, upstream)
            matched = decision.matched_rule.value if decision.matched_rule else ""
            self._record(ActivityRecord.now(
                process_name=display_process_name(process), process_path=process, host=host, port=port,
                target=decision.target, matched_rule=matched, status="完成",
            ))
        except Exception as exc:
            if not response_started:
                try:
                    client.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Type: text/plain; charset=utf-8\r\nConnection: close\r\n\r\nRouteWeaver connection failed")
                except OSError:
                    pass
            target = decision.target if decision else RouteTarget.DIRECT
            self._record(ActivityRecord.now(
                process_name=display_process_name(process), process_path=process, host=host or "未解析", port=port,
                target=target, matched_rule=decision.matched_rule.value if decision and decision.matched_rule else "",
                status="失败", detail=str(exc),
            ))
        finally:
            if upstream is not None:
                try:
                    upstream.close()
                except OSError:
                    pass
            try:
                client.close()
            except OSError:
                pass
