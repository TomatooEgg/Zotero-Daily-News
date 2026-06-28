"""原生窗口与 Flask 服务之间的轻量桥接（可选注册）。"""

from __future__ import annotations

from typing import Callable

# (navigated_immediately, queued_for_later)
NavigateResult = tuple[bool, bool]

_yield_focus: Callable[[], None] | None = None
_navigate_to_note: Callable[[str, bool], NavigateResult | bool] | None = None


def set_yield_focus(cb: Callable[[], None] | None) -> None:
    global _yield_focus
    _yield_focus = cb


def yield_focus_to_external_app() -> None:
    if _yield_focus:
        _yield_focus()


def set_navigate_to_note(cb: Callable[[str, bool], NavigateResult | bool] | None) -> None:
    global _navigate_to_note
    _navigate_to_note = cb


def is_bridge_registered() -> bool:
    return _navigate_to_note is not None


def navigate_to_note(note_id: str, *, activate: bool = True) -> NavigateResult:
    """在原生窗口内打开笔记；返回 (已跳转, 已排队待窗口就绪)。"""
    if not note_id or not _navigate_to_note:
        return False, False
    result = _navigate_to_note(note_id, activate=activate)
    if isinstance(result, tuple):
        return result
    return bool(result), False
