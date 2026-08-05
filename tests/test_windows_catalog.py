from pathlib import Path

from routeweaver.platform.windows_catalog import extract_executable, guess_executable
from routeweaver.platform.windows_startup import startup_command


def test_extract_executable_from_quoted_display_icon(tmp_path):
    executable = tmp_path / "Example App.exe"
    executable.write_bytes(b"MZ")
    assert extract_executable(f'"{executable}",0') == str(executable)


def test_relative_display_icon_is_rejected(tmp_path, monkeypatch):
    executable = tmp_path / "relative.exe"
    executable.write_bytes(b"MZ")
    monkeypatch.chdir(tmp_path)
    assert extract_executable("relative.exe") == ""


def test_guess_executable_never_scans_current_directory_for_blank_location(tmp_path, monkeypatch):
    executable = tmp_path / "wrong.exe"
    executable.write_bytes(b"MZ")
    monkeypatch.chdir(tmp_path)
    assert guess_executable("Missing App", "", "") == ""


def test_guess_executable_prefers_main_program_over_uninstaller(tmp_path):
    main = tmp_path / "UsefulApp.exe"
    uninstall = tmp_path / "uninstall.exe"
    main.write_bytes(b"MZ")
    uninstall.write_bytes(b"MZ")
    assert Path(guess_executable("Useful App", "", str(tmp_path))).name == "UsefulApp.exe"


def test_startup_command_requests_minimized_launch():
    command = startup_command()
    assert "--minimized" in command
    assert "routeweaver" in command.casefold()
