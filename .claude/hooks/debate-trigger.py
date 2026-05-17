#!/usr/bin/env python3
"""Carrel autonomous build: architectural-debate trigger.

Fires on PreToolUse for Bash, Edit, Write. Detects architectural changes via
three precise signals so the routine knows when to spawn proponent + adversary
+ synthesizer before committing to an approach:

1. Manifest-file edits (Package.swift, pyproject.toml, package.json, etc.).
2. Code-area path edits (new migrations, new routes, new top-level modules).
3. Dependency-management command VERBS in Bash (pnpm add, uv add, etc.).

Critically, this does NOT scan Bash command bodies for free-text keywords.
A previous version's `\\bdependency\\b` regex fired on the word "dependency"
inside heredoc commit messages, producing false positives that wasted cycles.
The fix is to gate Bash detection on actual command verbs only.

This hook does NOT block. The audit-gate is the hard gate. This is a nudge.

Opt-in: only fires when CARREL_AUTONOMOUS=true.
"""

import json
import os
import re
import sys
import time
from pathlib import Path

# Manifest files: editing these is always architectural.
MANIFEST_FILE_PATTERNS = [
    r"Package\.swift$",
    r"pyproject\.toml$",
    r"package\.json$",
    r"pnpm-lock\.yaml$",
    r"uv\.lock$",
    r"Cargo\.toml$",
    r"go\.mod$",
]

# Code-area paths: creating files here is architectural.
ARCH_FILE_PATTERNS = [
    r"migrations/[^/]+\.(sql|py)$",
    r"alembic/versions/[^/]+\.py$",
    r"models/[^/]+\.py$",
    r"routes/[^/]+\.py$",
    r"services/[^/]+/__init__\.py$",
    r"ai/[^/]+\.py$",
    r"macos-app/Sources/[^/]+/[^/]+\.swift$",
    r"frontend/src/features/[^/]+/index\.(tsx?|jsx?)$",
    r"openapi\.(yaml|json)$",
    r"\.proto$",
]

# Architectural keywords. Only match against Edit/Write CONTENT, never against
# Bash command strings (because commit messages with words like "architecture"
# would false-positive otherwise).
ARCH_CONTENT_KEYWORDS = [
    r"\bbreaking\s+change\b",
    r"\bpublic\s+API\b",
    r"\bdata\s+model\b",
    r"\barchitecture\s+decision\b",
    r"\bmigration\s+strategy\b",
    r"\bschema\s+(change|migration)\b",
]

# Bash command verbs that indicate architectural change. Verb-only matching:
# the verb must appear at a command-position boundary, not buried in text.
ARCH_BASH_VERBS = [
    r"(^|[;&|]|\s)(pnpm|npm|yarn)\s+(add|remove)\b",
    r"(^|[;&|]|\s)(pip|uv)\s+(install|add|remove)\b",
    r"(^|[;&|]|\s)poetry\s+(add|remove)\b",
    r"(^|[;&|]|\s)swift\s+package\s+(add-dependency|add)\b",
    r"(^|[;&|]|\s)cargo\s+(add|remove)\b",
    r"(^|[;&|]|\s)go\s+(get|mod\s+tidy)\b",
]


def match_patterns(patterns: list[str], text: str) -> list[str]:
    if not text:
        return []
    return [p for p in patterns if re.search(p, text, re.IGNORECASE)]


def detect(tool_name: str, tool_input: dict) -> list[str]:
    hits: list[str] = []
    if tool_name == "Bash":
        cmd = tool_input.get("command", "") or ""
        hits += match_patterns(ARCH_BASH_VERBS, cmd)
        return hits
    if tool_name in ("Edit", "Write"):
        fp = tool_input.get("file_path", "") or ""
        hits += match_patterns(MANIFEST_FILE_PATTERNS, fp)
        hits += match_patterns(ARCH_FILE_PATTERNS, fp)
        content = " ".join(
            [
                tool_input.get("new_string", "") or "",
                tool_input.get("content", "") or "",
            ]
        )
        hits += match_patterns(ARCH_CONTENT_KEYWORDS, content)
    return hits


def main() -> None:
    if os.environ.get("CARREL_AUTONOMOUS") != "true":
        sys.exit(0)

    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {}) or {}

    hits = detect(tool_name, tool_input)
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
        "matched_patterns": hits,
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
                f"Carrel debate trigger: architectural signals matched {hits}. "
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
