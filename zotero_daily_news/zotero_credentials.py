"""Zotero Web API 凭证读写（存于 .env）。"""

from __future__ import annotations

import os
from pathlib import Path

import httpx

from .config_manager import ENV_PATH
from .env_store import parse_env_file, set_env_values

ENV_KEYS = ("ZOTERO_API_KEY", "ZOTERO_LIBRARY_ID")


def _parse_env_file(path: Path) -> dict[str, str]:
    return parse_env_file(path)


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

    set_env_values({
        "ZOTERO_API_KEY": new_key or None,
        "ZOTERO_LIBRARY_ID": new_lib or None,
    })

    return {"api_key": new_key, "library_id": new_lib}


def resolve_library_id(api_key: str) -> str:
    base_url = os.environ.get("ZOTERO_API_BASE_URL", "https://api.zotero.org").rstrip("/")
    resp = httpx.get(
        f"{base_url}/keys/{api_key}",
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
    from .net_env import connect_zotero_web

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
