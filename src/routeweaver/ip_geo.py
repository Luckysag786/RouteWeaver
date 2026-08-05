from __future__ import annotations

import json
import http.client
import ssl
from datetime import datetime, timezone
from typing import Any
from urllib.request import ProxyHandler, Request, build_opener

from .models import IpIdentity, RouteTarget
from .upstream import normalize_upstream_protocol, socks5_connect


USER_AGENT = "RouteWeaver/1.0 (+local diagnostics)"


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _fetch_json(url: str, proxy_url: str | None, timeout: float) -> dict[str, Any]:
    handler = ProxyHandler({"http": proxy_url, "https": proxy_url} if proxy_url else {})
    opener = build_opener(handler)
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with opener.open(request, timeout=timeout) as response:
        if response.status != 200:
            raise OSError(f"HTTP {response.status}")
        return json.loads(response.read(262144).decode("utf-8"))


def _fetch_json_socks(url: str, proxy_host: str, proxy_port: int, timeout: float) -> dict[str, Any]:
    from urllib.parse import urlsplit

    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("SOCKS5 IP 检测只接受 HTTPS 地址")
    port = parsed.port or 443
    raw = socks5_connect(proxy_host, proxy_port, parsed.hostname, port, timeout=timeout)
    context = ssl.create_default_context()
    tls = context.wrap_socket(raw, server_hostname=parsed.hostname)
    try:
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        request = (
            f"GET {path} HTTP/1.1\r\nHost: {parsed.hostname}\r\n"
            f"User-Agent: {USER_AGENT}\r\nAccept: application/json\r\nConnection: close\r\n\r\n"
        ).encode("ascii")
        tls.sendall(request)
        response = http.client.HTTPResponse(tls)
        response.begin()
        if response.status != 200:
            raise OSError(f"HTTP {response.status}")
        return json.loads(response.read(262144).decode("utf-8"))
    finally:
        tls.close()


def lookup_identity(
    target: RouteTarget,
    upstream_host: str = "127.0.0.1",
    upstream_port: int = 7888,
    timeout: float = 12.0,
    upstream_protocol: str = "http",
) -> IpIdentity:
    protocol = normalize_upstream_protocol(upstream_protocol)
    proxy_url = f"http://{upstream_host}:{upstream_port}" if target is RouteTarget.VPN and protocol == "http" else None
    errors: list[str] = []
    providers = (
        ("ipwho.is", "https://ipwho.is/"),
        ("ifconfig.co", "https://ifconfig.co/json"),
    )
    for source, url in providers:
        try:
            if target is RouteTarget.VPN and protocol == "socks5":
                data = _fetch_json_socks(url, upstream_host, upstream_port, timeout)
            else:
                data = _fetch_json(url, proxy_url, timeout)
            if source == "ipwho.is":
                if data.get("success") is False or not data.get("ip"):
                    raise ValueError(str(data.get("message") or "响应缺少 IP"))
                connection = data.get("connection") or {}
                return IpIdentity(
                    ip=str(data["ip"]), country=str(data.get("country") or ""),
                    region=str(data.get("region") or ""), city=str(data.get("city") or ""),
                    isp=str(connection.get("isp") or connection.get("org") or ""),
                    source=url, checked_at=_now(), route=target,
                )
            if not data.get("ip"):
                raise ValueError("响应缺少 IP")
            return IpIdentity(
                ip=str(data["ip"]), country=str(data.get("country_name") or data.get("country") or ""),
                region=str(data.get("region") or ""), city=str(data.get("city") or ""),
                isp=str(data.get("org") or data.get("asn_org") or ""), source=url, checked_at=_now(), route=target,
            )
        except Exception as exc:
            errors.append(f"{source}: {exc}")
    return IpIdentity(
        ip="", country="", region="", city="", isp="", source="; ".join(url for _, url in providers),
        checked_at=_now(), route=target, error=" | ".join(errors),
    )
