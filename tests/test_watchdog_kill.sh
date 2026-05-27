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

# T68 Phase 5: orphan-claude sweep verifies that the watchdog's
# pgrep-based fallback finds and kills a claude-shaped process whose
# CWD matches the worktree. Spawn a fake "claude" process in a temp
# directory that masquerades as the autonomous-loop CLI, then run the
# same sweep logic the watchdog uses and assert it kills the fake.
FAKE_DIR="$TMP/fake-worktree"
mkdir -p "$FAKE_DIR"
FAKE_CLAUDE="$FAKE_DIR/claude"
cat >"$FAKE_CLAUDE" <<'INNER'
#!/usr/bin/env bash
# Fake claude binary for the watchdog orphan-sweep test. We do NOT
# exec the sleep child because exec would replace this bash process
# with `sleep` and lose the "claude" argv that pgrep -f matches on.
# Bash holds the original cmdline while it waits.
sleep 60 &
wait
INNER
chmod +x "$FAKE_CLAUDE"

(
  cd "$FAKE_DIR" || exit 1
  exec "$FAKE_CLAUDE" --permission-mode bypassPermissions /carrel-build
) &
ORPHAN_PID=$!

# Give the fake a beat to exec.
sleep 1

if ! kill -0 "$ORPHAN_PID" 2>/dev/null; then
  echo "FAIL: orphan fake-claude never started (pid $ORPHAN_PID)"
  exit 1
fi

# Replay the watchdog sweep against $FAKE_DIR (acting as $REPO_ROOT).
# Resolve via `pwd -P` to match lsof's symlink-canonicalized output on
# macOS (e.g. /var/folders -> /private/var/folders). The production
# watchdog does the same on its REPO_ROOT.
ORPHAN_REPO_ROOT="$(cd "$FAKE_DIR" && pwd -P)"
sweep_hit=0
for orphan_pid in $(pgrep -f "claude.*--permission-mode bypassPermissions" 2>/dev/null); do
  orphan_cwd=$(/usr/sbin/lsof -p "$orphan_pid" 2>/dev/null | awk '$4 == "cwd" {print $NF}' | head -1)
  if [ "$orphan_cwd" = "$ORPHAN_REPO_ROOT" ]; then
    sweep_hit=1
    kill -TERM "$orphan_pid" 2>/dev/null || true
    sleep 2
    kill -KILL "$orphan_pid" 2>/dev/null || true
  fi
done

if [ "$sweep_hit" -ne 1 ]; then
  echo "FAIL: orphan sweep did not match the fake claude in $FAKE_DIR"
  kill -KILL "$ORPHAN_PID" 2>/dev/null || true
  wait "$ORPHAN_PID" 2>/dev/null || true
  exit 1
fi

deadline=$(( $(date +%s) + 3 ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  if ! kill -0 "$ORPHAN_PID" 2>/dev/null; then
    break
  fi
  sleep 0.2
done

if kill -0 "$ORPHAN_PID" 2>/dev/null; then
  echo "FAIL: orphan fake-claude survived the sweep (pid $ORPHAN_PID, cwd=$FAKE_DIR)"
  kill -KILL "$ORPHAN_PID" 2>/dev/null || true
  wait "$ORPHAN_PID" 2>/dev/null || true
  exit 1
fi

wait "$ORPHAN_PID" 2>/dev/null || true

echo "PASS: orphan-claude sweep killed the fake CLI matching CWD"
exit 0
