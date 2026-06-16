"""生成 / 写入 Markdown 总结与 HTML 中转页。"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from md_render import normalize_plaintext
from zotero_links import zotero_item_url, zotero_pdf_url

KEY_TERMS_HEADING = "## 关键术语"
LEGACY_KEY_TERMS_HEADING = "## 关键术语 · 原文定位"


def clean_terms(terms: list[str]) -> list[str]:
    cleaned: list[str] = []
    for term in terms:
        t = re.sub(r"\s+", " ", term.strip())
        if len(t) >= 2:
            cleaned.append(t)
    return cleaned[:8]


def render_key_terms_section(terms: list[str]) -> list[str]:
    lines = [KEY_TERMS_HEADING, ""]
    for term in terms:
        lines.append(f"- {term}")
    lines.append("")
    return lines


def slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text, flags=re.UNICODE).strip("-")
    return (slug or "item")[:max_len]


def summary_paths(
    summaries_dir: Path,
    hubs_dir: Path,
    item_key: str,
    title: str,
) -> tuple[Path, Path]:
    summaries = summaries_dir
    hubs = hubs_dir
    summaries.mkdir(parents=True, exist_ok=True)
    hubs.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    name = f"{stamp}_{item_key}_{slugify(title)}"
    return summaries / f"{name}.md", hubs / f"{name}.html"


def build_markdown(
    item: dict[str, Any],
    briefing: str,
    sections: list[dict[str, str]],
    key_terms: list[str],
    pdf_attach_key: str | None,
) -> str:
    data = item["data"]
    title = data.get("title", "无标题")
    item_key = item["key"]
    authors = ", ".join(
        f"{c.get('lastName', '')} {c.get('firstName', '')}".strip()
        for c in data.get("creators", [])
        if c.get("creatorType") == "author"
    ) or "未知作者"
    journal = data.get("publicationTitle") or data.get("proceedingsTitle") or "未知来源"
    year = (data.get("date") or "")[:4]
    abstract = normalize_plaintext((data.get("abstractNote") or "").strip())

    lines = [
        f"# {title}",
        "",
        f"> **头条简报**：{briefing}",
        "",
        f"- **作者**：{authors}",
        f"- **出处**：{journal} ({year or '未知年份'})",
        f"- **Zotero 条目**：<{zotero_item_url(item_key)}>",
        "",
    ]

    if abstract:
        lines.extend(["## 摘要", "", abstract, ""])

    lines.append("## 速览解读")
    lines.append("")
    for sec in sections:
        heading = sec.get("heading", "").strip()
        body = sec.get("body", "").strip()
        if heading:
            lines.append(f"### {heading}")
            lines.append("")
        if body:
            lines.append(body)
            lines.append("")

    lines.extend(render_key_terms_section(key_terms))

    lines.append("## 快捷入口")
    lines.append("")
    lines.append(f"- [在 Zotero 中打开条目]({zotero_item_url(item_key)})")
    if pdf_attach_key:
        lines.append(f"- [打开 PDF]({zotero_pdf_url(pdf_attach_key)})")
    lines.append("")
    lines.append(f"---\n*生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    return "\n".join(lines)


def build_hub_html(note_id: str) -> str:
    from app import app
    from note_view import render_hub_static_html

    html = render_hub_static_html(app, note_id)
    if not html:
        raise ValueError(f"无法渲染中转页: {note_id}")
    return html


def parse_llm_summary(raw: str) -> dict[str, Any]:
    import json

    raw = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1)
    else:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1:
            raw = raw[start : end + 1]
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    return {
        "briefing": raw[:200],
        "sections": [{"heading": "解读", "body": raw}],
        "key_terms": [],
    }


def write_outputs(
    summaries_dir: Path,
    hubs_dir: Path,
    item: dict[str, Any],
    briefing: str,
    sections: list[dict[str, str]],
    key_terms: list[str],
    pdf_attach_key: str | None,
) -> tuple[Path, Path]:
    title = item["data"].get("title", "无标题")
    md_path, hub_path = summary_paths(summaries_dir, hubs_dir, item["key"], title)
    note_id = md_path.stem
    md_content = build_markdown(item, briefing, sections, key_terms, pdf_attach_key)
    md_path.write_text(md_content, encoding="utf-8")
    hub_path.write_text(build_hub_html(note_id), encoding="utf-8")
    return md_path, hub_path
