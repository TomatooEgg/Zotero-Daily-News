"""Zotero Web API 凭证读写（存于 .env）。"""

from __future__ import annotations

import os
import re
from pathlib import Path

import httpx

from config_manager import SCRIPT_DIR

ENV_PATH = SCRIPT_DIR / ".env"
ENV_KEYS = ("ZOTERO_API_KEY", "ZOTERO_LIBRARY_ID")


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def _apply_dotenv() -> None:
    for key, value in _parse_env_file(ENV_PATH).items():
        os.environ.setdefault(key, value)


def mask_api_key(key: str) -> str:
    key = key.strip()
    if len(key) <= 8:
        return "••••"
    return f"{key[:4]}…{key[-4:]}"


def get_zotero_credentials() -> dict[str, str]:
    _apply_dotenv()
    return {
        "api_key": (os.environ.get("ZOTERO_API_KEY") or "").strip(),
        "library_id": (os.environ.get("ZOTERO_LIBRARY_ID") or "").strip(),
    }


def is_zotero_configured() -> bool:
    return bool(get_zotero_credentials()["api_key"])


def zotero_config_for_ui() -> dict:
    creds = get_zotero_credentials()
    api_key = creds["api_key"]
    return {
        "configured": bool(api_key),
        "api_key_masked": mask_api_key(api_key) if api_key else "",
        "library_id": creds["library_id"],
    }


def _set_env_line(lines: list[str], key: str, value: str | None) -> list[str]:
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
    out: list[str] = []
    found = False
    for line in lines:
        if pattern.match(line):
            found = True
            if value:
                out.append(f"{key}={value}")
            continue
        out.append(line)
    if not found and value:
        out.append(f"{key}={value}")
    return out


def save_zotero_credentials(
    *,
    api_key: str | None = None,
    library_id: str | None = None,
    keep_api_key_if_empty: bool = True,
) -> dict[str, str]:
    """保存凭证到 .env。api_key 留空且 keep_api_key_if_empty 时保留原 Key。"""
    current = get_zotero_credentials()
    new_key = (api_key or "").strip()
    if not new_key and keep_api_key_if_empty:
        new_key = current["api_key"]

    new_lib = current["library_id"] if library_id is None else str(library_id).strip()

    lines: list[str] = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    elif not ENV_PATH.parent.exists():
        ENV_PATH.parent.mkdir(parents=True, exist_ok=True)

    lines = _set_env_line(lines, "ZOTERO_API_KEY", new_key or None)
    lines = _set_env_line(lines, "ZOTERO_LIBRARY_ID", new_lib or None)

    text = "\n".join(lines).rstrip()
    if text:
        text += "\n"
    ENV_PATH.write_text(text, encoding="utf-8")

    if new_key:
        os.environ["ZOTERO_API_KEY"] = new_key
    if new_lib:
        os.environ["ZOTERO_LIBRARY_ID"] = new_lib
    elif "ZOTERO_LIBRARY_ID" in os.environ:
        os.environ.pop("ZOTERO_LIBRARY_ID", None)

    return {"api_key": new_key, "library_id": new_lib}


def resolve_library_id(api_key: str) -> str:
    resp = httpx.get(
        f"https://api.zotero.org/keys/{api_key}",
        timeout=30.0,
        follow_redirects=True,
    )
    resp.raise_for_status()
    data = resp.json()
    user_id = data.get("userID")
    if user_id is None:
        raise RuntimeError("无法从 API Key 解析 library ID")
    return str(user_id)


def test_zotero_connection() -> dict:
    from net_env import connect_zotero_web

    creds = get_zotero_credentials()
    if not creds["api_key"]:
        return {"ok": False, "message": "未配置 API Key，请先在设置页填写"}

    try:
        zot = connect_zotero_web()
        lib_id = str(zot.library_id)
        zot.num_items()
        return {
            "ok": True,
            "message": "连接成功",
            "library_id": lib_id,
        }
    except Exception as exc:
        return {"ok": False, "message": str(exc)}
