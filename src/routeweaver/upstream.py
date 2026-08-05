from __future__ import annotations

import ipaddress
import socket
import struct


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

