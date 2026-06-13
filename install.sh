#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$PROJECT_DIR/.venv"
BIN_DIR="$PROJECT_DIR/bin"
NOTIFIER="$BIN_DIR/terminal-notifier"

echo "==> 创建 Python 虚拟环境"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip -q
"$VENV/bin/pip" install -r "$PROJECT_DIR/requirements.txt" -q

mkdir -p "$PROJECT_DIR/logs" "$PROJECT_DIR/summaries" "$PROJECT_DIR/hubs" "$BIN_DIR"

if [[ ! -f "$PROJECT_DIR/.env" ]]; then
  echo "==> 创建 .env（请填入 DEEPSEEK_API_KEY）"
  cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
fi

install_notifier() {
  # 复制真实 Mach-O，避免 shell 包装脚本被 subprocess 误用
  local src="$1"
  if [[ -f "$src" && $(stat -f%z "$src" 2>/dev/null || stat -c%s "$src") -lt 4096 ]]; then
    local real
    real=$(grep -o '"/[^"]*terminal-notifier"' "$src" | tr -d '"' | head -1)
    [[ -n "$real" && -f "$real" ]] && src="$real"
  fi
  cp "$src" "$NOTIFIER"
  chmod +x "$NOTIFIER"
  echo "    terminal-notifier → $NOTIFIER"
}

echo "==> 安装 terminal-notifier"
if [[ -x "$NOTIFIER" ]]; then
  echo "    已存在"
elif command -v terminal-notifier &>/dev/null; then
  install_notifier "$(command -v terminal-notifier)"
elif [[ -x "/opt/homebrew/bin/terminal-notifier" ]]; then
  install_notifier "/opt/homebrew/bin/terminal-notifier"
elif [[ -x "/usr/local/bin/terminal-notifier" ]]; then
  install_notifier "/usr/local/bin/terminal-notifier"
else
  echo "    未找到，建议: brew install terminal-notifier && bash install.sh"
fi

ALERTER="$BIN_DIR/alerter"
echo "==> 安装 alerter（通知「查看总结」按钮）"
if [[ -x "$ALERTER" ]]; then
  echo "    已存在"
elif command -v alerter &>/dev/null; then
  cp "$(command -v alerter)" "$ALERTER"
  chmod +x "$ALERTER"
  echo "    alerter → $ALERTER"
elif [[ -x "/opt/homebrew/bin/alerter" ]]; then
  cp "/opt/homebrew/bin/alerter" "$ALERTER"
  chmod +x "$ALERTER"
  echo "    alerter → $ALERTER"
elif [[ -x "/usr/local/bin/alerter" ]]; then
  cp "/usr/local/bin/alerter" "$ALERTER"
  chmod +x "$ALERTER"
  echo "    alerter → $ALERTER"
else
  echo "    未找到，建议: brew install vjeantet/tap/alerter && bash install.sh"
  echo "    （无 alerter 时仍可点击通知正文跳转 HTML）"
fi

echo "==> 生成并加载 launchd 定时任务"
cd "$PROJECT_DIR"
"$VENV/bin/python" -c "from launchd_mgr import write_plist, reload_launchd; from config_manager import load_config; c=load_config(); write_plist(c); ok,m=reload_launchd(c); print(m)"

chmod +x "$PROJECT_DIR/start_ui.sh" "$PROJECT_DIR/run.sh" "$PROJECT_DIR/digest.py" "$PROJECT_DIR/app.py"

echo "==> 构建桌面应用"
bash "$PROJECT_DIR/build_app.sh"

echo ""
echo "安装完成！"
echo "  双击打开: $PROJECT_DIR/Zotero 简报.app"
echo "  或桌面:   ~/Desktop/Zotero 简报.app"
echo "  命令行:   bash $PROJECT_DIR/start_ui.sh"
