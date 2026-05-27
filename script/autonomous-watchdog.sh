#!/usr/bin/env bash
# Keep the Carrel autonomous routine alive across 5-hour rolling rate limits.
#
# When Claude Code hits the cap, the CLI doesn't exit — it freezes showing
# "try again at X". A plain `while claude; do done` never iterates because
# claude never exits. This watchdog kills frozen sessions and relaunches.
#
# Detection (hybrid, designed to avoid false positives from claude reading
# its own infrastructure and writing prose about rate limits):
#
#   PRIMARY  — IDLENESS. The session log grows continuously while claude
#              is alive (TUI spinner + status updates + ANSI redraws emit
#              bytes/sec). If the log hasn't grown by IDLE_GROWTH_BYTES
#              in IDLE_THRESHOLD seconds, the session is stuck → kill.
#              Bulletproof: no false positives from text content.
#
#   FAST PATH — pattern + idleness. If a tight LIMIT_PATTERN is found in
#              the log AND idleness >= 60s, kill immediately rather than
#              waiting for the full IDLE_THRESHOLD. Pattern alone never
#              kills (would false-positive on prose); idleness gates it.
#
# Each relaunch is safe: /carrel-build reads TODOS.md + the active plan at
# the top of every iteration, so the loop's state is the filesystem, not
# the in-session memory.
#
# Usage:
#   ./script/autonomous-watchdog.sh
#       (foreground — you see claude in your terminal; ctrl-c kills both)
#
#   nohup ./script/autonomous-watchdog.sh > /tmp/carrel-watchdog.log 2>&1 &
#       (detached — survives terminal close; tail the session log to watch)
#
# Stop:
#   touch .claude/HALT   # graceful — finishes current cycle, then exits
#   kill <pid>           # hard stop
#
# Env knobs (all optional):
#   RETRY_SECONDS       sleep between session attempts (default 900 = 15 min)
#   IDLE_THRESHOLD      seconds of log inactivity before forced kill (default 600)
#   IDLE_GROWTH_BYTES   log growth that resets the idle timer (default 512)
#   POLL_SECONDS        how often the poller checks log state (default 20)
#   LIMIT_PATTERN       grep -iE regex for fast-path detection. Tight by
#                       default to avoid prose false positives.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
cd "$REPO_ROOT"

RETRY_SECONDS="${RETRY_SECONDS:-900}"
IDLE_THRESHOLD="${IDLE_THRESHOLD:-600}"
IDLE_GROWTH_BYTES="${IDLE_GROWTH_BYTES:-512}"
POLL_SECONDS="${POLL_SECONDS:-20}"

# Default LIMIT_PATTERN assigned in its own block: ${VAR:-default} terminates
# at the FIRST `}` in default, which would butcher our `.{0,15}` quantifiers
# into invalid regex. Single quotes pass through literally to grep -iE.
if [ -z "${LIMIT_PATTERN:-}" ]; then
  LIMIT_PATTERN='5.hour limit reached|usage limit reached|approaching.{0,15}usage limit|reached your.{0,15}limit|account.{0,15}rate.?limit'
fi

# Path where the routine writes its graceful-halt memo. If this file is
# touched DURING a session, the session ended cleanly (plan exhausted /
# voluntary halt), not because of a rate-limit hang. We exit the watchdog
# instead of churning relaunches. Override to disable graceful detection:
#   GRACEFUL_HALT_FILE=""
GRACEFUL_HALT_FILE="${GRACEFUL_HALT_FILE-$REPO_ROOT/.claude/logs/status.md}"

LOG_DIR="$REPO_ROOT/.claude/logs/watchdog"
mkdir -p "$LOG_DIR"

# Gate-machinery smoke test (T68 Phase 4). Refuse to launch if the
# auditor sub-routine can't converge on a synthetic action; the loop
# would otherwise wedge silently waiting for verdict files that never
# appear. Override with CARREL_SKIP_SMOKE=1 (use sparingly).
if [ -z "${CARREL_SKIP_SMOKE:-}" ]; then
  echo "$(date '+%F %T'): running gate-machinery smoke test..."
  smoke_python="$REPO_ROOT/.venv/bin/python"
  [ -x "$smoke_python" ] || smoke_python="$(command -v python3 || command -v python)"
  if [ -z "$smoke_python" ] || [ ! -x "$smoke_python" ]; then
    echo "$(date '+%F %T'): no python found for smoke test. Set CARREL_SKIP_SMOKE=1 to bypass."
    exit 1
  fi
  if ! "$smoke_python" -m pytest \
       "$REPO_ROOT/tests/test_routine_gate_smoke.py" \
       -x --tb=short --no-header -q; then
    echo "$(date '+%F %T'): gate-machinery smoke test FAILED. Refusing to launch."
    echo "  See .claude/logs/audits/pending/smoke-test-synthetic-action.json"
    echo "  Override with CARREL_SKIP_SMOKE=1 if you know what you're doing."
    exit 1
  fi
  echo "$(date '+%F %T'): gate-machinery smoke test PASSED."
fi

attempt=0
while true; do
  if [ -f "$REPO_ROOT/.claude/HALT" ]; then
    echo "$(date '+%F %T'): .claude/HALT present. Watchdog exiting."
    exit 0
  fi

  attempt=$((attempt + 1))
  session_log="$LOG_DIR/session-$(date +%Y%m%d-%H%M%S).log"

  # Capture pre-session mtime of the graceful-halt memo so we can tell
  # whether THIS session wrote it (clean halt) or it's left over from
  # a previous run.
  if [ -n "$GRACEFUL_HALT_FILE" ] && [ -f "$GRACEFUL_HALT_FILE" ]; then
    halt_mtime_before=$(stat -f %m "$GRACEFUL_HALT_FILE" 2>/dev/null || echo 0)
  else
    halt_mtime_before=0
  fi

  echo
  echo "================================================================"
  echo "$(date '+%F %T'): launching session #$attempt"
  echo "  session log:    $session_log"
  echo "  idle threshold: ${IDLE_THRESHOLD}s (kill if log frozen)"
  echo "  retry sleep:    ${RETRY_SECONDS}s after each session ends"
  echo "  graceful halt:  $GRACEFUL_HALT_FILE"
  echo "================================================================"
  echo

  # Background poller: idleness-based with pattern fast-path.
  (
    last_size=0
    last_growth=$(date +%s)

    while true; do
      sleep "$POLL_SECONDS"
      [ -f "$REPO_ROOT/.claude/HALT" ] && exit 0
      [ -f "$session_log" ] || continue

      current_size=$(wc -c < "$session_log" 2>/dev/null || echo 0)
      now=$(date +%s)

      if [ "$current_size" -gt "$((last_size + IDLE_GROWTH_BYTES))" ]; then
        last_size=$current_size
        last_growth=$now
      fi
      idle_seconds=$((now - last_growth))

      kill_reason=""
      if [ "$idle_seconds" -ge "$IDLE_THRESHOLD" ]; then
        kill_reason="idle ${idle_seconds}s >= ${IDLE_THRESHOLD}s threshold"
      elif [ "$idle_seconds" -ge 60 ]; then
        if tail -c 16384 "$session_log" 2>/dev/null | grep -iE "$LIMIT_PATTERN" >/dev/null; then
          kill_reason="rate-limit pattern matched + idle ${idle_seconds}s"
        fi
      fi

      if [ -n "$kill_reason" ]; then
        target=$(/usr/sbin/lsof -t "$session_log" 2>/dev/null | head -1)
        echo
        echo ">>> $(date '+%F %T'): killing session - $kill_reason"
        if [ -n "$target" ]; then
          pkill -TERM -P "$target" 2>/dev/null || true
          kill  -TERM    "$target" 2>/dev/null || true
          sleep 5
          pkill -KILL -P "$target" 2>/dev/null || true
          kill  -KILL    "$target" 2>/dev/null || true
        fi

        # T68 Phase 5: orphan-claude sweep. The script(1) wrapper can lose
        # parent linkage on its claude child via exec, so the pkill -P above
        # may leave a claude process running with the same CWD as this
        # worktree. Sweep it explicitly. The CWD check isolates the kill to
        # this worktree, so other fleet worktrees are untouched.
        for orphan_pid in $(pgrep -f "claude.*--permission-mode bypassPermissions" 2>/dev/null); do
          orphan_cwd=$(/usr/sbin/lsof -p "$orphan_pid" 2>/dev/null | awk '$4 == "cwd" {print $NF}' | head -1)
          if [ "$orphan_cwd" = "$REPO_ROOT" ]; then
            echo ">>> $(date '+%F %T'): killing orphaned claude (PID $orphan_pid, cwd=$orphan_cwd)"
            kill -TERM "$orphan_pid" 2>/dev/null || true
            sleep 2
            kill -KILL "$orphan_pid" 2>/dev/null || true
          fi
        done
        exit 0
      fi
    done
  ) &
  poller_pid=$!

  # Foreground script(1): you see claude live, output also captured to log.
  /usr/bin/script -q "$session_log" "$SCRIPT_DIR/start-autonomous.sh" /carrel-build || true

  # Session ended (clean exit, ctrl-c, or poller-kill). Tear down poller.
  kill -TERM "$poller_pid" 2>/dev/null || true
  wait "$poller_pid" 2>/dev/null || true

  # Did /carrel-build voluntarily halt by writing its status memo during
  # THIS session? If yes, the loop reached its designed exit point —
  # don't churn relaunches.
  if [ -n "$GRACEFUL_HALT_FILE" ] && [ -f "$GRACEFUL_HALT_FILE" ]; then
    halt_mtime_after=$(stat -f %m "$GRACEFUL_HALT_FILE" 2>/dev/null || echo 0)
    if [ "$halt_mtime_after" -gt "$halt_mtime_before" ]; then
      echo
      echo "$(date '+%F %T'): session #$attempt voluntarily halted (wrote $GRACEFUL_HALT_FILE)."
      echo "                  watchdog exiting cleanly — re-run this script to continue."
      exit 0
    fi
  fi

  echo
  echo "$(date '+%F %T'): session #$attempt ended (no graceful halt detected). sleeping ${RETRY_SECONDS}s before relaunch."
  echo "                  ctrl-c now, or touch .claude/HALT for graceful stop."

  # HALT-aware retry sleep: poll the HALT file every 5s so a graceful stop
  # takes effect within seconds, not the full RETRY_SECONDS window.
  slept=0
  while [ "$slept" -lt "$RETRY_SECONDS" ]; do
    if [ -f "$REPO_ROOT/.claude/HALT" ]; then
      echo "$(date '+%F %T'): .claude/HALT detected during retry sleep. Watchdog exiting."
      exit 0
    fi
    sleep 5
    slept=$((slept + 5))
  done
done
