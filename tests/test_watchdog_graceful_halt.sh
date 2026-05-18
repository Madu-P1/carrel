#!/usr/bin/env bash
# Smoke test for graceful-halt detection in script/autonomous-watchdog.sh.
#
# Three scenarios against a stubbed start-autonomous.sh assert the
# session-end branch in the watchdog correctly distinguishes:
#
#   (1) Stale GRACEFUL_HALT_FILE — mtime BEFORE session start, session
#       does not touch the memo. Result: no trigger; "no graceful halt
#       detected" appears in the log.
#
#   (2) Mid-session touch — session writes the memo while running, so
#       its mtime advances. Result: watchdog exits 0 with "voluntarily
#       halted" + "watchdog exiting cleanly" in the log.
#
#   (3) Disabled via empty string — GRACEFUL_HALT_FILE="" turns the
#       feature off. Even a touch is ignored; the relaunch path runs.
#
# Closes the quality-rater gap from the 98/100 review of caed2dbb.
#
# Run manually:
#   bash tests/test_watchdog_graceful_halt.sh
#
# Wired into the verify chain in CLAUDE.md alongside test_watchdog_kill.sh.
# Exit 0 on pass, non-zero on fail.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WATCHDOG_SRC="$REPO_ROOT/script/autonomous-watchdog.sh"

# Backdate $1 to one minute ago so its mtime is unambiguously BEFORE
# any session we spawn next.
backdate_one_minute() {
  touch -t "$(date -v-1M +%Y%m%d%H%M.%S)" "$1"
}

# Run one watchdog iteration against a stubbed start-autonomous.sh.
# Args:
#   $1: scenario name (used in the captured log filename)
#   $2: stub body bash code — passed through an unquoted heredoc, so
#       use single quotes around literal strings and prefer relative
#       paths (cwd inside the stub is the fake repo root).
#   $3: GRACEFUL_HALT_FILE mode — "DEFAULT" leaves the variable unset
#       (watchdog falls back to .claude/logs/status.md), "EMPTY" exports
#       an empty string (disables the feature), any other value exports
#       that literal path.
# Prints: absolute path to the captured watchdog log.
run_scenario() {
  local name="$1"
  local stub_body="$2"
  local halt_mode="$3"

  local tmp out
  tmp=$(mktemp -d)
  out="/tmp/test_watchdog_graceful_halt-$name.log"

  mkdir -p "$tmp/script" "$tmp/.claude/logs/watchdog"
  cp "$WATCHDOG_SRC" "$tmp/script/autonomous-watchdog.sh"

  cat >"$tmp/script/start-autonomous.sh" <<STUB_EOF
#!/usr/bin/env bash
$stub_body
exit 0
STUB_EOF
  chmod +x "$tmp/script/start-autonomous.sh"

  # Seed the default memo path with a clearly-stale mtime so every
  # scenario shares the same baseline.
  local default_halt="$tmp/.claude/logs/status.md"
  echo "stale memo from a prior run" > "$default_halt"
  backdate_one_minute "$default_halt"

  (
    cd "$tmp"
    case "$halt_mode" in
      DEFAULT) ;;
      EMPTY)   export GRACEFUL_HALT_FILE="" ;;
      *)       export GRACEFUL_HALT_FILE="$halt_mode" ;;
    esac
    RETRY_SECONDS=30 POLL_SECONDS=30 IDLE_THRESHOLD=600 \
      bash script/autonomous-watchdog.sh
  ) >"$out" 2>&1 &
  local pid=$!

  # Settled-state wait: either the graceful-halt branch fires (watchdog
  # exits, kill -0 returns false) or the retry-sleep branch fires
  # ("no graceful halt detected" appears). Either is enough to assert.
  local deadline=$(( $(date +%s) + 25 ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    if ! kill -0 "$pid" 2>/dev/null; then break; fi
    if grep -q "no graceful halt detected" "$out" 2>/dev/null; then break; fi
    sleep 0.3
  done

  # If the watchdog is still alive (cases 1 and 3 enter retry-sleep),
  # break it out via the .claude/HALT file the retry-sleep polls.
  if kill -0 "$pid" 2>/dev/null; then
    touch "$tmp/.claude/HALT"
    local kill_deadline=$(( $(date +%s) + 10 ))
    while kill -0 "$pid" 2>/dev/null && [ "$(date +%s)" -lt "$kill_deadline" ]; do
      sleep 0.3
    done
    kill -KILL "$pid" 2>/dev/null || true
  fi
  wait "$pid" 2>/dev/null || true

  rm -rf "$tmp"
  printf '%s\n' "$out"
}

assert_contains() {
  local where="$1" needle="$2" file="$3"
  if ! grep -q "$needle" "$file"; then
    echo "FAIL ($where): expected log to contain '$needle'"
    echo "--- log ---"
    cat "$file"
    echo "--- end log ---"
    exit 1
  fi
}

assert_not_contains() {
  local where="$1" needle="$2" file="$3"
  if grep -q "$needle" "$file"; then
    echo "FAIL ($where): did NOT expect log to contain '$needle'"
    echo "--- log ---"
    cat "$file"
    echo "--- end log ---"
    exit 1
  fi
}

STUB_NOTOUCH='echo fake session; sleep 1'
STUB_TOUCH_DEFAULT='echo fake session; date > .claude/logs/status.md; sleep 1'

log1=$(run_scenario stale "$STUB_NOTOUCH" DEFAULT)
assert_contains     "case 1 (stale)" "no graceful halt detected" "$log1"
assert_not_contains "case 1 (stale)" "voluntarily halted"        "$log1"
echo "PASS (case 1): stale GRACEFUL_HALT_FILE mtime does not trigger graceful halt"

log2=$(run_scenario touch "$STUB_TOUCH_DEFAULT" DEFAULT)
assert_contains     "case 2 (touch)" "voluntarily halted"        "$log2"
assert_contains     "case 2 (touch)" "watchdog exiting cleanly"  "$log2"
assert_not_contains "case 2 (touch)" "no graceful halt detected" "$log2"
echo "PASS (case 2): mid-session memo touch triggers graceful-halt clean exit"

log3=$(run_scenario disabled "$STUB_TOUCH_DEFAULT" EMPTY)
assert_contains     "case 3 (disabled)" "no graceful halt detected" "$log3"
assert_not_contains "case 3 (disabled)" "voluntarily halted"        "$log3"
echo "PASS (case 3): GRACEFUL_HALT_FILE=\"\" disables graceful-halt detection"

echo
echo "ALL PASSED: graceful-halt detection works in all 3 scenarios"
exit 0
