"""Windows tray integration for the pywebview shell."""

from __future__ import annotations

import sys
import threading
from typing import Any, Callable


class WindowsTray:
    def __init__(self, window: Any, *, title: str = "Zotero Daily News") -> None:
        self.window = window
        self.title = title
        self._quit_requested = False
        self._icon: Any = None
        self._lock = threading.Lock()

    @property
    def quit_requested(self) -> bool:
        return self._quit_requested

    def start(self) -> bool:
        if sys.platform != "win32":
            return False
        try:
            import pystray
            from PIL import Image, ImageDraw
        except Exception:
            return False

        image = Image.new("RGBA", (64, 64), (27, 78, 149, 255))
        draw = ImageDraw.Draw(image)
        draw.rectangle((10, 10, 54, 54), outline=(255, 255, 255, 255), width=4)
        draw.rectangle((20, 20, 44, 44), fill=(255, 255, 255, 255))
        draw.rectangle((26, 26, 38, 38), fill=(27, 78, 149, 255))

        self._icon = pystray.Icon(
            "zotero-daily-news",
            image,
            self.title,
            pystray.Menu(
                pystray.MenuItem("Open", self._menu_action(self.show_window), default=True),
                pystray.MenuItem("Hide", self._menu_action(self.hide_window)),
                pystray.MenuItem("Quit", self._menu_action(self.quit_app)),
            ),
        )
        self._icon.run_detached()
        return True

    def stop(self) -> None:
        icon = self._icon
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass
            self._icon = None

    def show_window(self) -> None:
        with self._lock:
            try:
                self.window.show()
            except Exception:
                pass
            try:
                self.window.restore()
            except Exception:
                pass

    def hide_window(self) -> None:
        with self._lock:
            try:
                self.window.hide()
            except Exception:
                pass

    def quit_app(self) -> None:
        self._quit_requested = True
        self.stop()
        try:
            self.window.destroy()
        except Exception:
            pass

    def on_window_closing(self) -> bool:
        if self._quit_requested:
            return True
        self.hide_window()
        return False

    def on_window_minimized(self) -> None:
        if not self._quit_requested:
            self.hide_window()

    @staticmethod
    def _menu_action(callback: Callable[[], None]) -> Callable[..., None]:
        def wrapped(*_args: object) -> None:
            callback()

        return wrapped


def install_windows_tray(window: Any, *, title: str = "Zotero Daily News") -> WindowsTray | None:
    tray = WindowsTray(window, title=title)
    if not tray.start():
        return None
    window.events.closing += tray.on_window_closing
    window.events.minimized += tray.on_window_minimized
    window.events.closed += tray.stop
    return tray
