from __future__ import annotations

import ipaddress
import socket
import struct
from dataclasses import dataclass
from urllib.parse import urlsplit


SOCKS5_ERRORS = {
    1: "general SOCKS server failure",
    2: "connection not allowed by ruleset",
    3: "network unreachable",
    4: "host unreachable",
    5: "connection refused",
    6: "TTL expired",
    7: "command not supported",
    8: "address type not supported",
}


@dataclass(frozen=True, slots=True)
class ProxyEndpoint:
    protocol: str
    host: str
    port: int
    source: str = ""

    @property
    def authority(self) -> str:
        host = f"[{self.host}]" if ":" in self.host and not self.host.startswith("[") else self.host
        return f"{host}:{self.port}"


def parse_proxy_setting(value: str, source: str = "") -> ProxyEndpoint | None:
    """Parse WinINET/PAC-style proxy strings without guessing credentials.

    WinINET may publish a single ``host:port`` value or a semicolon-delimited
    mapping such as ``http=...;https=...;socks=...``.  HTTP is preferred when
    both forms exist because RouteWeaver can forward HTTP and CONNECT through
    that endpoint; SOCKS-only settings remain supported.
    """
    candidates: list[tuple[str, str]] = []
    for raw_chunk in value.strip().split(";"):
        chunk = raw_chunk.strip()
        if not chunk or chunk.casefold() == "direct":
            continue
        if "=" in chunk:
            key, endpoint = chunk.split("=", 1)
            key = key.strip().casefold()
            if key not in ("http", "https", "proxy", "socks", "socks5"):
                continue
            protocol = "socks5" if key.startswith("socks") else "http"
        else:
            endpoint = chunk
            lowered = endpoint.casefold()
            protocol = "socks5" if lowered.startswith(("socks://", "socks5://", "socks5h://")) else "http"
        candidates.append((protocol, endpoint.strip()))

    candidates.sort(key=lambda item: item[0] != "http")
    for protocol, endpoint in candidates:
        parsed = urlsplit(endpoint if "://" in endpoint else f"{protocol}://{endpoint}")
        try:
            host = parsed.hostname or ""
            port = parsed.port
        except ValueError:
            continue
        if parsed.username is not None or parsed.password is not None:
            # Authenticated upstreams need credential-aware storage and UI;
            # silently dropping credentials would create a misleading setup.
            continue
        if not host or port is None or not (1 <= port <= 65535):
            continue
        return ProxyEndpoint(protocol, host, port, source)
    return None


def probe_proxy_protocol(host: str, port: int, timeout: float = 1.0) -> str | None:
    """Identify an unauthenticated local HTTP or SOCKS5 listener.

    SOCKS is checked first with its side-effect-free greeting.  HTTP detection
    uses an invalid reserved domain and accepts any syntactically valid proxy
    response, so discovery never depends on a particular public IP service.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.sendall(b"\x05\x01\x00")
            reply = recv_exact(sock, 2)
            if reply[0] == 5 and reply[1] in (0, 0xFF):
                return "socks5"
    except OSError:
        pass
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.sendall(
                b"CONNECT routeweaver.invalid:443 HTTP/1.1\r\n"
                b"Host: routeweaver.invalid:443\r\nConnection: close\r\n\r\n"
            )
            response = sock.recv(64)
            if response.startswith(b"HTTP/"):
                return "http"
    except OSError:
        pass
    return None


def normalize_upstream_protocol(value: str) -> str:
    protocol = value.strip().lower().replace("://", "")
    if protocol in ("socks", "socks5", "socks5h"):
        return "socks5"
    if protocol in ("http", "https"):
        return "http"
    raise ValueError(f"不支持的上游协议：{value}")


def recv_exact(sock: socket.socket, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise OSError("SOCKS5 上游提前关闭连接")
        data.extend(chunk)
    return bytes(data)


def _destination_address(host: str) -> bytes:
    clean_host = host.strip("[]")
    try:
        address = ipaddress.ip_address(clean_host)
    except ValueError:
        encoded = clean_host.encode("idna")
        if not encoded or len(encoded) > 255:
            raise ValueError("SOCKS5 目标域名长度无效")
        return b"\x03" + bytes((len(encoded),)) + encoded
    if address.version == 4:
        return b"\x01" + address.packed
    return b"\x04" + address.packed


def socks5_connect(
    proxy_host: str,
    proxy_port: int,
    target_host: str,
    target_port: int,
    timeout: float = 15.0,
) -> socket.socket:
    """Open a TCP stream through an unauthenticated SOCKS5 proxy.

    Domain names are sent to the proxy rather than resolved locally, preventing
    DNS-path disagreement between the selected VPN route and the local network.
    """
    sock = socket.create_connection((proxy_host, proxy_port), timeout=timeout)
    try:
        sock.sendall(b"\x05\x01\x00")
        version, method = recv_exact(sock, 2)
        if version != 5:
            raise OSError(f"SOCKS5 版本响应无效：{version}")
        if method == 0xFF:
            raise OSError("SOCKS5 上游拒绝无认证连接")
        if method != 0:
            raise OSError(f"SOCKS5 上游要求尚未支持的认证方式：{method}")
        request = b"\x05\x01\x00" + _destination_address(target_host) + struct.pack("!H", target_port)
        sock.sendall(request)
        version, reply, _, address_type = recv_exact(sock, 4)
        if version != 5:
            raise OSError(f"SOCKS5 CONNECT 版本响应无效：{version}")
        if reply != 0:
            raise OSError(f"SOCKS5 CONNECT 失败：{SOCKS5_ERRORS.get(reply, f'code {reply}')} ")
        if address_type == 1:
            recv_exact(sock, 4)
        elif address_type == 4:
            recv_exact(sock, 16)
        elif address_type == 3:
            recv_exact(sock, recv_exact(sock, 1)[0])
        else:
            raise OSError(f"SOCKS5 响应地址类型无效：{address_type}")
        recv_exact(sock, 2)
        return sock
    except Exception:
        sock.close()
        raise
