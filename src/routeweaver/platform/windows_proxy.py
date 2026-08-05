from __future__ import annotations

import ctypes
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import app_data_dir

if sys.platform == "win32":
    import winreg


INTERNET_SETTINGS = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
OWNER_KEY = r"Software\RouteWeaver"
MANAGED_VALUES = ("ProxyEnable", "ProxyServer", "ProxyOverride", "AutoConfigURL")


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

