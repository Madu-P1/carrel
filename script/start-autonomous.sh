#!/usr/bin/env bash
# Launch a Claude Code session with the Carrel autonomous routine armed.
#
# Sets CARREL_AUTONOMOUS=true so the four hooks at .claude/hooks/
# (route-task, audit-gate, debate-trigger, score-loop) actually fire.
# Without this var the hooks exit silently — that's the runbook's
# opt-in design so ad-hoc edits don't trigger the auditor + rater.
#
# Passes --permission-mode bypassPermissions so claude doesn't hang on
# tool-permission prompts (which it cannot show in a detached session
# under the watchdog). The audit-gate.py hook is the actual safety net:
# it blocks major actions (commits, migrations, dep changes) until the
# independent-auditor agent writes an approval file. Without bypassing
# claude's own prompts, the audit gate never gets reached.
#
# Override the permission mode via env var if you want to use this
# launcher interactively without bypass:
#   CARREL_PERMISSION_MODE=default ./script/start-autonomous.sh
#
# Usage:
#   ./script/start-autonomous.sh          # interactive, /carrel-build typed manually
#   ./script/start-autonomous.sh /carrel-build   # auto-fires the loop on launch
#
# Halt the routine with: touch .claude/HALT
# Or in-chat: tell Claude "halt the routine".

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

if [ ! -d ".claude/hooks" ] || [ ! -d ".claude/agents" ]; then
  echo "error: .claude/hooks or .claude/agents missing. Are you in the Carrel repo root?" >&2
  echo "  expected at: $REPO_ROOT/.claude/{hooks,agents}/" >&2
  exit 1
fi

if [ -f ".claude/HALT" ]; then
  echo "warning: .claude/HALT is present. The routine will refuse major actions." >&2
  echo "  remove with: rm $REPO_ROOT/.claude/HALT" >&2
  echo
fi

if ! command -v claude >/dev/null 2>&1; then
  echo "error: 'claude' not on PATH. Install Claude Code or fix PATH." >&2
  exit 1
fi

export CARREL_AUTONOMOUS=true

PERMISSION_MODE="${CARREL_PERMISSION_MODE:-bypassPermissions}"

echo "Carrel autonomous routine armed."
echo "  CARREL_AUTONOMOUS=true"
echo "  permission-mode: $PERMISSION_MODE"
echo "  cwd: $REPO_ROOT"
echo "  hooks: $(ls .claude/hooks/*.py 2>/dev/null | wc -l | tr -d ' ') python hooks"
echo "  agents: $(ls .claude/agents/*.md 2>/dev/null | wc -l | tr -d ' ') agent definitions"
if [ "$#" -gt 0 ]; then
  echo "  initial prompt: $*"
else
  echo "  initial prompt: (none — type /carrel-build to start the loop)"
fi
echo

exec claude --permission-mode "$PERMISSION_MODE" "$@"
