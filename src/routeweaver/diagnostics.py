from __future__ import annotations

import socket
from dataclasses import dataclass

from .models import AppConfig
from .platform.windows_proxy import SystemProxyManager, is_admin


@dataclass(slots=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def run_diagnostics(config: AppConfig, proxy_manager: SystemProxyManager) -> list[CheckResult]:
    results: list[CheckResult] = []
    results.append(CheckResult("管理员权限", is_admin(), "已获得" if is_admin() else "未获得（当前功能通常只需当前用户权限）"))
    try:
        with socket.create_connection((config.upstream_host, config.upstream_port), timeout=3):
            pass
        results.append(CheckResult("VPN 上游端口", True, f"{config.upstream_host}:{config.upstream_port} 可连接"))
    except OSError as exc:
        results.append(CheckResult("VPN 上游端口", False, str(exc)))
    try:
        addresses = sorted({item[4][0] for item in socket.getaddrinfo("ipwho.is", 443, type=socket.SOCK_STREAM)})
        results.append(CheckResult("DNS 解析", bool(addresses), ", ".join(addresses[:4])))
    except OSError as exc:
        results.append(CheckResult("DNS 解析", False, str(exc)))
    try:
        enabled, server = proxy_manager.current_proxy()
        results.append(CheckResult("Windows 系统代理", enabled, server if enabled else "当前未启用"))
    except Exception as exc:
        results.append(CheckResult("Windows 系统代理", False, str(exc)))
    if proxy_manager.is_owned():
        expected = f"{config.listen_host}:{config.listen_port}"
        enabled, server = proxy_manager.current_proxy()
        results.append(CheckResult("接管一致性", enabled and server == expected, f"当前 {server}，期望 {expected}"))
    return results

