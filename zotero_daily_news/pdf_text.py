"""从 Zotero PDF 附件提取正文文本。"""

from __future__ import annotations

import io
import os
import re
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

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


def _zotero_data_dir() -> Path | None:
    candidate = Path.home() / "Zotero"
    if (candidate / "zotero.sqlite").exists():
        return candidate
    return None


def _base_attachment_path(data_dir: Path) -> Path | None:
    prefs = data_dir / "prefs.js"
    if not prefs.exists():
        return None
    try:
        text = prefs.read_text(encoding="utf-8", errors="replace")
        match = re.search(
            r'user_pref\("extensions\.zotero\.baseAttachmentPath",\s*"([^"]+)"\)',
            text,
        )
        if match:
            return Path(match.group(1))
    except Exception:
        pass
    return None


def _resolve_zotero_path(
    zotero_path: str,
    attach_key: str,
    storage_dir: Path,
    data_dir: Path,
) -> Path | None:
    if not zotero_path:
        return None

    if zotero_path.startswith("storage:"):
        rel = zotero_path.split(":", 1)[1]
        parts = [p for p in rel.split("/") if p]
        return storage_dir / attach_key / Path(*parts)

    if zotero_path.startswith("file://"):
        parsed = urlparse(zotero_path)
        decoded = unquote(parsed.path or "")
        if (
            os.name == "nt"
            and decoded.startswith("/")
            and len(decoded) > 2
            and decoded[2] == ":"
        ):
            decoded = decoded[1:]
        return Path(decoded) if decoded else None

    if os.path.isabs(zotero_path):
        return Path(zotero_path)

    if zotero_path.startswith("attachments:"):
        rel = zotero_path.split(":", 1)[1]
        parts = [p for p in rel.split("/") if p]
        base = _base_attachment_path(data_dir)
        if base and base.exists():
            return base / Path(*parts)
        return None

    return None


def get_local_pdf_path(zot: zotero.Zotero, attach_key: str) -> Path | None:
    """定位 PDF 附件的本地文件路径。"""
    return _find_local_pdf_path(zot, attach_key)


def _find_local_pdf_path(zot: zotero.Zotero, attach_key: str) -> Path | None:
    """从 Zotero 本地 storage 或链接路径定位 PDF，绕过 file:// 下载。"""
    data_dir = _zotero_data_dir()
    if not data_dir:
        return None

    storage_dir = data_dir / "storage"
    zotero_path = ""
    filename = ""

    try:
        item_data = zot.item(attach_key).get("data") or {}
        zotero_path = (item_data.get("path") or "").strip()
        filename = (item_data.get("filename") or "").strip()
    except Exception:
        pass

    if zotero_path:
        resolved = _resolve_zotero_path(zotero_path, attach_key, storage_dir, data_dir)
        if resolved and resolved.is_file():
            return resolved

    folder = storage_dir / attach_key
    if not folder.is_dir():
        return None

    if filename:
        candidate = folder / filename
        if candidate.is_file():
            return candidate

    pdfs = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"]
    if not pdfs:
        return None
    return max(pdfs, key=lambda p: p.stat().st_mtime)


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

    # 回退：本地 PDF 解析（local API 的 dump 会走 file://，httpx 不支持）
    try:
        data: bytes | None = None
        local_path = _find_local_pdf_path(zot, attach_key)
        if local_path:
            data = local_path.read_bytes()
        else:
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
