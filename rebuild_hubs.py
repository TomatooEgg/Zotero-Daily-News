#!/usr/bin/env python3
"""重建所有 HTML 中转页（修复旧版 file:// 链接）。"""

from __future__ import annotations

import re

from notes_index import DATE_RE, list_notes
from summary_io import build_hub_html
from zotero_links import TermLink

BRIEFING_RE = re.compile(r"^>\s*\*\*头条简报\*\*[：:]\s*(.+)$", re.MULTILINE)
TERM_LINK_RE = re.compile(r"-\s*\*\*\[([^\]]+)\]\((zotero://[^)]+)\)\*\*")


def _parse_term_links(md_content: str) -> list[TermLink]:
    links: list[TermLink] = []
    for term, url in TERM_LINK_RE.findall(md_content):
        source = "annotation" if "annotation=" in url else "item"
        links.append(TermLink(term=term, url=url, source=source))
    return links


def main() -> None:
    count = 0
    for entry in list_notes():
        md_content = open(entry.md_path, encoding="utf-8").read()
        brief_m = BRIEFING_RE.search(md_content)
        briefing = brief_m.group(1).strip() if brief_m else entry.briefing
        item = {"key": entry.item_key, "data": {"title": entry.title}}
        term_links = _parse_term_links(md_content)

        hub_path = entry.hub_path
        if not hub_path:
            from config_manager import resolve_output_dirs, load_config
            _, hubs_dir = resolve_output_dirs(load_config())
            hub_path = str(hubs_dir / f"{entry.id}.html")

        from pathlib import Path
        Path(hub_path).write_text(
            build_hub_html(
                item, briefing, [], term_links, md_content, None, entry.id
            ),
            encoding="utf-8",
        )
        count += 1
        print(f"已重建: {Path(hub_path).name}")

    print(f"\n完成，共重建 {count} 个中转页")


if __name__ == "__main__":
    main()
