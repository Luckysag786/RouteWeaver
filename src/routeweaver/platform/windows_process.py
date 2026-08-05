from __future__ import annotations

import ctypes
import socket
import struct
import sys
import time
from ctypes import wintypes


AF_INET = 2
TCP_TABLE_OWNER_PID_ALL = 5
ERROR_INSUFFICIENT_BUFFER = 122
NO_ERROR = 0
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


class MIB_TCPROW_OWNER_PID(ctypes.Structure):
    _fields_ = [
        ("dwState", wintypes.DWORD),
        ("dwLocalAddr", wintypes.DWORD),
        ("dwLocalPort", wintypes.DWORD),
        ("dwRemoteAddr", wintypes.DWORD),
        ("dwRemotePort", wintypes.DWORD),
        ("dwOwningPid", wintypes.DWORD),
    ]


def _port(value: int) -> int:
    return socket.ntohs(value & 0xFFFF)


def _ipv4(value: int) -> str:
    return socket.inet_ntoa(struct.pack("<I", value))


def _tcp_rows() -> list[MIB_TCPROW_OWNER_PID]:
    if sys.platform != "win32":
        return []
    size = wintypes.ULONG(0)
    api = ctypes.windll.iphlpapi.GetExtendedTcpTable
    result = api(None, ctypes.byref(size), False, AF_INET, TCP_TABLE_OWNER_PID_ALL, 0)
    if result != ERROR_INSUFFICIENT_BUFFER:
        return []
    buffer = ctypes.create_string_buffer(size.value)
    result = api(buffer, ctypes.byref(size), False, AF_INET, TCP_TABLE_OWNER_PID_ALL, 0)
    if result != NO_ERROR:
        return []
    count = ctypes.cast(buffer, ctypes.POINTER(wintypes.DWORD)).contents.value
    address = ctypes.addressof(buffer) + ctypes.sizeof(wintypes.DWORD)
    row_size = ctypes.sizeof(MIB_TCPROW_OWNER_PID)
    return [MIB_TCPROW_OWNER_PID.from_address(address + index * row_size) for index in range(count)]


def process_path(pid: int) -> str:
    if sys.platform != "win32" or not pid:
        return ""
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return f"pid:{pid}"
    try:
        capacity = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(capacity.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(capacity)):
            return buffer.value
        return f"pid:{pid}"
    finally:
        kernel32.CloseHandle(handle)


def resolve_client_process(
    client_ip: str,
    client_port: int,
    server_ip: str,
    server_port: int,
    attempts: int = 5,
) -> tuple[int, str]:
    """Resolve the owner of the client half of a loopback TCP connection."""
    if sys.platform != "win32" or ":" in client_ip:
        return 0, ""
    for attempt in range(attempts):
        for row in _tcp_rows():
            if _port(row.dwLocalPort) != client_port or _port(row.dwRemotePort) != server_port:
                continue
            local_ip, remote_ip = _ipv4(row.dwLocalAddr), _ipv4(row.dwRemoteAddr)
            local_ok = local_ip in (client_ip, "0.0.0.0")
            remote_ok = remote_ip in (server_ip, "127.0.0.1", "0.0.0.0")
            if local_ok and remote_ok:
                pid = int(row.dwOwningPid)
                return pid, process_path(pid)
        if attempt + 1 < attempts:
            time.sleep(0.015)
    return 0, ""

