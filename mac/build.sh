#!/usr/bin/env bash
# Builds Glass.app with the Swift compiler from Xcode or the Command Line Tools:
#   ./build.sh            → build/Glass.app, then launches it
#   ./build.sh install    → also copies it to /Applications
# Needs macOS 14+. Liquid Glass (live refraction) turns on automatically on macOS 26
# when built with Xcode 26 / Swift 6.2; older setups get the vibrancy fallback.
set -euo pipefail
cd "$(dirname "$0")"

APP=build/Glass.app
ARCH=$(uname -m)
pkill -x Glass 2>/dev/null || true
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

echo "→ Compiling ($ARCH)…"
swiftc -O -parse-as-library -swift-version 5 \
  -target "$ARCH-apple-macos14.0" \
  -framework AppKit -framework SwiftUI -framework ScreenCaptureKit \
  -framework Speech -framework AVFoundation -framework Carbon \
  Sources/*.swift -o "$APP/Contents/MacOS/Glass"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Glass</string>
  <key>CFBundleDisplayName</key><string>Glass</string>
  <key>CFBundleIdentifier</key><string>com.glass.sidebar</string>
  <key>CFBundleExecutable</key><string>Glass</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>2.0</string>
  <key>CFBundleVersion</key><string>2</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>LSUIElement</key><true/>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSMicrophoneUsageDescription</key><string>Glass listens when you use dictation or voice mode.</string>
  <key>NSSpeechRecognitionUsageDescription</key><string>Glass turns your speech into text for dictation and voice mode.</string>
  <key>NSScreenCaptureUsageDescription</key><string>Glass takes a screenshot when you ask about your screen.</string>
</dict>
</plist>
PLIST

# ad-hoc signature so macOS remembers the permissions you grant
codesign --force --deep --sign - "$APP" >/dev/null

if [[ "${1:-}" == "install" ]]; then
  rm -rf /Applications/Glass.app
  cp -R "$APP" /Applications/
  APP=/Applications/Glass.app
  echo "✓ Installed to /Applications"
fi

echo "✓ Built $APP"
open "$APP"
