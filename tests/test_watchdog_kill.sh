#!/usr/bin/env bash
# Smoke test for the kill path inside script/autonomous-watchdog.sh.
#
# Verifies that lsof can find the writer of a session log and that the
# pkill -P / kill TERM sequence in the watchdog's poller actually
# terminates the target. Closes quality-rater gap #3 from the 95/100
# review of commit fa400fbd (chore(routine): add autonomous-watchdog).
#
# Run manually:
#   bash tests/test_watchdog_kill.sh
#
# Exit 0 on pass, non-zero on fail. Not wired into the verify chain
# because the verify chain is Python + pnpm only; this lives next to
# the bash infra it exercises.

set -euo pipefail

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

LOG="$TMP/session.log"

# Spawn a child that holds the log open and sleeps. Mirrors a "stuck"
# /usr/bin/script(1) wrapper around start-autonomous.sh.
(
  exec >"$LOG" 2>&1
  echo "starting fake stuck session"
  exec sleep 60
) &
CHILD_PID=$!

# Give the child a beat to open the log.
sleep 1

if ! kill -0 "$CHILD_PID" 2>/dev/null; then
  echo "FAIL: child process never started (pid $CHILD_PID)"
  exit 1
fi

# Step 1: lsof must identify the log's writer. This is the exact call
# the watchdog poller makes.
TARGET=$(/usr/sbin/lsof -t "$LOG" 2>/dev/null | head -1)
if [ -z "$TARGET" ]; then
  echo "FAIL: lsof did not identify a writer of $LOG"
  kill "$CHILD_PID" 2>/dev/null || true
  wait "$CHILD_PID" 2>/dev/null || true
  exit 1
fi

# Step 2: issue TERM via the same two-step sequence the watchdog uses.
pkill -TERM -P "$TARGET" 2>/dev/null || true
kill  -TERM    "$TARGET" 2>/dev/null || true

# Give SIGTERM up to 3s to take effect.
deadline=$(( $(date +%s) + 3 ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  if ! kill -0 "$CHILD_PID" 2>/dev/null; then
    break
  fi
  sleep 0.2
done

if kill -0 "$CHILD_PID" 2>/dev/null; then
  echo "FAIL: child survived SIGTERM after 3s (lsof target=$TARGET, child=$CHILD_PID)"
  kill -KILL "$CHILD_PID" 2>/dev/null || true
  wait "$CHILD_PID" 2>/dev/null || true
  exit 1
fi

wait "$CHILD_PID" 2>/dev/null || true

echo "PASS: lsof + pkill/kill TERM path terminated the session writer"
exit 0
