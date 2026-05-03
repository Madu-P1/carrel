"""Calendar feed CRUD + manual sync endpoints.

Three endpoints:
  POST   /api/calendar/feeds             add a feed (validates + initial sync)
  GET    /api/calendar/feeds             list feeds (URLs masked)
  DELETE /api/calendar/feeds/{id}        remove a feed (cascades events)
  PATCH  /api/calendar/feeds/{id}        rename (label only for v1)
  POST   /api/calendar/feeds/{id}/sync   manual "Sync now"

URL redaction discipline: the GET responses ALWAYS contain the masked
URL form. Raw feed URLs are stored only in the local secret store and are
never returned by GET responses.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

import db
from api_models import (
    CalendarFeedCreatedResponse,
    CalendarFeedCreateRequest,
    CalendarFeedRow,
    SyncFeedResponse,
)
from app_logging import get_logger
from services.calendar import repository, sync_service
from services.calendar.validators import (
    FeedURLRejected,
    mask_url,
    validate_feed_url,
)


LOGGER = get_logger("calendar_api")
router = APIRouter()


class FeedRenameRequest(BaseModel):
    label: str


def _row_to_response(feed: repository.FeedRow, *, mask: bool = True) -> CalendarFeedRow:
    """Convert a repository FeedRow to API response shape, masking the URL."""
    return CalendarFeedRow(
        id=feed.id,
        label=feed.label,
        url=mask_url(feed.url) if mask else feed.url,
        color=feed.color,
        is_enabled=feed.is_enabled,
        last_synced_at=feed.last_synced_at,
        last_successful_sync_at=feed.last_successful_sync_at,
        consecutive_failures=feed.consecutive_failures,
        last_error=feed.last_error,
    )


@router.post("/api/calendar/feeds", response_model=CalendarFeedCreatedResponse)
def create_feed(payload: CalendarFeedCreateRequest) -> CalendarFeedCreatedResponse:
    """Add a new feed.

    Steps:
      1. Validate URL (scheme + private-IP + DNS resolution)
      2. Insert (handles duplicate-URL case via unique index)
      3. Run initial sync inline so the user sees their data on first
         render — this is the one path where sync is intentionally
         coupled to a write request, because the user is watching.

    The initial sync may fail (4xx, network, parse error) — we still
    keep the feed so the user can retry; we surface the error in the
    response feed row's `last_error` field.
    """
    label = (payload.label or "").strip()
    url = (payload.url or "").strip()
    color = (payload.color or "").strip() or None

    if not label:
        raise HTTPException(status_code=400, detail="Label is required.")
    if not url:
        raise HTTPException(status_code=400, detail="URL is required.")

    pre_check = validate_feed_url(url)
    if not pre_check.ok:
        raise HTTPException(
            status_code=400,
            detail={
                "reason": pre_check.reason,
                "message": pre_check.detail,
            },
        )

    with db.get_db() as conn:
        try:
            feed = repository.insert_feed(
                conn,
                label=label,
                url=url,
                color=color,
            )
        except Exception as exc:
            # Most likely cause: UNIQUE (user_id, url_hash) collision —
            # the user added this URL once already. Surface that
            # specifically rather than a generic 500.
            if "UNIQUE" in str(exc).upper():
                raise HTTPException(
                    status_code=409,
                    detail={
                        "reason": "feed_already_exists",
                        "message": "This calendar URL is already added.",
                    },
                ) from exc
            raise

        # Initial sync, inline. The user is watching the dialog; they
        # want to see "12 events imported" not a silent success.
        outcome = sync_service.run_one_feed(conn, feed.id)
        # Re-fetch to get the post-sync bookkeeping fields (last_synced_at, etc.)
        feed = repository.get_feed(conn, feed.id)

    if outcome.status == "error":
        # Feed kept; user can retry. Surface error via the feed row.
        LOGGER.warning(
            "calendar feed added but initial sync failed: %s",
            outcome.error,
        )

    return CalendarFeedCreatedResponse(
        feed=_row_to_response(feed),
        raw_url_echo=mask_url(url),
    )


@router.get("/api/calendar/feeds", response_model=List[CalendarFeedRow])
def list_feeds() -> List[CalendarFeedRow]:
    with db.get_db() as conn:
        feeds = repository.list_feeds(conn)
    return [_row_to_response(f) for f in feeds]


@router.delete("/api/calendar/feeds/{feed_id}")
def delete_feed(feed_id: str) -> Dict[str, bool]:
    with db.get_db() as conn:
        ok = repository.delete_feed(conn, feed_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Feed not found.")
    return {"deleted": True}


@router.patch("/api/calendar/feeds/{feed_id}", response_model=CalendarFeedRow)
def rename_feed(feed_id: str, payload: FeedRenameRequest) -> CalendarFeedRow:
    label = (payload.label or "").strip()
    if not label:
        raise HTTPException(status_code=400, detail="Label is required.")
    with db.get_db() as conn:
        feed = repository.update_feed_label(conn, feed_id, label)
    if feed is None:
        raise HTTPException(status_code=404, detail="Feed not found.")
    return _row_to_response(feed)


@router.post("/api/calendar/feeds/{feed_id}/sync", response_model=SyncFeedResponse)
def sync_feed(feed_id: str) -> SyncFeedResponse:
    """Manual 'Sync now' button. Runs the same sync service as everything
    else, blocking on the response so the user gets immediate feedback.
    """
    with db.get_db() as conn:
        feed = repository.get_feed(conn, feed_id)
        if feed is None:
            raise HTTPException(status_code=404, detail="Feed not found.")
        outcome = sync_service.run_one_feed(conn, feed_id)
        feed_after = repository.get_feed(conn, feed_id)

    return SyncFeedResponse(
        feed=_row_to_response(feed_after),
        items_seen=outcome.items_seen,
        items_upserted=outcome.items_upserted,
        items_deleted=outcome.items_deleted,
        status=outcome.status,
        error=outcome.error,
    )


def register_calendar_routes(app) -> None:
    app.include_router(router)
