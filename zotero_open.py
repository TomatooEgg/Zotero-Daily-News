"""在 macOS 上可靠打开 zotero:// 深链接，并把焦点交给 Zotero。"""

from __future__ import annotations

import subprocess
import sys
import threading
import time

from net_env import connect_zotero
from platform_utils import open_target


def _is_zotero_api_ready() -> bool:
    try:
        connect_zotero().items(limit=1)
        return True
    except Exception:
        return False


def ensure_zotero_running(timeout: float = 20.0) -> bool:
    if _is_zotero_api_ready():
        return True
    if sys.platform != "darwin":
        return False
    subprocess.run(["open", "-a", "Zotero"], check=False, timeout=5)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _is_zotero_api_ready():
            return True
        time.sleep(0.25)
    return False


def _activate_zotero() -> None:
    if sys.platform != "darwin":
        return
    subprocess.run(
        ["osascript", "-e", 'tell application "Zotero" to activate'],
        check=False,
        timeout=5,
    )


def _activate_zotero_delayed(delay: float) -> None:
    def run() -> None:
        time.sleep(delay)
        _activate_zotero()

    threading.Thread(target=run, daemon=True).start()


def open_zotero_deeplink(url: str) -> None:
    """打开 zotero:// 链接；冷启动时重试 select，并延迟激活以免被 App 抢焦点。"""
    was_ready = _is_zotero_api_ready()
    if sys.platform == "darwin":
        ensure_zotero_running()

    open_target(url)

    if sys.platform == "darwin" and not was_ready and "/select/" in url:
        time.sleep(0.5)
        open_target(url)

    # pywebview 在 fetch 返回后常会抢回焦点，导致 Zotero 标签栏变灰；延迟再激活两次兜底。
    _activate_zotero_delayed(0.35)
    _activate_zotero_delayed(0.75)
