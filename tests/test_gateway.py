import http.server
import select
import socket
import socketserver
import struct
import threading
import time

from routeweaver.gateway import SplitProxyGateway, _relay
from routeweaver.models import AppConfig, RouteMode, Rule, RuleKind


class ReusableServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class Origin(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"DIRECT_ORIGIN"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


class FakeProxy(socketserver.BaseRequestHandler):
    def handle(self):
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = self.request.recv(4096)
            if not chunk:
                return
            data += chunk
        body = b"VPN_UPSTREAM"
        self.request.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body)


class StrictConnectProxy(socketserver.BaseRequestHandler):
    received_early_tunnel_data = False

    def handle(self):
        data = b""
        while b"\r\n\r\n" not in data:
            data += self.request.recv(4096)
        marker = data.index(b"\r\n\r\n") + 4
        tunnel_data = data[marker:]
        self.request.settimeout(0.15)
        if not tunnel_data:
            try:
                tunnel_data = self.request.recv(4096)
            except TimeoutError:
                tunnel_data = b""
        type(self).received_early_tunnel_data = bool(tunnel_data)
        self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        self.request.settimeout(2)
        if not tunnel_data:
            tunnel_data = self.request.recv(4096)
        self.request.sendall(b"ECHO:" + tunnel_data)


def recv_exact(sock, size):
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise OSError("unexpected EOF")
        data += chunk
    return data


class FakeSocks5(socketserver.BaseRequestHandler):
    hits = 0

    def handle(self):
        version, count = recv_exact(self.request, 2)
        assert version == 5
        methods = recv_exact(self.request, count)
        assert 0 in methods
        self.request.sendall(b"\x05\x00")
        version, command, _, address_type = recv_exact(self.request, 4)
        assert (version, command) == (5, 1)
        if address_type == 1:
            host = socket.inet_ntoa(recv_exact(self.request, 4))
        elif address_type == 3:
            host = recv_exact(self.request, recv_exact(self.request, 1)[0]).decode("idna")
        else:
            host = socket.inet_ntop(socket.AF_INET6, recv_exact(self.request, 16))
        port = struct.unpack("!H", recv_exact(self.request, 2))[0]
        target = socket.create_connection((host, port), timeout=3)
        type(self).hits += 1
        self.request.sendall(b"\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x00")
        sockets = [self.request, target]
        try:
            while True:
                readable, _, _ = select.select(sockets, [], [], 3)
                if not readable:
                    break
                for source in readable:
                    data = source.recv(65536)
                    if not data:
                        return
                    (target if source is self.request else self.request).sendall(data)
        finally:
            target.close()


def start_server(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def request(proxy_port, url, host):
    with socket.create_connection(("127.0.0.1", proxy_port), timeout=3) as sock:
        sock.sendall(f"GET {url} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode())
        response = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk
        return response


def test_forward_and_reverse_routing():
    origin = ReusableServer(("127.0.0.1", 0), Origin)
    fake_proxy = ReusableServer(("127.0.0.1", 0), FakeProxy)
    start_server(origin)
    start_server(fake_proxy)
    gateway_port = free_port()
    config = AppConfig(
        mode=RouteMode.FORWARD, listen_port=gateway_port,
        upstream_port=fake_proxy.server_address[1], rules=[Rule(RuleKind.DOMAIN, "vpn.test")],
    )
    gateway = SplitProxyGateway(config)
    gateway.start()
    try:
        vpn_response = request(gateway_port, "http://vpn.test/", "vpn.test")
        direct_url = f"http://127.0.0.1:{origin.server_address[1]}/"
        direct_response = request(gateway_port, direct_url, f"127.0.0.1:{origin.server_address[1]}")
        assert b"VPN_UPSTREAM" in vpn_response
        assert b"DIRECT_ORIGIN" in direct_response

        config.mode = RouteMode.REVERSE
        gateway.update_config(config)
        vpn_default = request(gateway_port, "http://other.test/", "other.test")
        assert b"VPN_UPSTREAM" in vpn_default
    finally:
        gateway.stop()
        origin.shutdown()
        origin.server_close()
        fake_proxy.shutdown()
        fake_proxy.server_close()


def test_socks5_upstream_routing():
    FakeSocks5.hits = 0
    origin = ReusableServer(("127.0.0.1", 0), Origin)
    socks = ReusableServer(("127.0.0.1", 0), FakeSocks5)
    start_server(origin)
    start_server(socks)
    gateway_port = free_port()
    config = AppConfig(
        mode=RouteMode.FORWARD,
        listen_port=gateway_port,
        upstream_protocol="socks5",
        upstream_port=socks.server_address[1],
        rules=[Rule(RuleKind.DOMAIN, "127.0.0.1")],
    )
    gateway = SplitProxyGateway(config)
    gateway.start()
    try:
        url = f"http://127.0.0.1:{origin.server_address[1]}/"
        response = request(gateway_port, url, f"127.0.0.1:{origin.server_address[1]}")
        assert b"DIRECT_ORIGIN" in response
        assert FakeSocks5.hits == 1
        deadline = time.monotonic() + 1
        while not gateway.activities and time.monotonic() < deadline:
            time.sleep(0.01)
        assert gateway.activities[-1].target.value == "vpn"
    finally:
        gateway.stop()
        origin.shutdown()
        origin.server_close()
        socks.shutdown()
        socks.server_close()


def test_connect_waits_for_upstream_acceptance_before_tunnel_data():
    StrictConnectProxy.received_early_tunnel_data = False
    proxy = ReusableServer(("127.0.0.1", 0), StrictConnectProxy)
    start_server(proxy)
    gateway_port = free_port()
    config = AppConfig(
        mode=RouteMode.FORWARD,
        listen_port=gateway_port,
        upstream_port=proxy.server_address[1],
        rules=[Rule(RuleKind.DOMAIN, "vpn.test")],
    )
    gateway = SplitProxyGateway(config)
    gateway.start()
    try:
        with socket.create_connection(("127.0.0.1", gateway_port), timeout=3) as client:
            client.sendall(b"CONNECT vpn.test:443 HTTP/1.1\r\nHost: vpn.test:443\r\n\r\nHELLO")
            response = b""
            while b"\r\n\r\n" not in response:
                response += client.recv(4096)
            marker = response.index(b"\r\n\r\n") + 4
            body = response[marker:]
            while b"ECHO:HELLO" not in body:
                body += client.recv(4096)
        assert StrictConnectProxy.received_early_tunnel_data is False
        assert b"ECHO:HELLO" in body
    finally:
        gateway.stop()
        proxy.shutdown()
        proxy.server_close()


def test_relay_drains_response_after_request_half_close():
    client, relay_left = socket.socketpair()
    relay_right, server = socket.socketpair()
    thread = threading.Thread(target=_relay, args=(relay_left, relay_right, 2), daemon=True)
    thread.start()
    try:
        client.sendall(b"request")
        client.shutdown(socket.SHUT_WR)
        assert server.recv(7) == b"request"
        assert server.recv(1) == b""
        server.sendall(b"late response")
        server.shutdown(socket.SHUT_WR)
        received = b""
        while True:
            chunk = client.recv(4096)
            if not chunk:
                break
            received += chunk
        assert received == b"late response"
        thread.join(timeout=2)
        assert not thread.is_alive()
    finally:
        for sock in (client, relay_left, relay_right, server):
            sock.close()
