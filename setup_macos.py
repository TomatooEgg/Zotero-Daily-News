from __future__ import annotations

import os
import sysconfig
from pathlib import Path

from cx_Freeze import Executable, setup

APP_NAME = "Zotero Daily News"
VERSION = "0.1.0"
ROOT = Path(__file__).resolve().parent
BUILD_EXE = Path(os.environ.get("ZDN_MACOS_BUILD_EXE", ROOT / "build" / "macos-exe"))
SGMLLIB = Path(sysconfig.get_paths()["purelib"]) / "sgmllib.py"

include_files = [
    (ROOT / "templates", "templates"),
    (ROOT / "static", "static"),
    (ROOT / "prompts", "prompts"),
    (ROOT / "fixtures", "fixtures"),
    (ROOT / "config.example.yaml", "config.example.yaml"),
    (ROOT / ".env.example", ".env.example"),
]
if SGMLLIB.is_file():
    include_files.append((SGMLLIB, "sgmllib.py"))

build_exe_options = {
    "build_exe": str(BUILD_EXE),
    "include_files": include_files,
    "packages": [
        "AppKit",
        "bleach",
        "flask",
        "Foundation",
        "httpx",
        "jinja2",
        "markdown",
        "objc",
        "openai",
        "PIL",
        "pystray",
        "pyzotero",
        "pypdf",
        "sgmllib",
        "webview",
        "WebKit",
        "yaml",
        "zotero_daily_news",
    ],
    "excludes": [
        "Cython",
        "IPython",
        "matplotlib",
        "notebook",
        "numpy",
        "pandas",
        "PyInstaller",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "scipy",
    ],
}

executables = [
    Executable(
        "zotero_daily.py",
        target_name="launcher",
    ),
]

setup(
    name=APP_NAME,
    version=VERSION,
    description="Daily Zotero paper digest with DeepSeek summaries",
    options={"build_exe": build_exe_options},
    executables=executables,
)
