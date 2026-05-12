#!/usr/bin/env python3
"""Carrel autonomous build: task classifier and skill router.

Fires on UserPromptSubmit. Reads JSON from stdin. Inspects the prompt for
patterns that map to specific skills or slash commands. Logs the routing
decision to .claude/logs/routing.jsonl. Injects additionalContext suggesting
the best-fit skill BEFORE generic execution.

Opt-in: only fires when CARREL_AUTONOMOUS=true. Otherwise exits silently so
ad-hoc Claude Code sessions are not affected.

Halt: if .claude/HALT exists, injects a halt-requested message instead of
routing advice.
"""
import json
import os
import re
import sys
import time
from pathlib import Path


def main() -> None:
    if os.environ.get("CARREL_AUTONOMOUS") != "true":
        sys.exit(0)

    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    prompt = data.get("prompt", "") or ""
    session = data.get("session_id", "")
    cwd = data.get("cwd", "")

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", cwd)
    project_path = Path(project_dir) if project_dir else Path.cwd()

    halt_file = project_path / ".claude" / "HALT"
    if halt_file.exists():
        out = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": (
                    "Carrel HALT signal present at .claude/HALT. The autonomous routine should stop "
                    "immediately and report current state to the operator. Do not start new work. "
                    "Remove the HALT file only after the operator confirms."
                ),
            }
        }
        print(json.dumps(out))
        sys.exit(0)

    log_dir = project_path / ".claude" / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        sys.exit(0)
    log_file = log_dir / "routing.jsonl"

    rules = [
        (r"\b(bug|broken|not working|investigate|debug|error|stack ?trace|crash)\b",
         "/investigate",
         "bug or debug keyword"),
        (r"\b(security|vulnerab|injection|XSS|CSRF|auth bypass|secrets?)\b",
         "/cso (full audit) or /security-review for the current diff",
         "security keyword"),
        (r"\b(adversarial review|second opinion|challenge my|/codex)\b",
         "/codex challenge",
         "adversarial review request"),
        (r"\b(ship it|ship this|deploy|release|land it|merge to main)\b",
         "/ship then /land-and-deploy",
         "ship or deploy keyword"),
        (r"\b(plan |planning|architecture decision|design a|architect a)\b",
         "/claude-mem:make-plan, then /claude-mem:do, or /autoplan for review chain",
         "planning keyword"),
        (r"\b(accessib|a11y|WCAG|screen reader|keyboard nav)\b",
         "design:accessibility-review",
         "accessibility keyword"),
        (r"\b(performance|benchmark|slow|latency|profiling|fps drop)\b",
         "/benchmark",
         "performance keyword"),
        (r"\b(visual polish|UX polish|UI polish|design review|design pass)\b",
         "/design-review",
         "design review keyword"),
        (r"\b(QA|test the site|find bugs|smoke test|dogfood)\b",
         "/qa",
         "QA keyword"),
        (r"\b(refactor|simplify|deduplicate|clean ?up)\b",
         "/simplify followed by /codex challenge",
         "refactor keyword"),
        (r"\b(review (this|the) (PR|diff|branch)|code review|review my)\b",
         "/review",
         "code review request"),
        (r"\b(retrospective|retro|weekly summary)\b",
         "/retro",
         "retrospective keyword"),
        (r"\b(document(ation)?|write docs|update README|update CLAUDE\.md)\b",
         "engineering:documentation",
         "documentation keyword"),
    ]

    suggestion = ""
    reason = "no specific skill match; fall through to general execution"
    for pattern, skill, why in rules:
        if re.search(pattern, prompt, re.IGNORECASE):
            suggestion = skill
            reason = why
            break

    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "session": session,
        "prompt_snippet": prompt[:200],
        "suggestion": suggestion,
        "reason": reason,
    }
    try:
        with log_file.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass

    if suggestion:
        out = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": (
                    f"Carrel autonomous routing hint: this task pattern-matched on "
                    f"\"{reason}\". The most fitting tool is: {suggestion}. "
                    f"Invoke it before generic execution unless you have a documented reason to prefer otherwise. "
                    f"If you override, append a counter-rationale to .claude/logs/routing.jsonl."
                ),
            }
        }
        print(json.dumps(out))

    sys.exit(0)


if __name__ == "__main__":
    main()
