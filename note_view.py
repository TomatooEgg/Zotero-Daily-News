"""统一笔记视图上下文与 HTML 渲染。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

from abstract_zh import (
    extract_abstract_zh,
    extract_original_abstract,
    has_abstract_zh,
    strip_abstract_zh_md,
)
from config_manager import load_config
from deep_read import (
    deep_read_to_html,
    extract_deep_read_md,
    has_deep_read,
    persist_note_md,
    repair_deep_read_md,
    strip_deep_read_md,
)
from md_render import markdown_to_html, prepare_overview_markdown
from notes_index import get_note
from url_handler import deeplink_for_note
from zotero_links import get_pdf_attachment, zotero_item_url, zotero_pdf_url

Viewer = Literal["app", "hub", "standalone"]

PDF_LINK_RE = re.compile(r"zotero://open-pdf/library/items/([A-Z0-9]+)", re.I)


def parse_pdf_url_from_md(md_text: str) -> str:
    match = PDF_LINK_RE.search(md_text)
    if match:
        return zotero_pdf_url(match.group(1))
    return ""


def resolve_pdf_url(md_text: str, item_key: str) -> str:
    try:
        from net_env import connect_zotero

        zot = connect_zotero()
        pdf = get_pdf_attachment(zot, item_key)
        if pdf:
            return zotero_pdf_url(pdf["key"])
    except Exception:
        pass
    return parse_pdf_url_from_md(md_text)


def prepare_note_view_context(
    note_id: str,
    viewer: Viewer = "app",
    *,
    embed: bool = False,
    for_static_file: bool = False,
) -> dict[str, Any] | None:
    entry = get_note(note_id)
    if not entry:
        return None

    md_path = Path(entry.md_path)
    md_text = md_path.read_text(encoding="utf-8", errors="replace")
    repaired_md, was_repaired = repair_deep_read_md(md_text)
    if was_repaired:
        persist_note_md(entry, repaired_md)
        md_text = repaired_md
    overview_md = prepare_overview_markdown(strip_abstract_zh_md(strip_deep_read_md(md_text)))
    html_body = markdown_to_html(overview_md)
    deep_md = extract_deep_read_md(md_text)
    deep_read_html = deep_read_to_html(deep_md) if deep_md else ""
    abstract_zh = extract_abstract_zh(md_text) or ""
    abstract_original = extract_original_abstract(md_text) or ""

    cfg = load_config()
    ui_port = int((cfg.get("ui") or {}).get("port", 18765))
    api_base = f"http://127.0.0.1:{ui_port}" if for_static_file else ""
    static_base = "_assets" if for_static_file else "/static"

    pdf_url = resolve_pdf_url(md_text, entry.item_key)
    zotero_url = zotero_item_url(entry.item_key)
    digest_app_url = deeplink_for_note(note_id)

    note_data = {
        "id": note_id,
        "has_abstract": "## 摘要" in md_text,
        "has_abstract_zh": has_abstract_zh(md_text),
        "abstract_zh": abstract_zh,
        "abstract_original": abstract_original,
        "has_deep_read": has_deep_read(md_text),
        "deep_read_html": deep_read_html,
        "zotero_url": zotero_url,
        "pdf_url": pdf_url,
    }

    return {
        "note_id": note_id,
        "viewer": viewer,
        "embed": embed,
        "for_static_file": for_static_file,
        "title": entry.title,
        "briefing": entry.briefing,
        "html_body": html_body,
        "zotero_url": zotero_url,
        "pdf_url": pdf_url,
        "digest_app_url": digest_app_url,
        "show_pdf": bool(pdf_url),
        "show_reveal": viewer in ("app", "standalone"),
        "show_digest_app": viewer == "hub",
        "api_base": api_base,
        "static_base": static_base,
        "ui_port": ui_port,
        "note_data": note_data,
    }


def render_note_view_html(
    flask_app,
    note_id: str,
    viewer: Viewer = "app",
    *,
    embed: bool = False,
    for_static_file: bool = False,
) -> str | None:
    ctx = prepare_note_view_context(
        note_id,
        viewer,
        embed=embed,
        for_static_file=for_static_file,
    )
    if not ctx:
        return None
    template = "note_view_fragment.html" if embed else "note_view.html"
    with flask_app.app_context():
        from flask import render_template

        return render_template(template, **ctx)


def render_hub_static_html(flask_app, note_id: str) -> str | None:
    return render_note_view_html(
        flask_app,
        note_id,
        viewer="hub",
        embed=False,
        for_static_file=True,
    )
