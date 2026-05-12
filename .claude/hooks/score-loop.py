#!/usr/bin/env python3
"""Carrel autonomous build: post-feature quality scoring loop.

Fires on Stop and SubagentStop. Nudges Claude to spawn the quality-rater
subagent in a fresh context to score completed work against the 100-point
rubric. If a recent score of 100 exists for the session, the hook stays
silent (the work is shipped). Otherwise it injects an additionalContext
reminder to run the rater before declaring done.

Loop control: a per-session counter caps nudges at 25 to prevent runaway
recursion. Also respects .claude/HALT and an explicit .claude/RATER_DONE
marker file the rater can write when it scores 100.

Opt-in: only fires when CARREL_AUTONOMOUS=true.
"""
import json
import os
import sys
import time
from pathlib import Path


MAX_NUDGES_PER_SESSION = 25
RECENT_PERFECT_WINDOW_S = 1800  # 30 minutes


def has_recent_perfect_score(score_dir: Path) -> bool:
    try:
        now = time.time()
        for p in sorted(score_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:10]:
            try:
                with p.open() as f:
                    s = json.load(f)
                if s.get("total", 0) >= 100 and (now - p.stat().st_mtime) < RECENT_PERFECT_WINDOW_S:
                    return True
            except Exception:
                continue
    except Exception:
        return False
    return False


def main() -> None:
    if os.environ.get("CARREL_AUTONOMOUS") != "true":
        sys.exit(0)

    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    event = data.get("hook_event_name", "")
    if event not in ("Stop", "SubagentStop"):
        sys.exit(0)

    session = data.get("session_id", "default")
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "")
    if not project_dir:
        sys.exit(0)
    project_path = Path(project_dir)
    log_dir = project_path / ".claude" / "logs"
    score_dir = log_dir / "scores"
    try:
        score_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        sys.exit(0)

    halt_file = project_path / ".claude" / "HALT"
    if halt_file.exists():
        # Let the session stop; surface a system message so the operator sees it.
        print(json.dumps({
            "systemMessage": (
                "Carrel HALT signal present at .claude/HALT. Routine winding down. "
                "Remove the file before resuming."
            )
        }))
        sys.exit(0)

    if has_recent_perfect_score(score_dir):
        # Work already scored 100 recently; suppress further nudging.
        sys.exit(0)

    # Per-session nudge counter
    counter_file = score_dir / f"nudge-count-{session}.txt"
    try:
        n = int(counter_file.read_text().strip())
    except Exception:
        n = 0
    n += 1
    try:
        counter_file.write_text(str(n))
    except Exception:
        pass

    if n > MAX_NUDGES_PER_SESSION:
        # Refuse to keep nudging; let stop succeed but warn loudly.
        print(json.dumps({
            "systemMessage": (
                f"Carrel quality-rater nudge cap hit ({MAX_NUDGES_PER_SESSION} per session). "
                f"The routine iterated without converging on a 100 score. Halt and surface "
                f"for human review. Status summary should be written to .claude/logs/status.md."
            )
        }))
        sys.exit(0)

    # Nudge: block the stop so Claude continues, with reason that drives a rater spawn.
    print(json.dumps({
        "decision": "block",
        "reason": (
            "Carrel quality gate: before declaring this work complete, spawn the "
            "quality-rater subagent in a fresh context with: (1) the original goal, "
            "(2) the diff produced (git diff HEAD~1 or git diff --cached), (3) test, lint, "
            "and build results. The rater scores against the 100-point rubric and writes "
            "JSON to .claude/logs/scores/<feature>-<ts>.json. If total is below 100, iterate "
            "(refactor, add tests, fix issues, re-debate if needed) until a fresh-context "
            "spawn returns 100 exactly. Only exit the loop on SHIP. If there is no work to "
            "rate yet (preflight halt, no feature touched), respond with a brief status "
            "summary and let the session stop without spawning the rater."
        )
    }))
    sys.exit(0)


if __name__ == "__main__":
    main()
