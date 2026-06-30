#!/usr/bin/env python3
"""将 fixtures/test_note.md 安装到 summaries/ 并重建对应 hub，供本地测试。"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from typing import Any

from .config_manager import SCRIPT_DIR, load_config, resolve_output_dirs
from .notes_index import get_note
from .summary_io import build_hub_html, ensure_hub_assets

FIXTURE_MD = SCRIPT_DIR / "fixtures" / "test_note.md"
TEST_NOTE_ID = "20990101_TESTNOTE_zotero-digest-test"


def ensure_test_note(*, rebuild_only: bool = False, quiet: bool = False) -> dict[str, Any]:
    """安装示例笔记并返回推送测试所需字段。"""
    hub_path = seed_test_note(rebuild_only=rebuild_only, quiet=quiet)
    entry = get_note(TEST_NOTE_ID)
    if not entry:
        raise RuntimeError(f"示例笔记安装后仍无法索引: {TEST_NOTE_ID}")
    title = entry.title
    return {
        "note_id": TEST_NOTE_ID,
        "hub_path": hub_path,
        "title": title,
        "subtitle": title[:80] + ("…" if len(title) > 80 else ""),
        "briefing": entry.briefing,
        "notify_title": "📚 今日文献 (1/1)",
    }


def seed_test_note(*, rebuild_only: bool = False, quiet: bool = False) -> Path:
    if not FIXTURE_MD.is_file():
        raise FileNotFoundError(f"缺少 fixture: {FIXTURE_MD}")

    config = load_config()
    summaries_dir, hubs_dir = resolve_output_dirs(config)
    summaries_dir.mkdir(parents=True, exist_ok=True)
    hubs_dir.mkdir(parents=True, exist_ok=True)
    ensure_hub_assets(hubs_dir)

    md_path = summaries_dir / f"{TEST_NOTE_ID}.md"
    hub_path = hubs_dir / f"{TEST_NOTE_ID}.html"

    if not rebuild_only:
        shutil.copy2(FIXTURE_MD, md_path)
        if not quiet:
            print(f"已安装 Markdown: {md_path}")

    hub_path.write_text(build_hub_html(TEST_NOTE_ID), encoding="utf-8")
    if not quiet:
        print(f"已重建 Hub:       {hub_path}")
    return hub_path


def main() -> int:
    rebuild_only = "--rebuild-hub" in sys.argv
    try:
        hub_path = seed_test_note(rebuild_only=rebuild_only)
    except Exception as exc:
        print(f"失败: {exc}", file=sys.stderr)
        return 1

    print()
    print("测试笔记 ID:", TEST_NOTE_ID)
    print("深链接:      zotero-digest://note/" + TEST_NOTE_ID)
    print("Hub 文件:   ", hub_path)
    print("App 内打开:  http://127.0.0.1:18765/note/" + TEST_NOTE_ID)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
