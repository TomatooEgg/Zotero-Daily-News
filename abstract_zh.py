"""按需生成摘要中文翻译。"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from openai import OpenAI

from config_manager import deepseek_briefing_model, load_config, SCRIPT_DIR
from digest import load_dotenv
from net_env import connect_zotero
from md_render import normalize_plaintext
from notes_index import get_note
from summary_io import build_hub_html

ENV_PATH = SCRIPT_DIR / ".env"
ZH_START = "<!-- zh-abstract -->"
ZH_END = "<!-- /zh-abstract -->"


def has_abstract_zh(md_text: str) -> bool:
    return ZH_START in md_text and ZH_END in md_text


def extract_abstract_zh(md_text: str) -> str | None:
    pattern = re.compile(
        re.escape(ZH_START) + r"\s*(.*?)\s*" + re.escape(ZH_END),
        re.DOTALL,
    )
    match = pattern.search(md_text)
    return match.group(1).strip() if match else None


def strip_abstract_zh_md(md_text: str) -> str:
    pattern = re.compile(r"\n?" + re.escape(ZH_START) + r".*?" + re.escape(ZH_END), re.DOTALL)
    return pattern.sub("", md_text)


def extract_original_abstract(md_text: str) -> str | None:
    match = re.search(r"## 摘要\s*\n\n(.*?)(?:\n## |\n<!-- zh-abstract -->|\Z)", md_text, re.DOTALL)
    if not match:
        return None
    text = normalize_plaintext(match.group(1).strip())
    return text or None


def is_mostly_chinese(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return False
    cjk = len(re.findall(r"[\u4e00-\u9fff]", compact))
    return cjk / len(compact) >= 0.3


def insert_abstract_zh(md_text: str, translation: str) -> str:
    base = strip_abstract_zh_md(md_text)
    block = f"\n\n{ZH_START}\n{translation.strip()}\n{ZH_END}"
    match = re.search(r"(## 摘要\s*\n\n)(.*?)(\n## )", base, re.DOTALL)
    if match:
        end = match.end(2)
        return base[:end] + block + base[match.start(3) :]
    if "## 摘要" in base:
        idx = base.find("## 摘要")
        next_h2 = base.find("\n## ", idx + 4)
        if next_h2 == -1:
            return base.rstrip() + block + "\n"
        return base[:next_h2] + block + base[next_h2:]
    return base.rstrip() + block + "\n"


def translate_abstract(client: OpenAI, abstract: str, config: dict) -> str:
    if is_mostly_chinese(abstract):
        return abstract.strip()

    model = deepseek_briefing_model(config)
    prompt = (
        "你是学术翻译助手。将以下文献摘要翻译为流畅、准确的中文。\n"
        "要求：只输出译文，不要标题、不要解释、不要 JSON。\n\n"
        f"摘要原文：\n{abstract}"
    )
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=2000,
    )
    text = (response.choices[0].message.content or "").strip()
    if not text:
        raise RuntimeError("翻译结果为空")
    return text


def generate_abstract_zh(note_id: str) -> dict[str, Any]:
    entry = get_note(note_id)
    if not entry:
        raise ValueError("笔记不存在")

    md_path = Path(entry.md_path)
    md_text = md_path.read_text(encoding="utf-8")

    abstract = extract_original_abstract(md_text)
    if not abstract:
        zot = connect_zotero()
        item = zot.item(entry.item_key)
        abstract = (item.get("data", {}).get("abstractNote") or "").strip()

    if not abstract:
        raise RuntimeError("该文献没有摘要")

    cached = extract_abstract_zh(md_text)
    if cached:
        return {"cached": True, "text": cached, "original": abstract}

    if is_mostly_chinese(abstract):
        translation = abstract.strip()
    else:
        load_dotenv(ENV_PATH)
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            raise RuntimeError("未设置 DEEPSEEK_API_KEY")
        config = load_config()
        ds = config.get("deepseek", {})
        client = OpenAI(api_key=api_key, base_url=ds.get("base_url", "https://api.deepseek.com"))
        translation = translate_abstract(client, abstract, config)

    updated_md = insert_abstract_zh(md_text, translation)
    md_path.write_text(updated_md, encoding="utf-8")
    if entry.hub_path:
        Path(entry.hub_path).write_text(build_hub_html(note_id), encoding="utf-8")

    return {"cached": False, "text": translation, "original": abstract}
