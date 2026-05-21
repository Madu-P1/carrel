#!/usr/bin/env bash
set -euo pipefail

ALLOW_UNSIGNED=0
TARGET=""
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_BUNDLE="$ROOT_DIR/dist/EinsteinDesktop.app"

usage() {
  echo "usage: script/validate_public_beta_package.sh [--allow-unsigned] [dmg-path]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --allow-unsigned)
      ALLOW_UNSIGNED=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      if [[ -n "$TARGET" ]]; then
        usage
        exit 2
      fi
      TARGET="$1"
      shift
      ;;
  esac
done

if [[ -z "$TARGET" ]]; then
  TARGET="$ROOT_DIR/dist/Carrel-public-beta.dmg"
fi

if [[ ! -d "$APP_BUNDLE" ]]; then
  echo "Missing app bundle: $APP_BUNDLE" >&2
  exit 1
fi

/usr/libexec/PlistBuddy -c "Print :CFBundleDisplayName" "$APP_BUNDLE/Contents/Info.plist" | grep -qx "Carrel"
/usr/libexec/PlistBuddy -c "Print :CFBundleIdentifier" "$APP_BUNDLE/Contents/Info.plist" | grep -qx "com.madu.EinsteinDesktop"
test -x "$APP_BUNDLE/Contents/MacOS/EinsteinDesktop"
test -f "$APP_BUNDLE/Contents/Resources/app.new.html"
test -d "$APP_BUNDLE/Contents/Resources/assets.new"
test -f "$APP_BUNDLE/Contents/Resources/AppIcon.icns"
test -f "$APP_BUNDLE/Contents/Resources/demo-library/carrel-demo-clean-reading.pdf"
test -f "$APP_BUNDLE/Contents/Resources/demo-library/carrel-demo-table-heavy.pdf"
test -f "$APP_BUNDLE/Contents/Resources/demo-library/carrel-demo-ocr-boundary.pdf"

# Native Swift sidecar binaries must ship inside the bundle. Without
# them a DMG-distributed .app has no .build/debug fallback, so Vision
# OCR (EinsteinIngestionBridge) and Apple Foundation Models
# (EinsteinAFMBridge) both fail at runtime. build_and_run.sh copies +
# chmod +x both; this check guards against a regression there.
if ! test -x "$APP_BUNDLE/Contents/MacOS/EinsteinIngestionBridge"; then
  echo "Missing or non-executable native bridge: $APP_BUNDLE/Contents/MacOS/EinsteinIngestionBridge" >&2
  echo "Re-run build_and_run.sh; it copies the sidecar binaries into the bundle." >&2
  exit 1
fi
if ! test -x "$APP_BUNDLE/Contents/MacOS/EinsteinAFMBridge"; then
  echo "Missing or non-executable native bridge: $APP_BUNDLE/Contents/MacOS/EinsteinAFMBridge" >&2
  echo "Re-run build_and_run.sh; it copies the sidecar binaries into the bundle." >&2
  exit 1
fi

if ! /usr/bin/codesign -dv "$APP_BUNDLE" >/dev/null 2>&1; then
  if [[ $ALLOW_UNSIGNED -eq 1 ]]; then
    echo "Warning: app bundle is not signed." >&2
  else
    echo "App bundle is not signed. Re-run package_public_beta.sh with Developer ID credentials." >&2
    exit 1
  fi
elif ! /usr/bin/codesign --verify --deep --strict "$APP_BUNDLE"; then
  if [[ $ALLOW_UNSIGNED -eq 1 ]]; then
    echo "Warning: app bundle signature is not release-valid. Sign with CARREL_CODESIGN_IDENTITY for beta distribution." >&2
  else
    echo "App bundle signature is not release-valid." >&2
    exit 1
  fi
fi

if [[ -f "$TARGET" ]]; then
  /usr/bin/hdiutil imageinfo "$TARGET" >/dev/null
else
  echo "DMG not found at $TARGET" >&2
  exit 1
fi

curl -fsS "http://127.0.0.1:8000/api/health" >/dev/null || {
  echo "Warning: backend health check is not reachable. Run build_and_run.sh --verify before release." >&2
}

echo "Public beta package validation passed."
