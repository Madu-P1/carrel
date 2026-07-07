#!/usr/bin/env bash
set -euo pipefail

# Build the frontend bundle and run the Cachet backend.
#
# The Einstein-era native macOS shell (the Swift app plus its PDF/OCR
# and Apple Foundation Models sidecars) was extracted out of this repo
# on 2026-07-07; the repo is now the Cachet verification engine +
# verify-source home. This
# script therefore only builds the frontend bundle and serves the
# FastAPI backend on 127.0.0.1:8000.
#
# Make sure standalone-installed tools are reachable. The pnpm and bun
# installers add to ~/.zshrc, but this script is often invoked in a
# session where the shell rc updates haven't taken effect yet. Prepend
# each known install location if it exists; the `command -v` checks
# downstream then resolve normally. This ALSO makes Node visible: the
# build:macos script invokes `node` directly.
[[ -d "$HOME/Library/pnpm/bin" ]] && export PATH="$HOME/Library/pnpm/bin:$PATH"
[[ -d "$HOME/.local/share/pnpm" ]] && export PATH="$HOME/.local/share/pnpm:$PATH"
[[ -d "$HOME/.bun/bin" ]] && export PATH="$HOME/.bun/bin:$PATH"
[[ -d "$HOME/.local/bin" ]] && export PATH="$HOME/.local/bin:$PATH"

MODE="run"
BACKEND_URL="http://127.0.0.1:8000/api/health"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"
BACKEND_PIDFILE="$DIST_DIR/cachet-backend.pid"
BACKEND_LOG="$DIST_DIR/cachet-backend.log"

usage() {
  echo "usage: $0 [run|--logs|--verify]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    run|--logs|logs|--verify|verify)
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

ensure_backend() {
  mkdir -p "$DIST_DIR"

  # Always nuke any prior backend bound to our slot first; the start
  # cost is ~1s and predictability beats reusing a possibly-stale one.
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

  # Self-heal: if node_modules is missing (fresh clone), populate it
  # before the build. Catches the "tsc: command not found" failure mode.
  if [[ ! -d "$ROOT_DIR/frontend/node_modules" ]]; then
    echo "frontend/node_modules missing — running install (~30-60s on first run)..."
    case "$runner" in
      pnpm) pnpm --dir "$ROOT_DIR/frontend" install ;;
      corepack-pnpm) corepack pnpm --dir "$ROOT_DIR/frontend" install ;;
      bun) ( cd "$ROOT_DIR/frontend" && bun install ) ;;
      npm) ( cd "$ROOT_DIR/frontend" && npm install ) ;;
    esac
  fi

  # Build the frontend bundle (writes dist/app.new.html + dist/assets.new).
  case "$runner" in
    pnpm) pnpm --dir "$ROOT_DIR/frontend" build:macos ;;
    corepack-pnpm) corepack pnpm --dir "$ROOT_DIR/frontend" build:macos ;;
    bun) ( cd "$ROOT_DIR/frontend" && bun run build:macos ) ;;
    npm) ( cd "$ROOT_DIR/frontend" && npm run build:macos ) ;;
  esac
}

prepare_frontend_resources
ensure_backend

case "$MODE" in
  run)
    echo "Backend running on http://127.0.0.1:8000 — frontend bundle at $DIST_DIR/app.new.html"
    ;;
  --logs|logs)
    tail -f "$BACKEND_LOG"
    ;;
  --verify|verify)
    curl -fsS "$BACKEND_URL" >/dev/null
    ;;
  *)
    usage
    exit 2
    ;;
esac
