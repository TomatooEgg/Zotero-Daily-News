"""配置读写与路径解析。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "config.yaml"

DEFAULT_PROMPT = """你是学术阅读助手。根据文献元数据，生成中文阅读简报。

请严格输出 JSON（不要其他文字）：
{{
  "briefing": "60-100字头条简报，一句话概括核心贡献",
  "sections": [
    {{"heading": "核心贡献", "body": "2-4句"}},
    {{"heading": "方法亮点", "body": "2-4句"}},
    {{"heading": "为何值得读", "body": "1-3句"}}
  ],
  "key_terms": ["专有名词1", "专有名词2", "专有名词3"]
}}

要求：
- key_terms 提取 3-5 个论文中的专有名词/方法名/数据集名，便于后续在 PDF 中定位
- 不要编造具体实验数字；无摘要时保守表述
- 全部使用中文

文献信息：
{context}"""

DEFAULT_CONFIG: dict[str, Any] = {
    "priority_tag": "want",
    "count": 2,
    "history_days": 14,
    "item_types": ["journalArticle", "conferencePaper", "preprint", "report"],
    "deepseek": {"base_url": "https://api.deepseek.com", "model": "deepseek-chat"},
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
    "ui": {"port": 18765},
}


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return dict(DEFAULT_CONFIG)
    with CONFIG_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    merged = dict(DEFAULT_CONFIG)
    merged.update({k: v for k, v in data.items() if v is not None})
    if "output" in data:
        merged["output"] = {**DEFAULT_CONFIG["output"], **(data.get("output") or {})}
    if "deepseek" in data:
        merged["deepseek"] = {**DEFAULT_CONFIG["deepseek"], **(data.get("deepseek") or {})}
    if "schedule" not in merged or not merged["schedule"]:
        merged["schedule"] = DEFAULT_CONFIG["schedule"]
    if not merged.get("summary_prompt"):
        merged["summary_prompt"] = DEFAULT_PROMPT
    return merged


def save_config(config: dict[str, Any]) -> None:
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False, default_flow_style=False)


def resolve_output_dirs(config: dict[str, Any]) -> tuple[Path, Path]:
    output = config.get("output") or {}
    summaries_raw = output.get("summaries_dir", "summaries")
    hubs_raw = output.get("hubs_dir", "hubs")

    def _resolve(raw: str) -> Path:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = SCRIPT_DIR / path
        path.mkdir(parents=True, exist_ok=True)
        return path.resolve()

    return _resolve(summaries_raw), _resolve(hubs_raw)


def build_summary_prompt(config: dict[str, Any], context: str) -> str:
    template = config.get("summary_prompt") or DEFAULT_PROMPT
    return template.replace("{context}", context)
