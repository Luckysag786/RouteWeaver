from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

if sys.platform == "win32":
    import winreg


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
PREFERENCES_KEY = r"Software\RouteWeaverPreferences"
VALUE_NAME = "RouteWeaver"
INSTALLER_CHOICE = "InstallerAutostart"


def startup_command() -> str:
    """Return a correctly quoted command that starts the UI in the tray."""
    if getattr(sys, "frozen", False):
        arguments = [str(Path(sys.executable).resolve()), "--minimized"]
    else:
        executable = Path(sys.executable)
        pythonw = executable.with_name("pythonw.exe")
        arguments = [str(pythonw if pythonw.exists() else executable), "-m", "routeweaver", "--minimized"]
    return subprocess.list2cmdline(arguments)


def startup_enabled() -> bool:
    if sys.platform != "win32":
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return bool(str(value).strip())
    except FileNotFoundError:
        return False


def set_startup(enabled: bool, command: str | None = None) -> None:
    if sys.platform != "win32":
        return
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command or startup_command())
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass


def installer_startup_choice() -> bool | None:
    """Read the one-time installer choice without inventing a preference."""
    if sys.platform != "win32":
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, PREFERENCES_KEY) as key:
            value, _ = winreg.QueryValueEx(key, INSTALLER_CHOICE)
            return bool(int(value))
    except (FileNotFoundError, OSError, ValueError, TypeError):
        return None


def clear_installer_startup_choice() -> None:
    if sys.platform != "win32":
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, PREFERENCES_KEY, 0, winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, INSTALLER_CHOICE)
            except FileNotFoundError:
                pass
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, PREFERENCES_KEY)
        except OSError:
            pass
    except FileNotFoundError:
        pass


def initialize_startup(config: object) -> bool:
    """Apply the installer/default choice once and return the effective value."""
    configured = bool(getattr(config, "startup_configured", False))
    enabled = bool(getattr(config, "start_with_windows", True))
    if not configured:
        installer_choice = installer_startup_choice()
        if installer_choice is not None:
            enabled = installer_choice
        setattr(config, "start_with_windows", enabled)
        setattr(config, "startup_configured", True)
    set_startup(enabled)
    clear_installer_startup_choice()
    return enabled


def executable_exists_in_command(command: str) -> bool:
    """Small diagnostic helper used by tests and the settings page."""
    expanded = os.path.expandvars(command).strip()
    if not expanded:
        return False
    executable = expanded[1:].split('"', 1)[0] if expanded.startswith('"') else expanded.split(" ", 1)[0]
    return Path(executable).exists()
