"""Small cross-platform helpers for opening files and URLs."""

from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from pathlib import Path


def is_macos() -> bool:
    return sys.platform == "darwin"


def is_windows() -> bool:
    return sys.platform == "win32"


def no_window_subprocess_kwargs() -> dict[str, int]:
    if not is_windows():
        return {}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def open_target(target: str | Path) -> None:
    raw = str(target)
    if is_macos():
        subprocess.run(["open", raw], check=False, timeout=5)
        return
    if is_windows():
        os.startfile(raw)  # type: ignore[attr-defined]
        return
    try:
        subprocess.run(["xdg-open", raw], check=False, timeout=5)
    except OSError:
        webbrowser.open(raw)


def reveal_path(path: Path) -> None:
    resolved = path.resolve()
    if is_macos():
        subprocess.run(["open", "-R", str(resolved)], check=False, timeout=5)
        return
    if is_windows():
        subprocess.run(["explorer", f"/select,{resolved}"], check=False, timeout=5)
        return
    open_target(resolved.parent)
