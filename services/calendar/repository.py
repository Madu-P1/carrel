"""SQL access for calendar feeds, events, sync runs, and study suggestions.

Module functions instead of repository classes — Carrel's existing
pattern. SQLite is the only backend; abstracting it behind a class
buys nothing today and makes test setup harder.

Each function takes a connection (sqlite3.Connection from db.get_db())
as its first argument so the caller controls transaction boundaries.
The connection is the unit of work; this layer commits nothing.
"""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Optional

from services.calendar.secrets import CalendarSecretStore, default_secret_store
from services.calendar.validators import mask_url


# ---------------------------------------------------------------------
# Domain dataclasses
# ---------------------------------------------------------------------


@dataclass
class FeedRow:
    id: str
    user_id: str
    label: str
    url: str
    keychain_ref: Optional[str]
    color: Optional[str]
    is_enabled: bool
    etag: Optional[str]
    last_modified: Optional[str]
    last_synced_at: Optional[str]
    last_successful_sync_at: Optional[str]
    consecutive_failures: int
    last_error: Optional[str]


@dataclass
class EventRow:
    id: str
    feed_id: str
    uid: str
    occurrence_key: str
    summary: str
    start_at: str
    end_at: str
    timezone: Optional[str]
    all_day: bool
    location: Optional[str]
    categories: Optional[str]
    status: str
    rrule: Optional[str]


@dataclass
class SyncRunRow:
    id: str
    feed_id: str
    started_at: str
    finished_at: Optional[str]
    status: str
    http_status: Optional[int]
    items_seen: int
    items_upserted: int
    items_deleted: int
    error: Optional[str]


@dataclass
class SuggestionRow:
    id: str
    user_id: str
    kind: str
    status: str
    start_at: str
    end_at: str
    due_at: Optional[str]
    doc_id: Optional[str]
    source_event_id: Optional[str]
    reason_code: str
    reason_text: str
    score: Optional[float]
    accepted_at: Optional[str]
    dismissed_at: Optional[str]
    created_at: str


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

DEFAULT_USER = "local"


def _new_id() -> str:
    return str(uuid.uuid4())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def url_hash(url: str) -> str:
    """Stable per-URL fingerprint for the (user_id, url_hash) unique key.

    SHA-256 hex digest. Not a security boundary — just a dedup key.
    """
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------
# Feeds
# ---------------------------------------------------------------------


def insert_feed(
    conn: sqlite3.Connection,
    *,
    label: str,
    url: str,
    color: Optional[str],
    user_id: str = DEFAULT_USER,
    secret_store: CalendarSecretStore | None = None,
) -> FeedRow:
    """Create a new feed row. Raises sqlite3.IntegrityError on duplicate URL."""
    feed_id = _new_id()
    now = _now_iso()
    store = secret_store or default_secret_store()
    keychain_ref = store.store_url(feed_id, url)
    conn.execute(
        """
        INSERT INTO calendar_feeds (
            id, user_id, label, url, url_hash, color, keychain_ref,
            is_enabled, consecutive_failures, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?)
        """,
        (feed_id, user_id, label, mask_url(url), url_hash(url), color, keychain_ref, now, now),
    )
    conn.commit()
    return _feed_from_row(
        conn.execute("SELECT * FROM calendar_feeds WHERE id = ?", (feed_id,)).fetchone()
    )


def list_feeds(conn: sqlite3.Connection, *, user_id: str = DEFAULT_USER) -> List[FeedRow]:
    migrate_plaintext_feed_urls(conn)
    rows = conn.execute(
        """
        SELECT * FROM calendar_feeds
        WHERE user_id = ?
        ORDER BY created_at ASC
        """,
        (user_id,),
    ).fetchall()
    return [_feed_from_row(r) for r in rows]


def get_feed(conn: sqlite3.Connection, feed_id: str) -> Optional[FeedRow]:
    migrate_plaintext_feed_urls(conn)
    row = conn.execute("SELECT * FROM calendar_feeds WHERE id = ?", (feed_id,)).fetchone()
    return _feed_from_row(row) if row else None


def list_stale_feeds(
    conn: sqlite3.Connection,
    *,
    threshold_minutes: int,
    user_id: str = DEFAULT_USER,
) -> List[FeedRow]:
    """Feeds whose last_synced_at is older than threshold_minutes (or NULL).

    Used by:
      - app startup tick (kick off async refresh of any stale feed)
      - GET /api/plan SWR path (only mark stale feeds for background sync)
    """
    migrate_plaintext_feed_urls(conn)
    cutoff = datetime.now(timezone.utc).timestamp() - threshold_minutes * 60
    cutoff_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    # SQLite quirk: ASC sorts NULLs first by default. We rely on that
    # behavior here (never-synced feeds get top priority) instead of
    # the explicit `NULLS FIRST` keyword which isn't supported on the
    # SQLite version that ships with macOS until 3.30.
    rows = conn.execute(
        """
        SELECT * FROM calendar_feeds
        WHERE user_id = ?
          AND is_enabled = 1
          AND (last_synced_at IS NULL OR last_synced_at < ?)
        ORDER BY consecutive_failures ASC, last_synced_at ASC
        """,
        (user_id, cutoff_iso),
    ).fetchall()
    return [_feed_from_row(r) for r in rows]


def update_feed_after_sync(
    conn: sqlite3.Connection,
    feed_id: str,
    *,
    succeeded: bool,
    etag: Optional[str],
    last_modified: Optional[str],
    error_message: Optional[str],
) -> None:
    """Update feed row's sync bookkeeping fields after a sync attempt.

    Always bumps last_synced_at (the attempt). Bumps last_successful_sync_at
    only on success. Increments consecutive_failures on error, resets to 0
    on success — drives any future backoff logic.
    """
    now = _now_iso()
    if succeeded:
        conn.execute(
            """
            UPDATE calendar_feeds SET
                last_synced_at = ?,
                last_successful_sync_at = ?,
                consecutive_failures = 0,
                last_error = NULL,
                etag = ?,
                last_modified = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (now, now, etag, last_modified, now, feed_id),
        )
    else:
        conn.execute(
            """
            UPDATE calendar_feeds SET
                last_synced_at = ?,
                consecutive_failures = consecutive_failures + 1,
                last_error = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (now, error_message, now, feed_id),
        )
    conn.commit()


def delete_feed(conn: sqlite3.Connection, feed_id: str) -> bool:
    """Delete a feed and (via FK cascade) its events + sync_runs."""
    row = conn.execute(
        "SELECT keychain_ref FROM calendar_feeds WHERE id = ?", (feed_id,)
    ).fetchone()
    cur = conn.execute("DELETE FROM calendar_feeds WHERE id = ?", (feed_id,))
    conn.commit()
    if row and row["keychain_ref"]:
        default_secret_store().delete_url(row["keychain_ref"])
    return cur.rowcount > 0


def update_feed_label(conn: sqlite3.Connection, feed_id: str, label: str) -> Optional[FeedRow]:
    conn.execute(
        "UPDATE calendar_feeds SET label = ?, updated_at = ? WHERE id = ?",
        (label, _now_iso(), feed_id),
    )
    conn.commit()
    return get_feed(conn, feed_id)


def _feed_from_row(row) -> FeedRow:
    columns = set(row.keys())
    return FeedRow(
        id=row["id"],
        user_id=row["user_id"],
        label=row["label"],
        url=row["url"],
        keychain_ref=row["keychain_ref"] if "keychain_ref" in columns else None,
        color=row["color"],
        is_enabled=bool(row["is_enabled"]),
        etag=row["etag"],
        last_modified=row["last_modified"],
        last_synced_at=row["last_synced_at"],
        last_successful_sync_at=row["last_successful_sync_at"],
        consecutive_failures=row["consecutive_failures"],
        last_error=row["last_error"],
    )


def resolve_feed_url(
    feed: FeedRow, secret_store: CalendarSecretStore | None = None
) -> Optional[str]:
    if feed.keychain_ref:
        return (secret_store or default_secret_store()).get_url(feed.keychain_ref)
    return feed.url if feed.url.startswith(("http://", "https://")) else None


def migrate_plaintext_feed_urls(
    conn: sqlite3.Connection,
    *,
    secret_store: CalendarSecretStore | None = None,
) -> int:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(calendar_feeds)").fetchall()}
    if "keychain_ref" not in columns:
        return 0

    rows = conn.execute(
        """
        SELECT id, url, keychain_ref FROM calendar_feeds
        WHERE (keychain_ref IS NULL OR keychain_ref = '')
          AND (url LIKE 'http://%' OR url LIKE 'https://%')
        """
    ).fetchall()
    store = secret_store or default_secret_store()
    migrated = 0
    for row in rows:
        raw_url = row["url"]
        reference = store.store_url(row["id"], raw_url)
        conn.execute(
            """
            UPDATE calendar_feeds
            SET url = ?, keychain_ref = ?, updated_at = ?
            WHERE id = ?
            """,
            (mask_url(raw_url), reference, _now_iso(), row["id"]),
        )
        migrated += 1
    if migrated:
        conn.commit()
    return migrated


# ---------------------------------------------------------------------
# Sync runs
# ---------------------------------------------------------------------


def begin_sync_run(conn: sqlite3.Connection, feed_id: str) -> str:
    """Insert a 'running' sync_runs row and return its id."""
    run_id = _new_id()
    conn.execute(
        """
        INSERT INTO calendar_sync_runs (id, feed_id, started_at, status)
        VALUES (?, ?, ?, 'running')
        """,
        (run_id, feed_id, _now_iso()),
    )
    conn.commit()
    return run_id


def complete_sync_run(
    conn: sqlite3.Connection,
    run_id: str,
    *,
    status: str,
    http_status: Optional[int] = None,
    items_seen: int = 0,
    items_upserted: int = 0,
    items_deleted: int = 0,
    error: Optional[str] = None,
) -> None:
    conn.execute(
        """
        UPDATE calendar_sync_runs SET
            finished_at = ?,
            status = ?,
            http_status = ?,
            items_seen = ?,
            items_upserted = ?,
            items_deleted = ?,
            error = ?
        WHERE id = ?
        """,
        (_now_iso(), status, http_status, items_seen, items_upserted, items_deleted, error, run_id),
    )
    conn.commit()


# ---------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------


def upsert_events(
    conn: sqlite3.Connection,
    feed_id: str,
    parsed_events: Iterable,
    *,
    user_id: str = DEFAULT_USER,
) -> tuple[int, int]:
    """Bulk upsert + tombstone events from a fresh parse.

    Returns (items_upserted, items_deleted).

    Strategy: for each parsed event we INSERT OR REPLACE keyed on
    (feed_id, occurrence_key). Then we DELETE any existing event for
    this feed whose occurrence_key wasn't in the parsed set — those
    occurrences disappeared from the source feed (cancellation,
    rescheduling, RRULE shrunk, EXDATE added).
    """
    parsed = list(parsed_events)
    seen_keys = {p.occurrence_key for p in parsed}
    now = _now_iso()
    upserted = 0

    for ev in parsed:
        existing = conn.execute(
            """
            SELECT id, source_hash FROM calendar_events
            WHERE feed_id = ? AND occurrence_key = ?
            """,
            (feed_id, ev.occurrence_key),
        ).fetchone()

        if existing and existing["source_hash"] == ev.source_hash:
            # Unchanged — skip the write so updated_at stays meaningful.
            continue

        if existing:
            conn.execute(
                """
                UPDATE calendar_events SET
                    summary = ?, start_at = ?, end_at = ?, timezone = ?,
                    all_day = ?, location = ?, categories = ?, status = ?,
                    rrule = ?, source_updated_at = ?, source_hash = ?,
                    recurrence_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    ev.summary,
                    ev.start_at,
                    ev.end_at,
                    ev.timezone,
                    1 if ev.all_day else 0,
                    ev.location,
                    ev.categories,
                    ev.status,
                    ev.rrule,
                    ev.source_updated_at,
                    ev.source_hash,
                    ev.recurrence_id,
                    now,
                    existing["id"],
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO calendar_events (
                    id, user_id, feed_id, uid, occurrence_key,
                    recurrence_id, rrule, summary, start_at, end_at,
                    timezone, all_day, location, categories, status,
                    source_updated_at, source_hash, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _new_id(),
                    user_id,
                    feed_id,
                    ev.uid,
                    ev.occurrence_key,
                    ev.recurrence_id,
                    ev.rrule,
                    ev.summary,
                    ev.start_at,
                    ev.end_at,
                    ev.timezone,
                    1 if ev.all_day else 0,
                    ev.location,
                    ev.categories,
                    ev.status,
                    ev.source_updated_at,
                    ev.source_hash,
                    now,
                    now,
                ),
            )
        upserted += 1

    # Tombstone occurrences that are no longer in the feed
    if seen_keys:
        placeholders = ",".join("?" * len(seen_keys))
        cur = conn.execute(
            f"""
            DELETE FROM calendar_events
            WHERE feed_id = ? AND occurrence_key NOT IN ({placeholders})
            """,
            (feed_id, *seen_keys),
        )
        deleted = cur.rowcount
    else:
        # Empty feed → drop everything we had
        cur = conn.execute("DELETE FROM calendar_events WHERE feed_id = ?", (feed_id,))
        deleted = cur.rowcount

    conn.commit()
    return upserted, deleted


def list_events_in_window(
    conn: sqlite3.Connection,
    *,
    start: str,
    end: str,
    user_id: str = DEFAULT_USER,
) -> List[EventRow]:
    """Events whose [start_at, end_at) overlaps [start, end).

    Both bounds are ISO 8601 UTC strings.
    """
    rows = conn.execute(
        """
        SELECT * FROM calendar_events
        WHERE user_id = ?
          AND status != 'cancelled'
          AND start_at < ?
          AND end_at > ?
        ORDER BY start_at ASC
        """,
        (user_id, end, start),
    ).fetchall()
    return [_event_from_row(r) for r in rows]


def _event_from_row(row) -> EventRow:
    return EventRow(
        id=row["id"],
        feed_id=row["feed_id"],
        uid=row["uid"],
        occurrence_key=row["occurrence_key"],
        summary=row["summary"] or "",
        start_at=row["start_at"],
        end_at=row["end_at"],
        timezone=row["timezone"],
        all_day=bool(row["all_day"]),
        location=row["location"],
        categories=row["categories"],
        status=row["status"],
        rrule=row["rrule"],
    )


# ---------------------------------------------------------------------
# Suggestions
# ---------------------------------------------------------------------


def insert_suggestion(
    conn: sqlite3.Connection,
    *,
    kind: str,
    start_at: str,
    end_at: str,
    reason_code: str,
    reason_text: str,
    due_at: Optional[str] = None,
    doc_id: Optional[str] = None,
    source_event_id: Optional[str] = None,
    score: Optional[float] = None,
    user_id: str = DEFAULT_USER,
) -> str:
    sug_id = _new_id()
    conn.execute(
        """
        INSERT INTO study_suggestions (
            id, user_id, kind, status, start_at, end_at, due_at,
            doc_id, source_event_id, reason_code, reason_text, score,
            created_at
        ) VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            sug_id,
            user_id,
            kind,
            start_at,
            end_at,
            due_at,
            doc_id,
            source_event_id,
            reason_code,
            reason_text,
            score,
            _now_iso(),
        ),
    )
    conn.commit()
    return sug_id


def list_active_suggestions(
    conn: sqlite3.Connection, *, user_id: str = DEFAULT_USER
) -> List[SuggestionRow]:
    rows = conn.execute(
        """
        SELECT * FROM study_suggestions
        WHERE user_id = ? AND status = 'pending'
        ORDER BY start_at ASC
        """,
        (user_id,),
    ).fetchall()
    return [_suggestion_from_row(r) for r in rows]


def update_suggestion_status(
    conn: sqlite3.Connection,
    suggestion_id: str,
    *,
    status: str,
) -> Optional[SuggestionRow]:
    """Transition a suggestion to accepted/dismissed/expired.

    Sets the corresponding timestamp column. The 5-second-undo flow is
    a frontend concern — the backend just records the final state.
    """
    now = _now_iso()
    if status == "accepted":
        conn.execute(
            "UPDATE study_suggestions SET status = ?, accepted_at = ? WHERE id = ?",
            (status, now, suggestion_id),
        )
    elif status == "dismissed":
        conn.execute(
            "UPDATE study_suggestions SET status = ?, dismissed_at = ? WHERE id = ?",
            (status, now, suggestion_id),
        )
    elif status == "expired":
        conn.execute(
            "UPDATE study_suggestions SET status = ? WHERE id = ?",
            (status, suggestion_id),
        )
    elif status == "pending":
        # Used by the undo flow within the 5-second window.
        conn.execute(
            "UPDATE study_suggestions SET status = ?, dismissed_at = NULL, accepted_at = NULL WHERE id = ?",
            (status, suggestion_id),
        )
    else:
        raise ValueError(f"Unknown suggestion status: {status}")
    conn.commit()
    return _row_or_none(
        conn.execute("SELECT * FROM study_suggestions WHERE id = ?", (suggestion_id,)).fetchone()
    )


def expire_past_pending_suggestions(
    conn: sqlite3.Connection, *, user_id: str = DEFAULT_USER
) -> int:
    """Mark any pending suggestion whose start_at has passed as expired.

    Run on every /api/plan request (cheap UPDATE on indexed column).
    Avoids stale "study Wednesday" suggestions hanging around on Friday.
    """
    cur = conn.execute(
        """
        UPDATE study_suggestions
        SET status = 'expired'
        WHERE user_id = ? AND status = 'pending' AND start_at < ?
        """,
        (user_id, _now_iso()),
    )
    conn.commit()
    return cur.rowcount


def _row_or_none(row) -> Optional[SuggestionRow]:
    return _suggestion_from_row(row) if row else None


def _suggestion_from_row(row) -> SuggestionRow:
    return SuggestionRow(
        id=row["id"],
        user_id=row["user_id"],
        kind=row["kind"],
        status=row["status"],
        start_at=row["start_at"],
        end_at=row["end_at"],
        due_at=row["due_at"],
        doc_id=row["doc_id"],
        source_event_id=row["source_event_id"],
        reason_code=row["reason_code"],
        reason_text=row["reason_text"],
        score=row["score"],
        accepted_at=row["accepted_at"],
        dismissed_at=row["dismissed_at"],
        created_at=row["created_at"],
    )
