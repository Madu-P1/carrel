#!/usr/bin/env bash
# Fan out the Carrel autonomous routine across N worktree-isolated slots.
#
# Why this exists:
#   start-autonomous.sh + autonomous-watchdog.sh run ONE /carrel-build session
#   against the main repo. Throughput is capped by that single stream of
#   execution, not by ideas or API quota. This script spawns N watchdogs,
#   each in its own git worktree pointed at a per-slot TODOS partition.
#
# Why git worktrees (not /tmp copies, not branches-in-place):
#   Every shared-state surface the routine touches resolves against CWD:
#     - .claude/HALT                (graceful-stop sentinel)
#     - .claude/logs/status.md      (graceful-halt memo the watchdog reads)
#     - .claude/logs/audits/*       (audit-gate per-action-hash files)
#     - .claude/logs/scores/        (quality-rater 100/100 logs)
#     - .claude/logs/watchdog/      (session captures)
#     - claude-mem namespace        (keyed on absolute cwd path)
#   Distinct worktrees = distinct CWDs = natural isolation, no symlink/copy
#   gymnastics. Slot N halting via its own HALT cannot stop slot M.
#
# Partition discipline:
#   You pass one TODOS file per slot. Each slot's TODOS must touch a
#   disjoint code subtree from every other slot's TODOS. If two slots both
#   edit services/tutor.py the audit-gate hashes will diverge per worktree
#   (good) but the merge back to main will conflict (bad, and harder to
#   review than the work it saved). This script does NOT enforce disjoint
#   subtrees — that judgment is yours. The partition is the actual hard
#   part. See docs/notes/fleet-partition-guide.md (write me when this
#   becomes routine).
#
# Usage:
#   # Dry-run (default): creates worktrees, validates partitions,
#   # prints the launch commands. Does NOT spawn watchdogs.
#   ./script/start-autonomous-fleet.sh 2 TODOS.fleet-1.md TODOS.fleet-2.md
#
#   # Actually spawn N detached watchdogs.
#   ./script/start-autonomous-fleet.sh --launch 2 TODOS.fleet-1.md TODOS.fleet-2.md
#
# Halt a single slot:
#   touch /Users/madu/Desktop/Codex/.claude/worktrees/fleet-1/.claude/HALT
#
# Halt all slots:
#   for d in /Users/madu/Desktop/Codex/.claude/worktrees/fleet-*; do
#     touch "$d/.claude/HALT"
#   done

set -euo pipefail

LAUNCH=false
if [ "${1:-}" = "--launch" ]; then
  LAUNCH=true
  shift
fi

if [ "$#" -lt 2 ]; then
  cat >&2 <<USAGE
usage: $0 [--launch] N TODOS_FILE_1 [TODOS_FILE_2 ... TODOS_FILE_N]

  N             number of fleet slots (must be >=1, <=4 — see cap rationale)
  TODOS_FILE_n  path (in MAIN repo) to the per-slot TODOS partition

  --launch      actually spawn watchdogs (omit to dry-run)

Caps:
  N >= 1 always
  N <= 4 by default. Past 4, review bandwidth dies before throughput rises.
  Override with FLEET_MAX_SLOTS=N env if you really mean it.
USAGE
  exit 2
fi

N="$1"
shift

FLEET_MAX_SLOTS="${FLEET_MAX_SLOTS:-4}"
if ! [[ "$N" =~ ^[0-9]+$ ]] || [ "$N" -lt 1 ] || [ "$N" -gt "$FLEET_MAX_SLOTS" ]; then
  echo "error: N must be 1..$FLEET_MAX_SLOTS (got: $N)" >&2
  exit 2
fi

if [ "$#" -ne "$N" ]; then
  echo "error: need exactly $N TODOS files for $N slots (got $#)" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Resolve the MAIN repo root, not whatever worktree we happen to be in.
# We need this so worktree-add resolves paths correctly and so we can
# locate the source TODOS partitions.
MAIN_REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --path-format=absolute --git-common-dir)"
MAIN_REPO_ROOT="$(cd "$MAIN_REPO_ROOT/.." && pwd)"

if [ ! -d "$MAIN_REPO_ROOT/.claude/hooks" ]; then
  echo "error: $MAIN_REPO_ROOT does not look like the Carrel repo (no .claude/hooks)" >&2
  exit 1
fi

# Validate all partitions exist before we touch any worktree.
declare -a SLOT_TODOS
for ((i=1; i<=N; i++)); do
  src="$1"
  shift
  # Allow either absolute paths or paths relative to MAIN_REPO_ROOT.
  case "$src" in
    /*) abs="$src" ;;
    *)  abs="$MAIN_REPO_ROOT/$src" ;;
  esac
  if [ ! -f "$abs" ]; then
    echo "error: slot $i TODOS file not found: $abs" >&2
    exit 1
  fi
  SLOT_TODOS[i]="$abs"
done

WORKTREE_ROOT="$MAIN_REPO_ROOT/.claude/worktrees"
mkdir -p "$WORKTREE_ROOT"

echo "Carrel autonomous fleet"
echo "  main repo:      $MAIN_REPO_ROOT"
echo "  worktree root:  $WORKTREE_ROOT"
echo "  slots:          $N"
echo "  mode:           $([ "$LAUNCH" = true ] && echo LAUNCH || echo dry-run)"
echo

declare -a LAUNCH_CMDS

for ((i=1; i<=N; i++)); do
  slot_dir="$WORKTREE_ROOT/fleet-$i"
  branch="fleet/slot-$i"
  partition_src="${SLOT_TODOS[i]}"

  echo "------------------------------------------------------------"
  echo "Slot $i"
  echo "  worktree:   $slot_dir"
  echo "  branch:     $branch"
  echo "  partition:  $partition_src"

  if [ ! -d "$slot_dir" ]; then
    # Create the worktree on a new branch off main.
    # Use -B to allow re-attaching to an existing branch if the worktree
    # was removed but the branch still exists.
    git -C "$MAIN_REPO_ROOT" worktree add -B "$branch" "$slot_dir" main >/dev/null
    echo "  status:     created"
  else
    echo "  status:     already exists"
  fi

  # Copy (not symlink) the partition file into the worktree as TODOS.md.
  # Why copy: a symlink crossing worktree boundaries makes the watchdog's
  # git operations (status, diff, commit) noisy and creates a foot-gun
  # where editing TODOS.md in one slot leaks into another. The partition
  # files in the main repo are the source of truth; the in-worktree copy
  # is the working surface for that slot only.
  cp "$partition_src" "$slot_dir/TODOS.md"
  echo "  TODOS.md:   refreshed from $partition_src"

  # Ensure the slot has its own .claude/HALT-free start state.
  rm -f "$slot_dir/.claude/HALT"

  launch_cmd="cd $slot_dir && nohup ./script/autonomous-watchdog.sh > /tmp/carrel-fleet-$i.log 2>&1 &"
  LAUNCH_CMDS[i]="$launch_cmd"
done

echo
echo "============================================================"
if [ "$LAUNCH" = true ]; then
  echo "Spawning $N watchdog(s)..."
  echo
  declare -a PIDS
  for ((i=1; i<=N; i++)); do
    slot_dir="$WORKTREE_ROOT/fleet-$i"
    # Spawn each watchdog detached from this script's TTY.
    nohup bash -c "cd '$slot_dir' && exec ./script/autonomous-watchdog.sh" \
      > "/tmp/carrel-fleet-$i.log" 2>&1 &
    PIDS[i]=$!
    echo "Slot $i: pid=${PIDS[i]}  log=/tmp/carrel-fleet-$i.log"
  done
  echo
  echo "Tail all: tail -f /tmp/carrel-fleet-*.log"
  echo "Halt one: touch $WORKTREE_ROOT/fleet-N/.claude/HALT"
  echo "Halt all: for d in $WORKTREE_ROOT/fleet-*; do touch \"\$d/.claude/HALT\"; done"
else
  echo "Dry-run complete. To actually spawn:"
  echo
  echo "  $0 --launch $N \\"
  for ((i=1; i<N; i++)); do
    src="${SLOT_TODOS[i]}"
    echo "    ${src#$MAIN_REPO_ROOT/} \\"
  done
  src="${SLOT_TODOS[N]}"
  echo "    ${src#$MAIN_REPO_ROOT/}"
  echo
  echo "Or, per-slot manually:"
  for ((i=1; i<=N; i++)); do
    echo "  Slot $i: ${LAUNCH_CMDS[i]}"
  done
fi
