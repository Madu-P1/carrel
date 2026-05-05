#!/usr/bin/env bash
set -euo pipefail

MODE="run"
FRONTEND_MODE="${EINSTEIN_FRONTEND:-new}"
APP_NAME="EinsteinDesktop"
BUNDLE_ID="com.madu.EinsteinDesktop"
MIN_SYSTEM_VERSION="14.0"
BACKEND_URL="http://127.0.0.1:8000/api/health"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_DIR="$ROOT_DIR/macos-app"
DIST_DIR="$ROOT_DIR/dist"
APP_BUNDLE="$DIST_DIR/$APP_NAME.app"
APP_CONTENTS="$APP_BUNDLE/Contents"
APP_MACOS="$APP_CONTENTS/MacOS"
APP_RESOURCES="$APP_CONTENTS/Resources"
APP_BINARY="$APP_MACOS/$APP_NAME"
INFO_PLIST="$APP_CONTENTS/Info.plist"
BACKEND_PIDFILE="$DIST_DIR/einstein-backend.pid"
BACKEND_LOG="$DIST_DIR/einstein-backend.log"

usage() {
  echo "usage: $0 [run|--debug|--logs|--telemetry|--verify] [--frontend new|legacy]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    run|--debug|debug|--logs|logs|--telemetry|telemetry|--verify|verify)
      MODE="$1"
      shift
      ;;
    --frontend)
      if [[ $# -lt 2 ]]; then
        usage
        exit 2
      fi
      FRONTEND_MODE="$(printf '%s' "$2" | tr '[:upper:]' '[:lower:]')"
      shift 2
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

if [[ "$FRONTEND_MODE" != "legacy" && "$FRONTEND_MODE" != "new" ]]; then
  echo "Unsupported frontend mode: $FRONTEND_MODE" >&2
  usage
  exit 2
fi

pick_python() {
  local candidate
  for candidate in \
    "$ROOT_DIR/.venv/bin/python3" \
    "$ROOT_DIR/.venv/bin/python" \
    "$(command -v python3 2>/dev/null || true)"
  do
    if [[ -z "$candidate" || ! -x "$candidate" ]]; then
      continue
    fi
    if "$candidate" - <<'PY' >/dev/null 2>&1
import fastapi
import uvicorn
PY
    then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

wait_for_backend() {
  local attempts=30
  local delay=0.5
  for ((i = 0; i < attempts; i++)); do
    if curl -fsS "$BACKEND_URL" >/dev/null 2>&1; then
      return 0
    fi
    sleep "$delay"
  done
  return 1
}

ensure_backend() {
  mkdir -p "$DIST_DIR"

  # Kill any uvicorn process bound to our slot, not just the one named in
  # the pidfile. Two earlier failure modes prompted this:
  #   1. The pidfile was stale (last build crashed before writing it) so
  #      the previous backend kept running and the new launch saw "port
  #      already bound" — opaque under `nohup`.
  #   2. A previous backend launched against a different Python (e.g.,
  #      brew vs venv) had stale imports that returned 200 on /health
  #      but EPERM on every other route. The "is it healthy?" probe
  #      below would return 0, the script would re-use the broken
  #      backend, and the dashboard would render "Could not load."
  # Always nuke first; the start cost is ~1s and predictability beats it.
  if [[ -f "$BACKEND_PIDFILE" ]]; then
    local old_pid
    old_pid="$(cat "$BACKEND_PIDFILE" 2>/dev/null || true)"
    if [[ -n "$old_pid" ]] && kill -0 "$old_pid" >/dev/null 2>&1; then
      kill "$old_pid" >/dev/null 2>&1 || true
    fi
    rm -f "$BACKEND_PIDFILE"
  fi
  pkill -f "uvicorn main:app" >/dev/null 2>&1 || true
  sleep 1

  local python_bin
  python_bin="$(pick_python)" || {
    echo "Could not find a Python runtime with FastAPI and Uvicorn installed." >&2
    exit 1
  }

  "$python_bin" - "$python_bin" "$ROOT_DIR" "$BACKEND_LOG" "$BACKEND_PIDFILE" <<'PY'
import subprocess
import sys
from pathlib import Path

python_bin, root_dir, backend_log, backend_pidfile = sys.argv[1:]

log_path = Path(backend_log)
log_path.parent.mkdir(parents=True, exist_ok=True)

with log_path.open("ab") as stream:
    proc = subprocess.Popen(
        [
            python_bin,
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
            "--app-dir",
            root_dir,
        ],
        cwd=root_dir,
        stdin=subprocess.DEVNULL,
        stdout=stream,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

Path(backend_pidfile).write_text(str(proc.pid))
PY

  if ! wait_for_backend; then
    echo "Backend failed to start. Recent log output:" >&2
    tail -n 40 "$BACKEND_LOG" >&2 || true
    exit 1
  fi
}

prepare_frontend_resources() {
  if [[ "$FRONTEND_MODE" == "new" ]]; then
    # Pick whichever JS runner is on PATH. The script used to require
    # `corepack pnpm`, which left bun-only environments stuck. The
    # build:macos npm-script is now runner-agnostic (vite + node
    # invocations only), so any of these work the same.
    if command -v bun >/dev/null 2>&1; then
      ( cd "$ROOT_DIR/frontend" && bun run build:macos )
    elif command -v pnpm >/dev/null 2>&1; then
      pnpm --dir "$ROOT_DIR/frontend" build:macos
    elif command -v corepack >/dev/null 2>&1; then
      corepack pnpm --dir "$ROOT_DIR/frontend" build:macos
    elif command -v npm >/dev/null 2>&1; then
      ( cd "$ROOT_DIR/frontend" && npm run build:macos )
    else
      echo "No JS runner found (bun/pnpm/corepack/npm). Install one of them." >&2
      exit 1
    fi
  fi
}

pkill -x "$APP_NAME" >/dev/null 2>&1 || true

prepare_frontend_resources

# Regenerate AppIcon.icns if icon-source.png was updated since the last
# build. Noops quietly when icon-source.png is absent.
"$ROOT_DIR/script/generate-icon.sh" || true

swift build --package-path "$PROJECT_DIR"
BUILD_BINARY="$(swift build --package-path "$PROJECT_DIR" --show-bin-path)/$APP_NAME"

rm -rf "$APP_BUNDLE"
mkdir -p "$APP_MACOS" "$APP_RESOURCES"
cp "$BUILD_BINARY" "$APP_BINARY"
cp "$PROJECT_DIR/Resources/app.html.legacy" "$APP_RESOURCES/app.html.legacy"
if [[ -f "$PROJECT_DIR/Resources/app.new.html" ]]; then
  cp "$PROJECT_DIR/Resources/app.new.html" "$APP_RESOURCES/app.new.html"
fi
if [[ -d "$PROJECT_DIR/Resources/assets.new" ]]; then
  cp -R "$PROJECT_DIR/Resources/assets.new" "$APP_RESOURCES/assets.new"
fi
# Floating companion (NSPanel WKWebView). Self-contained, no asset deps.
if [[ -f "$PROJECT_DIR/Resources/companion-floating.html" ]]; then
  cp "$PROJECT_DIR/Resources/companion-floating.html" "$APP_RESOURCES/companion-floating.html"
fi
if [[ -d "$ROOT_DIR/assets/demo-library" ]]; then
  mkdir -p "$APP_RESOURCES/demo-library"
  cp -R "$ROOT_DIR/assets/demo-library/." "$APP_RESOURCES/demo-library/"
fi
# Bundle the app icon when the generator produced one. Missing icon is not
# a build failure — just an unbranded Dock tile until the asset is added.
ICON_PRESENT=0
if [[ -f "$PROJECT_DIR/Resources/AppIcon.icns" ]]; then
  cp "$PROJECT_DIR/Resources/AppIcon.icns" "$APP_RESOURCES/AppIcon.icns"
  ICON_PRESENT=1
fi
chmod +x "$APP_BINARY"

ICON_PLIST_ENTRY=""
if [[ $ICON_PRESENT -eq 1 ]]; then
  # Both keys are required for older and newer macOS. CFBundleIconFile is
  # the classic key; CFBundleIconName is for asset-catalog-based icons but
  # a plain .icns with the same basename resolves fine here.
  ICON_PLIST_ENTRY=$'  <key>CFBundleIconFile</key>\n  <string>AppIcon</string>\n  <key>CFBundleIconName</key>\n  <string>AppIcon</string>\n'
fi

cat >"$INFO_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDisplayName</key>
  <string>Carrel</string>
  <key>CFBundleExecutable</key>
  <string>$APP_NAME</string>
${ICON_PLIST_ENTRY}  <key>CFBundleIdentifier</key>
  <string>$BUNDLE_ID</string>
  <key>CFBundleName</key>
  <string>Carrel</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>LSMinimumSystemVersion</key>
  <string>$MIN_SYSTEM_VERSION</string>
  <key>NSAppTransportSecurity</key>
  <dict>
    <key>NSAllowsArbitraryLoadsInWebContent</key>
    <true/>
    <key>NSAllowsLocalNetworking</key>
    <true/>
  </dict>
  <key>NSCalendarsFullAccessUsageDescription</key>
  <string>Carrel reads your Apple Calendar so the dashboard can suggest study sessions in your free blocks and re-plan when meetings move. No event content is sent off your machine.</string>
  <key>NSPrincipalClass</key>
  <string>NSApplication</string>
</dict>
</plist>
PLIST

launch_app() {
  /usr/bin/open -n --env "EINSTEIN_FRONTEND=$FRONTEND_MODE" "$APP_BUNDLE"
}

ensure_backend

case "$MODE" in
  run)
    launch_app
    ;;
  --debug|debug)
    EINSTEIN_FRONTEND="$FRONTEND_MODE" lldb -- "$APP_BINARY"
    ;;
  --logs|logs)
    launch_app
    /usr/bin/log stream --info --style compact --predicate "process == \"$APP_NAME\""
    ;;
  --telemetry|telemetry)
    launch_app
    /usr/bin/log stream --info --style compact --predicate "subsystem == \"$BUNDLE_ID\""
    ;;
  --verify|verify)
    launch_app
    sleep 2
    pgrep -x "$APP_NAME" >/dev/null
    curl -fsS "$BACKEND_URL" >/dev/null
    ;;
  *)
    usage
    exit 2
    ;;
esac
