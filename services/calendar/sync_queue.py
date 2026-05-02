from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

import db
from app_logging import get_logger, log_event
from services.calendar import sync_service


LOGGER = get_logger("calendar.sync_queue")


class CalendarSyncQueue:
    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cal-bg-sync")
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def submit(self, feed_id: str) -> None:
        if self._closed:
            raise RuntimeError("CalendarSyncQueue is closed")
        self._executor.submit(self._run_one, feed_id)

    def _run_one(self, feed_id: str) -> None:
        try:
            with db.get_db() as conn:
                sync_service.run_one_feed(conn, feed_id)
        except Exception as exc:
            log_event(
                LOGGER,
                logging.WARNING,
                "calendar_sync_failed",
                feed_id=feed_id,
                error_type=exc.__class__.__name__,
            )

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._executor.shutdown(wait=False, cancel_futures=True)


_QUEUE: CalendarSyncQueue | None = None


def get_calendar_sync_queue() -> CalendarSyncQueue:
    global _QUEUE
    if _QUEUE is None or _QUEUE.closed:
        _QUEUE = CalendarSyncQueue()
    return _QUEUE


def shutdown_calendar_sync_queue() -> None:
    global _QUEUE
    if _QUEUE is None:
        return
    _QUEUE.shutdown()
    _QUEUE = None
