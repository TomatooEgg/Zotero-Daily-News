"""macOS 自定义 URL Scheme（zotero-digest://）处理。"""

from __future__ import annotations

import sys
from typing import Callable
from urllib.parse import unquote, urlparse

DEEPLINK_SCHEME = "zotero-digest"


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


def deeplink_for_note(note_id: str) -> str:
    return f"{DEEPLINK_SCHEME}://note/{note_id}"


def note_path(note_id: str) -> str:
    return f"/note/{note_id}"


def deeplink_from_argv(argv: list[str] | None = None) -> str | None:
    for arg in argv or sys.argv[1:]:
        note_id = parse_deeplink(arg)
        if note_id:
            return note_id
    return None


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
    objc.retain(delegate)
