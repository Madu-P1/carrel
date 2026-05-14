"""Regression test for HANDOFF bug 2: post-insert/post-sync re-fetch
returning ``None`` must not crash the route. The route should fall back to
the in-scope FeedRow and still return a coherent 200 response.

This pins the runtime contract that mypy proves only statically. If a
future refactor reintroduces the ``feed = repository.get_feed(...)`` drop,
this test fails loudly with the original AttributeError.
"""

from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

import main
from services.calendar import sync_service
from services.calendar.secrets import set_default_secret_store_for_testing
from services.calendar.validators import ValidationResult
from services.local_api_security import HEADER_NAME, get_local_api_token

_LOGGER_NAME = "einstein.calendar_api"


class _NoopSecretStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def store_url(self, feed_id: str, raw_url: str) -> str:
        ref = f"fake:{feed_id}"
        self.values[ref] = raw_url
        return ref

    def get_url(self, reference: str) -> str | None:
        return self.values.get(reference)

    def delete_url(self, reference: str) -> None:
        self.values.pop(reference, None)


def _ok_validator(_url: str) -> ValidationResult:
    return ValidationResult(ok=True, reason="", detail="")


def _ok_sync_outcome(feed_id: str = "feed") -> sync_service.SyncOutcome:
    return sync_service.SyncOutcome(
        feed_id=feed_id,
        status="success",
        http_status=200,
        items_seen=0,
        items_upserted=0,
        items_deleted=0,
        error=None,
        final_url="https://calendar.example.com/***",
    )


class CalendarFeedRowFallbackTests(unittest.TestCase):
    """Three sites in routes/calendar.py re-fetch a just-inserted or
    just-synced feed. A concurrent delete from another connection can null
    the re-fetch; the route must still respond coherently.
    """

    def setUp(self) -> None:
        set_default_secret_store_for_testing(_NoopSecretStore())
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.original_base_dir = main.BASE_DIR
        self.original_data_dir = main.DATA_DIR
        self.original_upload_dir = main.UPLOAD_DIR
        self.original_db_path = main.DB_PATH
        self.original_schema_path = main.SCHEMA_PATH

        main.BASE_DIR = self.base_dir
        main.DATA_DIR = self.base_dir / "data"
        main.UPLOAD_DIR = main.DATA_DIR / "uploads"
        main.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        main.DB_PATH = main.DATA_DIR / "test.db"
        main.SCHEMA_PATH = self.original_schema_path
        main.initialize_database()
        self.client = TestClient(main.app, headers={HEADER_NAME: get_local_api_token()})

    def tearDown(self) -> None:
        set_default_secret_store_for_testing(None)
        main.BASE_DIR = self.original_base_dir
        main.DATA_DIR = self.original_data_dir
        main.UPLOAD_DIR = self.original_upload_dir
        main.DB_PATH = self.original_db_path
        main.SCHEMA_PATH = self.original_schema_path
        self.temp_dir.cleanup()

    def test_create_feed_falls_back_when_refetch_returns_none(self) -> None:
        with (
            mock.patch("routes.calendar.validate_feed_url", side_effect=_ok_validator),
            mock.patch(
                "routes.calendar.sync_service.run_one_feed", return_value=_ok_sync_outcome()
            ),
            mock.patch("routes.calendar.repository.get_feed", return_value=None),
            self.assertLogs(_LOGGER_NAME, level="WARNING") as captured,
        ):
            response = self.client.post(
                "/api/calendar/feeds",
                json={
                    "label": "Private",
                    "url": "https://calendar.example.com/private/basic.ics",
                    "color": "#4f8cff",
                },
            )

        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        # Pre-fix this branch would AttributeError inside _row_to_response.
        self.assertEqual("Private", body["feed"]["label"])
        self.assertTrue(any("post-insert re-fetch" in m for m in captured.output))

    def test_sync_feed_falls_back_when_post_sync_refetch_returns_none(self) -> None:
        with (
            mock.patch("routes.calendar.validate_feed_url", side_effect=_ok_validator),
            mock.patch(
                "routes.calendar.sync_service.run_one_feed", return_value=_ok_sync_outcome()
            ),
        ):
            created = self.client.post(
                "/api/calendar/feeds",
                json={
                    "label": "Test",
                    "url": "https://calendar.example.com/test.ics",
                    "color": "#4f8cff",
                },
            )
        self.assertEqual(200, created.status_code, created.text)
        feed_id = created.json()["feed"]["id"]

        # The pre-sync get_feed call must return the real row (so the route
        # passes the 404 guard); the post-sync call must return None to
        # exercise the fallback branch.
        import routes.calendar as calendar_route

        real_get_feed = calendar_route.repository.get_feed
        call_count = {"n": 0}

        def fake_get_feed(conn, fid):  # type: ignore[no-untyped-def]
            call_count["n"] += 1
            if call_count["n"] == 1:
                return real_get_feed(conn, fid)
            return None

        with (
            mock.patch(
                "routes.calendar.sync_service.run_one_feed",
                return_value=_ok_sync_outcome(feed_id),
            ),
            mock.patch("routes.calendar.repository.get_feed", side_effect=fake_get_feed),
            self.assertLogs(_LOGGER_NAME, level="WARNING") as captured,
        ):
            response = self.client.post(f"/api/calendar/feeds/{feed_id}/sync")

        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        self.assertEqual(feed_id, body["feed"]["id"])
        self.assertEqual("success", body["status"])
        self.assertTrue(any("post-sync re-fetch" in m for m in captured.output))

    def test_upload_ics_falls_back_when_refetch_returns_none(self) -> None:
        body = (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//apple-calendar-export//\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:evt-1@example\r\n"
            "DTSTART:20260504T140000Z\r\n"
            "DTEND:20260504T150000Z\r\n"
            "SUMMARY:Corporate Finance\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        ).encode("utf-8")

        with (
            mock.patch("routes.calendar.repository.get_feed", return_value=None),
            self.assertLogs(_LOGGER_NAME, level="WARNING") as captured,
        ):
            response = self.client.post(
                "/api/calendar/ics-upload",
                data={"label": "Apple Calendar", "color": "#4f8cff"},
                files={"file": ("export.ics", io.BytesIO(body), "text/calendar")},
            )

        self.assertEqual(200, response.status_code, response.text)
        body_json = response.json()
        self.assertEqual("Apple Calendar", body_json["feed"]["label"])
        self.assertEqual(1, body_json["items_seen"])
        self.assertTrue(any("post-ICS-upload re-fetch" in m for m in captured.output))


if __name__ == "__main__":
    unittest.main()
