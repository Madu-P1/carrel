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

from fastapi import APIRouter, HTTPException

import db
from api_models import (
    CalendarEventRow,
    PlanResponse,
    StudySessionInsertionRow,
    StudySessionInsertionsResponse,
    StudySuggestionRow,
)
from routes.calendar import _row_to_response
from services.calendar import repository
from services.calendar.sync_queue import get_calendar_sync_queue
from services.planning import coach
from services.planning import deadlines as deadline_engine
from services.planning import insertion as insertion_engine


router = APIRouter()


# How stale a feed has to be before we kick a background refresh on
# /api/plan. Mirrors the SWR contract from the spec.
STALE_THRESHOLD_MINUTES = 5

# Plan window: how much past + future to render. Keep this in sync with
# the WeekTimeGrid's default (7 days starting today).

# Plan window: how much past + future to ship to the client. Wider than
# the rendered week (7 days) so the user can navigate ±N weeks without
# refetching. The grid filters client-side; SQLite handles the larger
# scan trivially and the JSON payload stays under a few KB even for a
# heavily-booked calendar.
PLAN_WINDOW_PAST_DAYS = 14
PLAN_WINDOW_FUTURE_DAYS = 56


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
        events = repository.list_events_in_window(
            conn, start=window_start, end=window_end
        )
        # Refresh the suggestion set after expiring past-due ones.
        # Cheap (a single rule today) and keeps the read path
        # idempotent.
        coach.refresh_active_suggestions(conn)
        suggestions = repository.list_active_suggestions(conn)
        feeds = repository.list_feeds(conn)
        stale_feeds = repository.list_stale_feeds(
            conn, threshold_minutes=STALE_THRESHOLD_MINUTES
        )

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
        result = repository.update_suggestion_status(
            conn, suggestion_id, status="accepted"
        )
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
        result = repository.update_suggestion_status(
            conn, suggestion_id, status="dismissed"
        )
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
        result = repository.update_suggestion_status(
            conn, suggestion_id, status="pending"
        )
    if result is None:
        raise HTTPException(status_code=404, detail="Suggestion not found.")
    return {"status": "pending"}


@router.get("/api/plan/events/stream")
async def stream_plan_events(after_id: Optional[str] = None):
    """Server-Sent Events stream — emits when the plan should refresh.

    The dashboard's `useStudyInsertions` hook subscribes via
    `EventSource(...)`. Each `calendar-changed` event is the signal to
    refetch `/api/plan/insertions` and re-render the advice panel.

    Trigger: `study_events.event_type = 'local_calendar_synced'` rows
    landing — emitted when a Calendar.app change reaches the backend.
    1 s polling cadence against an indexed table.
    """
    import asyncio
    import json

    from fastapi.responses import StreamingResponse

    async def event_stream():
        cursor = after_id or ""
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


@router.get("/api/plan/insertions", response_model=StudySessionInsertionsResponse)
def get_study_session_insertions(tz: str = "UTC") -> StudySessionInsertionsResponse:
    """Read-only advice: where should the user insert a study session?

    Ranks free blocks across the next 14 days against detected
    deadlines (calendar-event keyword match + overdue SRS aggregate)
    and time-of-day fit. Top 3 returned.
    """
    with db.get_db() as conn:
        insertions = insertion_engine.best_study_session_insertions(
            conn, user_timezone=tz
        )
    return StudySessionInsertionsResponse(
        insertions=[
            StudySessionInsertionRow(
                start_at=ins.start_at,
                end_at=ins.end_at,
                duration_minutes=ins.duration_minutes,
                score=ins.score,
                reason_text=ins.reason_text,
                reason_code=ins.reason_code,
                deadline_label=ins.deadline_label,
                deadline_at=ins.deadline_at,
                source_event_id=ins.source_event_id,
            )
            for ins in insertions
        ],
        user_timezone=tz,
    )


@router.get("/api/plan/deadlines")
def get_upcoming_deadlines() -> Dict[str, list]:
    """Read-only list of detected deadlines within the next 30 days.

    Combines calendar-event keyword matches (midterm, exam, final, test,
    quiz, deadline) with the overdue-SRS aggregate. The frontend renders
    this as a horizontal rail above the WeekTimeGrid so students see what
    they are working toward without scrolling.

    Each deadline has a severity (high/normal/low) tied to days_until,
    so the UI can color-code urgency without re-deriving it.
    """
    with db.get_db() as conn:
        items = deadline_engine.detect_upcoming_deadlines(conn)
    return {
        "deadlines": [
            {
                "label": d.label,
                "deadline_at": d.deadline_at,
                "days_until": d.days_until,
                "severity": d.severity,
                "source": d.source,
                "event_id": d.event_id,
            }
            for d in items
        ],
    }


def register_plan_routes(app) -> None:
    app.include_router(router)
