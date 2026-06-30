#!/usr/bin/env python3
"""从 Zotero 随机抽取文献，生成中文头条简报并推送 macOS 通知。"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

from openai import OpenAI

from .config_manager import (
    ENV_PATH,
    SCRIPT_DIR,
    build_summary_prompt,
    deepseek_briefing_model,
    load_config,
    resolve_output_dirs,
    runtime_path,
)
from .env_store import parse_env_file
from .net_env import connect_zotero
from .notifier import diagnose as notify_diagnose
from .notifier import emit_notify_payload, notify_macos, SUMMARY_ACTION
from .notes_index import find_note_by_item_key
from .pending_publish import mark_pending
from .summary_io import clean_terms, ensure_hub_path, parse_llm_summary, write_outputs
from .zotero_links import get_pdf_attachment

HISTORY_PATH = runtime_path("history.json")
def load_dotenv(path: Path) -> None:
    for key, value in parse_env_file(path).items():
        os.environ[key] = value


def load_history() -> dict:
    if not HISTORY_PATH.exists():
        return {"items": {}}
    with HISTORY_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def save_history(history: dict) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_PATH.open("w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def recently_pushed_keys(history: dict, days: int) -> set[str]:
    cutoff = datetime.now() - timedelta(days=days)
    keys: set[str] = set()
    for key, ts in history.get("items", {}).items():
        try:
            if datetime.fromisoformat(ts) >= cutoff:
                keys.add(key)
        except ValueError:
            continue
    return keys


def record_pushed(history: dict, keys: list[str]) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    history.setdefault("items", {})
    for key in keys:
        history["items"][key] = now
    save_history(history)


def item_has_tag(item: dict, tag: str) -> bool:
    tags = item.get("data", {}).get("tags", [])
    return any(t.get("tag") == tag for t in tags)


def is_article(item: dict, allowed_types: set[str]) -> bool:
    data = item.get("data", {})
    if data.get("itemType") not in allowed_types:
        return False
    title = (data.get("title") or "").strip()
    return bool(title)


def fetch_articles(zot: zotero.Zotero, allowed_types: set[str]) -> list[dict]:
    try:
        raw = zot.everything(zot.items(itemType="-attachment"))
    except Exception as exc:
        raise RuntimeError(
            "无法连接 Zotero 本地 API。请确认 Zotero 已启动，"
            "并在 设置 → 高级 中开启「Allow other applications...」"
        ) from exc
    return [item for item in raw if is_article(item, allowed_types)]


def pick_items(
    articles: list[dict],
    priority_tag: str,
    count: int,
    excluded_keys: set[str],
) -> list[dict]:
    available = [a for a in articles if a["key"] not in excluded_keys]
    if not available:
        return []

    tagged = [a for a in available if item_has_tag(a, priority_tag)]
    others = [a for a in available if not item_has_tag(a, priority_tag)]

    random.shuffle(tagged)
    random.shuffle(others)

    pool = tagged + others
    return pool[: min(count, len(pool))]


def format_authors(creators: list[dict]) -> str:
    names: list[str] = []
    for creator in creators:
        if creator.get("creatorType") != "author":
            continue
        last = creator.get("lastName", "")
        first = creator.get("firstName", "")
        if last and first:
            names.append(f"{last} {first}".strip())
        else:
            names.append(last or first or "未知作者")
    if not names:
        return "未知作者"
    if len(names) <= 3:
        return "、".join(names)
    return "、".join(names[:3]) + " 等"


def metadata_summary(item: dict) -> str:
    data = item["data"]
    title = data.get("title", "无标题")
    authors = format_authors(data.get("creators", []))
    journal = data.get("publicationTitle") or data.get("proceedingsTitle") or ""
    year = data.get("date", "")[:4] if data.get("date") else ""
    bits = [title]
    if authors:
        bits.append(authors)
    if journal:
        bits.append(journal)
    if year:
        bits.append(year)
    return " · ".join(bits)


def build_llm_context(item: dict) -> str:
    data = item["data"]
    title = data.get("title", "")
    authors = format_authors(data.get("creators", []))
    abstract = (data.get("abstractNote") or "").strip()
    journal = data.get("publicationTitle") or data.get("proceedingsTitle") or "未知来源"
    year = data.get("date", "")[:4] if data.get("date") else "未知年份"
    tags = [t.get("tag", "") for t in data.get("tags", []) if t.get("tag")]
    return f"""标题：{title}
作者：{authors}
出处：{journal} ({year})
标签：{", ".join(tags) if tags else "无"}
摘要：{abstract if abstract else "（无摘要）"}"""


def generate_full_summary(client: OpenAI, item: dict, config: dict) -> dict:
    context = build_llm_context(item)
    prompt = build_summary_prompt(config, context)
    model = deepseek_briefing_model(config)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=1200,
        response_format={"type": "json_object"},
    )
    raw = (response.choices[0].message.content or "").strip()
    return parse_llm_summary(raw)


def metadata_only_summary(item: dict) -> dict:
    return {
        "briefing": metadata_summary(item),
        "sections": [{"heading": "文献信息", "body": metadata_summary(item)}],
        "key_terms": [],
    }


def emit_notification(
    title: str,
    message: str,
    subtitle: str = "",
    hub_path: Path | None = None,
    *,
    note_id: str | None = None,
    item_key: str | None = None,
    dry_run: bool = False,
    no_notify: bool = False,
) -> str | None:
    if dry_run:
        notify_macos(
            title=title,
            message=message,
            subtitle=subtitle,
            hub_path=hub_path,
            dry_run=True,
        )
        return SUMMARY_ACTION
    if no_notify:
        print(
            emit_notify_payload(
                title=title,
                message=message,
                subtitle=subtitle,
                hub_path=hub_path,
                note_id=note_id,
                item_key=item_key,
            )
        )
        return None
    _ok, action = notify_macos(
        title=title,
        message=message,
        subtitle=subtitle,
        hub_path=hub_path,
        note_id=note_id or (hub_path.stem if hub_path else None),
    )
    return action


def _record_if_published(
    *,
    item_key: str,
    note_id: str,
    action: str | None,
    dry_run: bool,
    no_notify: bool,
    picked_keys: list[str],
) -> None:
    if dry_run:
        picked_keys.append(item_key)
        return
    if no_notify:
        return
    from .push_finalize import apply_push_action

    if apply_push_action(
        item_key=item_key,
        note_id=note_id,
        action=action,
        update_queue=False,
    ):
        picked_keys.append(item_key)
    else:
        print(f"已推迟至下次推送: {item_key}（本地缓存已保留）")


def run(
    dry_run: bool = False,
    skip_llm: bool = False,
    force: bool = False,
    no_notify: bool = False,
) -> int:
    load_dotenv(ENV_PATH)
    config = load_config()
    history = load_history()
    summaries_dir, hubs_dir = resolve_output_dirs(config)

    priority_tag = config.get("priority_tag", "want")
    count = int(config.get("count", 2))
    history_days = int(config.get("history_days", 14))
    allowed_types = set(config.get("item_types", ["journalArticle"]))

    excluded = set() if force else recently_pushed_keys(history, history_days)
    zot = connect_zotero()
    articles = fetch_articles(zot, allowed_types)
    picked = pick_items(articles, priority_tag, count, excluded)

    if not picked:
        msg = "没有可推送的文献（可能已全部在近期推送过，或库中无匹配条目）"
        print(msg)
        if not dry_run:
            emit_notification("📚 Zotero 简报", msg, no_notify=no_notify)
        return 0

    client = None
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not skip_llm:
        if not api_key:
            print("警告: 未设置 DEEPSEEK_API_KEY，将使用纯元数据", file=sys.stderr)
            skip_llm = True
        else:
            ds = config.get("deepseek", {})
            client = OpenAI(api_key=api_key, base_url=ds.get("base_url", "https://api.deepseek.com"))

    picked_keys: list[str] = []
    total = len(picked)

    for idx, item in enumerate(picked, start=1):
        data = item["data"]
        title = data.get("title", "无标题")
        subtitle = format_authors(data.get("creators", []))
        item_key = item["key"]

        existing = find_note_by_item_key(item_key)
        if existing:
            hub_path = ensure_hub_path(existing.id, hubs_dir, existing.hub_path)
            briefing = re.sub(
                r"\s+",
                " ",
                (existing.briefing or metadata_summary(item)).strip(),
            )
            notify_title = f"📚 今日文献 ({idx}/{total})"
            action = emit_notification(
                title=notify_title,
                subtitle=title[:80] + ("…" if len(title) > 80 else ""),
                message=briefing,
                hub_path=hub_path,
                note_id=existing.id,
                item_key=item_key,
                dry_run=dry_run,
                no_notify=no_notify,
            )
            _record_if_published(
                item_key=item_key,
                note_id=existing.id,
                action=action,
                dry_run=dry_run,
                no_notify=no_notify,
                picked_keys=picked_keys,
            )
            print(f"已推送（复用已有简报）: {title}")
            print(f"  详细总结: {existing.md_path}")
            print(f"  中转页:   {hub_path}")
            continue

        pdf = get_pdf_attachment(zot, item_key)
        pdf_key = pdf["key"] if pdf else None

        if skip_llm or client is None:
            summary = metadata_only_summary(item)
        else:
            try:
                summary = generate_full_summary(client, item, config)
            except Exception as exc:
                print(f"DeepSeek 生成失败 ({item['key']}): {exc}", file=sys.stderr)
                summary = metadata_only_summary(item)

        briefing = re.sub(r"\s+", " ", (summary.get("briefing") or metadata_summary(item)).strip())
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
        note_id = md_path.stem
        mark_pending(note_id)

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
        _record_if_published(
            item_key=item_key,
            note_id=note_id,
            action=action,
            dry_run=dry_run,
            no_notify=no_notify,
            picked_keys=picked_keys,
        )
        print(f"已推送: {title}")
        print(f"  详细总结: {md_path}")
        print(f"  中转页:   {hub_path}")

    if not dry_run and not no_notify:
        record_pushed(history, picked_keys)

    return 0


def test_notification(verbose: bool = False) -> int:
    from .seed_test_note import ensure_test_note

    sample = ensure_test_note()
    ok, _action = notify_macos(
        title=sample["notify_title"],
        subtitle=sample["subtitle"],
        message=sample["briefing"],
        hub_path=sample["hub_path"],
        note_id=sample["note_id"],
        verbose=verbose,
    )
    if ok:
        print("示例推送已发送（请查看屏幕右上角通知中心）")
        print(f"  笔记: {sample['title']}")
        print(f"  Hub:  {sample['hub_path']}")
    else:
        print("示例推送失败 — 已播放提示音并尝试打开测试页，请查看上方说明")
    return 0 if ok else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Zotero 文献头条简报")
    parser.add_argument("--dry-run", action="store_true", help="只打印，不发通知、不写历史")
    parser.add_argument("--metadata-only", action="store_true", help="跳过 DeepSeek，仅用元数据")
    parser.add_argument("--force", action="store_true", help="忽略去重历史，强制推送")
    parser.add_argument("--test-notify", action="store_true", help="发送测试通知")
    parser.add_argument("--verbose-notify", action="store_true", help="通知诊断详情")
    parser.add_argument("--diagnose-notify", action="store_true", help="运行通知通道诊断")
    parser.add_argument(
        "--no-notify",
        action="store_true",
        help="不发送通知，改为向 stdout 输出 @@NOTIFY@@ 行供父进程处理",
    )
    parser.add_argument(
        "--refresh-queue",
        action="store_true",
        help="随机刷新待推清单（固定 item_key 列表）",
    )
    parser.add_argument(
        "--prepare-queue",
        action="store_true",
        help="为待推清单前 count 篇预生成简报与深度解读",
    )
    parser.add_argument(
        "--push-queue",
        action="store_true",
        help="从待推清单推送（定时任务默认使用）",
    )
    args = parser.parse_args()

    try:
        if args.diagnose_notify:
            notify_diagnose()
            sys.exit(0)
        if args.test_notify:
            sys.exit(test_notification(verbose=args.verbose_notify))
        if args.prepare_queue:
            from .queue_manager import load_queue, prepare_queue, refresh_queue

            if args.refresh_queue or args.force or not load_queue():
                refresh_queue(force=args.force)
            prepare_queue(skip_llm=args.metadata_only)
            sys.exit(0)
        if args.refresh_queue:
            from .queue_manager import refresh_queue

            refresh_queue(force=args.force)
            print("待推清单已刷新")
            sys.exit(0)
        if args.push_queue:
            from .queue_manager import load_queue, prepare_queue, push_from_queue, refresh_queue

            if args.force:
                sys.exit(
                    run(
                        dry_run=args.dry_run,
                        skip_llm=args.metadata_only,
                        force=True,
                        no_notify=args.no_notify,
                    )
                )
            if not load_queue():
                refresh_queue()
                prepare_queue(skip_llm=args.metadata_only)
            sys.exit(
                push_from_queue(
                    dry_run=args.dry_run,
                    no_notify=args.no_notify,
                    force_prepare=True,
                )
            )
        sys.exit(
            run(
                dry_run=args.dry_run,
                skip_llm=args.metadata_only,
                force=args.force,
                no_notify=args.no_notify,
            )
        )
    except RuntimeError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
