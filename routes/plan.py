"""GET /api/plan + suggestion accept/dismiss.

The Plan view's primary read endpoint. Implements stale-while-revalidate:

  1. Read events + suggestions from local DB (deterministic, fast)
  2. Run synth-suggestions to refresh the candidate set if needed
  3. Identify any feed whose `last_synced_at + 5min < now()` and kick
     a background fetch for it (fire-and-forget, doesn't block response)
  4. Return `is_freshening: true` if a refresh is in flight, so the
     frontend can show a subtle "syncing in background" affordance

The read path NEVER blocks on a remote fetch. If the user just opened
the app and feeds are stale, they see cached data instantly + the
freshening signal; the next /api/plan call (auto-triggered by the
hook on a short delay) will return the post-refresh state.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException

import db
from api_models import (
    CalendarEventRow,
    PlanResponse,
    StudySuggestionRow,
)
from routes.calendar import _row_to_response
from services.calendar import repository
from services.calendar.sync_queue import get_calendar_sync_queue
from services.planning import coach


router = APIRouter()


# How stale a feed has to be before we kick a background refresh on
# /api/plan. Mirrors the SWR contract from the spec.
STALE_THRESHOLD_MINUTES = 5

# Plan window: how much past + future to render. Keep this in sync with
# the WeekTimeGrid's default (7 days starting today).
PLAN_WINDOW_PAST_DAYS = 1
PLAN_WINDOW_FUTURE_DAYS = 7


def _kick_background_sync(feed_id: str) -> None:
    """Submit a calendar sync call to the lifecycle-managed background pool.

    Each task opens its OWN db connection — connections are not
    shareable across threads. Errors are logged, never raised; the
    next /api/plan call will see the resulting last_error on the feed
    row.
    """
    get_calendar_sync_queue().submit(feed_id)


def _events_to_response(rows: List[repository.EventRow]) -> List[CalendarEventRow]:
    return [
        CalendarEventRow(
            id=r.id,
            feed_id=r.feed_id,
            summary=r.summary,
            start_at=r.start_at,
            end_at=r.end_at,
            timezone=r.timezone,
            all_day=r.all_day,
            location=r.location,
            status=r.status,
        )
        for r in rows
    ]


def _suggestions_to_response(
    rows: List[repository.SuggestionRow],
) -> List[StudySuggestionRow]:
    return [
        StudySuggestionRow(
            id=s.id,
            kind=s.kind,
            status=s.status,
            start_at=s.start_at,
            end_at=s.end_at,
            due_at=s.due_at,
            reason_code=s.reason_code,
            reason_text=s.reason_text,
            score=s.score,
        )
        for s in rows
    ]


@router.get("/api/plan", response_model=PlanResponse)
def get_plan() -> PlanResponse:
    """Read the user's plan: events in the window, active suggestions,
    feeds. Kick stale-feed refreshes in the background.
    """
    now = datetime.now(timezone.utc)
    window_start = (now - timedelta(days=PLAN_WINDOW_PAST_DAYS)).isoformat().replace("+00:00", "Z")
    window_end = (now + timedelta(days=PLAN_WINDOW_FUTURE_DAYS)).isoformat().replace("+00:00", "Z")

    with db.get_db() as conn:
        events = repository.list_events_in_window(conn, start=window_start, end=window_end)
        # Refresh the suggestion set after expiring past-due ones.
        # Cheap (a single rule today) and keeps the read path
        # idempotent.
        coach.refresh_active_suggestions(conn)
        suggestions = repository.list_active_suggestions(conn)
        feeds = repository.list_feeds(conn)
        stale_feeds = repository.list_stale_feeds(conn, threshold_minutes=STALE_THRESHOLD_MINUTES)

    # Fire-and-forget. Does not delay the response.
    for stale in stale_feeds:
        _kick_background_sync(stale.id)

    return PlanResponse(
        events=_events_to_response(events),
        suggestions=_suggestions_to_response(suggestions),
        feeds=[_row_to_response(f) for f in feeds],
        is_freshening=len(stale_feeds) > 0,
    )


@router.post("/api/plan/suggestions/{suggestion_id}/accept")
def accept_suggestion(suggestion_id: str) -> Dict[str, str]:
    with db.get_db() as conn:
        result = repository.update_suggestion_status(conn, suggestion_id, status="accepted")
    if result is None:
        raise HTTPException(status_code=404, detail="Suggestion not found.")
    return {"status": "accepted"}


@router.post("/api/plan/suggestions/{suggestion_id}/dismiss")
def dismiss_suggestion(suggestion_id: str) -> Dict[str, str]:
    """Dismiss a suggestion. Frontend implements 5-second-undo via
    POST /api/plan/suggestions/{id}/restore (below) — we just record
    the final state here.
    """
    with db.get_db() as conn:
        result = repository.update_suggestion_status(conn, suggestion_id, status="dismissed")
    if result is None:
        raise HTTPException(status_code=404, detail="Suggestion not found.")
    return {"status": "dismissed"}


@router.post("/api/plan/suggestions/{suggestion_id}/restore")
def restore_suggestion(suggestion_id: str) -> Dict[str, str]:
    """Reverse a dismiss (the 5-second undo affordance).

    No timing window enforced server-side — the timing is a frontend
    UX concern. Backend just allows the transition.
    """
    with db.get_db() as conn:
        result = repository.update_suggestion_status(conn, suggestion_id, status="pending")
    if result is None:
        raise HTTPException(status_code=404, detail="Suggestion not found.")
    return {"status": "pending"}


@router.get("/api/plan/events/stream")
async def stream_plan_events(
    after_id: Optional[str] = None,
    last_event_id: Optional[str] = Header(default=None),
):
    """Server-Sent Events stream — emits when the plan should refresh.

    The companion alarm + dashboard insertions hook subscribe via
    fetch-SSE. Each `calendar-changed` event is the signal to refetch
    downstream views.

    Trigger: `study_events.event_type = 'local_calendar_synced'` rows
    landing — emitted when a Calendar.app change reaches the backend.
    1 s polling cadence against an indexed table.
    """
    import asyncio
    import json

    from fastapi.responses import StreamingResponse

    async def event_stream():
        cursor = last_event_id or after_id or ""
        yield "event: hello\ndata: {}\n\n"
        while True:
            with db.get_db() as conn:
                rows = conn.execute(
                    """
                    SELECT id, event_type, payload, created_at
                    FROM study_events
                    WHERE event_type = 'local_calendar_synced'
                      AND id > ?
                    ORDER BY id ASC
                    LIMIT 50
                    """,
                    (cursor,),
                ).fetchall()
            for row in rows:
                cursor = row["id"]
                yield (
                    f"id: {row['id']}\n"
                    "event: calendar-changed\n"
                    f"data: {json.dumps({'created_at': row['created_at']})}\n\n"
                )
            await asyncio.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def register_plan_routes(app) -> None:
    app.include_router(router)
