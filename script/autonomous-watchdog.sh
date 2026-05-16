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
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

RETRY_SECONDS="${RETRY_SECONDS:-900}"
IDLE_THRESHOLD="${IDLE_THRESHOLD:-600}"
IDLE_GROWTH_BYTES="${IDLE_GROWTH_BYTES:-512}"
POLL_SECONDS="${POLL_SECONDS:-20}"
LIMIT_PATTERN="${LIMIT_PATTERN:-5.hour limit reached|usage limit reached|approaching.{0,15}usage limit|reached your.{0,15}limit|account.{0,15}rate.?limit}"

LOG_DIR="$REPO_ROOT/.claude/logs/watchdog"
mkdir -p "$LOG_DIR"

attempt=0
while true; do
  if [ -f "$REPO_ROOT/.claude/HALT" ]; then
    echo "$(date '+%F %T'): .claude/HALT present. Watchdog exiting."
    exit 0
  fi

  attempt=$((attempt + 1))
  session_log="$LOG_DIR/session-$(date +%Y%m%d-%H%M%S).log"
  echo
  echo "================================================================"
  echo "$(date '+%F %T'): launching session #$attempt"
  echo "  session log:    $session_log"
  echo "  idle threshold: ${IDLE_THRESHOLD}s (kill if log frozen)"
  echo "  retry sleep:    ${RETRY_SECONDS}s after each session ends"
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
        echo ">>> $(date '+%F %T'): killing session — $kill_reason"
        if [ -n "$target" ]; then
          pkill -TERM -P "$target" 2>/dev/null || true
          kill  -TERM    "$target" 2>/dev/null || true
          sleep 5
          pkill -KILL -P "$target" 2>/dev/null || true
          kill  -KILL    "$target" 2>/dev/null || true
        fi
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

  echo
  echo "$(date '+%F %T'): session #$attempt ended. sleeping ${RETRY_SECONDS}s before relaunch."
  echo "                  ctrl-c now to abort the watchdog."
  sleep "$RETRY_SECONDS"
done
