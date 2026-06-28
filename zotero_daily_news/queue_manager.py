"""待推清单：随机选文、固定 item_key 列表、预生成与推送。"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from openai import OpenAI

from .config_manager import load_config, resolve_output_dirs, runtime_path
from .net_env import connect_zotero
from .notes_index import NoteEntry, latest_notes_by_item_key
from .pending_publish import mark_pending
from .summary_io import clean_terms, ensure_hub_path, write_outputs
from .zotero_links import get_pdf_attachment

QUEUE_PATH = runtime_path("queue.json")

STATUS_PENDING = "pending"
STATUS_READY = "ready"
STATUS_PUSHED = "pushed"
STATUS_ERROR = "error"

DEEP_PENDING = "pending"
DEEP_READY = "ready"
DEEP_SKIPPED = "skipped"
DEEP_ERROR = "error"


def _hub_file_exists(entry: dict[str, Any]) -> bool:
    raw = entry.get("hub_path")
    return bool(raw and Path(raw).is_file())


def _entries_in_push_window(
    items: list[dict[str, Any]],
    push_count: int,
) -> list[dict[str, Any]]:
    """下一批推送位：跳过已推送，取前 push_count 篇未推送条目。"""
    window: list[dict[str, Any]] = []
    for entry in items:
        if entry.get("status") == STATUS_PUSHED:
            continue
        window.append(entry)
        if len(window) >= push_count:
            break
    return window


def load_queue() -> dict[str, Any] | None:
    if not QUEUE_PATH.exists():
        return None
    try:
        with QUEUE_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def save_queue(queue: dict[str, Any]) -> None:
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = QUEUE_PATH.with_name(f"{QUEUE_PATH.name}.{os.getpid()}.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)
    tmp_path.replace(QUEUE_PATH)


def queue_settings(config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or load_config()
    queue_cfg = config.get("queue") or {}
    push_count = max(1, min(10, int(config.get("count", 2))))
    size = int(queue_cfg.get("size", max(push_count * 2, 4)))
    size = max(push_count, min(30, size))
    prepare_before = int(queue_cfg.get("prepare_before_minutes", 120))
    prepare_before = max(15, min(720, prepare_before))
    return {
        "size": size,
        "push_count": push_count,
        "prepare_before_minutes": prepare_before,
        "pre_generate_deep_read": bool(queue_cfg.get("pre_generate_deep_read", True)),
    }


def _item_meta(item: dict[str, Any], zot) -> dict[str, Any]:
    data = item["data"]
    pdf = get_pdf_attachment(zot, item["key"])
    from .digest import format_authors

    return {
        "item_key": item["key"],
        "title": data.get("title", "无标题"),
        "authors": format_authors(data.get("creators", [])),
        "has_pdf": pdf is not None,
        "status": STATUS_PENDING,
        "deep_read": DEEP_PENDING,
        "note_id": None,
        "hub_path": None,
        "briefing": None,
        "error": None,
        "deep_read_error": None,
    }


def refresh_queue(*, force: bool = False) -> dict[str, Any]:
    """随机抽取 queue.size 篇文献，写入固定 item_key 列表。"""
    from .digest import (
        fetch_articles,
        load_history,
        pick_items,
        recently_pushed_keys,
    )

    config = load_config()
    settings = queue_settings(config)
    history = load_history()
    history_days = int(config.get("history_days", 14))
    priority_tag = config.get("priority_tag", "want")
    allowed_types = set(config.get("item_types", ["journalArticle"]))

    excluded = set() if force else recently_pushed_keys(history, history_days)
    zot = connect_zotero()
    articles = fetch_articles(zot, allowed_types)
    picked = pick_items(articles, priority_tag, settings["size"], excluded)

    queue: dict[str, Any] = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "queue_size": settings["size"],
        "push_count": settings["push_count"],
        "items": [_item_meta(item, zot) for item in picked],
    }
    save_queue(queue)
    return queue


def _find_zotero_item(zot, item_key: str) -> dict[str, Any] | None:
    try:
        item = zot.item(item_key)
        if item and item.get("key"):
            return item
    except Exception:
        pass
    return None


def _prepare_deep_read_only(entry: dict[str, Any], config: dict[str, Any]) -> None:
    from .deep_read import generate_deep_read

    pdf_summary_enabled = bool((config.get("pdf_summary") or {}).get("enabled", True))
    if not pdf_summary_enabled or not entry.get("has_pdf") or not entry.get("note_id"):
        entry["deep_read"] = DEEP_SKIPPED
        entry["deep_read_error"] = None
        return
    try:
        generate_deep_read(entry["note_id"])
        entry["deep_read"] = DEEP_READY
        entry["deep_read_error"] = None
    except Exception as exc:
        entry["deep_read"] = DEEP_ERROR
        entry["deep_read_error"] = str(exc)
        print(f"深度解读预生成失败 ({entry['item_key']}): {exc}", file=sys.stderr)


def _apply_existing_summary(
    entry: dict[str, Any],
    existing: NoteEntry,
    *,
    hubs_dir: Path,
    zot,
    pre_deep_read: bool,
    config: dict[str, Any],
) -> bool:
    """若已有简报文件则复用，跳过 LLM。返回是否已复用。"""
    item_key = entry["item_key"]
    item = _find_zotero_item(zot, item_key)
    if not item:
        entry["status"] = STATUS_ERROR
        entry["error"] = "Zotero 条目不存在或已删除"
        return True

    data = item["data"]
    entry["title"] = data.get("title", entry.get("title") or "无标题")
    from .digest import format_authors

    entry["authors"] = format_authors(data.get("creators", []))
    entry["has_pdf"] = get_pdf_attachment(zot, item_key) is not None

    hub_path = ensure_hub_path(existing.id, hubs_dir, existing.hub_path)
    entry["status"] = STATUS_READY
    entry["note_id"] = existing.id
    entry["hub_path"] = str(hub_path)
    entry["briefing"] = existing.briefing or entry["title"]
    entry["error"] = None

    if pre_deep_read:
        _prepare_deep_read_only(entry, config)
    else:
        entry["deep_read"] = DEEP_SKIPPED
        entry["deep_read_error"] = None

    print(f"复用已有简报: {entry['title']} ({existing.id})")
    return True


def _prepare_one(
    entry: dict[str, Any],
    *,
    zot,
    client: OpenAI | None,
    config: dict[str, Any],
    summaries_dir: Path,
    hubs_dir: Path,
    skip_llm: bool,
    pre_deep_read: bool,
    existing: NoteEntry | None = None,
) -> None:
    from .digest import generate_full_summary, metadata_only_summary, metadata_summary

    item_key = entry["item_key"]
    if existing:
        _apply_existing_summary(
            entry,
            existing,
            hubs_dir=hubs_dir,
            zot=zot,
            pre_deep_read=pre_deep_read,
            config=config,
        )
        return

    item = _find_zotero_item(zot, item_key)
    if not item:
        entry["status"] = STATUS_ERROR
        entry["error"] = "Zotero 条目不存在或已删除"
        return

    data = item["data"]
    entry["title"] = data.get("title", entry.get("title") or "无标题")
    from .digest import format_authors

    entry["authors"] = format_authors(data.get("creators", []))

    pdf = get_pdf_attachment(zot, item_key)
    pdf_key = pdf["key"] if pdf else None
    entry["has_pdf"] = pdf is not None

    if skip_llm or client is None:
        summary = metadata_only_summary(item)
    else:
        try:
            summary = generate_full_summary(client, item, config)
        except Exception as exc:
            print(f"DeepSeek 简报生成失败 ({item_key}): {exc}", file=sys.stderr)
            summary = metadata_only_summary(item)

    briefing = re.sub(
        r"\s+",
        " ",
        (summary.get("briefing") or metadata_summary(item)).strip(),
    )
    sections = summary.get("sections") or []
    terms = clean_terms(summary.get("key_terms") or [])

    md_path, hub_path = write_outputs(
        summaries_dir,
        hubs_dir,
        item,
        briefing,
        sections,
        terms,
        pdf_key,
    )
    mark_pending(md_path.stem)

    entry["status"] = STATUS_READY
    entry["note_id"] = md_path.stem
    entry["hub_path"] = str(hub_path)
    entry["briefing"] = briefing
    entry["error"] = None

    if pre_deep_read:
        _prepare_deep_read_only(entry, config)
    else:
        entry["deep_read"] = DEEP_SKIPPED
        entry["deep_read_error"] = None


def prepare_queue(
    *,
    skip_llm: bool = False,
    limit: int | None = None,
) -> tuple[dict[str, Any], int]:
    """为待推清单前 push_count 篇预生成简报与深度解读。"""
    from .digest import ENV_PATH, load_dotenv

    load_dotenv(ENV_PATH)
    config = load_config()
    settings = queue_settings(config)
    queue = load_queue()
    if not queue or not queue.get("items"):
        queue = refresh_queue()

    summaries_dir, hubs_dir = resolve_output_dirs(config)
    push_count = limit if limit is not None else settings["push_count"]
    push_count = max(1, min(len(queue["items"]), push_count))

    client = None
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not skip_llm:
        if not api_key:
            print("警告: 未设置 DEEPSEEK_API_KEY，将使用纯元数据", file=sys.stderr)
            skip_llm = True
        else:
            ds = config.get("deepseek", {})
            client = OpenAI(api_key=api_key, base_url=ds.get("base_url", "https://api.deepseek.com"))

    zot = connect_zotero()
    existing_by_key = latest_notes_by_item_key()
    prepared = 0
    for entry in _entries_in_push_window(queue["items"], push_count):
        if entry.get("status") == STATUS_READY and entry.get("note_id") and _hub_file_exists(entry):
            if entry.get("deep_read") in (DEEP_READY, DEEP_SKIPPED):
                continue
            if settings["pre_generate_deep_read"] and entry.get("has_pdf"):
                _prepare_deep_read_only(entry, config)
                prepared += 1
            continue
        _prepare_one(
            entry,
            zot=zot,
            client=client,
            config=config,
            summaries_dir=summaries_dir,
            hubs_dir=hubs_dir,
            skip_llm=skip_llm,
            pre_deep_read=settings["pre_generate_deep_read"],
            existing=existing_by_key.get(entry["item_key"]),
        )
        prepared += 1

    queue["prepared_at"] = datetime.now().isoformat(timespec="seconds")
    save_queue(queue)
    if prepared:
        print(f"预生成完成，本次处理 {prepared} 篇")
    else:
        print("预生成完成，本次无需处理（推送位已就绪或清单为空）")
    return queue, prepared


def push_from_queue(
    *,
    dry_run: bool = False,
    no_notify: bool = False,
    force_prepare: bool = True,
) -> int:
    """从待推清单推送前 push_count 篇已就绪笔记。"""
    from .digest import emit_notification, load_history, record_pushed
    from .push_finalize import apply_push_action

    config = load_config()
    settings = queue_settings(config)
    queue = load_queue()

    if not queue or not queue.get("items"):
        print("待推清单为空，请先刷新清单并预生成", file=sys.stderr)
        return 1

    if force_prepare:
        push_window = _entries_in_push_window(queue["items"], settings["push_count"])
        ready_count = sum(
            1
            for e in push_window
            if e.get("status") == STATUS_READY and _hub_file_exists(e)
        )
        if ready_count < len(push_window):
            queue, _ = prepare_queue()
        else:
            reloaded = load_queue()
            if reloaded:
                queue = reloaded

    if not queue or not queue.get("items"):
        print("待推清单读取失败，请重新生成待推清单后再推送", file=sys.stderr)
        return 1

    candidates: list[dict[str, Any]] = []
    for entry in queue["items"]:
        if len(candidates) >= settings["push_count"]:
            break
        if entry.get("status") != STATUS_READY or not _hub_file_exists(entry):
            continue
        candidates.append(entry)

    if not candidates:
        print("没有可推送的就绪条目（请先预生成）", file=sys.stderr)
        return 1

    if settings["pre_generate_deep_read"]:
        for entry in candidates:
            if (
                entry.get("has_pdf")
                and entry.get("note_id")
                and entry.get("deep_read", DEEP_PENDING) == DEEP_PENDING
            ):
                _prepare_deep_read_only(entry, config)
        save_queue(queue)

    history = load_history()
    picked_keys: list[str] = []
    total = len(candidates)

    for idx, entry in enumerate(candidates, start=1):
        title = entry.get("title") or "无标题"
        hub_path = Path(entry["hub_path"])
        briefing = entry.get("briefing") or title
        subtitle = (entry.get("authors") or "")[:80]
        note_id = entry.get("note_id") or hub_path.stem
        item_key = entry.get("item_key")

        notify_title = f"📚 今日文献 ({idx}/{total})"
        action = emit_notification(
            title=notify_title,
            subtitle=title[:80] + ("…" if len(title) > 80 else ""),
            message=briefing,
            hub_path=hub_path,
            note_id=note_id,
            item_key=item_key,
            dry_run=dry_run,
            no_notify=no_notify,
        )
        if dry_run:
            entry["status"] = STATUS_PUSHED
            if item_key:
                picked_keys.append(item_key)
            print(f"已推送: {title}")
        elif no_notify:
            print(f"待确认: {title}")
        elif apply_push_action(
            item_key=item_key,
            note_id=note_id,
            action=action,
            update_queue=False,
        ):
            entry["status"] = STATUS_PUSHED
            if item_key:
                picked_keys.append(item_key)
            print(f"已推送: {title}")
        else:
            print(f"已推迟至下次推送: {title}（本地缓存已保留）")
        print(f"  中转页:   {hub_path}")

    if not dry_run and not no_notify:
        record_pushed(history, picked_keys)
        save_queue(queue)
    elif not dry_run and no_notify:
        save_queue(queue)

    return 0


def queue_summary_for_ui() -> dict[str, Any]:
    """供控制台展示的清单摘要。"""
    config = load_config()
    settings = queue_settings(config)
    queue = load_queue()
    if not queue:
        return {
            "exists": False,
            "settings": settings,
            "items": [],
            "ready_count": 0,
            "push_ready_count": 0,
        }

    items = queue.get("items") or []
    ready = [e for e in items if e.get("status") == STATUS_READY]
    push_window = _entries_in_push_window(items, settings["push_count"])
    push_ready = [
        e
        for e in push_window
        if e.get("status") == STATUS_READY and _hub_file_exists(e)
    ]

    return {
        "exists": True,
        "created_at": queue.get("created_at"),
        "prepared_at": queue.get("prepared_at"),
        "queue_size": queue.get("queue_size", len(items)),
        "push_count": queue.get("push_count", settings["push_count"]),
        "settings": settings,
        "items": items,
        "ready_count": len(ready),
        "push_ready_count": len(push_ready),
    }
