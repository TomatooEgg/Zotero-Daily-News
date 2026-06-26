"""Markdown 渲染：表格等格式预处理。"""

from __future__ import annotations

import html
import re

import markdown

from mermaid_sanitize import escape_bare_underscores, escape_pipes_in_table_math

_MD_EXTENSIONS = ["extra", "nl2br", "sane_lists"]
_TABLE_ROW_RE = re.compile(r"^\s*\|")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$")
_ABSTRACT_SECTION_RE = re.compile(r"(## 摘要\s*\n\n)(.*?)(\n## )", re.DOTALL)


def normalize_plaintext(text: str) -> str:
    """清理 Zotero/HTML 摘要，避免行首缩进在 Markdown 里变成代码块。"""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    lines = [re.sub(r"\s+", " ", line.strip()) for line in text.splitlines()]
    lines = [line for line in lines if line]
    if lines and lines[0].lower() == "abstract":
        lines = lines[1:]
    return " ".join(lines)


def strip_note_header_md(md: str) -> str:
    """去掉模板已展示的标题/简报/元信息，避免正文重复 Markdown 结构。"""
    for marker in ("## 摘要", "## 速览解读"):
        idx = md.find(marker)
        if idx != -1:
            return md[idx:]
    return md


def normalize_abstract_in_md(md: str) -> str:
    match = _ABSTRACT_SECTION_RE.search(md)
    if not match:
        return md
    body = normalize_plaintext(match.group(2))
    return md[: match.start(2)] + body + md[match.start(3) :]


def prepare_overview_markdown(md: str) -> str:
    return normalize_abstract_in_md(strip_note_header_md(md))


def ensure_blank_line_before_tables(md: str) -> str:
    """GFM 表格前必须有空行；LLM 常在标题后直接接 | 行，导致无法识别为表格。"""
    lines = md.split("\n")
    out: list[str] = []
    for i, line in enumerate(lines):
        if _TABLE_ROW_RE.match(line) and i > 0:
            prev = lines[i - 1].strip()
            if (
                prev
                and not _TABLE_ROW_RE.match(lines[i - 1])
                and not _TABLE_SEP_RE.match(prev)
                and out
                and out[-1].strip()
            ):
                out.append("")
        out.append(line)
    return "\n".join(out)


def markdown_to_html(md: str) -> str:
    prepared = escape_bare_underscores(
        escape_pipes_in_table_math(ensure_blank_line_before_tables(md))
    )
    return markdown.markdown(
        prepared,
        extensions=_MD_EXTENSIONS,
    )
