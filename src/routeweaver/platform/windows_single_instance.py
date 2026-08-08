from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from dataclasses import dataclass


ERROR_ALREADY_EXISTS = 183
DEFAULT_MUTEX_NAME = r"Local\RouteWeaver-{9C9037E8-EA55-42D4-B941-58128E8EF5A6}"


@dataclass(slots=True)
class SingleInstanceGuard:
    handle: int | None

    def close(self) -> None:
        if self.handle is None or sys.platform != "win32":
            self.handle = None
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.CloseHandle(self.handle)
        self.handle = None

    def __enter__(self) -> "SingleInstanceGuard":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def acquire_single_instance(name: str = DEFAULT_MUTEX_NAME) -> SingleInstanceGuard | None:
    """Acquire a per-user Windows mutex, returning ``None`` for a duplicate."""
    if sys.platform != "win32":
        return SingleInstanceGuard(None)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    ctypes.set_last_error(0)
    handle = kernel32.CreateMutexW(None, False, name)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return None
    return SingleInstanceGuard(int(handle))


_active_guard: SingleInstanceGuard | None = None


def ensure_single_instance() -> bool:
    global _active_guard
    if _active_guard is not None:
        return True
    _active_guard = acquire_single_instance()
    return _active_guard is not None


def release_single_instance() -> None:
    global _active_guard
    if _active_guard is not None:
        _active_guard.close()
        _active_guard = None


def show_duplicate_notice() -> None:
    if sys.platform != "win32":
        return
    ctypes.windll.user32.MessageBoxW(
        None,
        "路由织网已经在运行。请从任务栏或系统托盘打开现有窗口，无需重复启动。",
        "路由织网 RouteWeaver",
        0x00000040,
    )
