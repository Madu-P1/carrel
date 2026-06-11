#!/usr/bin/env bash
# Package Cachet for Windows (and any non-Mac OS): the cachet-mode frontend
# dist + the Python backend + the loopback server (script/serve-cachet.py)
# + a double-clickable run-cachet.bat. The launcher provisions a venv from
# requirements-cachet-win.txt (repo requirements minus docling/torch/
# transformers, which the deterministic verify path never imports).
#
# Usage: script/package-cachet-windows.sh [output-dir]   (default: dist/)
# Produces: <output-dir>/Cachet-Windows.zip
#
# The staged file set is the one proven by the 2026-06-11 fresh-venv smoke
# test; if main.py grows a new top-level import or mount, add it HERE or the
# package boots broken on someone else's machine.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-$ROOT_DIR/dist}"
STAGE="$(mktemp -d)/Cachet-Windows"
mkdir -p "$STAGE/script" "$STAGE/frontend" "$STAGE/assets"

if [[ ! -f "$ROOT_DIR/frontend/dist/index.html" ]]; then
  echo "frontend/dist missing - build it first:" >&2
  echo "    cd frontend && corepack pnpm exec vite build --mode cachet" >&2
  exit 1
fi
# Guard: dist must be the cachet build, not a stale Carrel one. The cachet
# flag is baked into the JS; the cheap proxy is the CachetApp shell string.
if ! grep -rqs "Independent verification for high-stakes drafts" "$ROOT_DIR/frontend/dist/assets/"; then
  echo "frontend/dist does not look like a --mode cachet build; rebuild it." >&2
  exit 1
fi

cp "$ROOT_DIR"/{main.py,db.py,api_models.py,app_logging.py,app_runtime.py,schema.sql} "$STAGE/"
cp -R "$ROOT_DIR"/{routes,services,ai,migrations,static} "$STAGE/"
cp -R "$ROOT_DIR/frontend/dist" "$STAGE/frontend/dist"
cp "$ROOT_DIR/script/serve-cachet.py" "$STAGE/script/"
cp -R "$ROOT_DIR/assets/demo-library" "$STAGE/assets/demo-library"
cp "$ROOT_DIR/packaging/windows/requirements-cachet-win.txt" \
   "$ROOT_DIR/packaging/windows/run-cachet.bat" \
   "$ROOT_DIR/packaging/windows/provision-models.bat" \
   "$ROOT_DIR/packaging/windows/README.txt" "$STAGE/"
find "$STAGE" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find "$STAGE" -name ".DS_Store" -delete 2>/dev/null || true

mkdir -p "$OUT_DIR"
rm -f "$OUT_DIR/Cachet-Windows.zip"
( cd "$(dirname "$STAGE")" && zip -qr "$OUT_DIR/Cachet-Windows.zip" "Cachet-Windows" )
rm -rf "$(dirname "$STAGE")"
echo "wrote $OUT_DIR/Cachet-Windows.zip ($(du -h "$OUT_DIR/Cachet-Windows.zip" | cut -f1))"
