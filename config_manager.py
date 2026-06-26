"""配置读写与路径解析。"""

from __future__ import annotations

import copy
import os
import sys
from pathlib import Path
from typing import Any

import yaml

def _resource_dir() -> Path:
    pyinstaller_dir = getattr(sys, "_MEIPASS", None)
    if pyinstaller_dir:
        return Path(pyinstaller_dir)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


SCRIPT_DIR = _resource_dir()
APP_DIR_NAME = "Zotero Daily News"


def user_config_dir() -> Path:
    override = os.environ.get("ZOTERO_DAILY_NEWS_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming"
        return Path(base) / APP_DIR_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "zotero-daily-news"


def runtime_dir() -> Path:
    override = os.environ.get("ZOTERO_DAILY_NEWS_RUNTIME_DIR")
    if override:
        root = Path(override).expanduser()
    elif sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
        root = Path(base) / APP_DIR_NAME
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    else:
        root = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "zotero-daily-news"
    root.mkdir(parents=True, exist_ok=True)
    return root


def runtime_path(name: str) -> Path:
    return runtime_dir() / name


def logs_dir() -> Path:
    path = runtime_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


CONFIG_PATH = user_config_dir() / "config.yaml"
LEGACY_CONFIG_PATH = SCRIPT_DIR / "config.yaml"
ENV_PATH = user_config_dir() / ".env"

DEFAULT_PROMPT = """你是学术阅读助手。根据文献元数据，生成中文阅读简报。

请严格输出 JSON（不要其他文字）：
{{
  "briefing": "60-100字头条简报，一句话概括核心贡献",
  "sections": [
    {{"heading": "核心贡献", "body": "2-4句"}},
    {{"heading": "方法亮点", "body": "2-4句"}},
    {{"heading": "为何值得读", "body": "1-3句"}}
  ],
  "key_terms": ["专有名词1[English]", "专有名词2[English]", "专有名词3[English]"]
}}

要求：
- key_terms 提取 3-5 个论文中的专有名词/方法名/数据集名，采用「中文[原文]」中英文对照形式
- 不要编造具体实验数字；无摘要时保守表述
- 全部使用中文

文献信息：
{context}"""

_PDF_PROMPT_PATH = SCRIPT_DIR / "prompts" / "pdf_summary_prompt.txt"
PDF_PROMPT_INPUT_MARKER = "\n# 输入\n"


def _load_default_pdf_prompt() -> str:
    if _PDF_PROMPT_PATH.is_file():
        return _PDF_PROMPT_PATH.read_text(encoding="utf-8").strip() + "\n"
    return (
        "你是学术阅读助手。请根据文献元数据与 PDF 正文，生成深度中文解读。\n\n"
        "请严格输出 JSON（不要其他文字）：\n"
        '{{\n  "sections": [...],\n  "key_terms": ["专有名词1[English]"]\n}}\n\n'
        f"{PDF_PROMPT_INPUT_MARKER.strip()}\n"
        "文献元数据：\n{context}\n\nPDF 正文（来源：{pdf_source}）：\n{pdf_text}\n"
    )


DEFAULT_PDF_PROMPT = _load_default_pdf_prompt()

DEFAULT_CONFIG: dict[str, Any] = {
    "priority_tag": "want",
    "count": 2,
    "history_days": 14,
    "item_types": ["journalArticle", "conferencePaper", "preprint", "report"],
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "briefing_model": "deepseek-v4-flash",
        "deep_read_model": "deepseek-v4-pro",
    },
    "language": "zh",
    "output": {
        "summaries_dir": "summaries",
        "hubs_dir": "hubs",
    },
    "schedule": [
        {"hour": 10, "minute": 0},
        {"hour": 18, "minute": 0},
    ],
    "summary_prompt": DEFAULT_PROMPT,
    "pdf_summary": {
        "enabled": True,
        "max_chars": 80000,
    },
    "pdf_summary_prompt": DEFAULT_PDF_PROMPT,
    "queue": {
        "size": 4,
        "prepare_before_minutes": 120,
        "pre_generate_deep_read": True,
    },
    "ui": {"port": 18765},
}


def load_config() -> dict[str, Any]:
    path = CONFIG_PATH if CONFIG_PATH.exists() else LEGACY_CONFIG_PATH
    if not path.exists():
        return copy.deepcopy(DEFAULT_CONFIG)
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    merged = copy.deepcopy(DEFAULT_CONFIG)
    merged.update({k: v for k, v in data.items() if v is not None})
    if "output" in data:
        merged["output"] = {**DEFAULT_CONFIG["output"], **(data.get("output") or {})}
    if "deepseek" in data:
        merged["deepseek"] = {**DEFAULT_CONFIG["deepseek"], **(data.get("deepseek") or {})}
    if "pdf_summary" in data:
        merged["pdf_summary"] = {**DEFAULT_CONFIG["pdf_summary"], **(data.get("pdf_summary") or {})}
    if "queue" in data:
        merged["queue"] = {**DEFAULT_CONFIG["queue"], **(data.get("queue") or {})}
    if "schedule" not in merged or not merged["schedule"]:
        merged["schedule"] = DEFAULT_CONFIG["schedule"]
    if not merged.get("summary_prompt"):
        merged["summary_prompt"] = DEFAULT_PROMPT
    if not merged.get("pdf_summary_prompt"):
        merged["pdf_summary_prompt"] = DEFAULT_PDF_PROMPT
    return merged


def save_config(config: dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False, default_flow_style=False)


def resolve_output_dirs(config: dict[str, Any]) -> tuple[Path, Path]:
    output = config.get("output") or {}
    summaries_raw = output.get("summaries_dir", "summaries")
    hubs_raw = output.get("hubs_dir", "hubs")

    def _resolve(raw: str) -> Path:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = runtime_dir() / path
        path.mkdir(parents=True, exist_ok=True)
        return path.resolve()

    return _resolve(summaries_raw), _resolve(hubs_raw)


def build_summary_prompt(config: dict[str, Any], context: str) -> str:
    template = config.get("summary_prompt") or DEFAULT_PROMPT
    return template.replace("{context}", context)


def _fill_pdf_summary_template(
    template: str,
    context: str,
    pdf_text: str,
    pdf_source: str,
) -> str:
    return (
        template.replace("{context}", context)
        .replace("{pdf_text}", pdf_text)
        .replace("{pdf_source}", pdf_source)
    )


def build_pdf_summary_prompt(
    config: dict[str, Any],
    context: str,
    pdf_text: str,
    pdf_source: str,
) -> str:
    template = config.get("pdf_summary_prompt") or DEFAULT_PDF_PROMPT
    return _fill_pdf_summary_template(template, context, pdf_text, pdf_source)


def build_pdf_summary_messages(
    config: dict[str, Any],
    context: str,
    pdf_text: str,
    pdf_source: str,
) -> list[dict[str, str]]:
    filled = build_pdf_summary_prompt(config, context, pdf_text, pdf_source)
    marker = PDF_PROMPT_INPUT_MARKER
    if marker in filled:
        system, user = filled.split(marker, 1)
        return [
            {"role": "system", "content": system.strip()},
            {"role": "user", "content": (marker.strip() + user).strip()},
        ]
    return [{"role": "user", "content": filled}]


def deepseek_briefing_model(config: dict[str, Any]) -> str:
    ds = config.get("deepseek") or {}
    return str(ds.get("briefing_model") or ds.get("model") or "deepseek-v4-flash").strip()


def deepseek_deep_read_model(config: dict[str, Any]) -> str:
    ds = config.get("deepseek") or {}
    return str(ds.get("deep_read_model") or ds.get("model") or "deepseek-v4-pro").strip()
