#!/usr/bin/env bash
#
# Carrel demo-readiness check.
#
# Runs the in-Python smoke check against the running backend. Use
# before any investor demo or design-partner walkthrough — if it
# exits 0, the live demo will not embarrass you.
#
# What it checks (each gates a specific demo failure mode I've seen):
#
#   1. Backend reachable on 127.0.0.1:8000
#   2. Local-API token resolvable (fixes the stale-cache bug class)
#   3. /api/documents returns 200 with the auth header
#   4. /api/plan returns events + suggestions
#   5. /api/plan/deadlines surfaces the deadline detector output
#   6. The first document's detail loads with chunks (citation flight
#      needs both)
#   7. At least one calendar feed exists (otherwise the Plan view
#      lands on the empty-state CTA, not the grid)
#   8. SRS pipeline answers (drives the dashboard's "next best action"
#      card)
#
# Run from the repo root:
#
#     bash script/demo-readiness.sh
#

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT_DIR/.venv/bin/python"

if [[ ! -x "$PY" ]]; then
  echo "Python venv not found at $PY"
  echo "Run from a Codex checkout that has had build_and_run.sh run at least once."
  exit 2
fi

exec "$PY" "$ROOT_DIR/script/_demo_check.py"
