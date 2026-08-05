from __future__ import annotations

import ctypes
import json
import os
import re
import subprocess
import sys
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

from .windows_process import process_path

if sys.platform == "win32":
    import winreg


TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(wintypes.ULONG)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


@dataclass(frozen=True, slots=True)
class RunningProcess:
    pid: int
    name: str
    executable: str


@dataclass(frozen=True, slots=True)
class InstalledApplication:
    name: str
    publisher: str
    executable: str
    source: str


def list_running_processes() -> list[RunningProcess]:
    if sys.platform != "win32":
        return []
    kernel32 = ctypes.windll.kernel32
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE:
        return []
    result: list[RunningProcess] = []
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        success = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while success:
            pid = int(entry.th32ProcessID)
            name = str(entry.szExeFile)
            executable = process_path(pid)
            if name and pid:
                result.append(RunningProcess(pid, name, executable if not executable.startswith("pid:") else ""))
            success = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return sorted(result, key=lambda item: (item.name.casefold(), item.pid))


def extract_executable(value: str) -> str:
    """Extract an existing .exe path from DisplayIcon/command-style values."""
    raw = os.path.expandvars(str(value or "")).strip()
    if not raw:
        return ""
    if raw.startswith('"'):
        candidate = raw[1:].split('"', 1)[0]
    else:
        match = re.match(r"(?i)^(.+?\.exe)(?:[,\s].*)?$", raw)
        candidate = match.group(1) if match else raw.split(",", 1)[0]
    candidate = candidate.strip().strip('"')
    path = Path(candidate)
    return str(path) if path.is_absolute() and candidate.lower().endswith(".exe") and path.is_file() else ""


def _score_executable(path: Path, display_name: str) -> tuple[int, int, str]:
    stem = re.sub(r"[^a-z0-9]", "", path.stem.casefold())
    wanted = re.sub(r"[^a-z0-9]", "", display_name.casefold())
    excluded = ("unins", "uninstall", "setup", "update", "crash", "helper", "service", "report")
    penalty = 100 if any(token in stem for token in excluded) else 0
    overlap = -len(os.path.commonprefix((stem, wanted)))
    return penalty, overlap, str(path).casefold()


def guess_executable(display_name: str, display_icon: str, install_location: str) -> str:
    icon = extract_executable(display_icon)
    if icon:
        return icon
    raw_location = os.path.expandvars(str(install_location or "")).strip().strip('"')
    if not raw_location:
        return ""
    location = Path(raw_location)
    if not location.is_dir():
        return ""
    try:
        candidates: list[Path] = list(location.glob("*.exe"))
        if len(candidates) < 80:
            for child in location.iterdir():
                try:
                    if child.is_dir():
                        candidates.extend(list(child.glob("*.exe"))[:20])
                except OSError:
                    continue
                if len(candidates) >= 120:
                    break
    except OSError:
        return ""
    candidates = [path for path in candidates if path.is_file()]
    if not candidates:
        return ""
    return str(sorted(candidates, key=lambda path: _score_executable(path, display_name))[0])


def _query(key: object, name: str, default: str = "") -> str:
    try:
        value, _ = winreg.QueryValueEx(key, name)
        return str(value or "")
    except OSError:
        return default


def _registry_applications() -> list[InstalledApplication]:
    if sys.platform != "win32":
        return []
    uninstall = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
    roots = (
        (winreg.HKEY_CURRENT_USER, 0, "当前用户"),
        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY, "桌面应用"),
        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY, "桌面应用 (32 位)"),
    )
    apps: list[InstalledApplication] = []
    for root, view, source in roots:
        try:
            parent = winreg.OpenKey(root, uninstall, 0, winreg.KEY_READ | view)
        except OSError:
            continue
        with parent:
            index = 0
            while True:
                try:
                    subname = winreg.EnumKey(parent, index)
                    index += 1
                except OSError:
                    break
                try:
                    with winreg.OpenKey(parent, subname) as key:
                        name = _query(key, "DisplayName").strip()
                        if not name or _query(key, "SystemComponent") == "1":
                            continue
                        publisher = _query(key, "Publisher").strip()
                        executable = guess_executable(name, _query(key, "DisplayIcon"), _query(key, "InstallLocation"))
                        apps.append(InstalledApplication(name, publisher, executable, source))
                except OSError:
                    continue
    return apps


def _app_paths() -> list[InstalledApplication]:
    if sys.platform != "win32":
        return []
    path_key = r"Software\Microsoft\Windows\CurrentVersion\App Paths"
    results: list[InstalledApplication] = []
    for root, view in ((winreg.HKEY_CURRENT_USER, 0), (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY), (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY)):
        try:
            parent = winreg.OpenKey(root, path_key, 0, winreg.KEY_READ | view)
        except OSError:
            continue
        with parent:
            index = 0
            while True:
                try:
                    subname = winreg.EnumKey(parent, index)
                    index += 1
                except OSError:
                    break
                try:
                    with winreg.OpenKey(parent, subname) as key:
                        raw, _ = winreg.QueryValueEx(key, "")
                    executable = extract_executable(str(raw))
                    if executable:
                        results.append(InstalledApplication(Path(executable).stem, "", executable, "系统应用入口"))
                except OSError:
                    continue
    return results


def _appx_applications() -> list[InstalledApplication]:
    """Resolve Microsoft Store/MSIX app executables from package manifests."""
    if sys.platform != "win32":
        return []
    script = r"""
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$items = foreach ($package in Get-AppxPackage -ErrorAction SilentlyContinue) {
  try {
    $manifest = Get-AppxPackageManifest -Package $package -ErrorAction Stop
    foreach ($app in @($manifest.Package.Applications.Application)) {
      $relative = [string]$app.Executable
      if ($relative -and $relative.EndsWith('.exe', [StringComparison]::OrdinalIgnoreCase)) {
        $display = [string]$manifest.Package.Properties.DisplayName
        if (-not $display -or $display.StartsWith('ms-resource:')) { $display = [string]$package.Name }
        [pscustomobject]@{
          Name = $display
          Publisher = [string]$manifest.Package.Properties.PublisherDisplayName
          Executable = Join-Path ([string]$package.InstallLocation) $relative
        }
      }
    }
  } catch {}
}
@($items) | ConvertTo-Json -Compress
"""
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=25,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=True,
        )
        payload = json.loads(completed.stdout or "[]")
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return []
    if isinstance(payload, dict):
        payload = [payload]
    results: list[InstalledApplication] = []
    for item in payload:
        name = str(item.get("Name", "")).strip()
        executable = str(item.get("Executable", "")).strip()
        if name and Path(executable).is_absolute() and executable.lower().endswith(".exe"):
            results.append(InstalledApplication(name, str(item.get("Publisher", "")).strip(), executable, "Microsoft Store / MSIX"))
    return results


def list_installed_applications() -> list[InstalledApplication]:
    merged: dict[tuple[str, str], InstalledApplication] = {}
    for app in _registry_applications() + _app_paths() + _appx_applications():
        key = (app.name.casefold(), os.path.normcase(app.executable))
        current = merged.get(key)
        if current is None or (not current.executable and app.executable):
            merged[key] = app
    return sorted(merged.values(), key=lambda item: (not bool(item.executable), item.name.casefold(), item.executable.casefold()))
