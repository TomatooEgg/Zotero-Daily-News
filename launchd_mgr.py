"""根据 config 生成并加载 launchd 定时任务。"""

from __future__ import annotations

import os
import plistlib
import subprocess
from pathlib import Path

from config_manager import SCRIPT_DIR, load_config

PLIST_LABEL = "com.TomatooEgg.zotero-digest"
PLIST_NAME = f"{PLIST_LABEL}.plist"
PLIST_DST = Path.home() / "Library" / "LaunchAgents" / PLIST_NAME
PLIST_SRC = SCRIPT_DIR / PLIST_NAME


def build_plist(config: dict | None = None) -> dict:
    config = config or load_config()
    schedule = config.get("schedule") or [{"hour": 10, "minute": 0}]
    intervals = []
    for slot in schedule:
        try:
            hour = int(slot.get("hour", 10))
            minute = int(slot.get("minute", 0))
        except (TypeError, ValueError):
            continue
        intervals.append({"Hour": hour, "Minute": minute})

    if not intervals:
        intervals = [{"Hour": 10, "Minute": 0}]

    project = str(SCRIPT_DIR)
    return {
        "Label": PLIST_LABEL,
        "ProgramArguments": ["/bin/bash", f"{project}/run.sh"],
        "WorkingDirectory": project,
        "EnvironmentVariables": {
            "PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin",
            "HOME": str(Path.home()),
            "LAUNCHD_JOB": "1",
        },
        "StartCalendarInterval": intervals,
        "StandardOutPath": f"{project}/logs/stdout.log",
        "StandardErrorPath": f"{project}/logs/stderr.log",
    }


def write_plist(config: dict | None = None) -> Path:
    plist = build_plist(config)
    PLIST_SRC.parent.mkdir(parents=True, exist_ok=True)
    (SCRIPT_DIR / "logs").mkdir(parents=True, exist_ok=True)
    with PLIST_SRC.open("wb") as f:
        plistlib.dump(plist, f)
    PLIST_DST.parent.mkdir(parents=True, exist_ok=True)
    with PLIST_DST.open("wb") as f:
        plistlib.dump(plist, f)
    return PLIST_DST


def launchd_status() -> dict:
    uid = os.getuid()
    target = f"gui/{uid}/{PLIST_LABEL}"
    result = subprocess.run(
        ["launchctl", "print", target],
        capture_output=True,
        text=True,
    )
    loaded = result.returncode == 0
    return {
        "loaded": loaded,
        "label": PLIST_LABEL,
        "plist_path": str(PLIST_DST),
        "detail": result.stdout.strip() if loaded else result.stderr.strip(),
    }


def reload_launchd(config: dict | None = None) -> tuple[bool, str]:
    write_plist(config)
    uid = os.getuid()
    domain = f"gui/{uid}"
    service = f"{domain}/{PLIST_LABEL}"
    subprocess.run(["launchctl", "bootout", service], capture_output=True)
    result = subprocess.run(
        ["launchctl", "bootstrap", domain, str(PLIST_DST)],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return True, "定时任务已重载"
    return False, result.stderr.strip() or "launchctl bootstrap 失败，请在终端手动执行"
