#!/usr/bin/env bash
# Asserts script/start-autonomous.sh expands MODEL_ARGS correctly under
# both CARREL_MODEL-set and CARREL_MODEL-unset cases.
#
# The script's behavior under test:
#   - CARREL_MODEL unset  → MODEL_ARGS=()   → claude invocation has no --model
#   - CARREL_MODEL=opus   → MODEL_ARGS=(--model opus) → claude gets --model opus
#   - CARREL_MODEL=<id>   → MODEL_ARGS=(--model <id>) → claude gets --model <id>
#
# Uses the CARREL_AUTONOMOUS_DRY_RUN=1 guard inside start-autonomous.sh
# so the script prints its would-be claude invocation and exits 0 instead
# of exec'ing claude (which would either start a real session or fail on
# CI where claude is absent).
#
# Run:
#   bash tests/test_start_autonomous_model.sh
#
# Local-only smoke. Not in the CLAUDE.md verify chain because the
# autonomous-routine scripts are operator-tooling, not product code.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LAUNCHER="$REPO_ROOT/script/start-autonomous.sh"

if [ ! -x "$LAUNCHER" ]; then
  echo "FAIL: $LAUNCHER not executable"
  exit 1
fi

run_dry() {
  # Capture stdout only; the launcher prints banner lines + the DRY_RUN: line.
  # We grep for the DRY_RUN: line specifically.
  CARREL_AUTONOMOUS_DRY_RUN=1 "$@" "$LAUNCHER" 2>&1 | grep '^DRY_RUN:' || true
}

# Case 1: CARREL_MODEL unset → no --model in invocation.
unset_output=$(env -u CARREL_MODEL bash -c "CARREL_AUTONOMOUS_DRY_RUN=1 '$LAUNCHER' 2>&1" | grep '^DRY_RUN:' || true)
if [ -z "$unset_output" ]; then
  echo "FAIL: case unset — no DRY_RUN line emitted. Did the guard fire?"
  echo "Full output:"
  env -u CARREL_MODEL bash -c "CARREL_AUTONOMOUS_DRY_RUN=1 '$LAUNCHER' 2>&1" || true
  exit 1
fi
if echo "$unset_output" | grep -q -- '--model'; then
  echo "FAIL: case unset — invocation contains --model when CARREL_MODEL was unset"
  echo "  got: $unset_output"
  exit 1
fi
echo "PASS: case unset — invocation has no --model flag"

# Case 2: CARREL_MODEL=opus → --model opus present.
opus_output=$(CARREL_MODEL=opus CARREL_AUTONOMOUS_DRY_RUN=1 "$LAUNCHER" 2>&1 | grep '^DRY_RUN:' || true)
if [ -z "$opus_output" ]; then
  echo "FAIL: case opus — no DRY_RUN line emitted"
  exit 1
fi
if ! echo "$opus_output" | grep -q -- '--model opus'; then
  echo "FAIL: case opus — invocation missing '--model opus'"
  echo "  got: $opus_output"
  exit 1
fi
echo "PASS: case opus — invocation contains --model opus"

# Case 3: CARREL_MODEL=claude-opus-4-7 (full model id) → --model claude-opus-4-7 present.
fullid_output=$(CARREL_MODEL=claude-opus-4-7 CARREL_AUTONOMOUS_DRY_RUN=1 "$LAUNCHER" 2>&1 | grep '^DRY_RUN:' || true)
if [ -z "$fullid_output" ]; then
  echo "FAIL: case fullid — no DRY_RUN line emitted"
  exit 1
fi
if ! echo "$fullid_output" | grep -q -- '--model claude-opus-4-7'; then
  echo "FAIL: case fullid — invocation missing '--model claude-opus-4-7'"
  echo "  got: $fullid_output"
  exit 1
fi
echo "PASS: case fullid — invocation contains --model claude-opus-4-7"

echo "ALL PASS: start-autonomous.sh MODEL_ARGS expansion is correct"
exit 0
