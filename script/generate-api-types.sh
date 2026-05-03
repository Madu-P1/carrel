#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT/.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python"
fi

PORT="$("$PYTHON_BIN" - <<'PY'
import socket

sock = socket.socket()
sock.bind(("127.0.0.1", 0))
print(sock.getsockname()[1])
sock.close()
PY
)"

if [ ! -d "$ROOT/frontend/node_modules" ]; then
  corepack pnpm --dir "$ROOT/frontend" install --frozen-lockfile
fi

cd "$ROOT"
"$PYTHON_BIN" -m uvicorn main:app --host 127.0.0.1 --port "$PORT" >/tmp/einstein-openapi.log 2>&1 &
SERVER_PID=$!
cleanup() {
  kill "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT

for _ in $(seq 1 40); do
  if curl -sf "http://127.0.0.1:$PORT/openapi.json" >/dev/null; then
    break
  fi
  sleep 0.25
done

if ! curl -sf "http://127.0.0.1:$PORT/openapi.json" >/dev/null; then
  echo "OpenAPI server failed to start; see /tmp/einstein-openapi.log" >&2
  exit 1
fi

corepack pnpm --dir "$ROOT/frontend" exec openapi-typescript \
  "http://127.0.0.1:$PORT/openapi.json" \
  -o "$ROOT/frontend/src/services/api/types.gen.ts"
