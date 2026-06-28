"""macOS pywebview 窗口焦点与深链接冷启动行为。"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .config_manager import SCRIPT_DIR

FRONT_APP_FILE = Path.home() / "Library/Application Support/Zotero Digest/front_app.txt"
IGNORE_FRONT_APP_NAMES = frozenset(
    {"Zotero 简报", "Zotero Digest Link", "Python", "python3", "Python3"}
)
_cold_start_frontmost_app: str | None = None


def digest_app_bundle_path() -> Path:
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        for parent in executable.parents:
            if parent.name.endswith(".app"):
                return parent
    return SCRIPT_DIR / "Zotero 简报.app"


def remember_frontmost_app_to_file() -> None:
    """立即把当前前台 App 写入文件（供 Link 中转与冷启动读取）。"""
    if sys.platform != "darwin":
        return
    try:
        result = subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to get name of first application process whose frontmost is true',
            ],
            capture_output=True,
            text=True,
            timeout=2,
        )
        name = (result.stdout or "").strip()
        if name and name not in IGNORE_FRONT_APP_NAMES:
            FRONT_APP_FILE.parent.mkdir(parents=True, exist_ok=True)
            FRONT_APP_FILE.write_text(name, encoding="utf-8")
    except (OSError, subprocess.SubprocessError):
        pass


def remember_frontmost_app_for_cold_start() -> None:
    """记录深链接冷启动前应恢复的前台 App（优先读 launcher / Link 写入的文件）。"""
    global _cold_start_frontmost_app
    if sys.platform != "darwin":
        return
    try:
        if FRONT_APP_FILE.is_file():
            name = FRONT_APP_FILE.read_text(encoding="utf-8").strip()
            if name and name not in IGNORE_FRONT_APP_NAMES:
                _cold_start_frontmost_app = name
                return
    except OSError:
        pass
    try:
        result = subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to get name of first application process whose frontmost is true',
            ],
            capture_output=True,
            text=True,
            timeout=2,
        )
        name = (result.stdout or "").strip()
        if name and name not in IGNORE_FRONT_APP_NAMES:
            _cold_start_frontmost_app = name
    except (OSError, subprocess.SubprocessError):
        pass


def restore_cold_start_focus(delay: float = 0.0) -> None:
    """将焦点交还给冷启动前的前台 App。"""
    if sys.platform != "darwin":
        return

    def _activate() -> None:
        if delay > 0:
            time.sleep(delay)
        global _cold_start_frontmost_app
        if not _cold_start_frontmost_app:
            try:
                if FRONT_APP_FILE.is_file():
                    name = FRONT_APP_FILE.read_text(encoding="utf-8").strip()
                    if name and name not in IGNORE_FRONT_APP_NAMES:
                        _cold_start_frontmost_app = name
            except OSError:
                pass
        app_name = _cold_start_frontmost_app
        if app_name:
            escaped = app_name.replace("\\", "\\\\").replace('"', '\\"')
            subprocess.run(
                ["osascript", "-e", f'tell application "{escaped}" to activate'],
                check=False,
                timeout=5,
            )
            return
        for browser in ("Safari", "Google Chrome", "Arc", "Firefox", "Microsoft Edge"):
            script = (
                f'tell application "System Events" to if exists (process "{browser}") '
                f'then tell application "{browser}" to activate'
            )
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode == 0:
                return

    threading.Thread(target=_activate, daemon=True).start()


def release_activation_keep_visible(pywebview_window: Any) -> None:
    """窗口仍可见，但放弃 key window / 应用前台激活。"""
    if sys.platform != "darwin":
        return
    try:
        from AppKit import NSApplication
        from webview.platforms.cocoa import AppHelper

        native = getattr(pywebview_window, "native", None)

        def _release() -> None:
            NSApplication.sharedApplication().deactivate()
            if native is not None:
                native.orderFront_(None)

        AppHelper.callAfter(_release)
    except Exception:
        pass


def order_front_without_activate(pywebview_window: Any) -> None:
    if sys.platform != "darwin":
        try:
            pywebview_window.show()
        except Exception:
            pass
        return
    try:
        from webview.platforms.cocoa import AppHelper

        native = getattr(pywebview_window, "native", None)
        if native is not None:
            AppHelper.callAfter(native.orderFront_, None)
            return
    except Exception:
        pass
    try:
        pywebview_window.show()
    except Exception:
        pass


def activate_window(pywebview_window: Any) -> None:
    """通知等场景：显式激活窗口并抢焦点。"""
    if sys.platform != "darwin":
        try:
            pywebview_window.show()
        except Exception:
            pass
        return
    try:
        import Foundation
        from AppKit import NSApplication
        from webview.platforms.cocoa import AppHelper

        native = getattr(pywebview_window, "native", None)

        def _activate() -> None:
            if native is not None:
                native.makeKeyAndOrderFront_(None)
            NSApplication.sharedApplication().activateIgnoringOtherApps_(Foundation.YES)

        AppHelper.callAfter(_activate)
    except Exception:
        try:
            pywebview_window.show()
        except Exception:
            pass


def activate_digest_app() -> None:
    """通过 AppleScript 激活简报 App（浏览器唤起时的兜底）。"""
    if sys.platform != "darwin":
        return
    subprocess.run(
        ["osascript", "-e", 'tell application "Zotero 简报" to activate'],
        check=False,
        timeout=5,
    )


def schedule_window_activate(pywebview_window: Any) -> None:
    """多次尝试激活窗口；从 hub/浏览器唤起时 macOS 常需延迟。"""
    activate_window(pywebview_window)
    if sys.platform != "darwin":
        return

    def _retry(delay: float) -> None:
        time.sleep(delay)
        activate_window(pywebview_window)
        activate_digest_app()

    for delay in (0.12, 0.35, 0.75, 1.2):
        threading.Thread(target=_retry, args=(delay,), daemon=True).start()


def patch_pywebview_deeplink_cold_start() -> None:
    """深链接冷启动：first_show 仅 orderFront，不 activateIgnoringOtherApps。"""
    if sys.platform != "darwin":
        return
    try:
        from webview.platforms import cocoa as pv_cocoa
    except ImportError:
        return
    if getattr(pv_cocoa.BrowserView, "_digest_deeplink_patch", False):
        return

    def first_show_patched(self) -> None:
        if not self.hidden:
            self.window.orderFront_(None)
        if self.maximized:
            self.maximize()
        elif self.minimized:
            self.minimize()
        self.shown.set()
        if not pv_cocoa.BrowserView.app.isRunning():
            new_menu = self._recreate_menus(self.menu)
            pv_cocoa.BrowserView.app.setMainMenu_(new_menu)
            pv_cocoa.AppHelper.installMachInterrupt()
            pv_cocoa.BrowserView.app.run()

    pv_cocoa.BrowserView.first_show = first_show_patched
    pv_cocoa.BrowserView._digest_deeplink_patch = True


def schedule_deeplink_focus_release() -> None:
    """深链接冷启动后多次交还焦点（窗口保持隐藏，不 orderFront）。"""
    remember_frontmost_app_for_cold_start()

    def _run(delay: float) -> None:
        time.sleep(delay)
        restore_cold_start_focus(0.0)

    for delay in (0.0, 0.12, 0.35, 0.7, 1.2):
        threading.Thread(target=_run, args=(delay,), daemon=True).start()


def chain_macos_app_handlers(
    on_note: Callable[[str], None] | None = None,
    on_reopen: Callable[[], None] | None = None,
) -> None:
    """在 pywebview delegate 上链式挂 deeplink 与 Dock 点击恢复窗口。"""
    if sys.platform != "darwin":
        return
    try:
        import objc
        from AppKit import NSApplication, NSObject
    except ImportError:
        return

    app = NSApplication.sharedApplication()
    parent = app.delegate()
    if parent is None:
        return
    if getattr(parent, "_digest_handler_chain", False):
        return

    class HandlerChain(NSObject):
        def initWithParent_(self, parent_delegate):
            self = objc.super(HandlerChain, self).init()
            if self is None:
                return None
            self._parent = parent_delegate
            self._on_note = on_note
            self._on_reopen = on_reopen
            self._digest_handler_chain = True
            return self

        def application_openURLs_(self, application, urls):
            if self._on_note:
                from .url_handler import deeplink_wants_activate, parse_deeplink

                for url in urls:
                    raw = str(url.absoluteString())
                    note_id = parse_deeplink(raw)
                    if note_id:
                        self._on_note(note_id, activate=deeplink_wants_activate(raw))
            if self._parent.respondsToSelector_("application:openURLs:"):
                self._parent.application_openURLs_(application, urls)

        def applicationShouldHandleReopen_(self, sender, hasVisibleWindows):
            if self._on_reopen:
                self._on_reopen()
            if self._parent.respondsToSelector_("applicationShouldHandleReopen:hasVisibleWindows:"):
                return self._parent.applicationShouldHandleReopen_(sender, hasVisibleWindows)
            return True

        def forwardingTargetForSelector_(self, sel):
            if self._parent.respondsToSelector_(sel):
                return self._parent
            return objc.super(HandlerChain, self).forwardingTargetForSelector_(sel)

    chain = HandlerChain.alloc().initWithParent_(parent)
    app.setDelegate_(chain)
    chain.retain()
