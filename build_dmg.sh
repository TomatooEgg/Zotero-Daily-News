#!/bin/bash
# 打包可直接分发的 macOS DMG（内含自包含 .app）
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="Zotero 简报.app"
LINK_APP_NAME="Zotero Digest Link.app"
ARCH="${ZOTERO_DAILY_NEWS_MAC_ARCH:-$(uname -m)}"
BUILD_VENV="$PROJECT_DIR/.build-macos-venv"
BUILD_PYTHON="$BUILD_VENV/bin/python"
BUILD_EXE="$PROJECT_DIR/build/macos-exe"
STAGE="$PROJECT_DIR/dist/stage"
APP_DIR="$STAGE/$APP_NAME"
LINK_DIR="$STAGE/$LINK_APP_NAME"
RUNTIME_DIR="$APP_DIR/Contents/Resources/runtime"
DMG_NAME="Zotero-Daily-News-macOS-${ARCH}.dmg"
DMG_PATH="$PROJECT_DIR/dist/$DMG_NAME"

echo "==> Preparing staging directory"
rm -rf "$STAGE" "$BUILD_EXE"
mkdir -p "$RUNTIME_DIR" "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources" \
  "$LINK_DIR/Contents/MacOS" "$LINK_DIR/Contents/Resources"
ln -s /Applications "$STAGE/Applications"

echo "==> Installing build dependencies"
if [[ ! -x "$BUILD_PYTHON" ]]; then
  python3 -m venv "$BUILD_VENV"
fi
"$BUILD_PYTHON" -m pip install --upgrade pip -q
"$BUILD_PYTHON" -m pip install -r "$PROJECT_DIR/requirements.txt" -q
"$BUILD_PYTHON" -m pip install "cx_Freeze>=7.2" -q

echo "==> Freezing Python runtime"
(
  cd "$PROJECT_DIR"
  ZDN_MACOS_BUILD_EXE="$BUILD_EXE" "$BUILD_PYTHON" setup_macos.py build_exe
)
rsync -a "$BUILD_EXE/" "$RUNTIME_DIR/"
mkdir -p "$RUNTIME_DIR/bin"

install_binary() {
  local name="$1"
  local dest="$RUNTIME_DIR/bin/$name"
  if [[ -x "$PROJECT_DIR/bin/$name" ]]; then
    cp "$PROJECT_DIR/bin/$name" "$dest"
    chmod +x "$dest"
    echo "    ${name} -> project bin/"
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
    echo "    ${name} -> ${src}"
    return
  fi
  echo "    warning: ${name} not found; notification support may be limited"
}

echo "==> Copying notification helpers"
install_binary terminal-notifier
install_binary alerter

cat > "$APP_DIR/Contents/MacOS/launcher" << 'LAUNCHER'
#!/bin/bash
BUNDLE="$(cd "$(dirname "$0")/../.." && pwd)"
RUNTIME="$BUNDLE/Contents/Resources/runtime"
EXECUTABLE="$RUNTIME/launcher"
SUPPORT_DIR="$HOME/Library/Application Support/Zotero Digest"
cd "$RUNTIME" || exit 1
if [ "$#" -gt 0 ]; then
  mkdir -p "$SUPPORT_DIR"
  osascript -e 'tell application "System Events" to get name of first application process whose frontmost is true' \
    > "$SUPPORT_DIR/front_app.txt" 2>/dev/null || true
fi
exec "$EXECUTABLE" "$@"
LAUNCHER
chmod +x "$APP_DIR/Contents/MacOS/launcher"

cat > "$LINK_DIR/Contents/MacOS/launcher" << 'LINK_LAUNCHER'
#!/bin/bash
BUNDLE="$(cd "$(dirname "$0")/../.." && pwd)"
if [[ -d "$BUNDLE/../Zotero 简报.app/Contents/Resources/runtime" ]]; then
  MAIN_APP="$BUNDLE/../Zotero 简报.app"
else
  MAIN_APP="$(cat "$BUNDLE/Contents/Resources/main_app.path" 2>/dev/null || dirname "$BUNDLE")/Zotero 简报.app"
fi
EXECUTABLE="$MAIN_APP/Contents/Resources/runtime/launcher"
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
if [[ -x "$EXECUTABLE" ]]; then
  exec "$EXECUTABLE" --digest-link-handler "$@"
fi
exit 0
LINK_LAUNCHER
chmod +x "$LINK_DIR/Contents/MacOS/launcher"
echo "$(dirname "$APP_DIR")" > "$LINK_DIR/Contents/Resources/main_app.path"

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
    <key>CFBundleVersion</key><string>3</string>
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
    <key>CFBundleVersion</key><string>3</string>
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

echo "==> Creating DMG"
hdiutil create \
  -volname "Zotero 简报" \
  -srcfolder "$STAGE" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

echo ""
echo "Done."
echo "  DMG: $DMG_PATH"
echo "  Size: $(du -h "$DMG_PATH" | cut -f1)"
echo ""
echo "Usage:"
echo "  1. Open the DMG and drag Zotero 简报.app to Applications."
echo "  2. On first launch, complete the setup wizard."
echo "  3. Scheduled delivery is enabled only after validation succeeds."
