#!/usr/bin/env bash
# Build and launch Cachet as a native macOS .app — the "build it like Carrel" path.
#
# Reuses the EinsteinDesktop Swift shell with CACHET_BUNDLE: WebAppView loads
# cachet.new.html (not Carrel's app.new.html) and BackendSupervisor runs the
# backend in CACHET_ONLY mode. We bake CACHET_BUNDLE=1 into the bundle's
# Info.plist (LSEnvironment) so `open` passes it through, and we pre-start the
# CACHET_ONLY backend with a known-good venv so the app's supervisor finds it
# already healthy (sidestepping its own Python resolution, which has the same
# worktree-.venv gap as run-cachet.sh did).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_DIR="$ROOT_DIR/macos-app"
DIST_DIR="$ROOT_DIR/dist"
APP_NAME="EinsteinDesktop"
APP_BUNDLE="$DIST_DIR/Cachet.app"
APP_CONTENTS="$APP_BUNDLE/Contents"
APP_MACOS="$APP_CONTENTS/MacOS"
APP_RESOURCES="$APP_CONTENTS/Resources"
APP_BINARY="$APP_MACOS/$APP_NAME"
INFO_PLIST="$APP_CONTENTS/Info.plist"
PORT="${CACHET_PORT:-8000}"
mkdir -p "$DIST_DIR"

# 1. A Python that actually has the deps (worktree-safe: fall back to the main
#    checkout's .venv via the common git dir, like run-cachet.sh).
PY="${CACHET_PYTHON:-}"
if [[ -z "$PY" || ! -x "$PY" ]]; then
  _MAIN_VENV=""
  if _CG="$(cd "$ROOT_DIR" && git rev-parse --git-common-dir 2>/dev/null)"; then
    case "$_CG" in /*) ;; *) _CG="$ROOT_DIR/$_CG" ;; esac
    _MAIN_ROOT="$(cd "$(dirname "$_CG")" 2>/dev/null && pwd || true)"
    [[ -n "$_MAIN_ROOT" ]] && _MAIN_VENV="$_MAIN_ROOT/.venv/bin/python"
  fi
  for _c in "$ROOT_DIR/.venv/bin/python" "$_MAIN_VENV"; do
    if [[ -n "$_c" && -x "$_c" ]]; then PY="$_c"; break; fi
  done
fi
[[ -n "$PY" && -x "$PY" ]] || PY="python3"
if ! "$PY" -c 'import httpx, fastapi, uvicorn' 2>/dev/null; then
  echo "run-cachet-app: '$PY' is missing backend deps (httpx/fastapi/uvicorn)." >&2
  echo "run-cachet-app: set CACHET_PYTHON to a venv that has them, e.g.:" >&2
  echo "  CACHET_PYTHON=${_MAIN_VENV:-/path/to/Codex/.venv/bin/python} $0" >&2
  exit 1
fi
echo "Cachet backend python -> $PY"

# 2. The local API token: same file the app's LocalApiToken + WebView read, so the
#    pre-started backend and the WKWebView agree on the token.
TOKEN_DIR="$HOME/Library/Application Support/Carrel"
TOKEN_PATH="$TOKEN_DIR/local-api-token"
mkdir -p "$TOKEN_DIR"
[[ -s "$TOKEN_PATH" ]] || (umask 077 && "$PY" -c 'import secrets;print(secrets.token_urlsafe(32),end="")' >"$TOKEN_PATH")

# 3. Pre-start the CACHET_ONLY backend on $PORT.
if lsof -ti tcp:"$PORT" >/dev/null 2>&1; then
  echo "note: port $PORT busy; clearing the stale listener so the Cachet backend can bind."
  lsof -ti tcp:"$PORT" | xargs kill 2>/dev/null || true
  sleep 1
fi
echo "Starting Cachet backend (CACHET_ONLY) on 127.0.0.1:$PORT ..."
# Docling/RapidOCR typed-node ingest adds ~50s/15-page PDF (full OCR even on
# digital text-layer PDFs) and blocks the worker, which makes the app flash
# "Backend offline" and time out uploads mid-ingest. The Cachet verify catch is
# deterministic over `chunks` (not typed nodes), so skip the typed-node path:
# ingest drops to a few seconds. Re-enable post-demo for the nodes retrieval work.
CACHET_ONLY=1 CARREL_AI_PROVIDER="${CARREL_AI_PROVIDER:-ollama}" \
  INGEST_USE_DOCLING="${INGEST_USE_DOCLING:-false}" RETRIEVAL_USE_NODES="${RETRIEVAL_USE_NODES:-false}" \
  CARREL_LOCAL_API_TOKEN="$(cat "$TOKEN_PATH")" \
  "$PY" -m uvicorn main:app --host 127.0.0.1 --port "$PORT" --app-dir "$ROOT_DIR" \
  >"$DIST_DIR/cachet-backend.log" 2>&1 &
BACKEND_PID=$!
trap 'kill "$BACKEND_PID" 2>/dev/null || true' EXIT
for _ in $(seq 1 40); do
  curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && { echo "backend healthy."; break; }
  kill -0 "$BACKEND_PID" 2>/dev/null || { echo "backend exited; log:" >&2; tail -20 "$DIST_DIR/cachet-backend.log" >&2; exit 1; }
  sleep 1
done

# 4. Build the Cachet frontend bundle (cachet.new.html) with the current source.
echo "Building Cachet frontend bundle (build:cachet) ..."
if command -v corepack >/dev/null 2>&1; then
  corepack pnpm --dir "$ROOT_DIR/frontend" build:cachet
else
  ( cd "$ROOT_DIR/frontend" && npm run build:cachet )
fi

# 5. Build the Swift shell + the PDF/OCR sidecar (no macOS-26 dependency).
# NOTE: building both products in ONE `swift build --product A --product B` call
# silently builds only the bridge and skips EinsteinDesktop (observed 2026-06-04),
# so the app binary goes stale and source edits never ship. Build them in separate
# invocations, and fail loud if the app binary did not actually get produced.
echo "Building the macOS shell (swift build, first run is slow) ..."
swift build --package-path "$PROJECT_DIR" --product EinsteinDesktop
swift build --package-path "$PROJECT_DIR" --product EinsteinIngestionBridge
BUILD_DIR="$(swift build --package-path "$PROJECT_DIR" --show-bin-path)"
if [[ ! -x "$BUILD_DIR/$APP_NAME" ]]; then
  echo "run-cachet-app: swift build did not produce $BUILD_DIR/$APP_NAME" >&2
  exit 1
fi

# 6. Assemble Cachet.app (distinct bundle id so it never collides with Carrel's).
echo "Assembling $APP_BUNDLE ..."
rm -rf "$APP_BUNDLE"
mkdir -p "$APP_MACOS" "$APP_RESOURCES"
cp "$BUILD_DIR/$APP_NAME" "$APP_BINARY"; chmod +x "$APP_BINARY"
cp "$BUILD_DIR/EinsteinIngestionBridge" "$APP_MACOS/EinsteinIngestionBridge"; chmod +x "$APP_MACOS/EinsteinIngestionBridge"
cp "$PROJECT_DIR/Resources/cachet.new.html" "$APP_RESOURCES/cachet.new.html"
# build:cachet emits a parallel cachet-assets.new/ (self-hosted fonts etc.) that
# cachet.new.html references relatively; it MUST sit beside the html in Resources.
[[ -d "$PROJECT_DIR/Resources/cachet-assets.new" ]] && cp -R "$PROJECT_DIR/Resources/cachet-assets.new" "$APP_RESOURCES/cachet-assets.new"
[[ -f "$PROJECT_DIR/Resources/app.new.html" ]] && cp "$PROJECT_DIR/Resources/app.new.html" "$APP_RESOURCES/app.new.html"
[[ -d "$PROJECT_DIR/Resources/assets.new" ]] && cp -R "$PROJECT_DIR/Resources/assets.new" "$APP_RESOURCES/assets.new"
[[ -f "$PROJECT_DIR/Resources/AppIcon.icns" ]] && cp "$PROJECT_DIR/Resources/AppIcon.icns" "$APP_RESOURCES/AppIcon.icns"

cat >"$INFO_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDisplayName</key><string>Cachet</string>
  <key>CFBundleName</key><string>Cachet</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundleExecutable</key><string>$APP_NAME</string>
  <key>CFBundleIdentifier</key><string>com.madu.Cachet</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>LSEnvironment</key><dict><key>CACHET_BUNDLE</key><string>1</string><key>CACHET_BACKEND_PYTHON</key><string>$PY</string><key>INGEST_USE_DOCLING</key><string>false</string><key>RETRIEVAL_USE_NODES</key><string>false</string></dict>
  <key>NSAppTransportSecurity</key><dict>
    <key>NSAllowsArbitraryLoadsInWebContent</key><true/>
    <key>NSAllowsLocalNetworking</key><true/>
  </dict>
  <key>NSPrincipalClass</key><string>NSApplication</string>
</dict>
</plist>
PLIST

# 7. Launch. LSEnvironment in the plist carries CACHET_BUNDLE into the app.
echo "Launching Cachet.app ..."
open -n "$APP_BUNDLE"
echo ""
echo "Cachet.app is open (native window). Backend log: $DIST_DIR/cachet-backend.log"
echo "Leave this terminal running; Ctrl+C stops the Cachet backend."
wait "$BACKEND_PID"
