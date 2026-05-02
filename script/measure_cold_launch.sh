#!/usr/bin/env bash
set -euo pipefail

FRONTEND_MODE="${EINSTEIN_FRONTEND:-new}"
RUNS=1
APP_NAME="EinsteinDesktop"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_BINARY="$ROOT_DIR/dist/$APP_NAME.app/Contents/MacOS/$APP_NAME"
APP_PID=""
WAIT_SECONDS="${CARREL_COLD_LAUNCH_WAIT_SECONDS:-8}"

usage() {
  echo "usage: $0 [--frontend new|legacy] [--runs N]" >&2
}

filter_markers() {
  if command -v rg >/dev/null 2>&1; then
    rg "launch-start|app-interactive|DidFirstMeaningfulPaint"
    return
  fi

  grep -E "launch-start|app-interactive|DidFirstMeaningfulPaint"
}

cleanup() {
  if [[ -n "$APP_PID" ]]; then
    kill "$APP_PID" >/dev/null 2>&1 || true
    wait "$APP_PID" 2>/dev/null || true
  fi
}

trap cleanup EXIT

while [[ $# -gt 0 ]]; do
  case "$1" in
    --frontend)
      if [[ $# -lt 2 ]]; then
        usage
        exit 2
      fi
      FRONTEND_MODE="$(printf '%s' "$2" | tr '[:upper:]' '[:lower:]')"
      shift 2
      ;;
    --runs)
      if [[ $# -lt 2 ]]; then
        usage
        exit 2
      fi
      RUNS="$2"
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

if ! [[ "$RUNS" =~ ^[0-9]+$ ]] || [[ "$RUNS" -lt 1 ]]; then
  echo "Runs must be a positive integer." >&2
  usage
  exit 2
fi

if ! [[ "$WAIT_SECONDS" =~ ^[0-9]+([.][0-9]+)?$ ]] || ! awk -v value="$WAIT_SECONDS" 'BEGIN { exit !(value > 0) }'; then
  echo "CARREL_COLD_LAUNCH_WAIT_SECONDS must be a positive number." >&2
  exit 2
fi

# TODO(cold-launch): replace this unified-log fallback with a deterministic one-shot
# handshake once the native telemetry path is reliable during direct app launches too.

"$ROOT_DIR/script/build_and_run.sh" --verify --frontend "$FRONTEND_MODE" >/dev/null
pkill -x "$APP_NAME" >/dev/null 2>&1 || true

run_log="$(mktemp)"

for ((run_index = 1; run_index <= RUNS; run_index++)); do
  window_start="$(date '+%Y-%m-%d %H:%M:%S')"

  env EINSTEIN_FRONTEND="$FRONTEND_MODE" "$APP_BINARY" >/dev/null 2>/dev/null &
  APP_PID=$!
  sleep "$WAIT_SECONDS"

  log_window="$(
    /usr/bin/log show \
      --info \
      --style compact \
      --start "$window_start" \
      --predicate "process == \"$APP_NAME\"" \
      2>/dev/null \
      | filter_markers || true
  )"

  launch_line="$(printf '%s\n' "$log_window" | grep "launch-start frontend=$FRONTEND_MODE" | tail -n 1 || true)"
  marker_line="$(printf '%s\n' "$log_window" | grep "app-interactive frontend=$FRONTEND_MODE" | tail -n 1 || true)"
  marker_kind="app-interactive"
  if [[ -z "$marker_line" ]]; then
    marker_line="$(printf '%s\n' "$log_window" | grep "DidFirstMeaningfulPaint" | tail -n 1 || true)"
    marker_kind="webkit-first-meaningful-paint"
  fi

  if [[ -z "$launch_line" || -z "$marker_line" ]]; then
    echo "Failed to capture cold-launch markers for run $run_index frontend=$FRONTEND_MODE" >&2
    printf '%s\n' "$log_window" >&2
    exit 1
  fi

  delta_ms="$(python3 - "$launch_line" "$marker_line" <<'PY'
from datetime import datetime
import sys

launch_line, marker_line = sys.argv[1], sys.argv[2]
fmt = "%Y-%m-%d %H:%M:%S.%f"

def parse_timestamp(line: str) -> datetime:
    return datetime.strptime(line[:23], fmt)

delta_ms = (parse_timestamp(marker_line) - parse_timestamp(launch_line)).total_seconds() * 1000
print(f"{delta_ms:.2f}")
PY
)"

  printf '%s\t%s\t%s\n' "$run_index" "$marker_kind" "$delta_ms" >>"$run_log"

  kill "$APP_PID" >/dev/null 2>&1 || true
  wait "$APP_PID" 2>/dev/null || true
  APP_PID=""
  pkill -x "$APP_NAME" >/dev/null 2>&1 || true
  sleep 0.2
done

python3 - "$FRONTEND_MODE" "$run_log" <<'PY'
import json
import math
import statistics
import sys
from pathlib import Path

frontend = sys.argv[1]
run_log = Path(sys.argv[2])

runs = []
for line in run_log.read_text().splitlines():
    if not line.strip():
        continue
    run_index, marker, delta_ms = line.split("\t")
    runs.append(
        {
            "run": int(run_index),
            "marker": marker,
            "delta_ms": float(delta_ms),
        }
    )

if not runs:
    raise SystemExit("No cold-launch runs were recorded.")

values = sorted(run["delta_ms"] for run in runs)

def percentile(sorted_values: list[float], rank: float) -> float:
    index = max(0, math.ceil(rank * len(sorted_values)) - 1)
    return sorted_values[index]

result = {
    "frontend": frontend,
    "runs": runs,
    "p50_ms": statistics.median(values),
    "p95_ms": percentile(values, 0.95),
    "mean_ms": statistics.fmean(values),
}

print(json.dumps(result, indent=2, sort_keys=True))
PY
