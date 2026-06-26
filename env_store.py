"""Read and update the user .env file."""

from __future__ import annotations

import os
import re
from pathlib import Path

from config_manager import ENV_PATH, SCRIPT_DIR

LEGACY_ENV_PATH = SCRIPT_DIR / ".env"


def parse_env_file(path: Path = ENV_PATH) -> dict[str, str]:
    if path == ENV_PATH and not path.exists() and LEGACY_ENV_PATH.exists():
        path = LEGACY_ENV_PATH
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


def set_env_values(values: dict[str, str | None], path: Path = ENV_PATH) -> None:
    lines: list[str] = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    else:
        path.parent.mkdir(parents=True, exist_ok=True)

    for key, value in values.items():
        pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
        found = False
        out: list[str] = []
        clean_value = (value or "").strip()
        for line in lines:
            if pattern.match(line):
                found = True
                if clean_value:
                    out.append(f"{key}={clean_value}")
                continue
            out.append(line)
        if not found and clean_value:
            out.append(f"{key}={clean_value}")
        lines = out

    text = "\n".join(lines).rstrip()
    if text:
        text += "\n"
    path.write_text(text, encoding="utf-8")

    for key, value in values.items():
        clean_value = (value or "").strip()
        if clean_value:
            os.environ[key] = clean_value
        else:
            os.environ.pop(key, None)
