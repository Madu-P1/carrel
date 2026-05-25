#!/usr/bin/env python3
"""Carrel autonomous build: worktree isolation gate.

Fires on PreToolUse for Write, Edit, MultiEdit. Rejects writes whose
resolved absolute path falls OUTSIDE the current worktree root with a
sane allow-list for legitimate cross-worktree writes.

Diagnosed leak (2026-05-25): when the routine runs in a worktree under
`.claude/worktrees/<slot>/`, slots have been observed writing files using
ABSOLUTE PATHS that point at the MAIN repo at `/Users/madu/Desktop/Codex/`
rather than their own worktree root. The Write tool doesn't care about
CWD when given an absolute path. Result: another slot's files end up
staged or untracked in main.

Existing `audit-gate.py` only fires on MAJOR_FILE_PATTERNS (manifests,
migrations, CLAUDE.md, etc.). New files under `docs/decisions/`,
`services/retrieval/`, `tests/`, etc. don't match those patterns and
leak silently. This hook closes that gap.

Logic:
1. Gate on `CARREL_AUTONOMOUS=true` (mirrors audit-gate / debate-trigger).
2. Read tool_input. Extract `file_path`.
3. Resolve to absolute path (expand `~`, resolve relative paths against
   `CLAUDE_PROJECT_DIR`).
4. Allow if inside the current worktree root, allow-listed user-config
   dirs (`~/.agent-cockpit/`, `~/.gstack/`, `~/.claude/`), or transient
   dirs (`/tmp/`, `/private/tmp/`).
5. Reject everything else (especially sibling worktree paths and main
   repo paths from a worktree) with a clear reason and append a JSONL
   audit line to `.claude/logs/worktree-isolation-blocks.jsonl`.

Opt-in: silent no-op when CARREL_AUTONOMOUS is unset, so ad-hoc operator
edits and ordinary sessions don't get policed.
"""

import json
import os
import sys
import time
from pathlib import Path

# Allow-listed prefixes for writes outside the worktree root. Each is
# resolved at runtime (handling `~`) and checked with `Path.is_relative_to`.
ALLOWED_HOME_PREFIXES = [
    "~/.agent-cockpit",
    "~/.gstack",
    "~/.claude",
]

ALLOWED_ABS_PREFIXES = [
    "/tmp",
    "/private/tmp",
]

# Where Carrel keeps its sibling worktrees. Used to surface a SPECIFIC
# "you wrote to a sibling worktree" reason instead of the generic one.
WORKTREES_ROOT = Path("/Users/madu/Desktop/Codex/.claude/worktrees").resolve()


def _resolve(file_path: str, project_dir: Path) -> Path:
    """Resolve `file_path` to an absolute, symlink-resolved Path.

    - Expands `~`.
    - Resolves relatives against `project_dir` (the current worktree root,
      as Claude Code sets `CLAUDE_PROJECT_DIR`).
    - Calls `.resolve(strict=False)` so non-existent target paths (the
      common Write case for a new file) still normalize.
    """
    expanded = os.path.expanduser(file_path)
    p = Path(expanded)
    if not p.is_absolute():
        p = project_dir / p
    return p.resolve(strict=False)


def _is_under(child: Path, parent: Path) -> bool:
    """Path.is_relative_to backport-style check. Works for non-existent paths."""
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _allowed_outside_worktree(resolved: Path) -> bool:
    """Return True if `resolved` is on the allow-list for cross-worktree writes."""
    for prefix in ALLOWED_HOME_PREFIXES:
        root = Path(os.path.expanduser(prefix)).resolve(strict=False)
        if _is_under(resolved, root):
            return True
    for prefix in ALLOWED_ABS_PREFIXES:
        root = Path(prefix).resolve(strict=False)
        if _is_under(resolved, root):
            return True
    return False


def _classify_leak(resolved: Path, worktree_root: Path) -> str:
    """Classify the kind of leak for the deny reason."""
    if WORKTREES_ROOT.exists() or True:  # path string check is sufficient
        if _is_under(resolved, WORKTREES_ROOT) and not _is_under(resolved, worktree_root):
            return "sibling-worktree"
    # Main repo = parent of WORKTREES_ROOT's parent (i.e. /Users/madu/Desktop/Codex)
    main_repo = WORKTREES_ROOT.parent.parent
    if _is_under(resolved, main_repo) and not _is_under(resolved, worktree_root):
        # Inside main repo but not inside this worktree (and not inside a
        # sibling worktree — that case was handled above).
        return "main-repo"
    return "outside-tree"


def _extract_file_paths(tool_name: str, tool_input: dict) -> list[str]:
    """Pull all file_path values out of the tool_input.

    Write/Edit use `file_path`. MultiEdit uses `file_path` for the target
    plus an `edits` array; the target is the only path written, so one
    entry suffices.
    """
    fp = tool_input.get("file_path", "") or ""
    if fp:
        return [fp]
    return []


def evaluate(
    tool_name: str,
    tool_input: dict,
    project_dir: Path,
) -> tuple[bool, str, str, str]:
    """Return (allowed, reason, original_path, resolved_path).

    Pure function so the unit tests can exercise it without stdin plumbing.
    """
    paths = _extract_file_paths(tool_name, tool_input)
    if not paths:
        # Nothing to check; pass through.
        return True, "", "", ""

    worktree_root = project_dir.resolve(strict=False)

    for original in paths:
        resolved = _resolve(original, project_dir)
        if _is_under(resolved, worktree_root):
            continue
        if _allowed_outside_worktree(resolved):
            continue

        kind = _classify_leak(resolved, worktree_root)
        if kind == "sibling-worktree":
            reason = (
                f"WORKTREE ISOLATION (sibling worktree leak): {tool_name} target "
                f"{resolved} resolves into a SIBLING worktree, not the current "
                f"worktree at {worktree_root}. The autonomous routine must keep all "
                f"writes inside its own worktree. Use a path RELATIVE to CWD, or "
                f"prefix with $CLAUDE_PROJECT_DIR (which is set to this worktree). "
                f"Original path: {original}."
            )
        elif kind == "main-repo":
            reason = (
                f"WORKTREE ISOLATION (main-repo leak): {tool_name} target "
                f"{resolved} resolves into the MAIN repo, not the current worktree at "
                f"{worktree_root}. This is the exact bug diagnosed on 2026-05-25: "
                f"absolute paths bypass CWD and stage files in main. Fix: drop the "
                f"absolute prefix and use a path RELATIVE to CWD, or prefix with "
                f"$CLAUDE_PROJECT_DIR. Original path: {original}."
            )
        else:
            reason = (
                f"WORKTREE ISOLATION (out-of-tree write): {tool_name} target "
                f"{resolved} is outside the current worktree at {worktree_root} and "
                f"not on the allow-list (~/.agent-cockpit, ~/.gstack, ~/.claude, "
                f"/tmp). Use a worktree-relative path or $CLAUDE_PROJECT_DIR. "
                f"Original path: {original}."
            )
        return False, reason, original, str(resolved)

    return True, "", "", ""


def _log_block(
    project_dir: Path,
    tool_name: str,
    original: str,
    resolved: str,
    worktree_root: Path,
    reason: str,
) -> None:
    log_dir = project_dir / ".claude" / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tool_name": tool_name,
        "original_file_path": original,
        "resolved_path": resolved,
        "worktree_root": str(worktree_root),
        "reason": reason,
    }
    try:
        (log_dir / "worktree-isolation-blocks.jsonl").open("a").write(
            json.dumps(entry, ensure_ascii=False) + "\n"
        )
    except Exception:
        pass


def main() -> None:
    if os.environ.get("CARREL_AUTONOMOUS") != "true":
        sys.exit(0)

    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {}) or {}

    if tool_name not in ("Write", "Edit", "MultiEdit"):
        sys.exit(0)

    project_dir_env = os.environ.get("CLAUDE_PROJECT_DIR", "")
    if not project_dir_env:
        sys.exit(0)
    project_dir = Path(project_dir_env)

    allowed, reason, original, resolved = evaluate(tool_name, tool_input, project_dir)
    if allowed:
        sys.exit(0)

    _log_block(
        project_dir,
        tool_name,
        original,
        resolved,
        project_dir.resolve(strict=False),
        reason,
    )

    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(out))
    sys.exit(0)


if __name__ == "__main__":
    main()
