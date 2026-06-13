"""解析 Zotero 条目 → PDF / 注释 / 全文页码定位链接。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pyzotero import zotero


@dataclass
class TermLink:
    term: str
    url: str
    source: str  # annotation | fulltext | item
    snippet: str = ""


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


def get_pdf_annotations(zot: zotero.Zotero, attachment_key: str) -> list[dict[str, Any]]:
    try:
        children = zot.children(attachment_key)
    except Exception:
        return []
    return [c for c in children if c.get("data", {}).get("itemType") == "annotation"]


def _annotation_text(ann: dict[str, Any]) -> str:
    data = ann.get("data", {})
    return " ".join(
        filter(
            None,
            [
                data.get("annotationText") or "",
                data.get("annotationComment") or "",
            ],
        )
    )


def find_annotation_link(zot: zotero.Zotero, item_key: str, term: str) -> TermLink | None:
    pdf = get_pdf_attachment(zot, item_key)
    if not pdf:
        return None
    attach_key = pdf["key"]
    term_lower = term.lower()
    best: tuple[int, dict[str, Any]] | None = None

    for ann in get_pdf_annotations(zot, attach_key):
        text = _annotation_text(ann)
        if term_lower not in text.lower():
            continue
        score = text.lower().find(term_lower)
        if best is None or score < best[0]:
            best = (score, ann)

    if not best:
        return None

    ann = best[1]
    data = ann["data"]
    page = data.get("annotationPageLabel") or ""
    snippet = _annotation_text(ann)[:120]
    return TermLink(
        term=term,
        url=zotero_pdf_url(attach_key, page=page or None, annotation_key=ann["key"]),
        source="annotation",
        snippet=snippet,
    )


def find_fulltext_page_link(zot: zotero.Zotero, item_key: str, term: str) -> TermLink | None:
    pdf = get_pdf_attachment(zot, item_key)
    if not pdf:
        return None
    attach_key = pdf["key"]
    term_lower = term.lower()

    try:
        ft = zot.fulltext_item(attach_key)
    except Exception:
        return None

    pages = ft.get("pages") or []
    for page_info in pages:
        text = page_info.get("text") or ""
        if term_lower in text.lower():
            page_num = page_info.get("page") or page_info.get("pageIndex")
            idx = text.lower().find(term_lower)
            snippet = text[max(0, idx - 40) : idx + 80].strip()
            return TermLink(
                term=term,
                url=zotero_pdf_url(attach_key, page=page_num),
                source="fulltext",
                snippet=snippet,
            )

    content = ft.get("content") or ""
    if term_lower in content.lower():
        return TermLink(
            term=term,
            url=zotero_pdf_url(attach_key),
            source="fulltext",
            snippet="在全文中匹配到该术语（未能定位具体页码）",
        )
    return None


def resolve_term_links(zot: zotero.Zotero, item_key: str, terms: list[str]) -> list[TermLink]:
    links: list[TermLink] = []
    seen_terms: set[str] = set()

    for raw in terms:
        term = raw.strip()
        if not term or term.lower() in seen_terms:
            continue
        seen_terms.add(term.lower())

        link = find_annotation_link(zot, item_key, term)
        if link is None:
            link = find_fulltext_page_link(zot, item_key, term)
        if link is None:
            link = TermLink(
                term=term,
                url=zotero_item_url(item_key),
                source="item",
                snippet="未在 PDF 注释/全文中定位，点击打开 Zotero 条目",
            )
        links.append(link)
    return links


def clean_terms(terms: list[str]) -> list[str]:
    cleaned: list[str] = []
    for term in terms:
        t = re.sub(r"\s+", " ", term.strip())
        if len(t) >= 2:
            cleaned.append(t)
    return cleaned[:8]
