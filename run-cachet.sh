#!/usr/bin/env bash
#
# Build + run Cachet — the VAULT UI (Lectern / Vault / VerifyResults).
# This is the proper interface. Do NOT build the standalone "Verify/Shelf"
# shell off main; this script always builds the vault shell (--mode cachet
# from THIS worktree, where CachetApp.tsx is the vault shell).
#
# Usage:  ./run-cachet.sh            # build, then serve at http://127.0.0.1:8000
#         ./run-cachet.sh --serve    # skip the build, just serve the current dist
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=/Users/madu/Desktop/Codex/.venv/bin/python

if [[ "${1:-}" != "--serve" ]]; then
  # First run on a fresh clone needs deps.
  if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
    echo "==> installing frontend deps (one time)…"
    ( cd "$ROOT/frontend" && corepack pnpm install )
  fi
  echo "==> building the vault frontend  (vite build --mode cachet)…"
  ( cd "$ROOT/frontend" && corepack pnpm exec vite build --mode cachet )
fi

# Free the port if a previous instance is still bound.
lsof -ti tcp:8000 | xargs kill 2>/dev/null || true
sleep 1

echo "==> serving Cachet (deterministic, offline, no egress) at http://127.0.0.1:8000"
echo "    Ctrl-C to stop."
exec "$PY" "$ROOT/script/serve-cachet.py"
