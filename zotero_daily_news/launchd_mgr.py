"""根据 config 生成并加载 launchd 定时任务（推送 + 预生成）。"""

from __future__ import annotations

import os
import plistlib
import subprocess
from pathlib import Path

from .config_manager import SCRIPT_DIR, load_config, logs_dir, runtime_path
from .net_env import LOCAL_NO_PROXY
from .queue_manager import queue_settings

PLIST_LABEL = "com.TomatooEgg.zotero-digest"
PLIST_PREPARE_LABEL = "com.TomatooEgg.zotero-digest.prepare"
PLIST_NAME = f"{PLIST_LABEL}.plist"
PLIST_PREPARE_NAME = f"{PLIST_PREPARE_LABEL}.plist"
PLIST_DST = Path.home() / "Library" / "LaunchAgents" / PLIST_NAME
PLIST_PREPARE_DST = Path.home() / "Library" / "LaunchAgents" / PLIST_PREPARE_NAME
PLIST_SRC = runtime_path(PLIST_NAME)
PLIST_PREPARE_SRC = runtime_path(PLIST_PREPARE_NAME)


def _env_block() -> dict[str, str]:
    return {
        "PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin",
        "HOME": str(Path.home()),
        "LAUNCHD_JOB": "1",
        "NO_PROXY": LOCAL_NO_PROXY,
        "no_proxy": LOCAL_NO_PROXY,
    }


def _schedule_intervals(config: dict) -> list[dict[str, int]]:
    schedule = config.get("schedule") or [{"hour": 10, "minute": 0}]
    intervals: list[dict[str, int]] = []
    for slot in schedule:
        try:
            hour = int(slot.get("hour", 10))
            minute = int(slot.get("minute", 0))
        except (TypeError, ValueError):
            continue
        intervals.append({"Hour": hour, "Minute": minute})
    return intervals or [{"Hour": 10, "Minute": 0}]


def _prepare_intervals(config: dict) -> list[dict[str, int]]:
    settings = queue_settings(config)
    offset = settings["prepare_before_minutes"]
    result: list[dict[str, int]] = []
    for slot in _schedule_intervals(config):
        total = slot["Hour"] * 60 + slot["Minute"] - offset
        total %= 24 * 60
        result.append({"Hour": total // 60, "Minute": total % 60})
    return result


def build_plist(config: dict | None = None) -> dict:
    config = config or load_config()
    project = str(SCRIPT_DIR)
    return {
        "Label": PLIST_LABEL,
        "ProgramArguments": ["/bin/bash", f"{project}/run.sh", "--push-queue"],
        "WorkingDirectory": project,
        "EnvironmentVariables": _env_block(),
        "StartCalendarInterval": _schedule_intervals(config),
        "StandardOutPath": str(logs_dir() / "stdout.log"),
        "StandardErrorPath": str(logs_dir() / "stderr.log"),
    }


def build_prepare_plist(config: dict | None = None) -> dict:
    config = config or load_config()
    project = str(SCRIPT_DIR)
    return {
        "Label": PLIST_PREPARE_LABEL,
        "ProgramArguments": ["/bin/bash", f"{project}/prepare_queue.sh"],
        "WorkingDirectory": project,
        "EnvironmentVariables": _env_block(),
        "StartCalendarInterval": _prepare_intervals(config),
        "StandardOutPath": str(logs_dir() / "prepare_stdout.log"),
        "StandardErrorPath": str(logs_dir() / "prepare_stderr.log"),
    }


def write_plist(config: dict | None = None) -> Path:
    config = config or load_config()
    logs_dir().mkdir(parents=True, exist_ok=True)
    for src, dst, builder in (
        (PLIST_SRC, PLIST_DST, build_plist),
        (PLIST_PREPARE_SRC, PLIST_PREPARE_DST, build_prepare_plist),
    ):
        plist = builder(config)
        src.parent.mkdir(parents=True, exist_ok=True)
        with src.open("wb") as f:
            plistlib.dump(plist, f)
        dst.parent.mkdir(parents=True, exist_ok=True)
        with dst.open("wb") as f:
            plistlib.dump(plist, f)
    return PLIST_DST


def _service_loaded(label: str) -> dict:
    uid = os.getuid()
    target = f"gui/{uid}/{label}"
    result = subprocess.run(
        ["launchctl", "print", target],
        capture_output=True,
        text=True,
    )
    loaded = result.returncode == 0
    return {
        "loaded": loaded,
        "label": label,
        "detail": result.stdout.strip() if loaded else result.stderr.strip(),
    }


def launchd_status() -> dict:
    push = _service_loaded(PLIST_LABEL)
    prepare = _service_loaded(PLIST_PREPARE_LABEL)
    settings = queue_settings()
    return {
        "loaded": push["loaded"],
        "prepare_loaded": prepare["loaded"],
        "label": PLIST_LABEL,
        "prepare_label": PLIST_PREPARE_LABEL,
        "plist_path": str(PLIST_DST),
        "prepare_plist_path": str(PLIST_PREPARE_DST),
        "prepare_before_minutes": settings["prepare_before_minutes"],
        "detail": push["detail"],
        "prepare_detail": prepare["detail"],
    }


def reload_launchd(config: dict | None = None) -> tuple[bool, str]:
    write_plist(config)
    uid = os.getuid()
    domain = f"gui/{uid}"
    errors: list[str] = []
    for label, dst in (
        (PLIST_LABEL, PLIST_DST),
        (PLIST_PREPARE_LABEL, PLIST_PREPARE_DST),
    ):
        service = f"{domain}/{label}"
        subprocess.run(["launchctl", "bootout", service], capture_output=True)
        result = subprocess.run(
            ["launchctl", "bootstrap", domain, str(dst)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            errors.append(result.stderr.strip() or f"{label} bootstrap 失败")

    if not errors:
        return True, "推送与预生成定时任务已重载"
    return False, "；".join(errors)
