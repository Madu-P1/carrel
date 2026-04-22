#!/usr/bin/env bash
# Generate macos-app/Resources/AppIcon.icns from icon-source.png.
#
# Apple expects a .icns bundle containing multiple resolutions. We use
# `iconutil` (shipped with Xcode command-line tools) which takes a
# directory of correctly-named PNGs and packs them into an .icns.
#
# Input:   macos-app/Resources/icon-source.png
#          (square PNG, ideally 1024x1024, any power-of-two smaller is OK
#          but 1024 is recommended so Retina displays look sharp)
#
# Output:  macos-app/Resources/AppIcon.icns
#          Bundled into Einstein.app/Contents/Resources by build_and_run.sh.
#
# Usage:
#   script/generate-icon.sh              # idempotent — skips if source older
#   script/generate-icon.sh --force      # regenerate even if up-to-date
#
# Honest noop: if icon-source.png does not exist, we print a one-line hint
# and exit 0. This lets CI + dev machines that haven't dropped a logo in
# yet build without error.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="$REPO_ROOT/macos-app/Resources/icon-source.png"
TARGET="$REPO_ROOT/macos-app/Resources/AppIcon.icns"
ICONSET="$REPO_ROOT/macos-app/Resources/AppIcon.iconset"

if [[ ! -f "$SOURCE" ]]; then
  echo "generate-icon: no source at $SOURCE — skipping (drop a 1024×1024 PNG there to enable)"
  exit 0
fi

FORCE=0
if [[ "${1:-}" == "--force" ]]; then
  FORCE=1
fi

if [[ $FORCE -eq 0 && -f "$TARGET" && "$SOURCE" -ot "$TARGET" ]]; then
  echo "generate-icon: $TARGET up to date"
  exit 0
fi

command -v sips >/dev/null 2>&1 || { echo "generate-icon: sips not found (macOS only)" >&2; exit 1; }
command -v iconutil >/dev/null 2>&1 || { echo "generate-icon: iconutil not found (install Xcode CLT)" >&2; exit 1; }

rm -rf "$ICONSET"
mkdir -p "$ICONSET"

# Apple naming convention: icon_<size>x<size>{,@2x}.png. macOS selects the
# right file for the display pixel density at render time. 16 through 512
# base sizes cover every UI surface (Dock, Finder sidebar, Cmd-Tab, About).
declare -a PAIRS=(
  "16:icon_16x16.png"
  "32:icon_16x16@2x.png"
  "32:icon_32x32.png"
  "64:icon_32x32@2x.png"
  "128:icon_128x128.png"
  "256:icon_128x128@2x.png"
  "256:icon_256x256.png"
  "512:icon_256x256@2x.png"
  "512:icon_512x512.png"
  "1024:icon_512x512@2x.png"
)

for pair in "${PAIRS[@]}"; do
  size="${pair%%:*}"
  name="${pair##*:}"
  sips -z "$size" "$size" "$SOURCE" --out "$ICONSET/$name" >/dev/null
done

iconutil --convert icns --output "$TARGET" "$ICONSET"
rm -rf "$ICONSET"

echo "generate-icon: wrote $TARGET"
