from __future__ import annotations

from pathlib import Path

from cx_Freeze import Executable, setup

APP_NAME = "Zotero Daily News"
VERSION = "0.1.0"
ROOT = Path(__file__).resolve().parent
SGMLLIB = ROOT / ".build-venv" / "Lib" / "site-packages" / "sgmllib.py"

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
    "include_files": include_files,
    "packages": [
        "bleach",
        "flask",
        "httpx",
        "jinja2",
        "markdown",
        "openai",
        "PIL",
        "pystray",
        "pyzotero",
        "pypdf",
        "sgmllib",
        "webview",
        "yaml",
        "zotero_daily_news",
    ],
    "excludes": [
        "Cython",
        "IPython",
        "PyInstaller",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "matplotlib",
        "notebook",
        "numpy",
        "pandas",
        "scipy",
    ],
    "include_msvcr": True,
}

bdist_msi_options = {
    "upgrade_code": "{8F0F91D0-5ED0-4D9E-B155-3D8A5F490F7F}",
    "initial_target_dir": r"[LocalAppDataFolder]\Programs\Zotero Daily News",
    "add_to_path": False,
}

executables = [
    Executable(
        "zotero_daily.py",
        base="Win32GUI",
        target_name="Zotero Daily News.exe",
        shortcut_name="Zotero Daily News",
        shortcut_dir="DesktopFolder",
    ),
    Executable(
        "zotero_daily.py",
        base=None,
        target_name="Zotero Daily News CLI.exe",
    ),
]

setup(
    name=APP_NAME,
    version=VERSION,
    description="Daily Zotero paper digest with DeepSeek summaries",
    options={
        "build_exe": build_exe_options,
        "bdist_msi": bdist_msi_options,
    },
    executables=executables,
)
