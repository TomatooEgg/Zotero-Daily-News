"""将本地简报回推到 Zotero 条目下的子笔记。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

from abstract_zh import extract_abstract_zh, has_abstract_zh, strip_abstract_zh_md
from md_render import markdown_to_html
from net_env import connect_zotero, connect_zotero_web
from notes_index import get_note
from zotero_credentials import is_zotero_configured

DIGEST_NOTE_TAG = "zotero-digest"
ZH_START = "<!-- zh-abstract -->"
ZH_END = "<!-- /zh-abstract -->"


def _has_digest_tag(tags: list[dict[str, Any]] | None) -> bool:
    for tag in tags or []:
        if (tag.get("tag") or "") == DIGEST_NOTE_TAG:
            return True
    return False


def find_digest_notes(zot, item_key: str) -> list[dict[str, Any]]:
    try:
        children = zot.children(item_key)
    except Exception:
        return []
    notes: list[dict[str, Any]] = []
    for child in children:
        data = child.get("data") or {}
        if data.get("itemType") != "note":
            continue
        if not _has_digest_tag(data.get("tags")):
            continue
        notes.append(
            {
                "key": child.get("key") or data.get("key", ""),
                "dateModified": data.get("dateModified", ""),
            }
        )
    notes.sort(key=lambda n: n.get("dateModified") or "", reverse=True)
    return notes


def expand_zh_abstract_md(md_text: str) -> str:
    """将摘要译文注释块展开为可见 Markdown。"""
    if not has_abstract_zh(md_text):
        return md_text
    zh = extract_abstract_zh(md_text) or ""
    if not zh:
        return strip_abstract_zh_md(md_text)

    pattern = re.compile(
        r"(## 摘要\s*\n\n)(.*?)(\n## )",
        re.DOTALL,
    )
    match = pattern.search(md_text)
    if match:
        replacement = f"{match.group(1)}{zh}\n\n> 英文原文：{match.group(2).strip()}\n\n{match.group(3)}"
        md_text = md_text[: match.start()] + replacement + md_text[match.end() :]
    return strip_abstract_zh_md(md_text)


def prepare_note_html(md_text: str) -> str:
    expanded = expand_zh_abstract_md(md_text)
    return markdown_to_html(expanded)


def push_status(note_id: str) -> dict[str, Any]:
    entry = get_note(note_id)
    if not entry:
        raise ValueError("笔记不存在")

    configured = is_zotero_configured()
    existing: list[dict[str, str]] | None = None
    if configured:
        try:
            zot = connect_zotero_web()
            existing = find_digest_notes(zot, entry.item_key) or None
        except Exception:
            existing = None

    return {
        "configured": configured,
        "existing": existing,
        "item_key": entry.item_key,
    }


PushMode = Literal["create", "update"]


def push_digest_note(
    note_id: str,
    mode: PushMode,
    *,
    target_key: str | None = None,
) -> dict[str, Any]:
    entry = get_note(note_id)
    if not entry:
        raise ValueError("笔记不存在")

    if not is_zotero_configured():
        raise RuntimeError(
            "未配置 ZOTERO_API_KEY。请打开控制台 → 设置 → Zotero 回推 填写 API Key"
        )

    try:
        local_zot = connect_zotero()
        local_zot.item(entry.item_key)
    except Exception as exc:
        raise ValueError("Zotero 条目不存在或无法访问，请确认 Zotero 已运行") from exc

    md_text = Path(entry.md_path).read_text(encoding="utf-8", errors="replace")
    note_html = prepare_note_html(md_text)

    web_zot = connect_zotero_web()

    if mode == "update":
        if not target_key:
            existing = find_digest_notes(web_zot, entry.item_key)
            if not existing:
                raise ValueError("未找到可更新的回推笔记")
            target_key = existing[0]["key"]
        item = web_zot.item(target_key)
        item["data"]["note"] = note_html
        if not _has_digest_tag(item["data"].get("tags")):
            tags = list(item["data"].get("tags") or [])
            tags.append({"tag": DIGEST_NOTE_TAG})
            item["data"]["tags"] = tags
        web_zot.update_item(item)
        return {
            "note_key": target_key,
            "mode": "update",
            "item_key": entry.item_key,
        }

    template = web_zot.item_template("note")
    template["note"] = note_html
    template["tags"] = [{"tag": DIGEST_NOTE_TAG}]
    resp = web_zot.create_items([template], parentid=entry.item_key)
    failed = (resp or {}).get("failed") or {}
    if failed:
        detail = next(iter(failed.values()), {})
        msg = detail.get("message") if isinstance(detail, dict) else str(detail)
        raise RuntimeError(f"创建笔记失败: {msg or failed}")
    success = (resp or {}).get("success") or {}
    note_key = success.get("0") or next(iter(success.values()), "")
    if not note_key:
        raise RuntimeError("创建笔记失败：未返回 note key")
    return {
        "note_key": note_key,
        "mode": "create",
        "item_key": entry.item_key,
    }
