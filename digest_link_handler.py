#!/usr/bin/env python3
"""zotero-digest:// 中转：记录前台 App 后用 open -g 后台唤起主程序。"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from macos_window import digest_app_bundle_path, remember_frontmost_app_to_file
from url_handler import deeplink_from_argv, parse_deeplink

LINK_LOG = Path.home() / "Library/Application Support/Zotero Digest/link.log"


def _log(message: str) -> None:
    try:
        LINK_LOG.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with LINK_LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{stamp} {message}\n")
    except OSError:
        pass


def _notify(title: str, message: str) -> None:
    safe_title = title.replace("\\", "\\\\").replace('"', '\\"')
    safe_msg = message.replace("\\", "\\\\").replace('"', '\\"')[:200]
    subprocess.run(
        [
            "osascript",
            "-e",
            f'display notification "{safe_msg}" with title "{safe_title}"',
        ],
        check=False,
        timeout=5,
    )


def launch_main_app_background(url: str) -> None:
    bundle = digest_app_bundle_path()
    if bundle.exists():
        cmd = ["open", "-g", "-a", str(bundle.resolve()), url]
    else:
        cmd = ["open", "-g", url]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "open failed").strip()
        _log(f"launch failed: {err} url={url}")
        _notify("Zotero Digest Link", f"无法唤起简报: {err[:80]}")
    else:
        _log(f"launch ok url={url}")


def handle_deeplink(url: str) -> None:
    _log(f"handle url={url}")
    remember_frontmost_app_to_file()
    launch_main_app_background(url)


def _terminate_app() -> None:
    try:
        from AppKit import NSApplication

        NSApplication.sharedApplication().terminate_(None)
    except ImportError:
        pass


def _run_url_delegate() -> None:
    from AppKit import NSApplication, NSObject

    class LinkDelegate(NSObject):
        def application_openURLs_(self, application, urls):
            for url in urls:
                raw = str(url.absoluteString())
                if parse_deeplink(raw):
                    handle_deeplink(raw)
            _terminate_app()

    app = NSApplication.sharedApplication()
    delegate = LinkDelegate.alloc().init()
    app.setDelegate_(delegate)
    delegate.retain()

    def _timeout_exit() -> None:
        time.sleep(2.0)
        _terminate_app()

    threading.Thread(target=_timeout_exit, daemon=True).start()
    app.run()


def main() -> None:
    try:
        for arg in sys.argv[1:]:
            if parse_deeplink(arg):
                handle_deeplink(arg)
                return

        try:
            from AppKit import NSApplication
        except ImportError:
            note_id = deeplink_from_argv()
            if note_id:
                from url_handler import deeplink_for_note

                handle_deeplink(deeplink_for_note(note_id))
            return

        _run_url_delegate()
    except Exception as exc:
        _log(f"error: {exc}")
        _notify("Zotero Digest Link", str(exc)[:120])
        raise


if __name__ == "__main__":
    main()
