#!/usr/bin/env python3
"""重建所有 HTML 中转页。"""

from __future__ import annotations

from pathlib import Path

from config_manager import load_config, resolve_output_dirs
from notes_index import list_notes
from summary_io import build_hub_html, ensure_hub_assets


def main() -> None:
    _, hubs_dir = resolve_output_dirs(load_config())
    ensure_hub_assets(hubs_dir)
    count = 0
    for entry in list_notes():
        hub_path = entry.hub_path
        if not hub_path:
            _, hubs_dir = resolve_output_dirs(load_config())
            hub_path = str(hubs_dir / f"{entry.id}.html")

        Path(hub_path).write_text(build_hub_html(entry.id), encoding="utf-8")
        count += 1
        print(f"已重建: {Path(hub_path).name}")

    print(f"\n完成，共重建 {count} 个中转页")


if __name__ == "__main__":
    main()
