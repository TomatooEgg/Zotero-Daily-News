#!/bin/bash
# 构建可双击打开的 macOS 应用
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="Zotero 简报.app"
LINK_APP_NAME="Zotero Digest Link.app"
APP_DIR="$PROJECT_DIR/$APP_NAME"
LINK_DIR="$PROJECT_DIR/$LINK_APP_NAME"
CONTENTS="$APP_DIR/Contents"
MACOS="$CONTENTS/MacOS"
RES="$CONTENTS/Resources"
LINK_MACOS="$LINK_DIR/Contents/MacOS"
LINK_RES="$LINK_DIR/Contents/Resources"

echo "==> 构建 $APP_NAME"
rm -rf "$APP_DIR"
mkdir -p "$MACOS" "$RES"

echo "$PROJECT_DIR" > "$RES/project.path"

cat > "$MACOS/launcher" << 'LAUNCHER'
#!/bin/bash
BUNDLE="$(cd "$(dirname "$0")/../.." && pwd)"
PROJECT="$(cat "$BUNDLE/Contents/Resources/project.path" 2>/dev/null || dirname "$BUNDLE")"
cd "$PROJECT" || exit 1
PYTHON="$PROJECT/.venv/bin/python"
SUPPORT_DIR="$HOME/Library/Application Support/Zotero Digest"
if [ "$#" -gt 0 ]; then
  remember_front=1
  for arg in "$@"; do
    case "$arg" in
      *activate=1*|*activate=true*|*activate=yes*) remember_front=0 ;;
    esac
  done
  if [ "$remember_front" -eq 1 ]; then
    mkdir -p "$SUPPORT_DIR"
    osascript -e 'tell application "System Events" to get name of first application process whose frontmost is true' \
      > "$SUPPORT_DIR/front_app.txt" 2>/dev/null || true
  fi
fi
if sysctl -n hw.optional.arm64 2>/dev/null | grep -q 1; then
  exec arch -arm64 "$PYTHON" -m zotero_daily_news.launcher "$@"
else
  exec "$PYTHON" -m zotero_daily_news.launcher "$@"
fi
LAUNCHER
chmod +x "$MACOS/launcher"

cat > "$CONTENTS/Info.plist" << PLIST
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
    <key>CFBundleShortVersionString</key><string>1.0</string>
    <key>CFBundleVersion</key><string>1</string>
    <key>LSMinimumSystemVersion</key><string>11.0</string>
    <key>NSHighResolutionCapable</key><true/>
    <key>LSUIElement</key><false/>
    <key>LSMultipleInstancesProhibited</key><true/>
</dict>
</plist>
PLIST

echo "==> 构建 ${LINK_APP_NAME} (zotero-digest:// handler)"
rm -rf "$LINK_DIR"
mkdir -p "$LINK_MACOS" "$LINK_RES"

echo "$PROJECT_DIR" > "$LINK_RES/project.path"

cat > "$LINK_MACOS/launcher" << 'LINK_LAUNCHER'
#!/bin/bash
BUNDLE="$(cd "$(dirname "$0")/../.." && pwd)"
PROJECT="$(cat "$BUNDLE/Contents/Resources/project.path" 2>/dev/null || dirname "$BUNDLE")"
cd "$PROJECT" || exit 1
PYTHON="$PROJECT/.venv/bin/python"
MAIN_APP="$PROJECT/Zotero 简报.app"
SUPPORT_DIR="$HOME/Library/Application Support/Zotero Digest"
mkdir -p "$SUPPORT_DIR"
for arg in "$@"; do
  case "$arg" in
    zotero-digest:*)
      background=1
      case "$arg" in
        *activate=1*|*activate=true*|*activate=yes*) background=0 ;;
      esac
      echo "$(date '+%Y-%m-%d %H:%M:%S') shell handle background=$background $arg" >> "$SUPPORT_DIR/link.log" 2>/dev/null || true
      if [ "$background" -eq 1 ]; then
        osascript -e 'tell application "System Events" to get name of first application process whose frontmost is true' \
          > "$SUPPORT_DIR/front_app.txt" 2>/dev/null || true
      fi
      if [[ -d "$MAIN_APP" ]]; then
        if [ "$background" -eq 1 ]; then
          open -g -a "$MAIN_APP" "$arg"
        else
          open -a "$MAIN_APP" "$arg"
        fi
      elif [ "$background" -eq 1 ]; then
        open -g "$arg"
      else
        open "$arg"
      fi
      exit 0
      ;;
  esac
done
if sysctl -n hw.optional.arm64 2>/dev/null | grep -q 1; then
  exec arch -arm64 "$PYTHON" -m zotero_daily_news.digest_link_handler "$@"
else
  exec "$PYTHON" -m zotero_daily_news.digest_link_handler "$@"
fi
LINK_LAUNCHER
chmod +x "$LINK_MACOS/launcher"

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
    <key>CFBundleShortVersionString</key><string>1.2</string>
    <key>CFBundleVersion</key><string>4</string>
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

# 注册深链接到 Link 中转（先注销其它同名 handler，避免 hub 误路由到 _new / dist 包）
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
unregister_link_handler() {
  local app_path="$1"
  if [[ -d "$app_path" ]]; then
    "$LSREGISTER" -u "$app_path" 2>/dev/null || true
    echo "    已注销: $app_path"
  fi
}
if [[ -x "$LSREGISTER" ]]; then
  unregister_link_handler "$PROJECT_DIR/dist/stage/Zotero 简报.app"
  unregister_link_handler "$PROJECT_DIR/dist/stage/$LINK_APP_NAME"
  unregister_link_handler "$PROJECT_DIR/new app/Zotero Digest Link_new.app"
  unregister_link_handler "$PROJECT_DIR/new/$LINK_APP_NAME"
  unregister_link_handler "/Applications/Zotero Digest Link_new.app"
  unregister_link_handler "/Applications/$LINK_APP_NAME"
  "$LSREGISTER" -f "$APP_DIR" 2>/dev/null || true
  "$LSREGISTER" -f "$LINK_DIR" 2>/dev/null || true
  echo "    已注册本地深链接: $LINK_DIR"
fi

# 可选：链到桌面（-n 避免目标已是目录 symlink 时在 .app 包内再嵌一层）
DESKTOP_LINK="$HOME/Desktop/Zotero 简报.app"
ln -sfn "$APP_DIR" "$DESKTOP_LINK" 2>/dev/null || true

echo ""
echo "完成！双击打开："
echo "  $APP_DIR"
echo "  深链接中转: $LINK_DIR"
echo "  （hub 冷启动依赖 Link.app 处理 zotero-digest://，无需手动打开）"
echo "  或桌面快捷方式: $DESKTOP_LINK"
