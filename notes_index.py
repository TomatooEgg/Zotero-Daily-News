"""扫描并按日期索引已生成的简报笔记。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from config_manager import load_config, resolve_output_dirs

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


def list_notes(date_filter: str | None = None) -> list[NoteEntry]:
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
    for entry in list_notes():
        if entry.id == note_id:
            return entry
    return None
