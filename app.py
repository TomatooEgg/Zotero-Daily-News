#!/usr/bin/env python3
"""Zotero 简报控制台 — 本地 Web / 原生窗口界面。"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import markdown
from flask import Flask, jsonify, render_template, request, send_file

from config_manager import DEFAULT_CONFIG, SCRIPT_DIR, load_config, save_config
from launchd_mgr import launchd_status, reload_launchd
from notes_index import get_note, group_by_date, list_notes

app = Flask(__name__)


def tail_log(path: Path, lines: int = 30) -> str:
    if not path.exists():
        return "（暂无日志）"
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(content[-lines:]) or "（空）"


def config_for_ui() -> dict:
    cfg = load_config()
    output = cfg.get("output") or {}
    return {
        "priority_tag": cfg.get("priority_tag", "want"),
        "count": cfg.get("count", 2),
        "history_days": cfg.get("history_days", 14),
        "summaries_dir": output.get("summaries_dir", "summaries"),
        "hubs_dir": output.get("hubs_dir", "hubs"),
        "schedule": cfg.get("schedule") or DEFAULT_CONFIG["schedule"],
        "summary_prompt": cfg.get("summary_prompt", DEFAULT_CONFIG["summary_prompt"]),
        "deepseek_model": (cfg.get("deepseek") or {}).get("model", "deepseek-chat"),
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


@app.get("/api/notes/<note_id>")
def api_note_detail(note_id: str):
    entry = get_note(note_id)
    if not entry:
        return jsonify({"error": "笔记不存在"}), 404
    md_text = Path(entry.md_path).read_text(encoding="utf-8", errors="replace")
    html_body = markdown.markdown(
        md_text,
        extensions=["extra", "nl2br", "sane_lists"],
    )
    return jsonify({
        **entry.to_dict(),
        "markdown": md_text,
        "html": html_body,
        "hub_route": f"/hub/{note_id}",
        "zotero_url": f"zotero://select/library/items/{entry.item_key}",
    })


@app.get("/hub/<note_id>")
def serve_hub(note_id: str):
    entry = get_note(note_id)
    if not entry or not entry.hub_path:
        return "中转页不存在", 404
    return send_file(entry.hub_path)


@app.get("/note/<note_id>")
def note_page(note_id: str):
    """供中转页「在应用中打开」链接使用。"""
    entry = get_note(note_id)
    if not entry:
        return "笔记不存在", 404
    md_text = Path(entry.md_path).read_text(encoding="utf-8", errors="replace")
    html_body = markdown.markdown(md_text, extensions=["extra", "nl2br", "sane_lists"])
    return render_template(
        "note.html",
        title=entry.title,
        briefing=entry.briefing,
        html_body=html_body,
        zotero_url=f"zotero://select/library/items/{entry.item_key}",
        hub_url=f"/hub/{note_id}",
    )


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

    cfg.setdefault("deepseek", {})
    cfg["deepseek"]["model"] = str(data.get("deepseek_model", "deepseek-chat")).strip()

    save_config(cfg)
    return jsonify({"ok": True, "message": "配置已保存"})


@app.post("/api/reload-schedule")
def api_reload_schedule():
    cfg = load_config()
    ok, message = reload_launchd(cfg)
    return jsonify({"ok": ok, "message": message, "status": launchd_status()})


@app.post("/api/run")
def api_run():
    force = bool(request.json and request.json.get("force"))
    cmd = python_cmd(str(SCRIPT_DIR / "digest.py"))
    if force:
        cmd.append("--force")
    result = subprocess.run(
        cmd,
        cwd=str(SCRIPT_DIR),
        capture_output=True,
        text=True,
        env={**os.environ, **load_env()},
    )
    return jsonify({
        "ok": result.returncode == 0,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
    })


@app.post("/api/test-notify")
def api_test_notify():
    result = subprocess.run(
        python_cmd(str(SCRIPT_DIR / "digest.py"), "--test-notify"),
        cwd=str(SCRIPT_DIR),
        capture_output=True,
        text=True,
        env={**os.environ, **load_env()},
    )
    return jsonify({
        "ok": result.returncode == 0,
        "stdout": result.stdout,
        "stderr": result.stderr,
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
