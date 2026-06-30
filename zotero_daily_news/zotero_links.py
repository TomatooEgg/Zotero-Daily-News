"""解析 Zotero 条目 → PDF / 注释链接。"""

from __future__ import annotations

from typing import Any

from pyzotero import zotero


def zotero_item_url(item_key: str) -> str:
    return f"zotero://select/library/items/{item_key}"


def zotero_pdf_url(attach_key: str, page: str | int | None = None, annotation_key: str | None = None) -> str:
    url = f"zotero://open-pdf/library/items/{attach_key}"
    params: list[str] = []
    if page is not None and str(page).strip():
        params.append(f"page={page}")
    if annotation_key:
        params.append(f"annotation={annotation_key}")
    if params:
        url += "?" + "&".join(params)
    return url


def get_pdf_attachment(zot: zotero.Zotero, parent_key: str) -> dict[str, Any] | None:
    try:
        children = zot.children(parent_key)
    except Exception:
        return None
    for child in children:
        data = child.get("data", {})
        if data.get("itemType") != "attachment":
            continue
        mime = (data.get("contentType") or "").lower()
        name = (data.get("filename") or "").lower()
        if "pdf" in mime or name.endswith(".pdf"):
            return child
    return None
