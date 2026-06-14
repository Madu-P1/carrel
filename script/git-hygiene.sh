#!/usr/bin/env bash
# git-hygiene.sh - safely trim worktree/branch sprawl.
#
# Every Claude/Codex session spawns a worktree + branch, so the repo accretes
# dozens of stale worktrees and branches whose work has already landed on main.
# This prunes the provably-redundant ones and REFUSES anything that could lose
# work. Dry-run by default; pass --apply to act.
#
# Safety guards (a 2026-06-14 cleanup lost 2 untracked docs by removing a worktree
# whose work was never committed; these guards exist so that cannot recur):
#   - A worktree is removed ONLY when it has NO real (non-cruft) uncommitted
#     change. Real uncommitted work is reported and KEPT, never force-removed.
#   - A branch is deleted ONLY when its content is already in origin/main, OR it
#     is fully contained in its own origin/<branch> (recoverable from the remote).
#     A branch with unique commits that are NOT on any remote is KEPT, never -D.
#   - main, master, the current branch, and the main checkout are always skipped.
set -u

APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1
# A worktree touched within this many days is treated as an ACTIVE session and
# never pruned, even if clean and content-in-main. This is what stops the script
# from removing the worktree of the very session running it (or any live session)
# when invoked from the main checkout. Override with STALE_DAYS=N.
STALE_DAYS="${STALE_DAYS:-2}"
ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "not a git repo"; exit 1; }
MAIN_WT="$(git -C "$ROOT" worktree list --porcelain | awk '/^worktree /{print $2; exit}')"
CUR_WT="$(git -C "$ROOT" rev-parse --show-toplevel 2>/dev/null)"
CUR_BR="$(git -C "$ROOT" branch --show-current 2>/dev/null)"
CRUFT='\.venv|node_modules|/dist/|frontend/dist|\.forge|\.forge-stage|\.claude/launch\.json|\.claude/forge|__pycache__|\.mypy_cache|\.ruff_cache|\.DS_Store|\.bak$|\.db$|\.local$|cachet\.new|app\.new\.html|\.mythos|og-card| 2$'

say() { if [ "$APPLY" = 1 ]; then echo "  $1"; else echo "  [dry-run] would $1"; fi; }

git -C "$ROOT" fetch origin --quiet 2>/dev/null || true
echo "git-hygiene ($([ "$APPLY" = 1 ] && echo APPLY || echo DRY-RUN)) on $ROOT"
echo "protected: main, $CUR_BR (current), the main checkout"

# --- worktrees: remove only those with no real uncommitted work ---
echo ""
echo "== worktrees =="
wt_rm=0; wt_keep=0
while IFS= read -r wt; do
  [ -z "$wt" ] && continue
  [ "$wt" = "$MAIN_WT" ] && continue
  [ "$wt" = "$CUR_WT" ] && continue
  [ -d "$wt" ] || continue
  # Activity guard: any non-cruft file touched within STALE_DAYS means a live
  # session. Skip it. (find prunes the heavy/cruft dirs so this stays fast.)
  recent="$(find "$wt" \( -name .git -o -name node_modules -o -name .venv -o -name dist -o -name __pycache__ -o -name .forge \) -prune -o -type f -mtime "-${STALE_DAYS}" -print 2>/dev/null | head -1)"
  if [ -n "$recent" ]; then
    echo "  KEEP $(basename "$wt"): active (modified within ${STALE_DAYS}d)"
    wt_keep=$((wt_keep + 1))
    continue
  fi
  real="$(git -C "$wt" status --porcelain 2>/dev/null | grep -vE "$CRUFT")"
  if [ -n "$real" ]; then
    n="$(printf '%s\n' "$real" | grep -c .)"
    echo "  KEEP $(basename "$wt"): $n uncommitted file(s) - commit them before this can be pruned"
    wt_keep=$((wt_keep + 1))
    continue
  fi
  say "remove worktree $(basename "$wt") (no uncommitted work)"
  if [ "$APPLY" = 1 ]; then git -C "$ROOT" worktree remove --force "$wt" 2>/dev/null && wt_rm=$((wt_rm + 1)); else wt_rm=$((wt_rm + 1)); fi
done < <(git -C "$ROOT" worktree list --porcelain | awk '/^worktree /{print $2}')
[ "$APPLY" = 1 ] && git -C "$ROOT" worktree prune 2>/dev/null

# --- branches: delete only content-in-main or fully-on-origin ---
echo ""
echo "== branches =="
br_del=0; br_keep=0
checked_out="$(git -C "$ROOT" worktree list --porcelain | awk '/^branch /{sub("refs/heads/","",$2); print $2}' | tr '\n' ' ')"
while IFS= read -r b; do
  [ -z "$b" ] && continue
  case " main master $CUR_BR " in *" $b "*) continue;; esac
  case " $checked_out " in *" $b "*) echo "  KEEP $b (checked out in a worktree)"; br_keep=$((br_keep + 1)); continue;; esac
  uniq="$(git -C "$ROOT" cherry origin/main "$b" 2>/dev/null | grep -c '^+')"
  if [ "$uniq" = "0" ]; then
    say "delete branch $b (content already in origin/main)"
    if [ "$APPLY" = 1 ]; then git -C "$ROOT" branch -D "$b" >/dev/null 2>&1 && br_del=$((br_del + 1)); else br_del=$((br_del + 1)); fi
    continue
  fi
  # Has unique commits: KEEP it. Weekly hygiene only removes pure-redundant
  # content-in-main branches; a branch with its own work (even if pushed) might be
  # active, so deleting it is a manual call, not an automated one.
  if git -C "$ROOT" rev-parse --verify --quiet "origin/$b" >/dev/null 2>&1; then
    echo "  KEEP $b ($uniq unique commit(s); on origin/$b - delete by hand if done)"
  else
    echo "  KEEP $b ($uniq unique commit(s); NOT on any remote - back up before deleting)"
  fi
  br_keep=$((br_keep + 1))
done < <(git -C "$ROOT" for-each-ref --format='%(refname:short)' refs/heads)

echo ""
echo "summary: worktrees $([ "$APPLY" = 1 ] && echo removed || echo prunable) $wt_rm (kept-with-work $wt_keep) | branches $([ "$APPLY" = 1 ] && echo deleted || echo deletable) $br_del (kept $br_keep)"
[ "$APPLY" = 0 ] && echo "re-run with --apply to perform the above."
exit 0
