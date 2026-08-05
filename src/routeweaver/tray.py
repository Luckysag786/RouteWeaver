from __future__ import annotations

import threading
from collections.abc import Callable


class TrayUnavailable(RuntimeError):
    pass


class TrayController:
    """Small pystray adapter that never touches Tk from the tray thread."""

    def __init__(
        self,
        show_window: Callable[[], None],
        toggle_routing: Callable[[], None],
        exit_app: Callable[[], None],
    ) -> None:
        self._show_window = show_window
        self._toggle_routing = toggle_routing
        self._exit_app = exit_app
        self._icon: object | None = None
        self._lock = threading.RLock()

    @property
    def running(self) -> bool:
        return self._icon is not None

    @staticmethod
    def _image() -> object:
        from PIL import Image, ImageDraw

        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((4, 4, 60, 60), radius=14, fill=(37, 99, 235, 255))
        draw.line((18, 21, 46, 21), fill="white", width=6)
        draw.line((18, 32, 40, 32), fill="white", width=6)
        draw.line((18, 43, 48, 43), fill="white", width=6)
        draw.ellipse((42, 16, 52, 26), fill=(15, 157, 115, 255))
        return image

    def start(self) -> None:
        with self._lock:
            if self._icon is not None:
                return
            try:
                import pystray
            except ImportError as exc:
                raise TrayUnavailable("系统托盘组件未随程序安装") from exc
            menu = pystray.Menu(
                pystray.MenuItem("显示主窗口", lambda *_: self._show_window(), default=True),
                pystray.MenuItem("启用/停用分流", lambda *_: self._toggle_routing()),
                pystray.MenuItem("完全退出", lambda *_: self._exit_app()),
            )
            icon = pystray.Icon("RouteWeaver", self._image(), "路由织网 RouteWeaver", menu)
            self._icon = icon
            icon.run_detached()

    def notify_hidden(self) -> None:
        with self._lock:
            icon = self._icon
        if icon is not None:
            try:
                icon.notify("程序仍在后台运行；双击托盘图标可重新打开。", "路由织网")
            except Exception:
                pass

    def stop(self) -> None:
        with self._lock:
            icon = self._icon
            self._icon = None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass
