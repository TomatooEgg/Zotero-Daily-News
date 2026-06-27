#!/bin/bash
# 打包可直接分发的 macOS DMG（内含自包含 .app）
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="Zotero 简报.app"
LINK_APP_NAME="Zotero Digest Link.app"
ARCH="${ZOTERO_DAILY_NEWS_MAC_ARCH:-$(uname -m)}"
STAGE="$PROJECT_DIR/dist/stage"
APP_DIR="$STAGE/$APP_NAME"
LINK_DIR="$STAGE/$LINK_APP_NAME"
BUNDLE_APP="$APP_DIR/Contents/Resources/app"
DMG_NAME="Zotero-Daily-News-macOS-${ARCH}.dmg"
DMG_PATH="$PROJECT_DIR/dist/$DMG_NAME"

echo "==> 清理并创建 staging"
rm -rf "$STAGE"
mkdir -p "$BUNDLE_APP" "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources" \
  "$LINK_DIR/Contents/MacOS" "$LINK_DIR/Contents/Resources"
ln -s /Applications "$STAGE/Applications"

echo "==> 复制项目文件"
rsync -a \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude 'dist/' \
  --exclude 'summaries/' \
  --exclude 'hubs/' \
  --exclude 'logs/' \
  --exclude 'bin/' \
  --exclude 'Zotero 简报.app/' \
  --exclude 'Zotero Digest Link.app/' \
  --exclude '.env' \
  --exclude 'history.json' \
  --exclude 'queue.json' \
  --exclude 'pending_publish.json' \
  --exclude 'com.*.zotero-digest*.plist' \
  --exclude '__pycache__/' \
  --exclude '.DS_Store' \
  --exclude '.cursor/' \
  "$PROJECT_DIR/" "$BUNDLE_APP/"

mkdir -p "$BUNDLE_APP/summaries" "$BUNDLE_APP/hubs" "$BUNDLE_APP/logs" "$BUNDLE_APP/bin"

echo "==> 创建虚拟环境并安装依赖"
python3 -m venv "$BUNDLE_APP/.venv"
"$BUNDLE_APP/.venv/bin/pip" install --upgrade pip -q
"$BUNDLE_APP/.venv/bin/pip" install -r "$BUNDLE_APP/requirements.txt" -q

install_binary() {
  local name="$1"
  local dest="$BUNDLE_APP/bin/$name"
  if [[ -x "$PROJECT_DIR/bin/$name" ]]; then
    cp "$PROJECT_DIR/bin/$name" "$dest"
    chmod +x "$dest"
    echo "    $name ← 项目 bin/"
    return
  fi
  if command -v "$name" &>/dev/null; then
    local src
    src="$(command -v "$name")"
    if [[ "$name" == "terminal-notifier" && -f "$src" && $(stat -f%z "$src") -lt 4096 ]]; then
      local real
      real=$(grep -o '"/[^"]*terminal-notifier"' "$src" | tr -d '"' | head -1 || true)
      [[ -n "$real" && -f "$real" ]] && src="$real"
    fi
    cp "$src" "$dest"
    chmod +x "$dest"
    echo "    $name ← $src"
    return
  fi
  echo "    警告: 未找到 $name，通知功能可能受限"
}

echo "==> 复制通知工具"
install_binary terminal-notifier
install_binary alerter

if [[ ! -f "$BUNDLE_APP/.env" ]]; then
  cp "$BUNDLE_APP/.env.example" "$BUNDLE_APP/.env"
fi

cat > "$APP_DIR/Contents/MacOS/launcher" << 'LAUNCHER'
#!/bin/bash
BUNDLE="$(cd "$(dirname "$0")/../.." && pwd)"
if [[ -d "$BUNDLE/Contents/Resources/app" ]]; then
  PROJECT="$BUNDLE/Contents/Resources/app"
else
  PROJECT="$(cat "$BUNDLE/Contents/Resources/project.path" 2>/dev/null || dirname "$BUNDLE")"
fi
cd "$PROJECT" || exit 1
PYTHON="$PROJECT/.venv/bin/python"
SUPPORT_DIR="$HOME/Library/Application Support/Zotero Digest"
if [ "$#" -gt 0 ]; then
  mkdir -p "$SUPPORT_DIR"
  osascript -e 'tell application "System Events" to get name of first application process whose frontmost is true' \
    > "$SUPPORT_DIR/front_app.txt" 2>/dev/null || true
fi
if sysctl -n hw.optional.arm64 2>/dev/null | grep -q 1; then
  exec arch -arm64 "$PYTHON" "$PROJECT/launcher.py" "$@"
else
  exec "$PYTHON" "$PROJECT/launcher.py" "$@"
fi
LAUNCHER
chmod +x "$APP_DIR/Contents/MacOS/launcher"

cat > "$LINK_DIR/Contents/MacOS/launcher" << 'LINK_LAUNCHER'
#!/bin/bash
BUNDLE="$(cd "$(dirname "$0")/../.." && pwd)"
if [[ -d "$BUNDLE/../Zotero 简报.app/Contents/Resources/app" ]]; then
  PROJECT="$BUNDLE/../Zotero 简报.app/Contents/Resources/app"
  MAIN_APP="$BUNDLE/../Zotero 简报.app"
else
  PROJECT="$(cat "$BUNDLE/Contents/Resources/project.path" 2>/dev/null || dirname "$BUNDLE")"
  MAIN_APP="$PROJECT/Zotero 简报.app"
fi
cd "$PROJECT" || exit 1
PYTHON="$PROJECT/.venv/bin/python"
SUPPORT_DIR="$HOME/Library/Application Support/Zotero Digest"
mkdir -p "$SUPPORT_DIR"
osascript -e 'tell application "System Events" to get name of first application process whose frontmost is true' \
  > "$SUPPORT_DIR/front_app.txt" 2>/dev/null || true
for arg in "$@"; do
  case "$arg" in
    zotero-digest:*)
      echo "$(date '+%Y-%m-%d %H:%M:%S') shell handle $arg" >> "$SUPPORT_DIR/link.log" 2>/dev/null || true
      if [[ -d "$MAIN_APP" ]]; then
        open -g -a "$MAIN_APP" "$arg"
      else
        open -g "$arg"
      fi
      exit 0
      ;;
  esac
done
if sysctl -n hw.optional.arm64 2>/dev/null | grep -q 1; then
  exec arch -arm64 "$PYTHON" "$PROJECT/digest_link_handler.py" "$@"
else
  exec "$PYTHON" "$PROJECT/digest_link_handler.py" "$@"
fi
LINK_LAUNCHER
chmod +x "$LINK_DIR/Contents/MacOS/launcher"
echo "$BUNDLE_APP" > "$LINK_DIR/Contents/Resources/project.path"

cat > "$APP_DIR/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key><string>zh_CN</string>
    <key>CFBundleExecutable</key><string>launcher</string>
    <key>CFBundleIdentifier</key><string>com.TomatooEgg.zotero-digest.app</string>
    <key>CFBundleName</key><string>Zotero 简报</string>
    <key>CFBundleDisplayName</key><string>Zotero 简报</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleShortVersionString</key><string>1.1</string>
    <key>CFBundleVersion</key><string>2</string>
    <key>LSMinimumSystemVersion</key><string>11.0</string>
    <key>NSHighResolutionCapable</key><true/>
    <key>LSUIElement</key><false/>
    <key>LSMultipleInstancesProhibited</key><true/>
</dict>
</plist>
PLIST

cat > "$LINK_DIR/Contents/Info.plist" << 'LINK_PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key><string>zh_CN</string>
    <key>CFBundleExecutable</key><string>launcher</string>
    <key>CFBundleIdentifier</key><string>com.TomatooEgg.zotero-digest.link</string>
    <key>CFBundleName</key><string>Zotero Digest Link</string>
    <key>CFBundleDisplayName</key><string>Zotero Digest Link</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleShortVersionString</key><string>1.1</string>
    <key>CFBundleVersion</key><string>2</string>
    <key>LSMinimumSystemVersion</key><string>11.0</string>
    <key>NSHighResolutionCapable</key><true/>
    <key>LSUIElement</key><true/>
    <key>CFBundleURLTypes</key>
    <array>
        <dict>
            <key>CFBundleURLName</key><string>com.TomatooEgg.zotero-digest</string>
            <key>CFBundleURLSchemes</key>
            <array><string>zotero-digest</string></array>
        </dict>
    </array>
</dict>
</plist>
LINK_PLIST

# 注册深链接到 Link 中转（避免 dist 旧包占用 scheme）
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
STAGE_APP="$PROJECT_DIR/dist/stage/Zotero 简报.app"
if [[ -x "$LSREGISTER" ]]; then
  if [[ -d "$STAGE_APP" ]]; then
    "$LSREGISTER" -u "$STAGE_APP" 2>/dev/null || true
  fi
  "$LSREGISTER" -f "$APP_DIR" 2>/dev/null || true
  "$LSREGISTER" -f "$LINK_DIR" 2>/dev/null || true
fi

echo "==> 生成 DMG"
hdiutil create \
  -volname "Zotero 简报" \
  -srcfolder "$STAGE" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

echo ""
echo "完成！"
echo "  DMG: $DMG_PATH"
echo "  大小: $(du -h "$DMG_PATH" | cut -f1)"
echo ""
echo "使用方式："
echo "  1. 打开 DMG，将「Zotero 简报.app」拖到「应用程序」"
echo "  2. 首次启动后按向导填写 DeepSeek Key、Zotero 写入 Key 和模型名"
echo "  3. 验证通过后，向导会启用定时推送任务"
