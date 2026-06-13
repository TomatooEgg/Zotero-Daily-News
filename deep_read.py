"""按需生成全文深度解读。"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import markdown
from openai import OpenAI
from pyzotero import zotero

from config_manager import (
    SCRIPT_DIR,
    build_pdf_summary_prompt,
    load_config,
)
from digest import build_llm_context, load_dotenv
from notes_index import get_note
from pdf_text import extract_pdf_text
from summary_io import build_hub_html, parse_llm_summary
from zotero_links import TermLink, clean_terms, get_pdf_attachment, resolve_term_links

ENV_PATH = SCRIPT_DIR / ".env"
DEEP_READ_HEADING = "## 全文深度解读"
LEGACY_DEEP_READ_HEADING = "## PDF 深度解读"
KEY_TERMS_HEADING = "## 关键术语 · 原文定位"


def connect_zotero() -> zotero.Zotero:
    return zotero.Zotero(library_id=0, library_type="user", local=True)


def has_deep_read(md_text: str) -> bool:
    return DEEP_READ_HEADING in md_text or LEGACY_DEEP_READ_HEADING in md_text


def _deep_read_start(md_text: str) -> int:
    for heading in (DEEP_READ_HEADING, LEGACY_DEEP_READ_HEADING):
        idx = md_text.find(f"\n{heading}\n")
        if idx != -1:
            return idx + 1
        if md_text.startswith(heading):
            return 0
    return -1


def extract_deep_read_md(md_text: str) -> str | None:
    start = _deep_read_start(md_text)
    if start == -1:
        return None
    end = md_text.find(f"\n{KEY_TERMS_HEADING}", start)
    if end == -1:
        return md_text[start:].strip()
    return md_text[start:end].strip()


def strip_deep_read_md(md_text: str) -> str:
    start = _deep_read_start(md_text)
    if start == -1:
        return md_text
    end = md_text.find(f"\n{KEY_TERMS_HEADING}", start)
    if end == -1:
        return md_text[:start].rstrip() + "\n"
    return (md_text[:start].rstrip() + "\n" + md_text[end + 1 :]).strip() + "\n"


def _render_deep_read_block(sections: list[dict[str, str]], pdf_source: str) -> str:
    lines = [DEEP_READ_HEADING, ""]
    if pdf_source:
        lines.extend([f"*正文来源：{pdf_source}*", ""])
    for sec in sections:
        heading = sec.get("heading", "").strip()
        body = sec.get("body", "").strip()
        if heading:
            lines.extend([f"### {heading}", ""])
        if body:
            lines.extend([body, ""])
    return "\n".join(lines).rstrip()


def insert_deep_read_md(
    md_text: str,
    sections: list[dict[str, str]],
    pdf_source: str,
) -> str:
    base = strip_deep_read_md(md_text)
    block = _render_deep_read_block(sections, pdf_source)
    key_idx = base.find(f"\n{KEY_TERMS_HEADING}")
    if key_idx != -1:
        return base[:key_idx].rstrip() + "\n\n" + block + "\n" + base[key_idx + 1 :]
    return base.rstrip() + "\n\n" + block + "\n"


def _update_key_terms_section(md_text: str, term_links: list[TermLink]) -> str:
    key_idx = md_text.find(f"\n{KEY_TERMS_HEADING}")
    quick_idx = md_text.find("\n## 快捷入口")
    if key_idx == -1 or quick_idx == -1:
        return md_text

    lines = [KEY_TERMS_HEADING, ""]
    for link in term_links:
        source_note = {
            "annotation": "PDF 高亮注释",
            "fulltext": "PDF 全文检索",
            "item": "条目（未精确定位）",
        }.get(link.source, "")
        lines.append(f"- **[{link.term}]({link.url})** — {source_note}")
        if link.snippet:
            lines.append(f"  - 片段：{link.snippet}")
    lines.append("")
    new_block = "\n".join(lines)
    return md_text[: key_idx + 1] + "\n" + new_block + md_text[quick_idx:]


def _parse_briefing(md_text: str) -> str:
    match = re.search(r"^>\s*\*\*头条简报\*\*[：:]\s*(.+)$", md_text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _parse_sections(md_text: str) -> list[dict[str, str]]:
    start = md_text.find("\n## 速览解读\n")
    if start == -1:
        return []
    end = _deep_read_start(md_text)
    if end == -1:
        end = md_text.find(f"\n{KEY_TERMS_HEADING}", start)
    if end == -1:
        chunk = md_text[start:]
    else:
        chunk = md_text[start:end]

    sections: list[dict[str, str]] = []
    parts = re.split(r"\n### ", chunk)
    for part in parts[1:]:
        lines = part.strip().split("\n", 1)
        heading = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        if heading or body:
            sections.append({"heading": heading, "body": body})
    return sections


def _parse_term_links(md_text: str) -> list[TermLink]:
    links: list[TermLink] = []
    pattern = re.compile(r"-\s*\*\*\[([^\]]+)\]\((zotero://[^)]+)\)\*\*\s*—\s*([^\n]+)")
    for term, url, note in pattern.findall(md_text):
        source = "annotation" if "annotation=" in url else "fulltext" if "open-pdf" in url else "item"
        if "全文检索" in note:
            source = "fulltext"
        elif "高亮" in note:
            source = "annotation"
        links.append(TermLink(term=term, url=url, source=source))
    return links


def merge_key_terms(primary: list[str], secondary: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for term in primary + secondary:
        t = term.strip()
        key = t.lower()
        if len(t) >= 2 and key not in seen:
            seen.add(key)
            merged.append(t)
    return merged[:8]


def generate_pdf_summary(
    client: OpenAI,
    item: dict,
    config: dict,
    zot: zotero.Zotero,
    attach_key: str,
) -> dict | None:
    pdf_cfg = config.get("pdf_summary") or {}
    if not pdf_cfg.get("enabled", True):
        return None

    max_chars = int(pdf_cfg.get("max_chars", 80000))
    pdf_text, pdf_source = extract_pdf_text(zot, attach_key, max_chars=max_chars)
    if not pdf_text:
        raise RuntimeError(pdf_source or "无法提取 PDF 正文")

    context = build_llm_context(item)
    prompt = build_pdf_summary_prompt(config, context, pdf_text, pdf_source)
    model = config.get("deepseek", {}).get("model", "deepseek-chat")
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=4000,
        response_format={"type": "json_object"},
    )
    raw = (response.choices[0].message.content or "").strip()
    result = parse_llm_summary(raw)
    result["pdf_source"] = pdf_source
    return result


def deep_read_to_html(deep_md: str) -> str:
    return markdown.markdown(deep_md, extensions=["extra", "nl2br", "sane_lists"])


def generate_deep_read(note_id: str) -> dict[str, Any]:
    entry = get_note(note_id)
    if not entry:
        raise ValueError("笔记不存在")

    md_path = Path(entry.md_path)
    md_text = md_path.read_text(encoding="utf-8")

    if has_deep_read(md_text):
        deep_md = extract_deep_read_md(md_text) or ""
        return {
            "cached": True,
            "html": deep_read_to_html(deep_md),
            "markdown": deep_md,
        }

    load_dotenv(ENV_PATH)
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise RuntimeError("未设置 DEEPSEEK_API_KEY")

    config = load_config()
    ds = config.get("deepseek", {})
    client = OpenAI(api_key=api_key, base_url=ds.get("base_url", "https://api.deepseek.com"))

    zot = connect_zotero()
    item = zot.item(entry.item_key)
    pdf = get_pdf_attachment(zot, entry.item_key)
    if not pdf:
        raise RuntimeError("该文献没有 PDF 附件，无法生成全文深度解读")

    pdf_summary = generate_pdf_summary(client, item, config, zot, pdf["key"])
    if not pdf_summary:
        raise RuntimeError("PDF 深度解读未启用")

    sections = pdf_summary.get("sections") or []
    pdf_source = pdf_summary.get("pdf_source") or ""
    briefing_terms = _parse_term_links(md_text)
    briefing_term_names = [link.term for link in briefing_terms]
    merged_terms = merge_key_terms(
        pdf_summary.get("key_terms") or [],
        briefing_term_names,
    )
    term_links = resolve_term_links(zot, entry.item_key, clean_terms(merged_terms))

    updated_md = insert_deep_read_md(md_text, sections, pdf_source)
    updated_md = _update_key_terms_section(updated_md, term_links)
    md_path.write_text(updated_md, encoding="utf-8")

    if entry.hub_path:
        hub_path = Path(entry.hub_path)
        hub_path.write_text(build_hub_html(entry.id), encoding="utf-8")

    deep_md = extract_deep_read_md(updated_md) or ""
    return {
        "cached": False,
        "html": deep_read_to_html(deep_md),
        "markdown": deep_md,
        "pdf_source": pdf_source,
    }
