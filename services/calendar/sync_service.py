"""Orchestration: fetch + parse + upsert + sync_runs bookkeeping.

The single public entry point is `run_one_feed(conn, feed_id)`. Wraps:
  1. Look up the feed
  2. Open a sync_runs row (status=running)
  3. Call feed_client.fetch_feed
  4. Branch on 304/2xx/non-2xx
  5. Parse the body via ical_parser
  6. Upsert events via repository
  7. Update feed bookkeeping + close sync_runs row

Every error path masks URLs before logging or persisting. The caller
(routes, lifespan tick) does NOT need to remember this discipline.

Idempotent — running it twice in a row with no remote change yields
one 200 then one 304, and zero event row writes the second time.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from typing import Optional

from app_logging import get_logger
from services.calendar import repository
from services.calendar.feed_client import (
    FeedFetchError,
    FetchResult,
    fetch_feed,
)
from services.calendar.ical_parser import ICalParseError, parse_ics
from services.calendar.validators import mask_url


LOGGER = get_logger("calendar.sync")


@dataclass
class SyncOutcome:
    """What `run_one_feed` returns to the caller.

    Captures enough for routes to render a status response (e.g. the
    "Sync now" button's toast: "Synced 14 events from Blackboard").
    """
    feed_id: str
    status: str               # 'success' | 'not_modified' | 'error'
    http_status: Optional[int]
    items_seen: int
    items_upserted: int
    items_deleted: int
    error: Optional[str]      # already mask_url'd
    final_url: str            # already masked


def run_one_feed(conn: sqlite3.Connection, feed_id: str) -> SyncOutcome:
    """Sync a single feed. Idempotent. Records a sync_runs entry either way.

    Errors are recorded, not re-raised — the caller (route handler or
    background tick) wants to know what happened, but a single feed
    failing should never crash the orchestrator.
    """
    feed = repository.get_feed(conn, feed_id)
    if feed is None:
        # Defensive: caller passed a feed_id that doesn't exist. Don't
        # write a sync_runs row for a phantom feed; just return error.
        return SyncOutcome(
            feed_id=feed_id,
            status="error",
            http_status=None,
            items_seen=0,
            items_upserted=0,
            items_deleted=0,
            error="feed_not_found",
            final_url="",
        )

    run_id = repository.begin_sync_run(conn, feed_id)
    masked = mask_url(feed.url)
    LOGGER.info("calendar sync start: %s (%s)", masked, feed.label)

    try:
        result: FetchResult = fetch_feed(
            feed.url,
            etag=feed.etag,
            last_modified=feed.last_modified,
        )
    except FeedFetchError as exc:
        # URL/network/redirect/content-type/size errors. Already
        # human-readable + URL-safe by construction of FeedFetchError.
        repository.complete_sync_run(
            conn,
            run_id,
            status="error",
            error=f"{exc.reason}: {exc.detail}",
        )
        repository.update_feed_after_sync(
            conn,
            feed_id,
            succeeded=False,
            etag=feed.etag,
            last_modified=feed.last_modified,
            error_message=f"{exc.reason}: {exc.detail}",
        )
        LOGGER.warning("calendar sync error (%s): %s", exc.reason, masked)
        return SyncOutcome(
            feed_id=feed_id,
            status="error",
            http_status=None,
            items_seen=0,
            items_upserted=0,
            items_deleted=0,
            error=f"{exc.reason}: {exc.detail}",
            final_url=masked,
        )

    # 304 Not Modified — server confirms we have the latest. Bookkeep
    # and exit; no parse, no event writes.
    if result.status == 304:
        repository.complete_sync_run(
            conn,
            run_id,
            status="not_modified",
            http_status=304,
        )
        repository.update_feed_after_sync(
            conn,
            feed_id,
            succeeded=True,
            etag=feed.etag or result.etag,
            last_modified=feed.last_modified or result.last_modified,
            error_message=None,
        )
        LOGGER.info("calendar sync 304 (no changes): %s", masked)
        return SyncOutcome(
            feed_id=feed_id,
            status="not_modified",
            http_status=304,
            items_seen=0,
            items_upserted=0,
            items_deleted=0,
            error=None,
            final_url=result.final_url,
        )

    # Non-2xx (4xx/5xx) — record HTTP status and back off.
    if result.body is None or not (200 <= result.status < 300):
        msg = f"http_{result.status}: feed returned {result.status}"
        repository.complete_sync_run(
            conn,
            run_id,
            status="error",
            http_status=result.status,
            error=msg,
        )
        repository.update_feed_after_sync(
            conn,
            feed_id,
            succeeded=False,
            etag=feed.etag,
            last_modified=feed.last_modified,
            error_message=msg,
        )
        LOGGER.warning("calendar sync HTTP %d: %s", result.status, masked)
        return SyncOutcome(
            feed_id=feed_id,
            status="error",
            http_status=result.status,
            items_seen=0,
            items_upserted=0,
            items_deleted=0,
            error=msg,
            final_url=result.final_url,
        )

    # 2xx with body — parse and upsert
    try:
        parsed = parse_ics(result.body)
    except ICalParseError as exc:
        repository.complete_sync_run(
            conn,
            run_id,
            status="error",
            http_status=result.status,
            error=f"{exc.reason}: {exc.detail}",
        )
        repository.update_feed_after_sync(
            conn,
            feed_id,
            succeeded=False,
            etag=feed.etag,
            last_modified=feed.last_modified,
            error_message=f"{exc.reason}: {exc.detail}",
        )
        LOGGER.warning("calendar parse error (%s): %s", exc.reason, masked)
        return SyncOutcome(
            feed_id=feed_id,
            status="error",
            http_status=result.status,
            items_seen=0,
            items_upserted=0,
            items_deleted=0,
            error=f"{exc.reason}: {exc.detail}",
            final_url=result.final_url,
        )

    items_seen = len(parsed)
    items_upserted, items_deleted = repository.upsert_events(
        conn, feed_id, parsed
    )

    repository.complete_sync_run(
        conn,
        run_id,
        status="success",
        http_status=result.status,
        items_seen=items_seen,
        items_upserted=items_upserted,
        items_deleted=items_deleted,
    )
    repository.update_feed_after_sync(
        conn,
        feed_id,
        succeeded=True,
        etag=result.etag,
        last_modified=result.last_modified,
        error_message=None,
    )
    LOGGER.info(
        "calendar sync ok: %s (seen=%d upserted=%d deleted=%d)",
        masked,
        items_seen,
        items_upserted,
        items_deleted,
    )

    return SyncOutcome(
        feed_id=feed_id,
        status="success",
        http_status=result.status,
        items_seen=items_seen,
        items_upserted=items_upserted,
        items_deleted=items_deleted,
        error=None,
        final_url=result.final_url,
    )
