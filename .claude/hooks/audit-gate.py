#!/usr/bin/env python3
"""Carrel autonomous build: major-action audit gate.

Fires on PreToolUse for Bash, Edit, Write. Detects "major actions": commits,
migrations, dependency changes, install-script writes, top-level module
creation, destructive operations.

Flow:
1. Hash the tool_input deterministically.
2. If an approval file already exists at .claude/logs/audits/approved/<hash>.json,
   pass through (the auditor already signed off).
3. Otherwise, write the pending action to .claude/logs/audits/pending/<hash>.json
   and return a deny decision with reasoning that instructs Claude to spawn the
   independent-auditor subagent first, await its verdict, then retry.

Destructive actions (force push, rm -rf, DROP TABLE, money-moving curl,
external messaging) require an explicit written justification in the auditor
approval file or are hard-blocked.

Opt-in: only fires when CARREL_AUTONOMOUS=true. Halt-aware: if .claude/HALT
exists, denies all major actions until removed.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path


def compute_staged_diff_hash(project_dir: str) -> str:
    """Hash the current staged diff so that approval invalidates on staged-content edits.

    Fix for the hash-drift weakness surfaced in operator-followups: previously the
    hash was computed from the bash command alone, so approving `git commit -m foo`
    once meant any later staged-file edits got the same approval. Including the
    staged-diff hash means each distinct staged tree gets its own audit.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--staged", "--no-color"],
            cwd=project_dir,
            capture_output=True,
            timeout=5,
            check=False,
        )
        return hashlib.sha256(result.stdout).hexdigest()[:16]
    except Exception:
        return "no-diff"


HEREDOC_PATTERN = re.compile(
    r"<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n(.*?)\n\s*\1\s*(?:\n|$)",
    re.DOTALL,
)


def _strip_heredocs(cmd: str) -> str:
    """Elide heredoc bodies so command-verb pattern matching isn't fooled
    by free text inside JSON payloads, commit messages, or docs.

    Matches `<<TAG`, `<<-TAG`, `<< 'TAG'`, `<< "TAG"` openings and
    removes everything up to the matching closing tag line. The outer
    command surface (anything before `<<TAG` and after the closing tag)
    is preserved so real verbs after a heredoc still fire.

    Trade-off: a heredoc whose body is piped to a shell (`cat << EOF | sh`)
    would silently lose its verb. The Carrel routine does not use that
    pattern; heredocs here are exclusively for `git commit -m "<msg>"`
    bodies and `cat > file.json << EOF` writes, neither of which executes
    the heredoc body as commands.
    """
    if not cmd:
        return cmd
    return HEREDOC_PATTERN.sub("\n", cmd)


MAJOR_BASH_PATTERNS = [
    r"\bgit\s+commit\b",
    r"\bgit\s+push\b",
    r"\bgit\s+merge\b(?!\s*--abort)",
    r"\bgit\s+rebase\b(?!\s*--abort)",
    r"\bgit\s+reset\b",
    r"\bgit\s+tag\b",
    r"\balembic\s+(upgrade|downgrade|revision)\b",
    r"\buv\s+(add|remove|sync)\b",
    r"\bpip\s+install\b",
    r"\bpnpm\s+(add|remove|install)\b",
    r"\bnpm\s+(install|uninstall|publish)\b",
    r"\bswift\s+package\s+(add|update)\b",
    r"\bcurl\s+[^|]*\|\s*(sh|bash|zsh)\b",
    r"\bgh\s+(pr|release|workflow|issue)\s+",
]

MAJOR_FILE_PATTERNS = [
    r"Package\.swift$",
    r"pyproject\.toml$",
    r"package\.json$",
    r"pnpm-lock\.yaml$",
    r"uv\.lock$",
    r"poetry\.lock$",
    r"install\.sh$",
    r"scripts/install\.sh$",
    r"migrations/[^/]+\.sql$",
    r"alembic/versions/[^/]+\.py$",
    r"\.github/workflows/[^/]+\.ya?ml$",
    r"Dockerfile$",
    r"docker-compose\.ya?ml$",
    r"CLAUDE\.md$",
    r"DESIGN\.md$",
]

DESTRUCTIVE_BASH_PATTERNS = [
    r"\brm\s+-rf\s+(?:/|\$HOME|~|/Users)",
    r"\bgit\s+push\s+-{1,2}f(orce)?\b",
    r"\bgit\s+push\s+.*--force-with-lease\b.*\b(main|master|production)\b",
    r"\bDROP\s+(TABLE|DATABASE|SCHEMA)\b",
    r"\bTRUNCATE\s+TABLE\b",
    r"\bgh\s+pr\s+merge\b",
    r"\bnpm\s+publish\b",
    r"\bpnpm\s+publish\b",
    r"\bcargo\s+publish\b",
    r"\bdocker\s+(push|tag)\s+.+:(latest|prod)\b",
]

# Outreach patterns (operator-set scope as of 2026-05-12: build-only, no
# outreach). These flag the action with kind=outreach so the auditor's
# operator-scope clause hard-rejects them.
OUTREACH_BASH_PATTERNS = [
    r"\b(mail|sendmail|mutt|mailx)\s+",
    r"\bosascript\b.*\b(Messages|Mail|Slack)\b",
    r"\bcurl\b.*\bhooks\.slack\.com\b",
    r"\bcurl\b.*\bapi\.telegram\.org\b",
    r"\bcurl\b.*\bdiscord(?:app)?\.com/api/webhooks\b",
    r"\bcurl\b.*\bapi\.twitter\.com\b",
    r"\bcurl\b.*\bapi\.x\.com\b",
    r"\bcurl\b.*\bapi\.linkedin\.com\b",
    r"\bcurl\b.*\b(mailchimp|sendgrid|postmark|resend|convertkit|mailerlite)\.com\b",
    r"\bcurl\b.*\bapi\.twilio\.com\b",
    r"\btwitter-cli\b|\btw\s+(post|tweet)\b",
    # Generic external POST/PUT/DELETE: this was previously classified as
    # destructive; reclassify so the operator-scope reason is clearer.
    r"\bcurl\s+.*-X\s+(POST|PUT|DELETE)\b.*https?://(?!localhost|127\.|0\.0\.0\.0)",
]


def is_major(tool_name: str, tool_input: dict) -> tuple[bool, str]:
    if tool_name == "Bash":
        raw = tool_input.get("command", "") or ""
        # Strip heredoc bodies so prose inside JSON writes or commit
        # messages doesn't false-positive against the verb regexes.
        cmd = _strip_heredocs(raw)
        for p in OUTREACH_BASH_PATTERNS:
            if re.search(p, cmd, re.IGNORECASE):
                return True, "outreach"
        for p in DESTRUCTIVE_BASH_PATTERNS:
            if re.search(p, cmd, re.IGNORECASE):
                return True, "destructive"
        for p in MAJOR_BASH_PATTERNS:
            if re.search(p, cmd, re.IGNORECASE):
                return True, "major"
    if tool_name in ("Edit", "Write"):
        fp = tool_input.get("file_path", "") or ""
        for p in MAJOR_FILE_PATTERNS:
            if re.search(p, fp):
                return True, "major"
    return False, ""


def main() -> None:
    if os.environ.get("CARREL_AUTONOMOUS") != "true":
        sys.exit(0)

    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {}) or {}

    major, kind = is_major(tool_name, tool_input)
    if not major:
        sys.exit(0)

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "")
    if not project_dir:
        sys.exit(0)
    project_path = Path(project_dir)
    log_dir = project_path / ".claude" / "logs"
    audit_dir = log_dir / "audits"
    approved_dir = audit_dir / "approved"
    pending_dir = audit_dir / "pending"
    halt_file = project_path / ".claude" / "HALT"

    for d in (approved_dir, pending_dir):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    # Stable hash of the action. For git commit, include the staged-diff hash so
    # that modifying staged files invalidates a previous approval (fix for the
    # audit-gate hash-drift weakness in operator-followups.jsonl).
    #
    # For Bash, the `description` field is a cosmetic LLM-generated label that
    # never affects what the shell runs. Drop it from the hash so relabeling
    # does not force a re-audit on identical commands. The pending file still
    # records the full tool_input including description.
    hash_input = dict(tool_input)
    if tool_name == "Bash":
        hash_input.pop("description", None)
    canonical_parts: dict = {"tool": tool_name, "input": hash_input}
    if tool_name == "Bash":
        cmd = tool_input.get("command", "") or ""
        # Use the heredoc-stripped form so "git commit" inside a JSON
        # body or message prose doesn't trigger staged_diff_hash on a
        # non-commit action (e.g., gh pr create whose body mentions it).
        if re.search(r"\bgit\s+commit\b", _strip_heredocs(cmd), re.IGNORECASE):
            canonical_parts["staged_diff_hash"] = compute_staged_diff_hash(project_dir)
    canonical = json.dumps(canonical_parts, sort_keys=True, ensure_ascii=False)
    h = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    if halt_file.exists():
        out = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    "Carrel HALT signal present at .claude/HALT. No major actions allowed "
                    "until the operator removes the file."
                ),
            }
        }
        print(json.dumps(out))
        sys.exit(0)

    approval_file = approved_dir / f"{h}.json"
    if approval_file.exists():
        # Already audited; allow through.
        try:
            allow_log = log_dir / "audit-allowed.jsonl"
            allow_log.open("a").write(
                json.dumps({
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "hash": h,
                    "tool": tool_name,
                    "kind": kind,
                }) + "\n"
            )
        except Exception:
            pass
        sys.exit(0)

    # Persist pending action so the auditor can pick it up.
    pending = pending_dir / f"{h}.json"
    try:
        pending.write_text(json.dumps({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "hash": h,
            "kind": kind,
            "tool_name": tool_name,
            "tool_input": tool_input,
        }, indent=2, ensure_ascii=False))
    except Exception:
        pass

    if kind == "outreach":
        reason = (
            f"OUTREACH SCOPE GATE (hash {h}): this {tool_name} call matches an outreach "
            f"pattern (mail, messaging, social, marketing, or external HTTP write). Per the "
            f"operator-set scope of the Carrel autonomous routine as of 2026-05-12, the "
            f"routine is BUILD-ONLY: it does not send DMs, recruitment messages, marketing "
            f"posts, or any external communication. Do NOT spawn the auditor to approve this. "
            f"Instead: log the surfaced outreach moment as a non-blocking follow-up in "
            f".claude/logs/operator-followups.jsonl with the task context and the proposed "
            f"action, then skip to the next plan task. The operator will handle outreach "
            f"manually. If you believe the constraint should be lifted, halt the routine and "
            f"surface for operator review; do not work around the gate."
        )
    elif kind == "destructive":
        reason = (
            f"DESTRUCTIVE ACTION GATE (hash {h}): this {tool_name} call matches a destructive "
            f"pattern (force push, rm -rf at root, DROP TABLE, publish, or PR merge). Per the "
            f"Carrel autonomous routine, this requires the independent-auditor subagent to "
            f"produce a WRITTEN JUSTIFICATION, a ROLLBACK PLAN, and an explicit answer to "
            f"'what would make this not necessary?' before approval. Spawn the auditor with "
            f"the pending action at .claude/logs/audits/pending/{h}.json. On APPROVED, the "
            f"auditor writes .claude/logs/audits/approved/{h}.json with the three required "
            f"fields. Retry only after the approval file exists."
        )
    else:
        reason = (
            f"MAJOR ACTION GATE (hash {h}): this {tool_name} call has been flagged as a major "
            f"action (commit, migration, dependency change, install-script edit, or top-level "
            f"module). Per the Carrel autonomous routine, you MUST spawn the independent-auditor "
            f"subagent first with: (1) the goal of the current work, (2) the diff or command "
            f"proposed, (3) the success criteria. The auditor will write its verdict to "
            f".claude/logs/audits/approved/{h}.json on APPROVED, or .claude/logs/audits/rejected/{h}.json "
            f"with a counter-proposal on REJECTED. Retry this tool call after the approval file "
            f"exists. Pending action persisted at .claude/logs/audits/pending/{h}.json."
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
