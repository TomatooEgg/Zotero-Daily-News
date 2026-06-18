"""macOS 通知发送（多通道 + 真实成功检测）。"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
LOCAL_NOTIFIER = SCRIPT_DIR / "bin" / "terminal-notifier"
LOCAL_ALERTER = SCRIPT_DIR / "bin" / "alerter"
NOTIFY_PREFIX = "@@NOTIFY@@"
SUMMARY_ACTION = "查看总结"
DEFER_ACTION = "下次再推"
IMMEDIATE_PUBLISH_ACTION = "@IMMEDIATE"
OPEN_ON_ACTIONS = {SUMMARY_ACTION, "@CONTENTCLICKED", "@ACTIONCLICKED"}
DEFER_ACTIONS = {DEFER_ACTION, "关闭", "@CLOSED", "@TIMEOUT"}


def is_publish_action(action: str | None) -> bool:
    if not action:
        return False
    text = action.strip()
    if text in DEFER_ACTIONS:
        return False
    if text == IMMEDIATE_PUBLISH_ACTION:
        return True
    return text in OPEN_ON_ACTIONS

# 常见 terminal-notifier  Mach-O 路径
TN_CANDIDATES = [
    LOCAL_NOTIFIER,
    Path("/opt/homebrew/Cellar/terminal-notifier/2.0.0/terminal-notifier.app/Contents/MacOS/terminal-notifier"),
    Path("/usr/local/Cellar/terminal-notifier/2.0.0/terminal-notifier.app/Contents/MacOS/terminal-notifier"),
    Path("/Applications/terminal-notifier.app/Contents/MacOS/terminal-notifier"),
]


def _resolve_terminal_notifier() -> Path | None:
    for candidate in TN_CANDIDATES:
        if not candidate.exists():
            continue
        if candidate.suffix == ".app":
            candidate = candidate / "Contents/MacOS/terminal-notifier"
        if not candidate.exists():
            continue
        # 跳过 shell 包装脚本（124 字节左右），解析到真实二进制
        if candidate.stat().st_size < 4096:
            try:
                text = candidate.read_text(encoding="utf-8", errors="ignore")
                match = re.search(r'exec\s+"([^"]+terminal-notifier)"', text)
                if match:
                    real = Path(match.group(1))
                    if real.is_file() and real.stat().st_size > 4096:
                        return real
            except OSError:
                pass
            continue
        if os.access(candidate, os.X_OK) and candidate.stat().st_size > 4096:
            return candidate

    found = shutil.which("terminal-notifier")
    if found:
        return _resolve_terminal_notifier_from_path(Path(found))
    return None


def _resolve_terminal_notifier_from_path(path: Path) -> Path | None:
    if path.stat().st_size > 4096:
        return path
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        match = re.search(r'exec\s+"([^"]+)"', text)
        if match:
            real = Path(match.group(1))
            if real.is_file():
                return real
    except OSError:
        pass
    return None


def _resolve_alerter() -> Path | None:
    for candidate in (LOCAL_ALERTER, Path("/opt/homebrew/bin/alerter"), Path("/usr/local/bin/alerter")):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    found = shutil.which("alerter")
    return Path(found) if found else None


def emit_notify_payload(
    title: str,
    message: str,
    subtitle: str = "",
    hub_path: Path | None = None,
    *,
    note_id: str | None = None,
    item_key: str | None = None,
) -> str:
    payload: dict[str, str] = {
        "title": title,
        "message": message,
        "subtitle": subtitle,
    }
    if hub_path:
        payload["hub_path"] = str(hub_path.resolve())
    if note_id:
        payload["note_id"] = note_id
    if item_key:
        payload["item_key"] = item_key
    return NOTIFY_PREFIX + json.dumps(payload, ensure_ascii=False)


def parse_notify_stdout(stdout: str) -> list[dict[str, str]]:
    specs: list[dict[str, str]] = []
    for line in stdout.splitlines():
        if not line.startswith(NOTIFY_PREFIX):
            continue
        try:
            data = json.loads(line[len(NOTIFY_PREFIX) :])
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("title") and data.get("message") is not None:
            specs.append(data)
    return specs


def _notify_alerter(
    binary: Path,
    title: str,
    message: str,
    subtitle: str,
    hub_path: Path,
    verbose: bool,
) -> str | None:
    group = f"zotero-digest-{hub_path.stem}"
    cmd = [
        str(binary),
        "--title",
        title,
        "--message",
        message,
        "--actions",
        f"{SUMMARY_ACTION},{DEFER_ACTION}",
        "--close-label",
        "关闭",
        "--timeout",
        "0",
        "--group",
        group,
    ]
    if subtitle:
        cmd.extend(["--subtitle", subtitle])

    result = subprocess.run(cmd, capture_output=True, text=True)
    action = (result.stdout or "").strip()
    if verbose:
        print(f"[alerter] exit={result.returncode} action={action!r}", file=sys.stderr)
        if result.stderr.strip():
            print(f"  stderr: {result.stderr.strip()}", file=sys.stderr)
    if result.returncode != 0:
        if verbose:
            print("[alerter] 失败，尝试降级到 terminal-notifier", file=sys.stderr)
        return None
    if hub_path.exists() and is_publish_action(action):
        subprocess.run(["open", str(hub_path.resolve())], check=False)
    return action


def _escape_applescript(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _notify_terminal_notifier(
    binary: Path,
    title: str,
    message: str,
    subtitle: str,
    open_url: str | None,
    sender: str,
    verbose: bool,
) -> bool:
    cmd = [
        str(binary),
        "-sender",
        sender,
        "-title",
        title,
        "-message",
        message,
        "-group",
        "zotero-digest",
    ]
    if subtitle:
        cmd.extend(["-subtitle", subtitle])
    if open_url:
        cmd.extend(["-open", open_url])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if verbose:
        print(f"[terminal-notifier] exit={result.returncode}", file=sys.stderr)
        if result.stdout.strip():
            print(f"  stdout: {result.stdout.strip()}", file=sys.stderr)
        if result.stderr.strip():
            print(f"  stderr: {result.stderr.strip()}", file=sys.stderr)
    return result.returncode == 0


def _notify_osascript(title: str, message: str, subtitle: str, verbose: bool) -> bool:
    msg = _escape_applescript(message[:250])
    tit = _escape_applescript(title)
    if subtitle:
        sub = _escape_applescript(subtitle[:100])
        script = f'display notification "{msg}" with title "{tit}" subtitle "{sub}" sound name "Glass"'
    else:
        script = f'display notification "{msg}" with title "{tit}" sound name "Glass"'

    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
    )
    err = (result.stderr or "").lower()
    broken = any(x in err for x in ("invalid", "connection", "failure", "error received"))
    if verbose:
        print(f"[osascript] exit={result.returncode} broken={broken}", file=sys.stderr)
        if result.stderr.strip():
            print(f"  stderr: {result.stderr.strip()}", file=sys.stderr)
    return result.returncode == 0 and not broken


def _fallback_alert(hub_path: Path | None, verbose: bool) -> None:
    subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"], check=False)
    if hub_path and hub_path.exists():
        subprocess.run(["open", str(hub_path.resolve())], check=False)
    if verbose:
        print("[fallback] 已播放提示音并打开中转页", file=sys.stderr)


def detect_sender() -> str:
    """launchd 后台与终端前台使用不同 sender，便于在系统设置里授权。"""
    if os.environ.get("LAUNCHD_JOB") or os.environ.get("XPC_SERVICE_NAME"):
        return "com.apple.loginwindow"
    term = os.environ.get("TERM_PROGRAM", "")
    if term == "Apple_Terminal":
        return "com.apple.Terminal"
    if term == "iTerm.app":
        return "com.iterm2"
    # VS Code / Cursor 内置终端
    if os.environ.get("VSCODE_INJECTION"):
        return "com.microsoft.VSCode"
    return "com.apple.Terminal"


def notify_macos(
    title: str,
    message: str,
    subtitle: str = "",
    hub_path: Path | None = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> tuple[bool, str | None]:
    if dry_run:
        print(f"\n[通知] {title}")
        if subtitle:
            print(f"  副标题: {subtitle}")
        print(f"  {message}")
        if hub_path:
            print(f"  按钮「{SUMMARY_ACTION}」→ {hub_path.resolve().as_uri()}")
            print(f"  按钮「{DEFER_ACTION}」→ 保留缓存，暂不写入 App 当日内容")
        return True, SUMMARY_ACTION

    hub_uri = hub_path.resolve().as_uri() if hub_path and hub_path.exists() else None
    sender = detect_sender()
    alerter = _resolve_alerter()
    binary = _resolve_terminal_notifier()

    if verbose:
        print(f"[notify] sender={sender} alerter={alerter} binary={binary}", file=sys.stderr)

    # 1) alerter（带「查看总结」「下次再推」操作按钮）
    if alerter and hub_path and hub_path.exists():
        action = _notify_alerter(alerter, title, message, subtitle, hub_path, verbose)
        if action is not None:
            return True, action

    # 2) terminal-notifier（点击通知正文跳转；无推迟按钮，视为立即发布）
    if binary:
        if _notify_terminal_notifier(binary, title, message, subtitle, hub_uri, sender, verbose):
            return True, IMMEDIATE_PUBLISH_ACTION
        if _notify_terminal_notifier(binary, title, message, subtitle, None, sender, verbose):
            if hub_path and hub_path.exists():
                subprocess.run(["open", str(hub_path.resolve())], check=False)
            return True, IMMEDIATE_PUBLISH_ACTION

    # 3) osascript（需在 系统设置→通知→脚本编辑器 或 终端 中允许）
    if _notify_osascript(title, message, subtitle, verbose):
        if hub_path and hub_path.exists():
            subprocess.run(["open", str(hub_path.resolve())], check=False)
        return True, IMMEDIATE_PUBLISH_ACTION

    # 4) 兜底：声音 + 打开页面
    _fallback_alert(hub_path, verbose)
    print(
        "\n未能弹出系统通知。请在「系统设置 → 通知」中开启以下任一应用的通知：\n"
        "  • 终端 (Terminal)\n"
        "  • 脚本编辑器 (Script Editor)\n"
        "  • alerter（带「查看总结」「下次再推」按钮，推荐: brew install vjeantet/tap/alerter）\n"
        "  • terminal-notifier（若列表中有）\n"
        "然后重新运行: run.sh --test-notify --verbose-notify\n",
        file=sys.stderr,
    )
    return False, None


def diagnose() -> None:
    print("=== Zotero 简报 通知诊断 ===")
    alerter = _resolve_alerter()
    binary = _resolve_terminal_notifier()
    print(f"alerter: {alerter or '未找到（建议 brew install vjeantet/tap/alerter）'}")
    print(f"terminal-notifier: {binary or '未找到'}")
    print(f"sender: {detect_sender()}")
    print(f"TERM_PROGRAM: {os.environ.get('TERM_PROGRAM', '(无)')}")
    notify_macos(
        title="Zotero 简报诊断",
        subtitle="通知测试",
        message="如果你看到这条通知，说明通道正常。",
        verbose=True,
    )
