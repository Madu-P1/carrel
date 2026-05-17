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

import hashlib
from typing import Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

import db
from api_models import (
    CalendarFeedCreatedResponse,
    CalendarFeedCreateRequest,
    CalendarIcsUploadResponse,
    CalendarFeedRow,
    LocalCalendarSyncRequest,
    LocalCalendarSyncResponse,
    SyncFeedResponse,
)
from app_logging import get_logger
from services.calendar import local_sync, repository, sync_service
from services.calendar.ical_parser import ICalParseError, parse_ics
from services.calendar.validators import (
    MAX_RESPONSE_BYTES,
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
        # Re-fetch to get the post-sync bookkeeping fields (last_synced_at, etc.).
        # Fall back to the just-inserted row if a concurrent delete races us —
        # the caller already saw a successful insert, so swallowing the
        # bookkeeping refresh is friendlier than a misleading 404.
        refreshed = repository.get_feed(conn, feed.id)
        if refreshed is None:
            LOGGER.warning(
                "calendar feed %s missing on post-insert re-fetch; falling back to inserted row",
                feed.id,
            )
        else:
            feed = refreshed

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


@router.post("/api/calendar/ics-upload", response_model=CalendarIcsUploadResponse)
async def upload_ics_file(
    label: str = Form(...),
    color: Optional[str] = Form(default=None),
    file: UploadFile = File(...),
) -> CalendarIcsUploadResponse:
    """Import an Apple Calendar `.ics` export as a local calendar source.

    We parse the file and upsert events immediately, but we do not keep
    the uploaded bytes, local path, or filename. The feed row stores a
    stable content hash for duplicate detection plus a non-secret display
    label.
    """
    clean_label = (label or "").strip()
    clean_color = (color or "").strip() or None
    filename = (file.filename or "").lower()
    if not clean_label:
        raise HTTPException(status_code=400, detail="Label is required.")
    if not filename.endswith(".ics"):
        raise HTTPException(
            status_code=400,
            detail="Choose an .ics file exported from Apple Calendar.",
        )

    body = await file.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise HTTPException(status_code=413, detail="Calendar file is too large.")
    if b"BEGIN:VCALENDAR" not in body[:4096].upper():
        raise HTTPException(
            status_code=400,
            detail="This does not look like an iCalendar (.ics) file.",
        )

    try:
        parsed = parse_ics(body)
    except ICalParseError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"{exc.reason}: {exc.detail}",
        ) from exc

    content_hash = hashlib.sha256(body).hexdigest()
    with db.get_db() as conn:
        try:
            feed = repository.insert_uploaded_ics_feed(
                conn,
                label=clean_label,
                content_hash=content_hash,
                color=clean_color,
            )
        except Exception as exc:
            if "UNIQUE" in str(exc).upper():
                raise HTTPException(
                    status_code=409,
                    detail="This .ics file has already been imported.",
                ) from exc
            raise

        run_id = repository.begin_sync_run(conn, feed.id)
        items_upserted, items_deleted = repository.upsert_events(conn, feed.id, parsed)
        repository.complete_sync_run(
            conn,
            run_id,
            status="success",
            items_seen=len(parsed),
            items_upserted=items_upserted,
            items_deleted=items_deleted,
        )
        repository.update_feed_after_sync(
            conn,
            feed.id,
            succeeded=True,
            etag=None,
            last_modified=None,
            error_message=None,
        )
        refreshed = repository.get_feed(conn, feed.id)
        if refreshed is None:
            LOGGER.warning(
                "calendar feed %s missing on post-ICS-upload re-fetch; falling back to inserted row",
                feed.id,
            )
        else:
            feed = refreshed

    return CalendarIcsUploadResponse(
        feed=_row_to_response(feed),
        raw_url_echo="Uploaded .ics file",
        items_seen=len(parsed),
        items_upserted=items_upserted,
        items_deleted=items_deleted,
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
        # Concurrent delete after the pre-sync guard would null this out;
        # the sync did run, so fall back to the pre-sync row rather than
        # surfacing a confusing 404 on a successful sync response.
        feed_after = repository.get_feed(conn, feed_id)
        if feed_after is None:
            LOGGER.warning(
                "calendar feed %s missing on post-sync re-fetch; falling back to pre-sync row",
                feed_id,
            )
            feed_after = feed

    return SyncFeedResponse(
        feed=_row_to_response(feed_after),
        items_seen=outcome.items_seen,
        items_upserted=outcome.items_upserted,
        items_deleted=outcome.items_deleted,
        status=outcome.status,
        error=outcome.error,
    )


@router.post("/api/calendar/local/sync", response_model=LocalCalendarSyncResponse)
def sync_local_calendar(payload: LocalCalendarSyncRequest) -> LocalCalendarSyncResponse:
    """Receive an Apple Calendar (EventKit) sync from the macOS shell.

    The macOS bridge calls this on launch and again on every
    EKEventStoreChanged notification. The body carries one EKCalendar's
    events; this handler upserts them through the same code path that
    HTTP feeds use, so downstream consumers (planner, coach, dashboard)
    don't care which kind of feed produced an event.
    """
    with db.get_db() as conn:
        feed, items_seen, items_upserted, items_deleted = local_sync.sync_local_calendar(
            conn, payload
        )
    LOGGER.info(
        "local_calendar_synced",
        extra={
            "context": {
                "feed_id": feed.id,
                "calendar_identifier": payload.calendar_identifier,
                "items_seen": items_seen,
                "items_upserted": items_upserted,
                "items_deleted": items_deleted,
            }
        },
    )
    return LocalCalendarSyncResponse(
        feed_id=feed.id,
        items_seen=items_seen,
        items_upserted=items_upserted,
        items_deleted=items_deleted,
    )


def register_calendar_routes(app) -> None:
    app.include_router(router)
