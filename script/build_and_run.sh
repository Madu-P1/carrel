#!/usr/bin/env bash
set -euo pipefail

# Make sure standalone-installed tools are reachable. The pnpm and bun
# installers add to ~/.zshrc, but build_and_run.sh is often invoked in
# a session where the shell rc updates haven't taken effect yet — for
# example, immediately after `./install.sh` exits without restarting
# the terminal. Prepend each known install location if it exists; the
# `command -v` checks downstream then resolve normally.
#
# Crucially, this ALSO makes Node visible. pnpm-standalone places its
# bundled Node at ~/Library/pnpm/bin/node, and the build:macos script
# invokes `node` directly. Without this prepend, the build fails at
# "exec: node: not found" inside tsc's binstub.
[[ -d "$HOME/Library/pnpm/bin" ]] && export PATH="$HOME/Library/pnpm/bin:$PATH"
[[ -d "$HOME/.local/share/pnpm" ]] && export PATH="$HOME/.local/share/pnpm:$PATH"
[[ -d "$HOME/.bun/bin" ]] && export PATH="$HOME/.bun/bin:$PATH"
[[ -d "$HOME/.local/bin" ]] && export PATH="$HOME/.local/bin:$PATH"

MODE="run"
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
  echo "usage: $0 [run|--debug|--logs|--telemetry|--verify]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    run|--debug|debug|--logs|logs|--telemetry|telemetry|--verify|verify)
      MODE="$1"
      shift
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

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

ensure_local_api_token() {
  # PR-S1 + S4 follow-up: bash launcher must agree with Swift on the
  # local-API token. Swift's LocalApiToken.resolve() reads/writes a
  # mode-0600 file at this path; we mirror that contract here so a
  # uvicorn spawned by this script uses the same token the WKWebView
  # gets injected with. Without this, every fetch from the bundled
  # frontend 403's because Python generated a fresh random token at
  # boot that does not match what Swift hands to the WebView.
  local token_dir="$HOME/Library/Application Support/Carrel"
  local token_path="$token_dir/local-api-token"

  if [[ ! -f "$token_path" ]]; then
    mkdir -p "$token_dir"
    # URL-safe base64 over 32 random bytes — matches secrets.token_urlsafe(32)
    # on the Python side and Swift's LocalApiToken.resolve() output.
    local generated
    generated="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32), end="")')"
    (umask 077 && printf '%s' "$generated" > "$token_path")
  fi

  CARREL_LOCAL_API_TOKEN="$(cat "$token_path")"
  export CARREL_LOCAL_API_TOKEN
}

ensure_backend() {
  mkdir -p "$DIST_DIR"

  ensure_local_api_token

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
  # Pick whichever JS runner is on PATH. pnpm is the project's declared
  # packageManager and what CI uses, so prefer it. bun and npm stay as
  # fallbacks for devs who already have them set up.
  #
  # The PATH prepend at the top of this script means standalone-installed
  # pnpm and bun are reachable here even in non-restarted shells.
  local runner=""
  if command -v pnpm >/dev/null 2>&1; then
    runner="pnpm"
  elif command -v corepack >/dev/null 2>&1; then
    runner="corepack-pnpm"
  elif command -v bun >/dev/null 2>&1; then
    runner="bun"
  elif command -v npm >/dev/null 2>&1; then
    runner="npm"
  else
    echo "No JS runner found (pnpm/bun/corepack/npm)." >&2
    echo "Run ./install.sh to provision pnpm, or install one manually." >&2
    exit 1
  fi

  # Self-heal: if node_modules is missing (fresh clone, deleted by mistake,
  # SKIP_LAUNCH path of install.sh), populate it before the build. This
  # catches the "tsc: command not found" failure mode that surfaces when
  # the build script reaches for tsc inside a missing node_modules/.bin.
  if [[ ! -d "$ROOT_DIR/frontend/node_modules" ]]; then
    echo "frontend/node_modules missing — running install (~30-60s on first run)..."
    case "$runner" in
      pnpm) pnpm --dir "$ROOT_DIR/frontend" install ;;
      corepack-pnpm) corepack pnpm --dir "$ROOT_DIR/frontend" install ;;
      bun) ( cd "$ROOT_DIR/frontend" && bun install ) ;;
      npm) ( cd "$ROOT_DIR/frontend" && npm install ) ;;
    esac
  fi

  # Build the macOS bundle.
  case "$runner" in
    pnpm) pnpm --dir "$ROOT_DIR/frontend" build:macos ;;
    corepack-pnpm) corepack pnpm --dir "$ROOT_DIR/frontend" build:macos ;;
    bun) ( cd "$ROOT_DIR/frontend" && bun run build:macos ) ;;
    npm) ( cd "$ROOT_DIR/frontend" && npm run build:macos ) ;;
  esac
}

pkill -x "$APP_NAME" >/dev/null 2>&1 || true

prepare_frontend_resources

# Regenerate AppIcon.icns if icon-source.png was updated since the last
# build. Noops quietly when icon-source.png is absent.
"$ROOT_DIR/script/generate-icon.sh" || true

swift build --package-path "$PROJECT_DIR"
BUILD_DIR="$(swift build --package-path "$PROJECT_DIR" --show-bin-path)"
BUILD_BINARY="$BUILD_DIR/$APP_NAME"

rm -rf "$APP_BUNDLE"
mkdir -p "$APP_MACOS" "$APP_RESOURCES"
cp "$BUILD_BINARY" "$APP_BINARY"

# Bundle the Swift sidecar binaries beside the main executable so a
# DMG-distributed .app finds them via CARREL_BUNDLE_MACOS (set in
# BackendSupervisor.swift, read by ai/native_bridge_paths.py). Without
# these copies dev mode still works (the helper falls through to
# .build/debug), but Vision OCR and Apple Foundation Models both break
# the moment a user lacks a Codex checkout.
cp "$BUILD_DIR/EinsteinIngestionBridge" "$APP_MACOS/EinsteinIngestionBridge"
cp "$BUILD_DIR/EinsteinAFMBridge" "$APP_MACOS/EinsteinAFMBridge"
chmod +x "$APP_MACOS/EinsteinIngestionBridge" "$APP_MACOS/EinsteinAFMBridge"
if [[ -f "$PROJECT_DIR/Resources/app.new.html" ]]; then
  cp "$PROJECT_DIR/Resources/app.new.html" "$APP_RESOURCES/app.new.html"
fi
if [[ -d "$PROJECT_DIR/Resources/assets.new" ]]; then
  cp -R "$PROJECT_DIR/Resources/assets.new" "$APP_RESOURCES/assets.new"
fi
# Floating companion cube — the WKWebView in FloatingCompanionWindow.swift
# loads this via Bundle.main.url(forResource: "companion-floating", ...).
# Without the copy the lookup returns nil at applicationDidFinishLaunching
# time and the cube never appears (the Swift side logs an error to OSLog
# but the user just sees nothing). Package.swift's executableTarget does
# not declare resources, so the manual cp is the only path into the
# bundle today.
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
  <key>NSPrincipalClass</key>
  <string>NSApplication</string>
</dict>
</plist>
PLIST

launch_app() {
  /usr/bin/open -n "$APP_BUNDLE"
}

ensure_backend

case "$MODE" in
  run)
    launch_app
    ;;
  --debug|debug)
    lldb -- "$APP_BINARY"
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
