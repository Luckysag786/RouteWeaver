from __future__ import annotations

import ctypes
import json
import locale
import os
import re
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, build_opener

from ..config import app_data_dir
from ..upstream import ProxyEndpoint, parse_proxy_setting, probe_proxy_protocol

if sys.platform == "win32":
    import winreg


INTERNET_SETTINGS = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
OWNER_KEY = r"Software\RouteWeaver"
MANAGED_VALUES = ("ProxyEnable", "ProxyServer", "ProxyOverride", "AutoConfigURL")
COMMON_LOCAL_PROXY_PORTS = (7890, 7891, 7897, 1080, 10808, 20171, 8080, 8888)


@dataclass(slots=True)
class ProxySnapshot:
    values: dict[str, dict[str, Any] | None]

    def to_dict(self) -> dict[str, Any]:
        return {"values": self.values}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProxySnapshot":
        return cls(values=dict(data["values"]))


class SystemProxyManager:
    def __init__(self, backup_path: Path | None = None):
        self.backup_path = backup_path or app_data_dir() / "proxy-backup.json"

    @property
    def supported(self) -> bool:
        return sys.platform == "win32"

    def snapshot(self) -> ProxySnapshot:
        if not self.supported:
            return ProxySnapshot(values={})
        values: dict[str, dict[str, Any] | None] = {}
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS) as key:
            for name in MANAGED_VALUES:
                try:
                    value, value_type = winreg.QueryValueEx(key, name)
                    values[name] = {"value": value, "type": value_type}
                except FileNotFoundError:
                    values[name] = None
        return ProxySnapshot(values=values)

    def current_proxy(self) -> tuple[bool, str]:
        snap = self.snapshot().values
        enabled_entry = snap.get("ProxyEnable") or {"value": 0}
        server_entry = snap.get("ProxyServer") or {"value": ""}
        return bool(enabled_entry["value"]), str(server_entry["value"])

    def _backup_snapshot(self) -> ProxySnapshot | None:
        try:
            data = json.loads(self.backup_path.read_text(encoding="utf-8"))
            return ProxySnapshot.from_dict(data)
        except (OSError, ValueError, KeyError, TypeError):
            return None

    @staticmethod
    def _snapshot_value(snapshot: ProxySnapshot, name: str, default: Any = "") -> Any:
        entry = snapshot.values.get(name)
        return entry.get("value", default) if entry else default

    def _discovery_snapshot(self) -> tuple[ProxySnapshot, str]:
        # While RouteWeaver owns WinINET, the live value points back to its own
        # gateway. The transactional backup is the authoritative upstream.
        if self.is_owned():
            backup = self._backup_snapshot()
            if backup is not None:
                return backup, "启用前的 Windows 系统代理"
        return self.snapshot(), "Windows 系统代理"

    @staticmethod
    def _endpoint_from_pac(url: str, source: str) -> ProxyEndpoint | None:
        if not url:
            return None
        try:
            parsed = urlsplit(url)
            if parsed.scheme not in ("http", "https", "file"):
                return None
            opener = build_opener(ProxyHandler({}))
            with opener.open(url, timeout=2.0) as response:
                script = response.read(1048576).decode("utf-8", "replace")
        except (OSError, ValueError):
            return None
        matches = re.findall(r"(?i)\b(PROXY|HTTP|SOCKS5?|SOCKS5H)\s+([^\s;\"']+)", script)
        settings = []
        for kind, authority in matches:
            key = "socks" if kind.casefold().startswith("socks") else "http"
            settings.append(f"{key}={authority}")
        return parse_proxy_setting(";".join(settings), f"{source} PAC")

    @staticmethod
    def _winhttp_endpoint() -> ProxyEndpoint | None:
        if sys.platform != "win32":
            return None
        try:
            completed = subprocess.run(
                ["netsh", "winhttp", "show", "proxy"],
                capture_output=True,
                timeout=3,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError):
            return None
        output = completed.stdout
        if isinstance(output, bytes):
            output = output.decode(locale.getpreferredencoding(False), "replace")
        for line in (output or "").splitlines():
            candidate = line.split(":", 1)[1].strip() if ":" in line else line.strip()
            endpoint = parse_proxy_setting(candidate, "WinHTTP 系统代理")
            if endpoint:
                return endpoint
        return None

    @staticmethod
    def _is_excluded(endpoint: ProxyEndpoint, excluded: tuple[str, int] | None) -> bool:
        if not excluded:
            return False
        host, port = excluded
        loopbacks = {"127.0.0.1", "localhost", "::1"}
        same_host = endpoint.host.casefold() == host.casefold() or ({endpoint.host.casefold(), host.casefold()} <= loopbacks)
        return same_host and endpoint.port == port

    def detect_upstream(
        self,
        fallback: ProxyEndpoint | None = None,
        excluded: tuple[str, int] | None = None,
    ) -> ProxyEndpoint | None:
        """Discover the safest usable upstream without ever selecting our gateway."""
        declared: list[ProxyEndpoint] = []
        if self.supported:
            snapshot, source = self._discovery_snapshot()
            enabled = bool(self._snapshot_value(snapshot, "ProxyEnable", 0))
            server = str(self._snapshot_value(snapshot, "ProxyServer", ""))
            if enabled:
                endpoint = parse_proxy_setting(server, source)
                if endpoint and not self._is_excluded(endpoint, excluded):
                    return endpoint
            pac_url = str(self._snapshot_value(snapshot, "AutoConfigURL", ""))
            pac_endpoint = self._endpoint_from_pac(pac_url, source)
            if pac_endpoint and not self._is_excluded(pac_endpoint, excluded):
                return pac_endpoint
            winhttp = self._winhttp_endpoint()
            if winhttp and not self._is_excluded(winhttp, excluded):
                return winhttp

        # Environment proxies are useful for portable/local clients, but only
        # accept loopback values to avoid silently importing corporate secrets
        # or a remote proxy that this desktop app did not configure.
        for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
            endpoint = parse_proxy_setting(os.environ.get(name, ""), f"环境变量 {name}")
            if endpoint and endpoint.host.casefold() in ("127.0.0.1", "localhost", "::1"):
                declared.append(endpoint)
        for endpoint in declared:
            if not self._is_excluded(endpoint, excluded):
                return endpoint

        if fallback and not self._is_excluded(fallback, excluded):
            try:
                with socket.create_connection((fallback.host, fallback.port), timeout=0.7):
                    return ProxyEndpoint(fallback.protocol, fallback.host, fallback.port, "已保存设置（端口可用）")
            except OSError:
                pass

        ports = list(dict.fromkeys(([fallback.port] if fallback else []) + list(COMMON_LOCAL_PROXY_PORTS)))
        if not ports:
            return None

        def probe(port: int) -> ProxyEndpoint | None:
            if excluded and port == excluded[1]:
                return None
            for host in ("127.0.0.1", "::1"):
                protocol = probe_proxy_protocol(host, port, timeout=0.8)
                if protocol:
                    return ProxyEndpoint(protocol, host, port, "本地代理端口自动探测")
            return None

        found: dict[int, ProxyEndpoint] = {}
        with ThreadPoolExecutor(max_workers=min(8, len(ports))) as pool:
            futures = {pool.submit(probe, port): port for port in ports}
            for future in as_completed(futures):
                endpoint = future.result()
                if endpoint:
                    found[futures[future]] = endpoint
        for port in ports:
            if port in found:
                return found[port]
        return None

    def is_owned(self) -> bool:
        if not self.supported:
            return False
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, OWNER_KEY) as key:
                active, _ = winreg.QueryValueEx(key, "Active")
                return bool(active)
        except FileNotFoundError:
            return False

    def activate(self, host: str, port: int) -> None:
        if not self.supported:
            raise RuntimeError("系统代理接管只支持 Windows")
        if self.is_owned():
            enabled, server = self.current_proxy()
            if enabled and server == f"{host}:{port}":
                return
            raise RuntimeError("检测到未恢复的路由织网代理状态，请先执行恢复")
        snapshot = self.snapshot()
        self.backup_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.backup_path.with_suffix(".tmp")
        temp.write_text(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.backup_path)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, OWNER_KEY) as owner:
            winreg.SetValueEx(owner, "Active", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(owner, "Listen", 0, winreg.REG_SZ, f"{host}:{port}")
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, f"{host}:{port}")
                try:
                    winreg.DeleteValue(key, "AutoConfigURL")
                except FileNotFoundError:
                    pass
            self._notify()
        except Exception:
            self.restore()
            raise

    def restore(self) -> bool:
        if not self.supported:
            return False
        if not self.backup_path.exists():
            if self.is_owned():
                self._clear_owner()
            return False
        data = json.loads(self.backup_path.read_text(encoding="utf-8"))
        snapshot = ProxySnapshot.from_dict(data)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS, 0, winreg.KEY_SET_VALUE) as key:
            for name in MANAGED_VALUES:
                entry = snapshot.values.get(name)
                if entry is None:
                    try:
                        winreg.DeleteValue(key, name)
                    except FileNotFoundError:
                        pass
                else:
                    winreg.SetValueEx(key, name, 0, int(entry["type"]), entry["value"])
        self._clear_owner()
        try:
            self.backup_path.unlink()
        except OSError:
            pass
        self._notify()
        return True

    def _clear_owner(self) -> None:
        if not self.supported:
            return
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, OWNER_KEY)
        except (FileNotFoundError, OSError):
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, OWNER_KEY, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.SetValueEx(key, "Active", 0, winreg.REG_DWORD, 0)
            except OSError:
                pass

    @staticmethod
    def _notify() -> None:
        if sys.platform != "win32":
            return
        internet_set_option = ctypes.windll.Wininet.InternetSetOptionW
        internet_set_option(0, 39, 0, 0)  # INTERNET_OPTION_SETTINGS_CHANGED
        internet_set_option(0, 37, 0, 0)  # INTERNET_OPTION_REFRESH


def is_admin() -> bool:
    if sys.platform != "win32":
        return os.geteuid() == 0 if hasattr(os, "geteuid") else False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def relaunch_as_admin() -> bool:
    if sys.platform != "win32":
        return False
    import subprocess

    params = subprocess.list2cmdline(sys.argv)
    executable = sys.executable
    result = ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, params, None, 1)
    return result > 32
