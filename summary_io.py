"""生成 / 写入 Markdown 总结与 HTML 中转页。"""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from config_manager import SCRIPT_DIR
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


def ensure_hub_assets(hubs_dir: Path) -> None:
    """同步 static 资源到 hubs/_assets，供 file:// 中转页离线加载。"""
    assets = hubs_dir / "_assets"
    assets.mkdir(parents=True, exist_ok=True)
    static = SCRIPT_DIR / "static"
    for name in ("note-view.css", "note-view.js"):
        src = static / name
        if src.is_file():
            shutil.copy2(src, assets / name)
    katex_src = static / "katex"
    if katex_src.is_dir():
        shutil.copytree(katex_src, assets / "katex", dirs_exist_ok=True)


def build_hub_html(note_id: str) -> str:
    from app import app
    from config_manager import load_config, resolve_output_dirs
    from note_view import render_hub_static_html

    _, hubs_dir = resolve_output_dirs(load_config())
    ensure_hub_assets(hubs_dir)
    html = render_hub_static_html(app, note_id)
    if not html:
        raise ValueError(f"无法渲染中转页: {note_id}")
    return html


def _unescape_json_string(value: str) -> str:
    chars: list[str] = []
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == "\\" and i + 1 < len(value):
            nxt = value[i + 1]
            if nxt == "n":
                chars.append("\n")
            elif nxt == "t":
                chars.append("\t")
            elif nxt == "r":
                chars.append("\r")
            elif nxt == '"':
                chars.append('"')
            elif nxt == "\\":
                chars.append("\\")
            elif nxt == "/":
                chars.append("/")
            elif nxt == "u" and i + 5 < len(value):
                chars.append(chr(int(value[i + 2 : i + 6], 16)))
                i += 6
                continue
            else:
                chars.append(ch)
                chars.append(nxt)
            i += 2
        else:
            chars.append(ch)
            i += 1
    return "".join(chars)


def _extract_json_string_value(raw: str, key: str) -> tuple[str | None, str]:
    if key:
        match = re.search(rf'"{re.escape(key)}"\s*:\s*"', raw)
        if not match:
            return None, raw
        i = match.end()
    elif raw.startswith('"'):
        i = 1
    else:
        return None, raw
    chars: list[str] = []
    while i < len(raw):
        ch = raw[i]
        if ch == "\\" and i + 1 < len(raw):
            chars.append(ch)
            chars.append(raw[i + 1])
            i += 2
            continue
        if ch == '"':
            return _unescape_json_string("".join(chars)), raw[i + 1 :]
        chars.append(ch)
        i += 1
    return None, raw


def extract_sections_loose(raw: str) -> list[dict[str, str]] | None:
    pos = raw.find('"sections"')
    if pos == -1:
        return None
    chunk = raw[pos:]
    sections: list[dict[str, str]] = []
    while True:
        heading_match = re.search(r'"heading"\s*:\s*"', chunk)
        if not heading_match:
            break
        chunk = chunk[heading_match.start() :]
        heading, rest = _extract_json_string_value(chunk, "heading")
        if heading is None:
            break
        body_match = re.search(r'"body"\s*:\s*"', rest)
        if not body_match:
            break
        body, rest = _extract_json_string_value(rest[body_match.start() :], "body")
        if body is None:
            break
        sections.append({"heading": heading.strip(), "body": body.strip()})
        chunk = rest
    return sections or None


def _extract_key_terms_loose(raw: str) -> list[str]:
    match = re.search(r'"key_terms"\s*:\s*\[', raw)
    if not match:
        return []
    rest = raw[match.end() :]
    terms: list[str] = []
    while rest:
        rest = rest.lstrip(" \t\r\n,")
        if not rest or rest[0] == "]":
            break
        if not rest.startswith('"'):
            break
        term, rest = _extract_json_string_value(rest, "")
        if term is None:
            break
        terms.append(term.strip())
    return clean_terms(terms)


def _try_repair_json_text(raw: str) -> str | None:
    import json

    repaired = raw
    repaired = re.sub(r",(\s*[}\]])", r"\1", repaired)
    repaired = re.sub(r'\\"\]', r'\\\""]', repaired)
    try:
        json.loads(repaired)
        return repaired
    except json.JSONDecodeError:
        return None


def _extract_json_blob(raw: str) -> str:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        return fence.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def is_raw_json_summary_blob(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("{") and '"sections"' in stripped


def is_malformed_llm_sections(sections: list[dict[str, str]]) -> bool:
    if len(sections) != 1:
        return False
    sec = sections[0]
    heading = str(sec.get("heading", "")).strip()
    body = str(sec.get("body", "")).strip()
    if heading not in ("解读", ""):
        return False
    return is_raw_json_summary_blob(body)


def repair_sections_from_json_blob(body: str) -> dict[str, Any] | None:
    raw = _extract_json_blob(body)
    parsed = _parse_llm_json(raw)
    if parsed and parsed.get("sections"):
        return parsed
    sections = extract_sections_loose(raw)
    if not sections:
        return None
    return {
        "sections": sections,
        "key_terms": _extract_key_terms_loose(raw),
    }


def _parse_llm_json(raw: str) -> dict[str, Any] | None:
    import json

    blob = _extract_json_blob(raw)
    for candidate in (blob, _try_repair_json_text(blob)):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    sections = extract_sections_loose(blob)
    if not sections:
        return None
    data: dict[str, Any] = {
        "sections": sections,
        "key_terms": _extract_key_terms_loose(blob),
    }
    briefing, _ = _extract_json_string_value(blob, "briefing")
    if briefing:
        data["briefing"] = briefing
    return data


def parse_llm_summary(raw: str) -> dict[str, Any]:
    parsed = _parse_llm_json(raw)
    if parsed:
        sections = parsed.get("sections") or []
        if sections and not is_malformed_llm_sections(sections):
            return parsed
        if is_malformed_llm_sections(sections):
            repaired = repair_sections_from_json_blob(str(sections[0].get("body", "")))
            if repaired and repaired.get("sections"):
                merged = dict(parsed)
                merged.update(repaired)
                return merged
        return parsed

    blob = _extract_json_blob(raw)
    return {
        "briefing": blob[:200],
        "sections": [{"heading": "解读", "body": blob}],
        "key_terms": [],
    }


def ensure_hub_path(
    note_id: str,
    hubs_dir: Path,
    hub_path: str | None = None,
) -> Path:
    """确保中转页存在；缺失时按 note_id 重建。"""
    path = Path(hub_path) if hub_path else hubs_dir / f"{note_id}.html"
    if not path.is_file():
        hubs_dir.mkdir(parents=True, exist_ok=True)
        path = hubs_dir / f"{note_id}.html"
        path.write_text(build_hub_html(note_id), encoding="utf-8")
    return path


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
