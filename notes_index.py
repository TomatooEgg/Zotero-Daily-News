"""扫描并按日期索引已生成的简报笔记。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from config_manager import SCRIPT_DIR, load_config, resolve_output_dirs
from pending_publish import is_pending

HISTORY_PATH = SCRIPT_DIR / "history.json"

DATE_RE = re.compile(r"^(\d{8})_([A-Z0-9]+)_(.+)\.md$", re.IGNORECASE)
BRIEFING_RE = re.compile(r"^>\s*\*\*头条简报\*\*[：:]\s*(.+)$", re.MULTILINE)
TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


@dataclass
class NoteEntry:
    id: str
    date: str
    date_label: str
    item_key: str
    title: str
    briefing: str
    md_path: str
    hub_path: str | None
    mtime: float

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "date": self.date,
            "date_label": self.date_label,
            "item_key": self.item_key,
            "title": self.title,
            "briefing": self.briefing,
            "md_path": self.md_path,
            "hub_path": self.hub_path,
            "mtime": self.mtime,
        }


def _parse_date_label(yyyymmdd: str) -> str:
    try:
        dt = datetime.strptime(yyyymmdd, "%Y%m%d")
        weekdays = "周一 周二 周三 周四 周五 周六 周日".split()
        return f"{dt.year}年{dt.month}月{dt.day}日 {weekdays[dt.weekday()]}"
    except ValueError:
        return yyyymmdd


def _read_meta(md_path: Path) -> tuple[str, str]:
    try:
        text = md_path.read_text(encoding="utf-8", errors="replace")[:4000]
    except OSError:
        return md_path.stem, ""
    title_m = TITLE_RE.search(text)
    brief_m = BRIEFING_RE.search(text)
    title = title_m.group(1).strip() if title_m else md_path.stem
    briefing = brief_m.group(1).strip() if brief_m else ""
    return title, briefing


def _find_hub(hubs_dir: Path, stem: str) -> Path | None:
    hub = hubs_dir / f"{stem}.html"
    return hub if hub.exists() else None


def list_notes(date_filter: str | None = None, *, include_pending: bool = False) -> list[NoteEntry]:
    config = load_config()
    summaries_dir, hubs_dir = resolve_output_dirs(config)
    entries: list[NoteEntry] = []

    for md_path in sorted(summaries_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        if md_path.name.startswith("_"):
            continue
        match = DATE_RE.match(md_path.name)
        if not match:
            continue
        yyyymmdd, item_key, _slug = match.groups()
        iso_date = f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}"
        if date_filter and iso_date != date_filter:
            continue
        stem = md_path.stem
        if not include_pending and is_pending(stem):
            continue
        title, briefing = _read_meta(md_path)
        hub = _find_hub(hubs_dir, stem)
        stat = md_path.stat()
        entries.append(
            NoteEntry(
                id=stem,
                date=iso_date,
                date_label=_parse_date_label(yyyymmdd),
                item_key=item_key,
                title=title,
                briefing=briefing,
                md_path=str(md_path.resolve()),
                hub_path=str(hub.resolve()) if hub else None,
                mtime=stat.st_mtime,
            )
        )
    return entries


def group_by_date(entries: list[NoteEntry]) -> list[dict]:
    groups: dict[str, dict] = {}
    for entry in entries:
        if entry.date not in groups:
            groups[entry.date] = {
                "date": entry.date,
                "date_label": entry.date_label,
                "notes": [],
            }
        groups[entry.date]["notes"].append(entry.to_dict())
    return sorted(groups.values(), key=lambda g: g["date"], reverse=True)


def get_note(note_id: str) -> NoteEntry | None:
    for entry in list_notes(include_pending=True):
        if entry.id == note_id:
            return entry
    return None


def latest_notes_by_item_key() -> dict[str, NoteEntry]:
    """按 item_key 索引最近一条仍存在的简报（list_notes 已按 mtime 降序）。"""
    index: dict[str, NoteEntry] = {}
    for entry in list_notes(include_pending=True):
        if entry.item_key not in index and Path(entry.md_path).is_file():
            index[entry.item_key] = entry
    return index


def find_note_by_item_key(item_key: str) -> NoteEntry | None:
    """返回该 Zotero 条目最近一条未删除的简报，不存在则 None。"""
    for entry in list_notes(include_pending=True):
        if entry.item_key == item_key:
            return entry
    return None


def _valid_note_id(note_id: str) -> bool:
    return bool(DATE_RE.match(f"{note_id}.md"))


def _delete_files(entry: NoteEntry) -> None:
    Path(entry.md_path).unlink(missing_ok=True)
    if entry.hub_path:
        Path(entry.hub_path).unlink(missing_ok=True)


def _sync_history_after_delete(deleted_item_keys: list[str]) -> None:
    if not deleted_item_keys or not HISTORY_PATH.exists():
        return
    remaining_keys = {e.item_key for e in list_notes()}
    with HISTORY_PATH.open(encoding="utf-8") as f:
        history = json.load(f)
    items = history.setdefault("items", {})
    changed = False
    for key in deleted_item_keys:
        if key not in remaining_keys and key in items:
            del items[key]
            changed = True
    if changed:
        with HISTORY_PATH.open("w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)


def delete_notes(note_ids: list[str]) -> int:
    entries_to_delete: list[NoteEntry] = []
    seen: set[str] = set()
    for note_id in note_ids:
        if note_id in seen or not _valid_note_id(note_id):
            continue
        seen.add(note_id)
        entry = get_note(note_id)
        if entry:
            entries_to_delete.append(entry)
    if not entries_to_delete:
        return 0
    item_keys = [e.item_key for e in entries_to_delete]
    for entry in entries_to_delete:
        _delete_files(entry)
    _sync_history_after_delete(item_keys)
    return len(entries_to_delete)


def delete_note(note_id: str) -> bool:
    return delete_notes([note_id]) == 1


def delete_notes_by_date(iso_date: str) -> int:
    try:
        datetime.strptime(iso_date, "%Y-%m-%d")
    except ValueError:
        return -1
    entries = list_notes(date_filter=iso_date)
    if not entries:
        return 0
    return delete_notes([e.id for e in entries])
