"""The git commit the running process loaded, computed ONCE at import (boot).

The demo's stale-build guard. uvicorn loads the app once at boot, so a long-lived
server keeps running the code it loaded even after the repo moves on; it then
silently serves OLD code (the failure that made the engine look broken on
2026-06-14, see memory cachet-demo-empty-results-fix). Stamping the BOOT commit
into /api/health and the served page makes that visible, and comparing it to the
repo's live HEAD lets the demo warn that it is stale.

BOOT_COMMIT is read at import (process start), so it reflects the code the process
is actually running, never the repo's current state. current_head() reads the live
HEAD; keep it off hot paths (it shells out).
"""

from __future__ import annotations

import subprocess

import db


def _short_head() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(db.BASE_DIR),
            capture_output=True,
            text=True,
            timeout=2,
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        # No git (a packaged .app has no repo), git missing, or timeout: degrade
        # to a visible sentinel rather than raising. "unknown" disables the
        # stale-vs-current comparison (it never falsely warns).
        return "unknown"


# Computed once, at import (boot). Do NOT recompute per request: the whole point
# is that this stays pinned to the commit the process started on.
BOOT_COMMIT = _short_head()


def current_head() -> str:
    """The repo's CURRENT HEAD, read live. Compared against BOOT_COMMIT to detect a
    stale server (old in-memory code after the repo moved). Shells out, so callers
    keep it off hot paths (the served '/' page, never /api/health)."""
    return _short_head()


def is_stale() -> bool:
    """True when the process is running an older commit than the repo now holds."""
    head = current_head()
    return BOOT_COMMIT != "unknown" and head != "unknown" and head != BOOT_COMMIT
