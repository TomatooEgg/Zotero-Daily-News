"""原生窗口与 Flask 服务之间的轻量桥接（可选注册）。"""

from __future__ import annotations

from typing import Callable

_yield_focus: Callable[[], None] | None = None


def set_yield_focus(cb: Callable[[], None] | None) -> None:
    global _yield_focus
    _yield_focus = cb


def yield_focus_to_external_app() -> None:
    if _yield_focus:
        _yield_focus()
