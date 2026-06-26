"""本地网络环境：让 Zotero 等 localhost 请求绕过 VPN/系统代理。"""

from __future__ import annotations

import os
from typing import Any

import httpx
from pyzotero import zotero

LOCAL_NO_PROXY_HOSTS = ("localhost", "127.0.0.1", "::1")
LOCAL_NO_PROXY = ",".join(LOCAL_NO_PROXY_HOSTS)


def ensure_local_no_proxy() -> None:
    """合并 NO_PROXY，让 urllib / 默认 httpx 跳过本地地址。"""
    existing = os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or ""
    parts = [p.strip() for p in existing.split(",") if p.strip()]
    for host in LOCAL_NO_PROXY_HOSTS:
        if host not in parts:
            parts.append(host)
    merged = ",".join(parts)
    os.environ["NO_PROXY"] = merged
    os.environ["no_proxy"] = merged


def local_httpx_client(**kwargs: Any) -> httpx.Client:
    """用于 Zotero 本地 API，完全不读代理环境变量。"""
    kwargs.setdefault("follow_redirects", True)
    kwargs.setdefault("timeout", 30.0)
    return httpx.Client(trust_env=False, **kwargs)


def connect_zotero() -> zotero.Zotero:
    ensure_local_no_proxy()
    zot = zotero.Zotero(
        library_id=0,
        library_type="user",
        local=True,
        client=local_httpx_client(),
    )
    base_url = os.environ.get("ZOTERO_LOCAL_API_BASE_URL")
    if base_url:
        zot.endpoint = base_url.rstrip("/")
    return zot


def connect_zotero_web() -> zotero.Zotero:
    """Zotero Web API（用于创建/更新子笔记）。需配置 ZOTERO_API_KEY。"""
    from zotero_credentials import get_zotero_credentials, resolve_library_id

    creds = get_zotero_credentials()
    api_key = creds["api_key"]
    if not api_key:
        raise RuntimeError(
            "未配置 ZOTERO_API_KEY。请打开控制台 → 设置 → Zotero 回推 填写 API Key"
        )
    library_id = creds["library_id"] or resolve_library_id(api_key)
    zot = zotero.Zotero(
        library_id=library_id,
        library_type="user",
        api_key=api_key,
    )
    base_url = os.environ.get("ZOTERO_API_BASE_URL")
    if base_url:
        zot.endpoint = base_url.rstrip("/")
    return zot
