"""待发布简报：已预生成但尚未通过通知「查看总结」正式阅读的 note_id。"""

from __future__ import annotations

import json
from pathlib import Path

from config_manager import SCRIPT_DIR

PENDING_PATH = SCRIPT_DIR / "pending_publish.json"


def _load() -> set[str]:
    if not PENDING_PATH.exists():
        return set()
    try:
        with PENDING_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return set()
    if isinstance(data, dict):
        ids = data.get("note_ids")
        if isinstance(ids, list):
            return {str(i) for i in ids if i}
    if isinstance(data, list):
        return {str(i) for i in data if i}
    return set()


def _save(note_ids: set[str]) -> None:
    with PENDING_PATH.open("w", encoding="utf-8") as f:
        json.dump({"note_ids": sorted(note_ids)}, f, ensure_ascii=False, indent=2)


def is_pending(note_id: str) -> bool:
    return note_id in _load()


def mark_pending(note_id: str) -> None:
    if not note_id:
        return
    pending = _load()
    if note_id in pending:
        return
    pending.add(note_id)
    _save(pending)


def publish_note(note_id: str) -> None:
    if not note_id:
        return
    pending = _load()
    if note_id not in pending:
        return
    pending.remove(note_id)
    _save(pending)


def publish_notes(note_ids: list[str]) -> None:
    pending = _load()
    changed = False
    for note_id in note_ids:
        if note_id and note_id in pending:
            pending.remove(note_id)
            changed = True
    if changed:
        _save(pending)
