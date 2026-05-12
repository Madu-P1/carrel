#!/usr/bin/env python3
"""Carrel autonomous build: architectural-debate trigger.

Fires on PreToolUse for Bash, Edit, Write. Detects architectural keywords in
tool input (new top-level modules, schema changes, API design, dependency
choice, provider swap). Logs to .claude/logs/debates/triggers.jsonl. Injects
additionalContext suggesting a proponent+adversary+synthesizer round.

This hook does NOT block. The audit-gate is the hard gate. This is a nudge.

Opt-in: only fires when CARREL_AUTONOMOUS=true.
"""
import json
import os
import re
import sys
import time
from pathlib import Path


ARCHITECTURAL_KEYWORDS = [
    r"\bnew\s+(table|model|schema|migration|API|endpoint|provider|client|service|module)\b",
    r"\bbreaking\s+change\b",
    r"\bmajor\s+refactor\b",
    r"\barchitecture\s+decision\b",
    r"\bswap\s+(provider|client|library|framework|backend)\b",
    r"\bdrop\s+support\s+for\b",
    r"\bdepend(ency|ence)\s+(add|change|remove|bump)\b",
    r"\bpublic\s+API\b",
    r"\bmigration\s+(plan|strategy)\b",
    r"\bdata\s+model\b",
]


def matches(text: str) -> list[str]:
    if not text:
        return []
    return [k for k in ARCHITECTURAL_KEYWORDS if re.search(k, text, re.IGNORECASE)]


def main() -> None:
    if os.environ.get("CARREL_AUTONOMOUS") != "true":
        sys.exit(0)

    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {}) or {}

    haystack = ""
    if tool_name == "Bash":
        haystack = tool_input.get("command", "") or ""
    elif tool_name in ("Edit", "Write"):
        parts = [
            tool_input.get("file_path", "") or "",
            tool_input.get("new_string", "") or "",
            tool_input.get("content", "") or "",
            tool_input.get("description", "") or "",
        ]
        haystack = "\n".join(parts)

    hits = matches(haystack)
    if not hits:
        sys.exit(0)

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "")
    if not project_dir:
        sys.exit(0)
    log_dir = Path(project_dir) / ".claude" / "logs" / "debates"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        sys.exit(0)

    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tool": tool_name,
        "matched_keywords": hits,
    }
    try:
        (log_dir / "triggers.jsonl").open("a").write(json.dumps(entry) + "\n")
    except Exception:
        pass

    # Nudge, do not block.
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": (
                f"Carrel debate trigger: architectural keywords matched {hits}. "
                f"Per the autonomous routine, before this action lands, consider spawning "
                f"proponent + adversary in parallel, then synthesizer, and persist the verdict "
                f"as an ADR in docs/decisions/NNNN-<slug>.md. If the synthesizer determined the "
                f"decision is trivial in its short-circuit, proceed; otherwise debate first. "
                f"Log: .claude/logs/debates/triggers.jsonl."
            ),
        }
    }
    print(json.dumps(out))
    sys.exit(0)


if __name__ == "__main__":
    main()
