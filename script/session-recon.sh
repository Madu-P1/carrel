#!/usr/bin/env bash
# Session reconnaissance for the autonomous routine.
#
# Prints a structured snapshot of in-flight work + live agents so the
# launched Claude session can coordinate without trampling other
# sessions' state. Output goes to stdout (visible in terminal +
# watchdog log) AND to .claude/logs/session-recon-latest.md so the
# routine can re-read it inside the session.
#
# Designed to be fast (<2s) and idempotent — safe to run on every
# watchdog cycle.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

LATEST="$REPO_ROOT/.claude/logs/session-recon-latest.md"
TIMESTAMPED="$REPO_ROOT/.claude/logs/session-recon-$(date +%Y%m%d-%H%M%S).md"
mkdir -p "$(dirname "$LATEST")"

{
  echo "# Session reconnaissance — $(date '+%F %T %Z')"
  echo
  echo "Read this before picking your next task. Every file under"
  echo "**In-flight uncommitted work** is claimed by another agent or by"
  echo "the operator — leave it alone unless you wrote it yourself."
  echo
  echo "## Repository state"
  echo
  branch=$(git branch --show-current 2>/dev/null || echo unknown)
  head_line=$(git log -1 --oneline 2>/dev/null || echo unknown)
  upstream=$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || echo none)
  echo "- Branch: \`$branch\`"
  echo "- HEAD: \`$head_line\`"
  echo "- Upstream: \`$upstream\`"
  if [ "$upstream" != "none" ]; then
    ahead=$(git rev-list --count "$upstream..HEAD" 2>/dev/null || echo "?")
    behind=$(git rev-list --count "HEAD..$upstream" 2>/dev/null || echo "?")
    echo "- Ahead / behind upstream: $ahead / $behind"
  fi
  echo

  echo "## In-flight uncommitted work"
  echo
  # Filter machine-state noise that should be gitignored but isn't:
  # autonomous-loop audit/score logs, claude-flow caches, HALT marker.
  # We're surfacing IN-FLIGHT WORK, not state files.
  NOISE_RE='^(\.claude/logs/|\.claude-flow/|\.claude/HALT$|frontend/\.claude-flow/|macos-app/\.claude-flow/)'
  staged=$(git diff --name-only --cached 2>/dev/null | grep -vE "$NOISE_RE" | head -50 || true)
  modified=$(git diff --name-only 2>/dev/null | grep -vE "$NOISE_RE" | head -50 || true)
  untracked=$(git ls-files --others --exclude-standard 2>/dev/null | grep -vE "$NOISE_RE" | head -50 || true)
  if [ -z "$staged" ] && [ -z "$modified" ] && [ -z "$untracked" ]; then
    echo "_None — working tree clean._"
  else
    if [ -n "$staged" ]; then
      echo "**Staged:**"
      printf '```\n%s\n```\n\n' "$staged"
    fi
    if [ -n "$modified" ]; then
      echo "**Modified (unstaged) — DO NOT TOUCH unless you authored these:**"
      printf '```\n%s\n```\n\n' "$modified"
    fi
    if [ -n "$untracked" ]; then
      echo "**Untracked — likely another agent's in-progress new files:**"
      printf '```\n%s\n```\n\n' "$untracked"
    fi
  fi

  echo "## Recent commits (last 10)"
  echo
  printf '```\n'
  git log -10 --oneline 2>/dev/null || echo "(no history)"
  printf '```\n\n'

  echo "## Active worktrees (other branches checked out elsewhere)"
  echo
  printf '```\n'
  git worktree list 2>/dev/null || echo "(none)"
  printf '```\n\n'

  echo "## Live processes on this machine"
  echo
  # Process filters: pgrep -alf matches the entire command line, which on macOS
  # picks up Claude.app desktop helper renderers, MCP server children, and
  # filesystem paths containing "codex" (the macOS cryptexd internal paths).
  # We want actual CLI sessions, not their satellite processes — filter
  # /Applications/, npm exec, --type=renderer, and Helper.app.
  CLI_NOISE='/Applications/|npm exec|--type=(renderer|utility|gpu-process|zygote)|Helper\.app|Helper \(Renderer\)|Helper \(GPU\)|MCP server|server-pdf|ruv-swarm|cryptexd|com\.apple\.security'

  echo "**Claude Code CLI sessions (excluding desktop-app helpers + MCP servers):**"
  printf '```\n'
  claude_procs=$(pgrep -alf "[c]laude" 2>/dev/null | grep -vE "$CLI_NOISE" | head -10 || true)
  [ -n "$claude_procs" ] && echo "$claude_procs" || echo "(none other than this one)"
  printf '```\n\n'

  echo "**Codex CLI sessions:**"
  printf '```\n'
  codex_procs=$(pgrep -alf "[c]odex" 2>/dev/null | grep -vE "$CLI_NOISE" | head -10 || true)
  [ -n "$codex_procs" ] && echo "$codex_procs" || echo "(none)"
  printf '```\n\n'

  echo "**Autonomous watchdog instances:**"
  printf '```\n'
  pgrep -alf "[a]utonomous-watchdog" 2>/dev/null | head -5 || echo "(none other than this one)"
  printf '```\n\n'

  echo "**Carrel backend (uvicorn on :8000):**"
  printf '```\n'
  lsof -nP -iTCP:8000 -sTCP:LISTEN 2>/dev/null | head -5 || echo "(port 8000 not listening)"
  printf '```\n\n'

  echo "**EinsteinDesktop.app:**"
  printf '```\n'
  pgrep -alf "[E]insteinDesktop" 2>/dev/null | head -3 || echo "(not running)"
  printf '```\n\n'

  echo "## Last status memo from prior routine session"
  echo
  if [ -f .claude/logs/status.md ]; then
    mtime=$(stat -f '%Sm' .claude/logs/status.md 2>/dev/null || date -r .claude/logs/status.md '+%F %T')
    echo "Last updated: $mtime"
    echo
    echo "First 25 lines:"
    printf '```\n'
    head -25 .claude/logs/status.md
    printf '```\n\n'
  else
    echo "_No status.md present._"
    echo
  fi

  echo "## Coordination rules — IRON LAW"
  echo
  echo "1. **Do not commit, revert, or modify files in the In-flight"
  echo "   uncommitted work section above.** They belong to another"
  echo "   session or to the operator. If a task you'd pick would touch"
  echo "   one, STOP and pick something orthogonal."
  echo "2. **Do not switch branches.** Other worktrees listed above may"
  echo "   share branches; \`git checkout\` would disturb their checkout."
  echo "   If a different branch is genuinely required, ask the operator."
  echo "3. **Coordinate with running watchdogs.** If another"
  echo "   autonomous-watchdog instance is listed above, it is running"
  echo "   its own /carrel-build loop. Read"
  echo "   \`.claude/logs/routing.jsonl\` to see what it claimed recently"
  echo "   and pick something orthogonal."
  echo "4. **Never run destructive ops without explicit user approval:**"
  echo "   \`git reset --hard\`, \`git push --force\`, \`git rebase\` of"
  echo "   published commits, \`rm -rf\` outside ephemeral paths,"
  echo "   \`DROP TABLE\`, \`docker compose down --volumes\`."
  echo "5. **Never \`git stash\` or \`git checkout --\` someone else's"
  echo "   unstaged changes.** Those are work-in-progress; treat them"
  echo "   as sacred."
} > "$LATEST"

# Keep a timestamped copy for forensics
cp "$LATEST" "$TIMESTAMPED"

# Print to stdout so the operator sees it in the terminal
cat "$LATEST"
