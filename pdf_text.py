"""从 Zotero PDF 附件提取正文文本。"""

from __future__ import annotations

import io
import re
import tempfile
from pathlib import Path
from typing import Any

from pyzotero import zotero


def _normalize_text(text: str) -> str:
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _truncate_text(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    head = int(max_chars * 0.75)
    tail = max_chars - head - 80
    if tail < 1000:
        return text[:max_chars] + "\n\n…（正文过长，已截断）", True
    return (
        text[:head]
        + "\n\n…（中间部分已省略，以下为文末内容）…\n\n"
        + text[-tail:]
        + "\n\n…（正文过长，已截断）",
        True,
    )


def _text_from_fulltext(ft: dict[str, Any]) -> str:
    pages = ft.get("pages") or []
    if pages:
        ordered = sorted(
            pages,
            key=lambda p: p.get("pageIndex", p.get("page", 0)) or 0,
        )
        chunks = [p.get("text") or "" for p in ordered if (p.get("text") or "").strip()]
        if chunks:
            return _normalize_text("\n\n".join(chunks))
    content = (ft.get("content") or "").strip()
    return _normalize_text(content)


def _text_from_pdf_bytes(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    chunks: list[str] = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        if page_text.strip():
            chunks.append(page_text)
    return _normalize_text("\n\n".join(chunks))


def extract_pdf_text(
    zot: zotero.Zotero,
    attach_key: str,
    max_chars: int = 80000,
) -> tuple[str, str]:
    """返回 (正文, 来源说明)。无可用正文时返回 ("", 原因)。"""
    # 优先使用 Zotero 已索引的全文
    try:
        ft = zot.fulltext_item(attach_key)
        text = _text_from_fulltext(ft)
        if len(text) >= 200:
            truncated, was_truncated = _truncate_text(text, max_chars)
            source = "Zotero 全文索引"
            if was_truncated:
                source += f"（已截断至约 {max_chars} 字）"
            return truncated, source
    except Exception:
        pass

    # 回退：下载 PDF 并本地解析
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            zot.dump(attach_key, "paper.pdf", str(tmp_path))
            pdf_path = tmp_path / "paper.pdf"
            if not pdf_path.exists():
                return "", "无法下载 PDF 附件"
            data = pdf_path.read_bytes()
        text = _text_from_pdf_bytes(data)
        if len(text) < 200:
            return "", "PDF 未能提取足够文本（可能是扫描版）"
        truncated, was_truncated = _truncate_text(text, max_chars)
        source = "PDF 文件解析"
        if was_truncated:
            source += f"（已截断至约 {max_chars} 字）"
        return truncated, source
    except Exception as exc:
        return "", f"PDF 提取失败: {exc}"
