#!/usr/bin/env python3
"""启动 Zotero 简报原生窗口（双击 .app 时运行）。"""

from __future__ import annotations

import socket
import threading
import time

from config_manager import load_config

PORT = int((load_config().get("ui") or {}).get("port", 18765))


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _wait_server(url: str, timeout: float = 15.0) -> bool:
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.15)
    return False


def main() -> None:
    from app import app

    url = f"http://127.0.0.1:{PORT}"

    def run_flask() -> None:
        app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False, threaded=True)

    if _port_free(PORT):
        thread = threading.Thread(target=run_flask, daemon=True)
        thread.start()
        if not _wait_server(url):
            raise SystemExit("界面服务启动超时")
    else:
        print(f"复用已在运行的服务: {url}")

    try:
        import webview

        webview.create_window(
            "Zotero 简报",
            url,
            width=1180,
            height=820,
            min_size=(900, 600),
            text_select=True,
        )
        webview.start()
    except ImportError:
        import webbrowser

        webbrowser.open(url)
        print(f"已打开浏览器: {url}")
        print("安装 pywebview 可获得原生窗口: pip install pywebview")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
