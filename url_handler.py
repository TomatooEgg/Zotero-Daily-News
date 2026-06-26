"""macOS 自定义 URL Scheme（zotero-digest://）与 App 内导航。"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, quote, unquote, urlparse

from config_manager import load_config
from net_env import ensure_local_no_proxy
from platform_utils import is_macos, open_target

DEEPLINK_SCHEME = "zotero-digest"


def digest_app_port() -> int:
    return int((load_config().get("ui") or {}).get("port", 18765))


def digest_app_base_url() -> str:
    return f"http://127.0.0.1:{digest_app_port()}"


def is_digest_app_running(port: int | None = None) -> bool:
    port = port if port is not None else digest_app_port()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def navigate_to_note_in_app(note_id: str, *, activate: bool = True, port: int | None = None) -> bool:
    """App 已运行时通过本地 API 跳转到对应笔记。"""
    if not note_id or not is_digest_app_running(port):
        return False
    ensure_local_no_proxy()
    base = digest_app_base_url() if port is None else f"http://127.0.0.1:{port}"
    payload = json.dumps({"note_id": note_id, "activate": activate}).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/api/navigate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return resp.status == 200 and bool(body.get("ok")) and bool(body.get("navigated"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return False


def open_notify_target(note_id: str, hub_path: Path | None = None) -> None:
    """通知点击目标：App 已开则跳转条目，否则打开 hub 中转页。"""
    if note_id and navigate_to_note_in_app(note_id, activate=True):
        return
    if hub_path and hub_path.exists():
        open_target(hub_path.resolve())


def parse_deeplink(url: str) -> str | None:
    """从 zotero-digest://note/<note_id> 解析 note_id。"""
    parsed = urlparse(url.strip())
    if parsed.scheme != DEEPLINK_SCHEME:
        return None
    if parsed.netloc == "note":
        note_id = unquote((parsed.path or "").lstrip("/"))
        return note_id or None
    parts = [p for p in (parsed.path or "").split("/") if p]
    if len(parts) >= 2 and parts[0] == "note":
        return unquote("/".join(parts[1:])) or None
    return None


def deeplink_wants_activate(url: str) -> bool:
    parsed = urlparse(url.strip())
    if parsed.scheme != DEEPLINK_SCHEME:
        return False
    val = (parse_qs(parsed.query).get("activate") or [""])[0].strip().lower()
    return val in ("1", "true", "yes")


def deeplink_for_note(note_id: str, *, activate: bool = False) -> str:
    base = f"{DEEPLINK_SCHEME}://note/{note_id}"
    if activate:
        return f"{base}?activate=1"
    return base


def note_path(note_id: str) -> str:
    return f"/?note={quote(note_id, safe='')}"


def open_digest_app_for_note(note_id: str) -> bool:
    """Hub 打开简报：已运行则前台导航，否则前台冷启动。"""
    if not note_id:
        return False
    if navigate_to_note_in_app(note_id, activate=True):
        return True
    if is_macos():
        subprocess.run(["open", deeplink_for_note(note_id, activate=True)], check=False)
    else:
        open_target(f"{digest_app_base_url()}{note_path(note_id)}")
    return True


def deeplink_from_argv(argv: list[str] | None = None) -> str | None:
    note_id, _ = deeplink_launch_from_argv(argv)
    return note_id


def deeplink_launch_from_argv(argv: list[str] | None = None) -> tuple[str | None, bool]:
    for arg in argv or sys.argv[1:]:
        note_id = parse_deeplink(arg)
        if note_id:
            return note_id, deeplink_wants_activate(arg)
    return None, False


def install_macos_url_handler(on_note: Callable[[str], None]) -> None:
    """注册 NSApplicationDelegate，在 App 运行期间接收 deeplink。"""
    try:
        import objc
        from AppKit import NSApplication, NSApplicationDelegate
    except ImportError:
        return

    class AppDelegate(NSApplicationDelegate):
        def application_openURLs_(self, application, urls):
            for url in urls:
                note_id = parse_deeplink(str(url.absoluteString()))
                if note_id:
                    on_note(note_id)

    app = NSApplication.sharedApplication()
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    delegate.retain()


def chain_macos_url_handler(on_note: Callable[[str], None]) -> None:
    """pywebview 启动后链式注册 deeplink，不覆盖其 AppDelegate。"""
    try:
        import objc
        from AppKit import NSApplication, NSObject
    except ImportError:
        return

    app = NSApplication.sharedApplication()
    parent = app.delegate()
    if parent is None:
        install_macos_url_handler(on_note)
        return
    if getattr(parent, "_digest_url_chain", False):
        return

    class URLChainDelegate(NSObject):
        def initWithParent_(self, parent_delegate):
            self = objc.super(URLChainDelegate, self).init()
            if self is None:
                return None
            self._parent = parent_delegate
            self._on_note = on_note
            self._digest_url_chain = True
            return self

        def application_openURLs_(self, application, urls):
            for url in urls:
                note_id = parse_deeplink(str(url.absoluteString()))
                if note_id:
                    self._on_note(note_id)
            if self._parent.respondsToSelector_("application:openURLs:"):
                self._parent.application_openURLs_(application, urls)

        def forwardingTargetForSelector_(self, sel):
            if self._parent.respondsToSelector_(sel):
                return self._parent
            return objc.super(URLChainDelegate, self).forwardingTargetForSelector_(sel)

    chain = URLChainDelegate.alloc().initWithParent_(parent)
    app.setDelegate_(chain)
    chain.retain()
