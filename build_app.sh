#!/bin/bash
# 构建可双击打开的 macOS 应用
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="Zotero 简报.app"
APP_DIR="$PROJECT_DIR/$APP_NAME"
CONTENTS="$APP_DIR/Contents"
MACOS="$CONTENTS/MacOS"
RES="$CONTENTS/Resources"

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
if sysctl -n hw.optional.arm64 2>/dev/null | grep -q 1; then
  exec arch -arm64 "$PYTHON" "$PROJECT/launcher.py"
else
  exec "$PYTHON" "$PROJECT/launcher.py"
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
</dict>
</plist>
PLIST

# 可选：链到桌面（-n 避免目标已是目录 symlink 时在 .app 包内再嵌一层）
DESKTOP_LINK="$HOME/Desktop/Zotero 简报.app"
ln -sfn "$APP_DIR" "$DESKTOP_LINK" 2>/dev/null || true

echo ""
echo "完成！双击打开："
echo "  $APP_DIR"
echo "  或桌面快捷方式: $DESKTOP_LINK"
