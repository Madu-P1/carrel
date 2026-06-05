#!/usr/bin/env bash
#
# run-cachet.sh — run the STANDALONE Cachet app locally, the Carrel way.
#
# Cachet is its own app over the shared engine (see CACHET_ONLY in main.py and
# register_cachet_routes in routes/__init__.py): the backend serves ONLY the
# verification product routes (verify, briefs, documents, jobs, search, system),
# never Carrel's. This script starts that Cachet backend plus the Cachet
# frontend, mirroring build_and_run.sh.
#
# The bundled .app (the generic Swift WKWebView shell pointed at
# macos-app/Resources/cachet.new.html, produced by `pnpm --dir frontend
# build:cachet`) is the Xcode/GUI packaging step and is NOT launched here.
# Iterate via the Vite dev server this script starts.
#
# Env overrides: CACHET_PORT (default 8000), CACHET_PYTHON (default ./.venv/bin/python).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PORT="${CACHET_PORT:-8000}"

# The backend does not auto-load .env, so source it (ANTHROPIC_API_KEY, provider
# config) into the environment without echoing any value. Never printed.
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source ./.env
  set +a
fi

# Local-API token: the same mode-0600 file the Swift shell / WKWebView uses, so
# the frontend and backend agree on the token (mirrors build_and_run.sh).
TOKEN_DIR="$HOME/Library/Application Support/Carrel"
TOKEN_PATH="$TOKEN_DIR/local-api-token"
if [[ ! -f "$TOKEN_PATH" ]]; then
  mkdir -p "$TOKEN_DIR"
  (umask 077 && python3 -c 'import secrets; print(secrets.token_urlsafe(32), end="")' > "$TOKEN_PATH")
fi
export CARREL_LOCAL_API_TOKEN
CARREL_LOCAL_API_TOKEN="$(cat "$TOKEN_PATH")"
export CACHET_ONLY=1

# Resolve a Python that actually has the repo's deps. Prefer CACHET_PYTHON, then
# this checkout's .venv. A git worktree has no .venv of its own, so fall back to
# the MAIN checkout's .venv (found via the common git dir) before bare python3 --
# otherwise we silently land on a system python missing httpx/fastapi/etc.
PY="${CACHET_PYTHON:-}"
if [[ -z "$PY" || ! -x "$PY" ]]; then
  _MAIN_VENV=""
  if _CG="$(cd "$ROOT_DIR" && git rev-parse --git-common-dir 2>/dev/null)"; then
    case "$_CG" in /*) ;; *) _CG="$ROOT_DIR/$_CG" ;; esac
    _MAIN_ROOT="$(cd "$(dirname "$_CG")" 2>/dev/null && pwd || true)"
    [[ -n "$_MAIN_ROOT" ]] && _MAIN_VENV="$_MAIN_ROOT/.venv/bin/python"
  fi
  for _cand in "$ROOT_DIR/.venv/bin/python" "$_MAIN_VENV"; do
    if [[ -n "$_cand" && -x "$_cand" ]]; then PY="$_cand"; break; fi
  done
fi
[[ -n "$PY" && -x "$PY" ]] || PY="python3"

# Fail loud with the fix, not a cryptic ModuleNotFoundError mid-boot.
if ! "$PY" -c 'import httpx, fastapi, uvicorn' 2>/dev/null; then
  echo "run-cachet: '$PY' is missing backend deps (httpx / fastapi / uvicorn)." >&2
  echo "run-cachet: point CACHET_PYTHON at a venv that has them, e.g.:" >&2
  echo "  CACHET_PYTHON=${_MAIN_VENV:-/path/to/Codex/.venv/bin/python} $0" >&2
  exit 1
fi
echo "Cachet backend python -> $PY"

echo "Cachet backend (CACHET_ONLY) -> http://127.0.0.1:${PORT}"
"$PY" -m uvicorn main:app --host 127.0.0.1 --port "$PORT" &
BACKEND_PID=$!
trap 'kill "$BACKEND_PID" 2>/dev/null || true' EXIT

# Frontend dev server. Cachet lives at /cachet.html; the token reaches the dev
# app via VITE_CARREL_LOCAL_API_TOKEN so its API calls authenticate.
echo "Cachet frontend (Vite dev) -> open http://localhost:5173/cachet.html"
cd frontend
VITE_CARREL_LOCAL_API_TOKEN="$CARREL_LOCAL_API_TOKEN" node_modules/.bin/vite
