#!/usr/bin/env bash
# Weekly launchd wrapper for git-hygiene.sh. DRY-RUN only: it reports what is
# prunable and never deletes anything (a human runs `--apply` after a glance).
# Appends a timestamped report to the jarvis log and posts a desktop notification
# when there is sprawl to clean, so the report is not silently ignored.
REPO="${CACHET_REPO:-/Users/madu/Desktop/Codex}"
LOG_DIR="${HOME}/jarvis-upgrade/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/git-hygiene.log"

cd "$REPO" 2>/dev/null || { echo "git-hygiene-weekly: repo not found at $REPO" >>"$LOG"; exit 0; }

out="$(bash script/git-hygiene.sh 2>&1)"
{
  echo "=================================================================="
  echo "weekly git-hygiene (dry-run)  $(date '+%Y-%m-%d %H:%M')"
  echo "$out"
  echo "to clean: cd $REPO && bash script/git-hygiene.sh --apply"
} >>"$LOG"

# Extract the prunable/deletable counts from the summary line and notify if > 0.
summary="$(printf '%s\n' "$out" | grep -E '^summary:')"
prunable="$(printf '%s\n' "$summary" | grep -oE 'prunable [0-9]+' | grep -oE '[0-9]+' | head -1)"
delable="$(printf '%s\n' "$summary" | grep -oE 'deletable [0-9]+' | grep -oE '[0-9]+' | head -1)"
if [ "${prunable:-0}" -gt 0 ] || [ "${delable:-0}" -gt 0 ]; then
  osascript -e "display notification \"${prunable:-0} worktrees, ${delable:-0} branches prunable. Run git-hygiene --apply.\" with title \"Cachet git hygiene\"" 2>/dev/null || true
fi
exit 0
