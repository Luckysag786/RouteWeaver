from __future__ import annotations

import http.client
import ipaddress
import json
import ssl
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener

from . import __version__
from .models import IpIdentity, RouteTarget
from .upstream import normalize_upstream_protocol, socks5_connect


USER_AGENT = f"RouteWeaver/{__version__} (+local diagnostics)"
MAX_RESPONSE = 262144


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _proxy_url(host: str, port: int) -> str:
    authority = f"[{host}]" if ":" in host and not host.startswith("[") else host
    return f"http://{authority}:{port}"


def _fetch_bytes(url: str, proxy_url: str | None, timeout: float, accept: str) -> bytes:
    # Supplying an empty ProxyHandler deliberately disables environment proxies
    # for DIRECT probes. Otherwise a machine-wide HTTPS_PROXY could make both
    # cards report the same route.
    handler = ProxyHandler({"http": proxy_url, "https": proxy_url} if proxy_url else {})
    opener = build_opener(handler)
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept, "Connection": "close"})
    with opener.open(request, timeout=timeout) as response:
        if response.status != 200:
            raise OSError(f"HTTP {response.status}")
        return response.read(MAX_RESPONSE)


def _fetch_bytes_socks(url: str, proxy_host: str, proxy_port: int, timeout: float, accept: str) -> bytes:
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
        authority = parsed.hostname if port == 443 else f"{parsed.hostname}:{port}"
        request = (
            f"GET {path} HTTP/1.1\r\nHost: {authority}\r\n"
            f"User-Agent: {USER_AGENT}\r\nAccept: {accept}\r\nConnection: close\r\n\r\n"
        ).encode("ascii")
        tls.sendall(request)
        response = http.client.HTTPResponse(tls)
        response.begin()
        if response.status != 200:
            raise OSError(f"HTTP {response.status}")
        return response.read(MAX_RESPONSE)
    finally:
        tls.close()


def _fetch_json(url: str, proxy_url: str | None, timeout: float) -> dict[str, Any]:
    return json.loads(_fetch_bytes(url, proxy_url, timeout, "application/json").decode("utf-8-sig"))


def _fetch_json_socks(url: str, proxy_host: str, proxy_port: int, timeout: float) -> dict[str, Any]:
    return json.loads(
        _fetch_bytes_socks(url, proxy_host, proxy_port, timeout, "application/json").decode("utf-8-sig")
    )


def _valid_ip(value: object) -> str:
    text = str(value or "").strip()
    try:
        address = ipaddress.ip_address(text)
    except ValueError as exc:
        raise ValueError("响应缺少有效 IP") from exc
    if not address.is_global:
        raise ValueError("响应不是公网出口 IP")
    return str(address)


def _parse_ipapi(body: bytes) -> tuple[str, str, str, str, str]:
    data = json.loads(body.decode("utf-8-sig"))
    if data.get("error"):
        raise ValueError(str(data.get("reason") or "服务返回错误"))
    return (
        _valid_ip(data.get("ip")),
        str(data.get("country_name") or data.get("country") or ""),
        str(data.get("region") or data.get("region_name") or ""),
        str(data.get("city") or ""),
        str(data.get("org") or data.get("asn") or ""),
    )


def _parse_json_ip(body: bytes) -> tuple[str, str, str, str, str]:
    data = json.loads(body.decode("utf-8-sig"))
    return _valid_ip(data.get("ip")), "", "", "", ""


def _parse_text_ip(body: bytes) -> tuple[str, str, str, str, str]:
    return _valid_ip(body.decode("ascii", "strict")), "", "", "", ""


ProviderParser = Callable[[bytes], tuple[str, str, str, str, str]]
PROVIDERS: tuple[tuple[str, str, str, ProviderParser], ...] = (
    # Start with a currently reachable geo-capable endpoint, then fall back to
    # independent minimal echo services. Public IP display must not depend on
    # optional region/ISP metadata or on two services sharing the same outage.
    ("ipapi.co", "https://ipapi.co/json/", "application/json", _parse_ipapi),
    ("api.ipify.org", "https://api.ipify.org?format=json", "application/json", _parse_json_ip),
    ("api64.ipify.org", "https://api64.ipify.org?format=json", "application/json", _parse_json_ip),
    ("AWS CheckIP", "https://checkip.amazonaws.com/", "text/plain", _parse_text_ip),
    ("icanhazip.com", "https://icanhazip.com/", "text/plain", _parse_text_ip),
)


def lookup_identity(
    target: RouteTarget,
    upstream_host: str = "127.0.0.1",
    upstream_port: int = 7888,
    timeout: float = 6.0,
    upstream_protocol: str = "http",
) -> IpIdentity:
    protocol = normalize_upstream_protocol(upstream_protocol)
    proxy_url = _proxy_url(upstream_host, upstream_port) if target is RouteTarget.VPN and protocol == "http" else None
    errors: list[str] = []

    def fetch(provider: tuple[str, str, str, ProviderParser]) -> IpIdentity:
        source, url, accept, parser = provider
        try:
            if target is RouteTarget.VPN and protocol == "socks5":
                body = _fetch_bytes_socks(url, upstream_host, upstream_port, timeout, accept)
            else:
                body = _fetch_bytes(url, proxy_url, timeout, accept)
            ip, country, region, city, isp = parser(body)
            return IpIdentity(
                ip=ip,
                country=country,
                region=region,
                city=city,
                isp=isp,
                source=url,
                checked_at=_now(),
                route=target,
            )
        except Exception as exc:
            raise OSError(f"{source}: {exc}") from exc

    # Race independent providers in two small waves. This avoids serial timeout
    # amplification while keeping request volume bounded and still leaves a
    # second wave when an entire provider group is filtered by a network.
    for providers in (PROVIDERS[:3], PROVIDERS[3:]):
        if not providers:
            continue
        pool = ThreadPoolExecutor(max_workers=len(providers), thread_name_prefix="routeweaver-ip")
        futures = [pool.submit(fetch, provider) for provider in providers]
        try:
            for future in as_completed(futures):
                try:
                    identity = future.result()
                except Exception as exc:
                    errors.append(str(exc))
                    continue
                for pending in futures:
                    pending.cancel()
                return identity
        finally:
            if all(future.done() for future in futures):
                pool.shutdown(wait=True)
            else:
                pool.shutdown(wait=False, cancel_futures=True)
    return IpIdentity(
        ip="",
        country="",
        region="",
        city="",
        isp="",
        source="; ".join(url for _, url, _, _ in PROVIDERS),
        checked_at=_now(),
        route=target,
        error=" | ".join(errors),
    )
