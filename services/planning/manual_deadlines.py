"""Manual deadlines: students adding their own "exam Friday" without
needing it in their calendar.

Architecture choice: write manual deadlines into `calendar_events` under
a per-user `kind='manual'` `calendar_feeds` row, lazy-created on first
insert. This means:

  - The existing deadline detector (`services/planning/deadlines.py`)
    picks them up unchanged. It searches calendar_events with the
    keyword regex; manual deadlines whose label includes "midterm",
    "exam", "final", "test", "quiz", or "deadline" qualify automatically.
    For other labels (e.g. "Paper" or "Final project"), we prefix the
    summary with "deadline:" inside the label so the regex hits.

  - The WeekTimeGrid renders them at their date because they're real
    calendar_events rows.

  - The HTTP and EventKit sync paths skip 'manual' feeds because their
    short-circuit logic is `feed.kind != 'url'` for HTTP and per-feed
    DELETE for local. The events stick around forever (or until the
    user removes them).

  - The schema migration 0015 already extends the kind CHECK constraint
    to include 'manual'.
"""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

# Sentinel URL for the manual feed. url_hash is unique per (user_id,
# url_hash); the sentinel ensures one manual feed per user even after
# concurrent first-insert calls.
_MANUAL_FEED_URL = "carrel://manual-deadlines"
_MANUAL_FEED_LABEL = "Manual deadlines"

# The deadline detector matches a fixed keyword set. We prefix manual
# deadlines with "Deadline:" so the regex always hits even when the
# user's label doesn't naturally include the keyword. Display in the
# UI strips the prefix.
DISPLAY_PREFIX = "Deadline: "


def ensure_manual_feed(conn: sqlite3.Connection, *, user_id: str = "local") -> str:
    """Return the manual-deadline feed id for this user, creating it if
    needed. Idempotent — concurrent inserts converge on the same row
    via the UNIQUE (user_id, url_hash) constraint."""
    url_hash = hashlib.sha256(
        f"{user_id}:{_MANUAL_FEED_URL}".encode("utf-8")
    ).hexdigest()
    row = conn.execute(
        "SELECT id FROM calendar_feeds WHERE user_id = ? AND url_hash = ?",
        (user_id, url_hash),
    ).fetchone()
    if row:
        return row["id"]

    feed_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO calendar_feeds (
            id, user_id, label, url, url_hash, color, is_enabled,
            consecutive_failures, kind, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, NULL, 1, 0, 'manual',
                  CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        (feed_id, user_id, _MANUAL_FEED_LABEL, _MANUAL_FEED_URL, url_hash),
    )
    return feed_id


def insert_manual_deadline(
    conn: sqlite3.Connection,
    *,
    label: str,
    deadline_at: str,
    user_id: str = "local",
) -> str:
    """Persist a manual deadline as a calendar_events row inside the
    manual feed. Returns the new event_id.

    `deadline_at` must be ISO 8601. The detector reads `start_at`, so
    that's where we put the deadline timestamp; `end_at` is set to one
    hour later so the row passes any "duration > 0" sanity checks.
    """
    feed_id = ensure_manual_feed(conn, user_id=user_id)
    event_id = str(uuid.uuid4())

    # Prefix the label so the deadline detector's keyword regex hits
    # consistently regardless of user wording. The frontend strips
    # the prefix on display.
    summary = (
        f"{DISPLAY_PREFIX}{label.strip()}"
        if not label.lower().startswith(DISPLAY_PREFIX.lower().rstrip())
        else label.strip()
    )

    end_at = _add_hour(deadline_at)
    conn.execute(
        """
        INSERT INTO calendar_events (
            id, user_id, feed_id, uid, occurrence_key, summary,
            start_at, end_at, status, all_day, timezone,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'confirmed', 0, 'UTC',
                  CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        (
            event_id, user_id, feed_id,
            f"manual-{event_id}", f"manual-{event_id}-0",
            summary, deadline_at, end_at,
        ),
    )
    return event_id


def delete_manual_deadline(
    conn: sqlite3.Connection,
    *,
    event_id: str,
    user_id: str = "local",
) -> bool:
    """Remove a manual deadline. Returns True if a row was deleted."""
    feed_id = ensure_manual_feed(conn, user_id=user_id)
    cur = conn.execute(
        "DELETE FROM calendar_events WHERE id = ? AND feed_id = ? AND user_id = ?",
        (event_id, feed_id, user_id),
    )
    return cur.rowcount > 0


def list_manual_deadlines(
    conn: sqlite3.Connection,
    *,
    user_id: str = "local",
) -> list[dict]:
    """Return manual deadlines for this user, soonest first. The
    frontend strips DISPLAY_PREFIX before showing the label."""
    feed_id = ensure_manual_feed(conn, user_id=user_id)
    rows = conn.execute(
        """
        SELECT id, summary, start_at
        FROM calendar_events
        WHERE feed_id = ? AND user_id = ? AND status != 'cancelled'
        ORDER BY start_at ASC
        """,
        (feed_id, user_id),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "label": _strip_prefix(r["summary"] or ""),
            "deadline_at": r["start_at"],
        }
        for r in rows
    ]


def _add_hour(iso: str) -> str:
    if iso.endswith("Z"):
        iso = iso[:-1] + "+00:00"
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt2 = dt.timestamp() + 3600
    out = datetime.fromtimestamp(dt2, tz=timezone.utc).isoformat()
    return out.replace("+00:00", "Z")


def _strip_prefix(label: str) -> str:
    if label.lower().startswith(DISPLAY_PREFIX.lower()):
        return label[len(DISPLAY_PREFIX):]
    return label
