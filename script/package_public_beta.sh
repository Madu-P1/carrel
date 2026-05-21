#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_BUNDLE="$ROOT_DIR/dist/EinsteinDesktop.app"
DMG_PATH="$ROOT_DIR/dist/Carrel-public-beta.dmg"
ENTITLEMENTS="$ROOT_DIR/macos-app/Resources/Carrel.entitlements"
SIGN_IDENTITY="${CARREL_CODESIGN_IDENTITY:-}"
NOTARY_PROFILE="${CARREL_NOTARY_PROFILE:-}"
LOCAL_UNSIGNED=0

usage() {
  cat >&2 <<'USAGE'
usage: script/package_public_beta.sh [--local-unsigned]

By default this creates a real public-beta artifact and requires:
  CARREL_CODESIGN_IDENTITY  Developer ID Application identity
  CARREL_NOTARY_PROFILE    notarytool keychain profile

Use --local-unsigned only for private machine testing. It creates a DMG but
does not make the app distributable through Gatekeeper.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --local-unsigned)
      LOCAL_UNSIGNED=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

detect_developer_id_identity() {
  /usr/bin/security find-identity -v -p codesigning 2>/dev/null \
    | /usr/bin/awk -F '"' '/Developer ID Application/ { print $2; exit }'
}

if [[ -z "$SIGN_IDENTITY" ]]; then
  SIGN_IDENTITY="$(detect_developer_id_identity || true)"
fi

if [[ $LOCAL_UNSIGNED -eq 0 ]]; then
  if [[ -z "$SIGN_IDENTITY" ]]; then
    echo "No Developer ID Application signing identity found." >&2
    echo "Set CARREL_CODESIGN_IDENTITY or install a valid Developer ID certificate." >&2
    exit 1
  fi
  if [[ -z "$NOTARY_PROFILE" ]]; then
    echo "CARREL_NOTARY_PROFILE is required for public-beta notarization." >&2
    echo "Create one with: xcrun notarytool store-credentials <profile-name>" >&2
    exit 1
  fi
fi

# --release builds the Swift targets with -c release for distribution.
"$ROOT_DIR/script/build_and_run.sh" --verify --release

if [[ -n "$SIGN_IDENTITY" ]]; then
  /usr/bin/codesign \
    --force \
    --deep \
    --options runtime \
    --entitlements "$ENTITLEMENTS" \
    --sign "$SIGN_IDENTITY" \
    "$APP_BUNDLE"
  /usr/bin/codesign --verify --deep --strict --verbose=2 "$APP_BUNDLE"
else
  echo "Local unsigned mode: leaving app unsigned." >&2
fi

rm -f "$DMG_PATH"
/usr/bin/hdiutil create \
  -volname "Carrel Public Beta" \
  -srcfolder "$APP_BUNDLE" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

if [[ -n "$SIGN_IDENTITY" ]]; then
  /usr/bin/codesign --force --sign "$SIGN_IDENTITY" "$DMG_PATH"
fi

if [[ -n "$NOTARY_PROFILE" ]]; then
  /usr/bin/xcrun notarytool submit "$DMG_PATH" \
    --keychain-profile "$NOTARY_PROFILE" \
    --wait
  /usr/bin/xcrun stapler staple "$DMG_PATH"
else
  echo "Local unsigned mode: skipping notarization." >&2
fi

if [[ $LOCAL_UNSIGNED -eq 1 ]]; then
  "$ROOT_DIR/script/validate_public_beta_package.sh" --allow-unsigned "$DMG_PATH"
else
  "$ROOT_DIR/script/validate_public_beta_package.sh" "$DMG_PATH"
fi
echo "Packaged $DMG_PATH"
