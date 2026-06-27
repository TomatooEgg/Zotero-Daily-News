"""Platform scheduler facade: launchd on macOS, Task Scheduler on Windows."""

from __future__ import annotations

import subprocess
import sys
import os
import csv
import io
from pathlib import Path

from config_manager import SCRIPT_DIR, load_config
from platform_utils import no_window_subprocess_kwargs
from queue_manager import queue_settings

TASK_PREFIX = os.environ.get("ZOTERO_DAILY_NEWS_TASK_PREFIX", "ZoteroDailyNews")
PUSH_TASK = f"{TASK_PREFIX}\\Push"
PREPARE_TASK = f"{TASK_PREFIX}\\Prepare"
MAX_TASKS = 12


def _schedule_slots(config: dict) -> list[dict[str, int]]:
    schedule = config.get("schedule") or [{"hour": 10, "minute": 0}]
    slots: list[dict[str, int]] = []
    for slot in schedule:
        try:
            hour = max(0, min(23, int(slot.get("hour", 10))))
            minute = max(0, min(59, int(slot.get("minute", 0))))
        except (TypeError, ValueError):
            continue
        slots.append({"hour": hour, "minute": minute})
    return slots or [{"hour": 10, "minute": 0}]


def _prepare_slots(config: dict) -> list[dict[str, int]]:
    offset = queue_settings(config)["prepare_before_minutes"]
    slots: list[dict[str, int]] = []
    for slot in _schedule_slots(config):
        total = (slot["hour"] * 60 + slot["minute"] - offset) % (24 * 60)
        slots.append({"hour": total // 60, "minute": total % 60})
    return slots


def _task_name(base: str, index: int) -> str:
    return f"{base}{index + 1}"


def _powershell_cmd(script: Path, *args: str) -> str:
    quoted = " ".join([f'"{script}"', *args])
    return f'powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File {quoted}'


def _windows_cmd(script: Path, *args: str) -> str:
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).with_name("Zotero Daily News.exe")
        if not executable.exists():
            executable = Path(sys.executable)
        quoted_args = " ".join(args)
        return f'"{executable}" {quoted_args}'.strip()
    return _powershell_cmd(script, *args)


def _delete_windows_tasks() -> None:
    result = subprocess.run(
        ["schtasks.exe", "/Query", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        check=False,
        **no_window_subprocess_kwargs(),
    )
    if result.returncode != 0:
        return
    prefix = f"\\{TASK_PREFIX}\\"
    for row in csv.reader(io.StringIO(result.stdout)):
        if not row:
            continue
        task_name = row[0].strip().strip('"')
        if not task_name.startswith(prefix):
            continue
        subprocess.run(
            ["schtasks.exe", "/Delete", "/TN", task_name, "/F"],
            capture_output=True,
            text=True,
            check=False,
            **no_window_subprocess_kwargs(),
        )


def _create_windows_tasks(config: dict) -> tuple[bool, str]:
    _delete_windows_tasks()
    scripts = {
        PUSH_TASK: (SCRIPT_DIR / "run.ps1", ["--push-queue"], _schedule_slots(config)),
        PREPARE_TASK: (SCRIPT_DIR / "prepare_queue.ps1", ["--refresh-queue", "--prepare-queue"], _prepare_slots(config)),
    }
    errors: list[str] = []
    for base, (script, args, slots) in scripts.items():
        for idx, slot in enumerate(slots[:MAX_TASKS]):
            task_time = f"{slot['hour']:02d}:{slot['minute']:02d}"
            result = subprocess.run(
                [
                    "schtasks.exe",
                    "/Create",
                    "/TN",
                    _task_name(base, idx),
                    "/TR",
                    _windows_cmd(script, *args),
                    "/SC",
                    "DAILY",
                    "/ST",
                    task_time,
                    "/F",
                ],
                capture_output=True,
                text=True,
                check=False,
                **no_window_subprocess_kwargs(),
            )
            if result.returncode != 0:
                errors.append((result.stderr or result.stdout or "").strip())
    if errors:
        return False, "；".join(e for e in errors if e) or "Task Scheduler 创建失败"
    return True, "Windows 定时任务已启用"


def _windows_task_loaded(base: str) -> bool:
    result = subprocess.run(
        ["schtasks.exe", "/Query", "/TN", _task_name(base, 0)],
        capture_output=True,
        text=True,
        check=False,
        **no_window_subprocess_kwargs(),
    )
    return result.returncode == 0


def scheduler_status() -> dict:
    if sys.platform == "darwin":
        from launchd_mgr import launchd_status

        status = launchd_status()
        status["platform"] = "macos"
        status["name"] = "launchd"
        return status
    if sys.platform == "win32":
        settings = queue_settings()
        return {
            "platform": "windows",
            "name": "Windows Task Scheduler",
            "loaded": _windows_task_loaded(PUSH_TASK),
            "prepare_loaded": _windows_task_loaded(PREPARE_TASK),
            "label": PUSH_TASK,
            "prepare_label": PREPARE_TASK,
            "plist_path": "",
            "prepare_plist_path": "",
            "prepare_before_minutes": settings["prepare_before_minutes"],
            "detail": "",
            "prepare_detail": "",
        }
    settings = queue_settings()
    return {
        "platform": sys.platform,
        "name": "unsupported",
        "loaded": False,
        "prepare_loaded": False,
        "label": "",
        "prepare_label": "",
        "plist_path": "",
        "prepare_plist_path": "",
        "prepare_before_minutes": settings["prepare_before_minutes"],
        "detail": "当前平台暂不支持自动定时任务",
        "prepare_detail": "",
    }


def reload_scheduler(config: dict | None = None) -> tuple[bool, str]:
    config = config or load_config()
    if sys.platform == "darwin":
        from launchd_mgr import reload_launchd

        return reload_launchd(config)
    if sys.platform == "win32":
        return _create_windows_tasks(config)
    return False, "当前平台暂不支持自动定时任务"
