#!/usr/bin/env python3
"""启动 Zotero 简报原生窗口（双击 .app 时运行）。"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from typing import Any

from app_bridge import set_navigate_to_note, set_yield_focus
from config_manager import load_config
from macos_window import (
    activate_window,
    chain_macos_app_handlers,
    order_front_without_activate,
    patch_pywebview_deeplink_cold_start,
    remember_frontmost_app_for_cold_start,
    schedule_deeplink_focus_release,
    schedule_window_activate,
)
from net_env import ensure_local_no_proxy
from url_handler import (
    deeplink_launch_from_argv,
    digest_app_base_url,
    navigate_to_note_in_app,
    note_path,
)

PORT = int((load_config().get("ui") or {}).get("port", 18765))


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _wait_server(url: str, timeout: float = 15.0) -> bool:
    import urllib.request

    ensure_local_no_proxy()
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.15)
    return False


def _show_window(window: Any, *, activate: bool) -> None:
    if activate:
        try:
            window.restore()
        except Exception:
            pass
        try:
            window.show()
        except Exception:
            pass
        schedule_window_activate(window)
        return
    order_front_without_activate(window)


def main() -> None:
    ensure_local_no_proxy()
    from app import app

    base_url = digest_app_base_url()
    pending_note_id, deeplink_activate = deeplink_launch_from_argv()
    deeplink_launch = bool(pending_note_id)
    deeplink_background = deeplink_launch and not deeplink_activate
    if deeplink_background:
        remember_frontmost_app_for_cold_start()

    state: dict[str, Any] = {
        "window": None,
        "pending_note_id": pending_note_id,
        "pending_nav": None,
        "warm": False,
        "http_server": None,
        "shutting_down": False,
    }

    def navigate_in_window(note_id: str, *, activate: bool = True) -> tuple[bool, bool]:
        if state.get("shutting_down"):
            return False, False
        window = state.get("window")
        if window is None or not state.get("warm"):
            state["pending_nav"] = (note_id, activate)
            return False, True
        js = (
            "(function(){"
            f" if (typeof navigateToNote === 'function') {{ navigateToNote({json.dumps(note_id)}); return true; }}"
            " return false;"
            "})()"
        )
        try:
            if window.evaluate_js(js):
                _show_window(window, activate=activate)
                return True, False
        except Exception:
            pass
        window.load_url(f"{base_url}{note_path(note_id)}")
        _show_window(window, activate=activate)
        return True, False

    def flush_pending_navigation() -> None:
        pending = state.pop("pending_nav", None)
        if pending:
            note_id, activate = pending
            navigate_in_window(note_id, activate=activate)

    def open_note(note_id: str, *, activate: bool = False) -> None:
        state["pending_note_id"] = note_id
        navigate_in_window(note_id, activate=activate)

    def show_from_user() -> None:
        window = state.get("window")
        if window is not None:
            _show_window(window, activate=True)

    def shutdown_services() -> None:
        if state.get("shutting_down"):
            return
        state["shutting_down"] = True
        state["warm"] = False
        set_navigate_to_note(None)
        set_yield_focus(None)
        server = state.get("http_server")
        if server is not None:
            try:
                server.shutdown()
            except Exception:
                pass

    set_navigate_to_note(navigate_in_window)

    def yield_focus() -> None:
        window = state.get("window")
        if window is None:
            return
        try:
            window.minimize()
        except Exception:
            pass

    set_yield_focus(yield_focus)

    def run_flask() -> None:
        from werkzeug.serving import make_server

        server = make_server("127.0.0.1", PORT, app, threaded=True)
        state["http_server"] = server
        server.serve_forever()

    if not _port_free(PORT):
        print(f"复用已在运行的服务: {base_url}", file=sys.stderr)
        if pending_note_id and navigate_to_note_in_app(
            pending_note_id, activate=deeplink_activate
        ):
            print(f"已转发导航至笔记: {pending_note_id}", file=sys.stderr)
        return

    thread = threading.Thread(target=run_flask, daemon=True)
    thread.start()
    if not _wait_server(base_url):
        raise SystemExit("界面服务启动超时")

    initial_path = note_path(pending_note_id) if pending_note_id else "/"

    def on_gui_ready() -> None:
        state["warm"] = True
        chain_macos_app_handlers(
            on_note=open_note,
            on_reopen=show_from_user,
            on_quit=shutdown_services,
        )
        flush_pending_navigation()
        if deeplink_background:
            schedule_deeplink_focus_release()
        elif deeplink_activate:
            window = state.get("window")
            if window is not None:
                _show_window(window, activate=True)

    try:
        import webview

        if deeplink_background:
            patch_pywebview_deeplink_cold_start()

        window = webview.create_window(
            "Zotero 简报",
            f"{base_url}{initial_path}",
            width=1180,
            height=820,
            min_size=(900, 600),
            text_select=True,
            hidden=deeplink_background,
        )
        state["window"] = window
        webview.start(on_gui_ready)
    except ImportError:
        import webbrowser

        def browser_navigate(note_id: str, *, activate: bool = True) -> tuple[bool, bool]:
            webbrowser.open(f"{base_url}{note_path(note_id)}")
            return True, False

        set_navigate_to_note(browser_navigate)
        webbrowser.open(f"{base_url}{initial_path}")
        print(f"已打开浏览器: {base_url}{initial_path}")
        print("安装 pywebview 可获得原生窗口: pip install pywebview")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    finally:
        shutdown_services()
        os._exit(0)


if __name__ == "__main__":
    main()
