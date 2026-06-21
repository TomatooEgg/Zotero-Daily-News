#!/usr/bin/env python3
"""Zotero 简报控制台 — 本地 Web / 原生窗口界面。"""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from abstract_zh import generate_abstract_zh
from config_manager import DEFAULT_CONFIG, SCRIPT_DIR, deepseek_briefing_model, deepseek_deep_read_model, load_config, resolve_output_dirs, save_config
from deep_read import generate_deep_read
from launchd_mgr import launchd_status, reload_launchd
from notes_index import delete_note, delete_notes, delete_notes_by_date, get_note, group_by_date, list_notes
from note_view import prepare_note_view_context, render_note_view_html
from notifier import notify_macos, parse_notify_stdout
from push_finalize import apply_push_results
from app_bridge import navigate_to_note, yield_focus_to_external_app
from url_handler import open_digest_app_for_note
from zotero_credentials import save_zotero_credentials, test_zotero_connection, zotero_config_for_ui
from zotero_open import open_zotero_deeplink
from zotero_push import push_digest_note, push_status

app = Flask(__name__)

_generating_deep_read: set[str] = set()
_generating_abstract_zh: set[str] = set()
_pushing_zotero: set[str] = set()


@app.after_request
def add_cors_headers(response):
    if request.path.startswith("/api/"):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


def tail_log(path: Path, lines: int = 30) -> str:
    if not path.exists():
        return "（暂无日志）"
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(content[-lines:]) or "（空）"


def config_for_ui() -> dict:
    cfg = load_config()
    output = cfg.get("output") or {}
    queue_cfg = cfg.get("queue") or {}
    return {
        "priority_tag": cfg.get("priority_tag", "want"),
        "count": cfg.get("count", 2),
        "history_days": cfg.get("history_days", 14),
        "queue_size": int(queue_cfg.get("size", 4)),
        "prepare_before_minutes": int(queue_cfg.get("prepare_before_minutes", 120)),
        "pre_generate_deep_read": bool(queue_cfg.get("pre_generate_deep_read", True)),
        "summaries_dir": output.get("summaries_dir", "summaries"),
        "hubs_dir": output.get("hubs_dir", "hubs"),
        "schedule": cfg.get("schedule") or DEFAULT_CONFIG["schedule"],
        "summary_prompt": cfg.get("summary_prompt", DEFAULT_CONFIG["summary_prompt"]),
        "pdf_summary_enabled": bool((cfg.get("pdf_summary") or {}).get("enabled", True)),
        "pdf_summary_max_chars": int((cfg.get("pdf_summary") or {}).get("max_chars", 80000)),
        "pdf_summary_prompt": cfg.get("pdf_summary_prompt", DEFAULT_CONFIG["pdf_summary_prompt"]),
        "deepseek_briefing_model": deepseek_briefing_model(cfg),
        "deepseek_deep_read_model": deepseek_deep_read_model(cfg),
    }


def load_env() -> dict[str, str]:
    env_path = SCRIPT_DIR / ".env"
    extra: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                extra[k.strip()] = v.strip().strip('"').strip("'")
    return extra


def python_bin() -> str:
    venv_py = SCRIPT_DIR / ".venv" / "bin" / "python"
    return str(venv_py if venv_py.exists() else "python3")


def is_apple_silicon() -> bool:
    """检测 Apple Silicon，不受当前进程是否跑在 Rosetta 下影响。"""
    try:
        result = subprocess.run(
            ["sysctl", "-n", "hw.optional.arm64"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip() == "1"
    except OSError:
        return False


def python_cmd(*script_args: str) -> list[str]:
    """构建 Python 子进程命令；在 Apple Silicon 上强制 arm64，避免 Rosetta 下加载 arm64 wheel 失败。"""
    cmd = [python_bin(), *script_args]
    if is_apple_silicon():
        return ["arch", "-arm64", *cmd]
    return cmd


def dispatch_notifications(specs: list[dict[str, str]]) -> tuple[int, int, str, list[dict]]:
    """在主进程发送通知，返回 (成功数, 失败数, stderr 日志, 逐条结果)。"""
    sent = 0
    failed = 0
    logs: list[str] = []
    results: list[dict] = []

    for spec in specs:
        hub_raw = spec.get("hub_path")
        hub_path = Path(hub_raw) if hub_raw else None
        stderr_buf = io.StringIO()
        with contextlib.redirect_stderr(stderr_buf):
            ok, action = notify_macos(
                title=spec["title"],
                message=spec.get("message", ""),
                subtitle=spec.get("subtitle", ""),
                hub_path=hub_path,
                note_id=spec.get("note_id") or (hub_path.stem if hub_path else None),
                verbose=True,
            )
        log = stderr_buf.getvalue().strip()
        if log:
            logs.append(log)
        if ok:
            sent += 1
        else:
            failed += 1
        note_id = spec.get("note_id")
        if not note_id and hub_path:
            note_id = hub_path.stem
        results.append({
            "item_key": spec.get("item_key"),
            "note_id": note_id,
            "action": action,
            "ok": ok,
        })

    return sent, failed, "\n".join(logs), results


def create_test_hub() -> Path:
    hub = SCRIPT_DIR / "hubs" / "_test.html"
    hub.parent.mkdir(parents=True, exist_ok=True)
    hub.write_text(
        """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
        <title>测试</title></head><body><h1>通知测试成功</h1>
        <p>点击通知后应看到此页面。</p></body></html>""",
        encoding="utf-8",
    )
    return hub


@app.get("/")
def index():
    status = launchd_status()
    return render_template(
        "app.html",
        config=config_for_ui(),
        launchd_loaded=status["loaded"],
        project_dir=str(SCRIPT_DIR),
    )


@app.get("/api/notes")
def api_notes():
    date_filter = request.args.get("date")
    entries = list_notes(date_filter=date_filter or None)
    return jsonify({"groups": group_by_date(entries), "total": len(entries)})


@app.delete("/api/notes")
def api_delete_notes():
    data = request.get_json(silent=True) or {}
    ids = data.get("ids")
    if ids is not None:
        if not isinstance(ids, list) or not ids:
            return jsonify({"error": "ids 不能为空"}), 400
        count = delete_notes([str(i) for i in ids])
        if count == 0:
            return jsonify({"error": "未找到可删除的笔记"}), 404
        return jsonify({"ok": True, "deleted_count": count})

    iso_date = request.args.get("date", "").strip()
    if not iso_date:
        return jsonify({"error": "缺少 date 参数或 ids 列表"}), 400
    count = delete_notes_by_date(iso_date)
    if count < 0:
        return jsonify({"error": "日期格式无效，应为 YYYY-MM-DD"}), 400
    if count == 0:
        return jsonify({"error": "该日期无笔记"}), 404
    return jsonify({"ok": True, "deleted_count": count, "date": iso_date})


@app.delete("/api/notes/<note_id>")
def api_delete_note(note_id: str):
    if not delete_note(note_id):
        return jsonify({"error": "笔记不存在"}), 404
    return jsonify({"ok": True, "deleted": note_id})


def reveal_in_finder(path: Path) -> tuple[bool, str]:
    """在 macOS 访达中定位文件。"""
    if not path.exists():
        return False, "文件不存在"
    config = load_config()
    summaries_dir, hubs_dir = resolve_output_dirs(config)
    resolved = path.resolve()
    allowed = False
    for base in (summaries_dir.resolve(), hubs_dir.resolve()):
        try:
            resolved.relative_to(base)
            allowed = True
            break
        except ValueError:
            continue
    if not allowed:
        return False, "路径无效"
    subprocess.run(["open", "-R", str(resolved)], check=False)
    return True, ""


ALLOWED_OPEN_SCHEMES = ("zotero://", "zotero-digest://")


@app.post("/api/navigate")
def api_navigate():
    data = request.get_json(silent=True) or {}
    note_id = str(data.get("note_id") or "").strip()
    if not note_id:
        return jsonify({"error": "缺少 note_id"}), 400
    if not get_note(note_id):
        return jsonify({"error": "笔记不存在"}), 404
    activate = bool(data.get("activate", True))
    navigated = navigate_to_note(note_id, activate=activate)
    return jsonify({"ok": True, "navigated": navigated, "note_id": note_id})


@app.post("/api/open-digest-app")
def api_open_digest_app():
    data = request.get_json(silent=True) or {}
    note_id = str(data.get("note_id") or "").strip()
    if not note_id:
        return jsonify({"error": "缺少 note_id"}), 400
    if not get_note(note_id):
        return jsonify({"error": "笔记不存在"}), 404
    if navigate_to_note(note_id, activate=False):
        return jsonify({"ok": True, "mode": "navigate", "note_id": note_id})
    open_digest_app_for_note(note_id)
    return jsonify({"ok": True, "mode": "launch", "note_id": note_id})


@app.post("/api/open-url")
def api_open_url():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url or not url.startswith(ALLOWED_OPEN_SCHEMES):
        return jsonify({"error": "不支持的链接"}), 400
    if url.startswith("zotero://"):
        open_zotero_deeplink(url)
        yield_focus_to_external_app()
    else:
        subprocess.run(["open", url], check=False, timeout=5)
    return jsonify({"ok": True})


@app.post("/api/notes/<note_id>/reveal")
def api_reveal_note(note_id: str):
    entry = get_note(note_id)
    if not entry:
        return jsonify({"error": "笔记不存在"}), 404
    ok, message = reveal_in_finder(Path(entry.md_path))
    if not ok:
        return jsonify({"error": message}), 404
    return jsonify({"ok": True})


@app.get("/api/notes/<note_id>")
def api_note_detail(note_id: str):
    ctx = prepare_note_view_context(note_id, viewer="app")
    if not ctx:
        return jsonify({"error": "笔记不存在"}), 404
    entry = get_note(note_id)
    assert entry is not None
    return jsonify({
        **entry.to_dict(),
        "markdown": Path(entry.md_path).read_text(encoding="utf-8", errors="replace"),
        "html": ctx["html_body"],
        "has_abstract": ctx["note_data"]["has_abstract"],
        "has_abstract_zh": ctx["note_data"]["has_abstract_zh"],
        "abstract_zh": ctx["note_data"]["abstract_zh"],
        "abstract_original": ctx["note_data"]["abstract_original"],
        "has_deep_read": ctx["note_data"]["has_deep_read"],
        "deep_read_html": ctx["note_data"]["deep_read_html"],
        "pdf_url": ctx["pdf_url"],
        "hub_route": f"/hub/{note_id}",
        "zotero_url": ctx["zotero_url"],
    })


@app.get("/api/notes/<note_id>/view")
def api_note_view_fragment(note_id: str):
    html = render_note_view_html(app, note_id, viewer="app", embed=True)
    if not html:
        return "笔记不存在", 404
    return html


@app.post("/api/notes/<note_id>/deep-read")
def api_generate_deep_read(note_id: str):
    if note_id in _generating_deep_read:
        return jsonify({"error": "正在生成中，请稍候"}), 409
    _generating_deep_read.add(note_id)
    try:
        data = request.get_json(silent=True) or {}
        regenerate = bool(data.get("regenerate"))
        result = generate_deep_read(note_id, regenerate=regenerate)
        return jsonify({"ok": True, **result})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"生成失败: {exc}"}), 500
    finally:
        _generating_deep_read.discard(note_id)


@app.post("/api/notes/<note_id>/abstract-zh")
def api_generate_abstract_zh(note_id: str):
    if note_id in _generating_abstract_zh:
        return jsonify({"error": "正在翻译中，请稍候"}), 409
    _generating_abstract_zh.add(note_id)
    try:
        result = generate_abstract_zh(note_id)
        return jsonify({"ok": True, **result})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"翻译失败: {exc}"}), 500
    finally:
        _generating_abstract_zh.discard(note_id)


@app.get("/api/zotero-config")
def api_get_zotero_config():
    return jsonify(zotero_config_for_ui())


@app.post("/api/zotero-config")
def api_save_zotero_config():
    data = request.get_json(silent=True) or {}
    api_key = data.get("api_key")
    library_id = data.get("library_id")
    if api_key is not None:
        api_key = str(api_key).strip()
    if library_id is not None:
        library_id = str(library_id).strip()
    save_zotero_credentials(
        api_key=api_key if api_key else None,
        library_id=library_id,
        keep_api_key_if_empty=True,
    )
    return jsonify({"ok": True, "message": "凭证已保存", **zotero_config_for_ui()})


@app.post("/api/zotero-config/test")
def api_test_zotero_config():
    result = test_zotero_connection()
    status = 200 if result.get("ok") else 400
    return jsonify(result), status


@app.get("/api/notes/<note_id>/push-zotero/status")
def api_push_zotero_status(note_id: str):
    try:
        return jsonify(push_status(note_id))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404


@app.post("/api/notes/<note_id>/push-zotero")
def api_push_zotero(note_id: str):
    if note_id in _pushing_zotero:
        return jsonify({"error": "正在回推中，请稍候"}), 409
    _pushing_zotero.add(note_id)
    try:
        data = request.get_json(silent=True) or {}
        mode = str(data.get("mode", "create")).strip().lower()
        if mode not in ("create", "update"):
            return jsonify({"error": "mode 须为 create 或 update"}), 400
        target_key = (data.get("note_key") or "").strip() or None
        result = push_digest_note(note_id, mode, target_key=target_key)  # type: ignore[arg-type]
        return jsonify({"ok": True, **result, "message": "已回推，Zotero 同步后可在条目下查看"})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"回推失败: {exc}"}), 500
    finally:
        _pushing_zotero.discard(note_id)


@app.get("/hub/<note_id>")
def serve_hub(note_id: str):
    html = render_note_view_html(app, note_id, viewer="hub", for_static_file=False)
    if not html:
        return "中转页不存在", 404
    return html


@app.get("/note/<note_id>")
def note_page(note_id: str):
    """供 deeplink / 简报 App 按钮打开。"""
    html = render_note_view_html(app, note_id, viewer="standalone")
    if not html:
        return "笔记不存在", 404
    return html


@app.get("/api/config")
def api_get_config():
    return jsonify(config_for_ui())


@app.post("/api/config")
def api_save_config():
    data = request.get_json(force=True)
    cfg = load_config()

    cfg["priority_tag"] = str(data.get("priority_tag", "want")).strip()
    cfg["count"] = max(1, min(10, int(data.get("count", 2))))
    cfg["history_days"] = max(1, min(90, int(data.get("history_days", 14))))

    cfg.setdefault("queue", {})
    cfg["queue"]["size"] = max(
        cfg["count"],
        min(30, int(data.get("queue_size", cfg["count"] * 2))),
    )
    cfg["queue"]["prepare_before_minutes"] = max(
        15, min(720, int(data.get("prepare_before_minutes", 120)))
    )
    cfg["queue"]["pre_generate_deep_read"] = bool(data.get("pre_generate_deep_read", True))

    cfg.setdefault("output", {})
    cfg["output"]["summaries_dir"] = str(data.get("summaries_dir", "summaries")).strip()
    cfg["output"]["hubs_dir"] = str(data.get("hubs_dir", "hubs")).strip()

    schedule = []
    for slot in data.get("schedule", []):
        try:
            schedule.append({"hour": int(slot["hour"]), "minute": int(slot["minute"])})
        except (KeyError, TypeError, ValueError):
            continue
    cfg["schedule"] = schedule or DEFAULT_CONFIG["schedule"]
    cfg["summary_prompt"] = str(data.get("summary_prompt", "")).strip() or DEFAULT_CONFIG["summary_prompt"]
    cfg["pdf_summary_prompt"] = (
        str(data.get("pdf_summary_prompt", "")).strip() or DEFAULT_CONFIG["pdf_summary_prompt"]
    )
    cfg.setdefault("pdf_summary", {})
    cfg["pdf_summary"]["enabled"] = bool(data.get("pdf_summary_enabled", True))
    cfg["pdf_summary"]["max_chars"] = max(
        5000, min(200000, int(data.get("pdf_summary_max_chars", 80000)))
    )

    cfg.setdefault("deepseek", {})
    cfg["deepseek"]["briefing_model"] = str(
        data.get("deepseek_briefing_model", deepseek_briefing_model(cfg))
    ).strip()
    cfg["deepseek"]["deep_read_model"] = str(
        data.get("deepseek_deep_read_model", deepseek_deep_read_model(cfg))
    ).strip()
    cfg["deepseek"].pop("model", None)

    save_config(cfg)
    return jsonify({"ok": True, "message": "配置已保存"})


@app.get("/api/queue")
def api_get_queue():
    from queue_manager import queue_summary_for_ui

    return jsonify(queue_summary_for_ui())


@app.post("/api/queue/refresh")
def api_refresh_queue():
    from queue_manager import refresh_queue

    force = bool(request.json and request.json.get("force"))
    try:
        queue = refresh_queue(force=force)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"ok": True, "created_at": queue.get("created_at"), "count": len(queue.get("items") or [])})


@app.post("/api/queue/prepare")
def api_prepare_queue():
    from queue_manager import prepare_queue

    skip_llm = bool(request.json and request.json.get("metadata_only"))
    try:
        _, prepared = prepare_queue(skip_llm=skip_llm)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"ok": True, "prepared": prepared})


@app.post("/api/reload-schedule")
def api_reload_schedule():
    cfg = load_config()
    ok, message = reload_launchd(cfg)
    return jsonify({"ok": ok, "message": message, "status": launchd_status()})


@app.post("/api/run")
def api_run():
    force = bool(request.json and request.json.get("force"))
    script_args = [str(SCRIPT_DIR / "digest.py"), "--no-notify", "--push-queue"]
    if force:
        script_args.append("--force")
    cmd = python_cmd(*script_args)
    result = subprocess.run(
        cmd,
        cwd=str(SCRIPT_DIR),
        capture_output=True,
        text=True,
        env={**os.environ, **load_env()},
    )
    specs = parse_notify_stdout(result.stdout)
    sent, failed, notify_stderr, notify_results = dispatch_notifications(specs)
    published = apply_push_results(notify_results)
    combined_stderr = "\n".join(
        part for part in (result.stderr.strip(), notify_stderr.strip()) if part
    )
    return jsonify({
        "ok": result.returncode == 0,
        "stdout": result.stdout,
        "stderr": combined_stderr,
        "returncode": result.returncode,
        "notifications_sent": sent,
        "notifications_failed": failed,
    })


@app.post("/api/test-notify")
def api_test_notify():
    hub = create_test_hub()
    stderr_buf = io.StringIO()
    with contextlib.redirect_stderr(stderr_buf):
        ok, _action = notify_macos(
            title="Zotero 简报测试",
            subtitle="通知系统",
            message="如果你看到这条通知，说明推送正常。",
            hub_path=hub,
            verbose=True,
        )
    notify_log = stderr_buf.getvalue().strip()
    return jsonify({
        "ok": ok,
        "stdout": "通知已发送（请查看屏幕右上角通知中心）" if ok else "通知发送失败",
        "stderr": notify_log,
        "notifications_sent": 1 if ok else 0,
        "notifications_failed": 0 if ok else 1,
    })


@app.get("/api/status")
def api_status():
    return jsonify({
        "launchd": launchd_status(),
        "stdout": tail_log(SCRIPT_DIR / "logs" / "stdout.log"),
        "stderr": tail_log(SCRIPT_DIR / "logs" / "stderr.log"),
    })


def main() -> None:
    from launcher import main as launch_main

    launch_main()


if __name__ == "__main__":
    main()
