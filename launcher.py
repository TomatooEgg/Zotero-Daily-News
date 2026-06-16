#!/usr/bin/env python3
"""启动 Zotero 简报原生窗口（双击 .app 时运行）。"""

from __future__ import annotations

import socket
import threading
import time
from typing import Any

from config_manager import load_config
from net_env import ensure_local_no_proxy
from url_handler import deeplink_from_argv, install_macos_url_handler, note_path

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


def main() -> None:
    ensure_local_no_proxy()
    from app import app

    base_url = f"http://127.0.0.1:{PORT}"
    state: dict[str, Any] = {"window": None, "pending_note_id": deeplink_from_argv()}

    def open_note(note_id: str) -> None:
        state["pending_note_id"] = note_id
        window = state.get("window")
        if window is None:
            return
        window.load_url(f"{base_url}{note_path(note_id)}")
        window.show()

    install_macos_url_handler(open_note)

    def run_flask() -> None:
        app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False, threaded=True)

    if _port_free(PORT):
        thread = threading.Thread(target=run_flask, daemon=True)
        thread.start()
        if not _wait_server(base_url):
            raise SystemExit("界面服务启动超时")
    else:
        print(f"复用已在运行的服务: {base_url}")

    initial_path = "/"
    if state["pending_note_id"]:
        initial_path = note_path(state["pending_note_id"])

    try:
        import webview

        window = webview.create_window(
            "Zotero 简报",
            f"{base_url}{initial_path}",
            width=1180,
            height=820,
            min_size=(900, 600),
            text_select=True,
        )
        state["window"] = window
        webview.start()
    except ImportError:
        import webbrowser

        webbrowser.open(f"{base_url}{initial_path}")
        print(f"已打开浏览器: {base_url}{initial_path}")
        print("安装 pywebview 可获得原生窗口: pip install pywebview")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
