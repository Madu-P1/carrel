"""Apple Calendar (EventKit) → Carrel sync service.

The macOS shell reads the user's Calendar.app events via EventKit and
POSTs them to `/api/calendar/local/sync`. This module owns the
backend half of that boundary:

  1. Idempotently register the EKCalendar as a `calendar_feeds` row
     with `kind='local'` (synthetic URL `eventkit://local/{id}`).
  2. Convert each `LocalCalendarEventInput` into a `ParsedEvent`
     compatible with the existing repository upsert pipeline so
     local feeds and HTTP feeds share the same downstream code path
     (planner, coach, dashboard).
  3. Record a sync_runs row so the existing freshness UI ("synced 2
     min ago", consecutive-failure counter) lights up for local
     feeds the same way it does for HTTP feeds.
  4. Return upsert/delete counts to the caller.

Why ParsedEvent reuse: forking the events table for local-vs-remote
would mean rewriting the planner, the WeekTimeGrid query, and every
suggestion engine. Reusing ParsedEvent + upsert_events keeps local
calendars first-class without code duplication. The trade-off is a
small adapter layer here.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from api_models import LocalCalendarEventInput, LocalCalendarSyncRequest
from services.app_state import log_study_event
from services.calendar.ical_parser import ParsedEvent
from services.calendar.repository import (
    DEFAULT_USER,
    FeedRow,
    begin_sync_run,
    complete_sync_run,
    upsert_events,
    upsert_local_feed,
)


def _to_parsed_event(payload: LocalCalendarEventInput) -> ParsedEvent:
    """Adapt the JSON payload into a ParsedEvent the repository can upsert.

    The occurrence_key uses the EventKit UID directly — EventKit already
    distinguishes recurring instances by giving each its own UID,
    unlike iCal RECURRENCE-ID, so there's no extra indirection needed.

    source_hash is computed deterministically over the event fields so
    re-syncing identical events doesn't bump updated_at (cheaper writes,
    accurate "changed since" semantics).
    """
    raw_dict: dict[str, Any] = payload.model_dump(mode="json")
    payload_for_hash = json.dumps(raw_dict, sort_keys=True, ensure_ascii=False)
    source_hash = hashlib.sha256(payload_for_hash.encode("utf-8")).hexdigest()
    return ParsedEvent(
        uid=payload.uid,
        occurrence_key=payload.uid,
        recurrence_id=None,
        summary=payload.summary,
        start_at=payload.start_at,
        end_at=payload.end_at,
        timezone=payload.timezone,
        all_day=payload.all_day,
        location=payload.location,
        categories=None,
        status=payload.status,
        rrule=None,
        source_updated_at=None,
        source_hash=source_hash,
        raw=raw_dict,
    )


def sync_local_calendar(
    conn: sqlite3.Connection,
    request: LocalCalendarSyncRequest,
    *,
    user_id: str = DEFAULT_USER,
) -> tuple[FeedRow, int, int, int]:
    """Upsert one EKCalendar's worth of events. Returns
    (feed, items_seen, items_upserted, items_deleted).

    Caller owns the transaction (the FastAPI route's `with db.get_db()`).
    """
    feed = upsert_local_feed(
        conn,
        calendar_identifier=request.calendar_identifier,
        label=request.label,
        color=request.color,
        user_id=user_id,
    )

    parsed = [_to_parsed_event(ev) for ev in request.events]
    items_seen = len(parsed)

    sync_run_id = begin_sync_run(conn, feed.id)
    try:
        items_upserted, items_deleted = upsert_events(
            conn, feed.id, parsed, user_id=user_id
        )
        complete_sync_run(
            conn,
            sync_run_id,
            status="success",
            http_status=None,
            items_seen=items_seen,
            items_upserted=items_upserted,
            items_deleted=items_deleted,
            error=None,
        )
    except Exception as exc:
        complete_sync_run(
            conn,
            sync_run_id,
            status="error",
            http_status=None,
            items_seen=items_seen,
            items_upserted=0,
            items_deleted=0,
            error=str(exc)[:500],
        )
        raise

    # Mark the feed as just-synced so the freshness pill in the UI is
    # accurate for local feeds the same way it is for HTTP feeds.
    now_iso = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    conn.execute(
        """
        UPDATE calendar_feeds
        SET last_synced_at = ?, last_successful_sync_at = ?,
            consecutive_failures = 0, last_error = NULL, updated_at = ?
        WHERE id = ?
        """,
        (now_iso, now_iso, now_iso, feed.id),
    )

    # Emit a study event so the dashboard (and any future SSE / poll
    # consumer) sees the calendar changed and re-runs coach advice.
    # We only emit when something actually changed — pure no-op syncs
    # would create a stream of meaningless events that hurt the
    # signal-to-noise of the recent-events feed.
    if items_upserted > 0 or items_deleted > 0:
        log_study_event(
            conn,
            "local_calendar_synced",
            payload={
                "feed_id": feed.id,
                "calendar_identifier": request.calendar_identifier,
                "items_seen": items_seen,
                "items_upserted": items_upserted,
                "items_deleted": items_deleted,
            },
        )

    conn.commit()

    return feed, items_seen, items_upserted, items_deleted
