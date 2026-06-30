"""按需生成全文深度解读。"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from openai import OpenAI

from .config_manager import (
    ENV_PATH,
    SCRIPT_DIR,
    build_pdf_summary_messages,
    deepseek_deep_read_model,
    load_config,
)
from .digest import build_llm_context, load_dotenv
from .net_env import connect_zotero
from .notes_index import get_note
from .pdf_text import extract_pdf_text
from .md_render import markdown_to_html
from .mermaid_sanitize import sanitize_deep_read_body
from .summary_io import (
    KEY_TERMS_HEADING,
    LEGACY_KEY_TERMS_HEADING,
    build_hub_html,
    clean_terms,
    is_malformed_llm_sections,
    parse_llm_summary,
    repair_sections_from_json_blob,
    render_key_terms_section,
)
from .zotero_links import get_pdf_attachment

DEEP_READ_HEADING = "## 全文深度解读"
LEGACY_DEEP_READ_HEADING = "## PDF 深度解读"


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


def _key_terms_end(md_text: str, start: int) -> int:
    pos = _key_terms_heading_positions(md_text[start:])
    if pos is not None:
        return start + pos[0]
    return -1


def extract_deep_read_md(md_text: str) -> str | None:
    start = _deep_read_start(md_text)
    if start == -1:
        return None
    end = _key_terms_end(md_text, start)
    if end == -1:
        return md_text[start:].strip()
    return md_text[start:end].strip()


def strip_deep_read_md(md_text: str) -> str:
    start = _deep_read_start(md_text)
    if start == -1:
        return md_text
    end = _key_terms_end(md_text, start)
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
    pos = _key_terms_heading_positions(base)
    if pos is not None:
        key_idx, _ = pos
        return base[:key_idx].rstrip() + "\n\n" + block + "\n" + base[key_idx + 1 :]
    return base.rstrip() + "\n\n" + block + "\n"


def _key_terms_heading_positions(md_text: str) -> tuple[int, int] | None:
    for heading in (KEY_TERMS_HEADING, LEGACY_KEY_TERMS_HEADING):
        idx = md_text.find(f"\n{heading}")
        if idx != -1:
            return idx, len(heading)
    return None


def _update_key_terms_section(md_text: str, terms: list[str]) -> str:
    pos = _key_terms_heading_positions(md_text)
    quick_idx = md_text.find("\n## 快捷入口")
    if pos is None or quick_idx == -1:
        return md_text

    key_idx, _ = pos
    new_block = "\n".join(render_key_terms_section(terms))
    return md_text[: key_idx + 1] + "\n" + new_block + md_text[quick_idx:]


def _parse_key_terms(md_text: str) -> list[str]:
    pos = _key_terms_heading_positions(md_text)
    quick_idx = md_text.find("\n## 快捷入口")
    if pos is None or quick_idx == -1:
        return []

    key_idx, heading_len = pos
    chunk = md_text[key_idx + heading_len + 1 : quick_idx]
    terms: list[str] = []
    for line in chunk.splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        body = line[2:].strip()
        link_match = re.match(r"\*\*\[([^\]]+)\]\([^)]+\)\*\*", body)
        if link_match:
            terms.append(link_match.group(1))
            continue
        plain = re.sub(r"\s*—\s*.*$", "", body).strip()
        if plain:
            terms.append(plain)
    return terms


def _split_md_sections(chunk: str) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    parts = re.split(r"\n### ", chunk)
    for part in parts[1:]:
        lines = part.strip().split("\n", 1)
        heading = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        if heading or body:
            sections.append({"heading": heading, "body": body})
    return sections


def _close_open_mermaid_fence(body: str) -> str:
    if "```mermaid" not in body:
        return body
    if re.search(r"```mermaid[\s\S]*?```", body):
        return body
    return body.rstrip() + "\n```\n"


def _sections_have_body(sections: list[dict[str, str]]) -> bool:
    return any(str(sec.get("body", "")).strip() for sec in sections)


def _normalize_sections(sections: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "heading": str(sec.get("heading", "")).strip(),
            "body": sanitize_deep_read_body(
                _close_open_mermaid_fence(str(sec.get("body", "")).strip())
            ),
        }
        for sec in sections
    ]


def persist_note_md(entry, md_text: str) -> None:
    md_path = Path(entry.md_path)
    md_path.write_text(md_text, encoding="utf-8")
    if entry.hub_path:
        Path(entry.hub_path).write_text(build_hub_html(entry.id), encoding="utf-8")


def _extract_pdf_source_from_deep_md(deep_md: str) -> str:
    match = re.search(r"^\*正文来源：(.+?)\*$", deep_md, re.MULTILINE)
    return match.group(1).strip() if match else ""


def repair_deep_read_md(md_text: str) -> tuple[str, bool]:
    """将误存为 JSON 正文的深度解读修复为正常 Markdown 结构。"""
    deep_md = extract_deep_read_md(md_text)
    if not deep_md:
        return md_text, False

    sections = _split_md_sections(deep_md)
    if not is_malformed_llm_sections(sections):
        return md_text, False

    repaired = repair_sections_from_json_blob(str(sections[0].get("body", "")))
    if not repaired or not _sections_have_body(repaired.get("sections") or []):
        return md_text, False

    pdf_source = _extract_pdf_source_from_deep_md(deep_md)
    sections = _normalize_sections(repaired["sections"])
    updated = insert_deep_read_md(md_text, sections, pdf_source)
    terms = clean_terms(repaired.get("key_terms") or [])
    if terms:
        updated = _update_key_terms_section(
            updated,
            merge_key_terms(terms, _parse_key_terms(md_text)),
        )
    return updated, True


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
    messages = build_pdf_summary_messages(config, context, pdf_text, pdf_source)
    model = deepseek_deep_read_model(config)
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.5,
        max_tokens=6000,
        response_format={"type": "json_object"},
    )
    raw = (response.choices[0].message.content or "").strip()
    result = parse_llm_summary(raw)
    result["pdf_source"] = pdf_source
    return result


def deep_read_to_html(deep_md: str) -> str:
    return markdown_to_html(deep_md)


def generate_deep_read(note_id: str, *, regenerate: bool = False) -> dict[str, Any]:
    entry = get_note(note_id)
    if not entry:
        raise ValueError("笔记不存在")

    md_path = Path(entry.md_path)
    md_text = md_path.read_text(encoding="utf-8")

    if has_deep_read(md_text) and not regenerate:
        repaired_md, was_repaired = repair_deep_read_md(md_text)
        if was_repaired:
            persist_note_md(entry, repaired_md)
            md_text = repaired_md
        deep_md = extract_deep_read_md(md_text) or ""
        return {
            "cached": True,
            "repaired": was_repaired,
            "html": deep_read_to_html(deep_md),
            "markdown": deep_md,
        }

    if regenerate:
        md_text = strip_deep_read_md(md_text)

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

    sections = _normalize_sections(pdf_summary.get("sections") or [])
    if not _sections_have_body(sections):
        raise RuntimeError("深度解读生成结果为空，请稍后重试")

    pdf_source = pdf_summary.get("pdf_source") or ""
    merged_terms = merge_key_terms(
        pdf_summary.get("key_terms") or [],
        _parse_key_terms(md_text),
    )
    terms = clean_terms(merged_terms)

    updated_md = insert_deep_read_md(md_text, sections, pdf_source)
    if terms:
        updated_md = _update_key_terms_section(updated_md, terms)
    persist_note_md(entry, updated_md)

    deep_md = extract_deep_read_md(updated_md) or ""
    return {
        "cached": False,
        "html": deep_read_to_html(deep_md),
        "markdown": deep_md,
        "pdf_source": pdf_source,
    }
