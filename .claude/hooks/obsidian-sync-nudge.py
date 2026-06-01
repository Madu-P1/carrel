#!/usr/bin/env python3
"""Stop-hook nudge: remind the agent to sync the Obsidian vault at session end.

Belt-and-suspenders backstop for the `session-end-vault-sync` memory directive.
It does NOT dump anything into the vault (curation is the agent's job); it only
re-prompts the agent once when today's vault daily note still looks unsynced.

Safety properties (this hook must never trap a session in a loop):
- Silent in unattended build loops (FORGE_AUTONOMOUS / CARREL_AUTONOMOUS) so it
  never collides with the score-loop Stop gates and never nudges a headless run.
- Honors `stop_hook_active` and a per-session marker so it re-prompts AT MOST
  once, then allows the stop.
- Fails safe: any error or unreadable state -> allow the stop (exit 0).
"""

import hashlib
import json
import os
import pathlib
import sys
import tempfile
import time

VAULT_DAILY = pathlib.Path("/Users/madu/Documents/Obsidian Vault/Daily")
# A filled daily note is far longer than the ~360-char blank template.
SYNCED_MIN_CHARS = 700


def allow() -> None:
    sys.exit(0)


def main() -> None:
    # Never fire inside an autonomous build loop.
    if (
        os.environ.get("FORGE_AUTONOMOUS") == "true"
        or os.environ.get("CARREL_AUTONOMOUS") == "true"
    ):
        allow()

    try:
        data = json.load(sys.stdin)
    except Exception:
        allow()

    # If this stop is already a continuation triggered by a stop hook, let it end.
    if data.get("stop_hook_active"):
        allow()

    session = str(data.get("session_id", "") or "default")
    marker = pathlib.Path(tempfile.gettempdir()) / (
        "obsidian-nudge-" + hashlib.sha1(session.encode()).hexdigest()[:12]
    )
    if marker.exists():
        allow()

    today = time.strftime("%Y-%m-%d")
    note = VAULT_DAILY / f"{today}.md"
    try:
        if note.exists() and len(note.read_text().strip()) > SYNCED_MIN_CHARS:
            allow()  # already synced today
    except Exception:
        allow()

    # Needs a nudge. Mark FIRST (so we only ever re-prompt once), then block.
    try:
        marker.write_text(today)
    except Exception:
        allow()  # cannot guarantee single-shot -> do not risk a loop

    reason = (
        f"Session-end check: today's Obsidian vault daily note (Daily/{today}.md) "
        "does not look synced yet. If this session did substantive work "
        "(decisions, shipped code, state changes), mirror it into the vault now "
        "per the `session-end-vault-sync` memory: fill the daily note and update "
        "Timeline / Open threads / Projects, mirroring any new memory as a curated "
        "vault note. If the session was trivial with nothing worth keeping, say so "
        "in one line and stop."
    )
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


if __name__ == "__main__":
    main()
