from __future__ import annotations

import io
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

import main
from services.calendar import repository, sync_service
from services.calendar.secrets import set_default_secret_store_for_testing
from services.local_api_security import HEADER_NAME, get_local_api_token


class FakeCalendarSecretStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.deleted: list[str] = []

    def store_url(self, feed_id: str, raw_url: str) -> str:
        ref = f"fake:{feed_id}"
        self.values[ref] = raw_url
        return ref

    def get_url(self, reference: str) -> str | None:
        return self.values.get(reference)

    def delete_url(self, reference: str) -> None:
        self.deleted.append(reference)
        self.values.pop(reference, None)


class CalendarSecretTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = FakeCalendarSecretStore()
        set_default_secret_store_for_testing(self.store)
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

    def test_create_list_and_delete_never_store_or_return_raw_url(self) -> None:
        raw_url = "https://example.com/private/basic.ics?token=abc"
        with mock.patch(
            "routes.calendar.sync_service.run_one_feed",
            return_value=sync_service.SyncOutcome(
                feed_id="feed",
                status="success",
                http_status=200,
                items_seen=0,
                items_upserted=0,
                items_deleted=0,
                error=None,
                final_url="https://calendar.example.com/***",
            ),
        ):
            created = self.client.post(
                "/api/calendar/feeds",
                json={"label": "Private", "url": raw_url, "color": "#4f8cff"},
            )

        self.assertEqual(200, created.status_code, created.text)
        created_body = created.json()
        feed_id = created_body["feed"]["id"]
        self.assertEqual("https://example.com/***", created_body["raw_url_echo"])
        self.assertNotIn(raw_url, created.text)

        with main.get_db() as conn:
            row = conn.execute(
                "SELECT url, keychain_ref, url_hash FROM calendar_feeds WHERE id = ?",
                (feed_id,),
            ).fetchone()
        self.assertEqual("https://example.com/***", row["url"])
        self.assertIn(row["keychain_ref"], self.store.values)
        self.assertEqual(raw_url, self.store.values[row["keychain_ref"]])
        self.assertNotEqual(raw_url, row["url_hash"])

        listed = self.client.get("/api/calendar/feeds")
        self.assertEqual(200, listed.status_code)
        self.assertNotIn(raw_url, listed.text)
        self.assertEqual("https://example.com/***", listed.json()[0]["url"])

        deleted = self.client.delete(f"/api/calendar/feeds/{feed_id}")
        self.assertEqual(200, deleted.status_code)
        self.assertIn(row["keychain_ref"], self.store.deleted)

    def test_plaintext_rows_migrate_to_secret_store(self) -> None:
        raw_url = "https://calendar.example.com/private/basic.ics?token=abc"
        with main.get_db() as conn:
            conn.execute(
                """
                INSERT INTO calendar_feeds (
                    id, user_id, label, url, url_hash, color,
                    is_enabled, consecutive_failures, created_at, updated_at
                ) VALUES ('legacy-feed', 'local', 'Legacy', ?, ?, NULL, 1, 0, 'now', 'now')
                """,
                (raw_url, repository.url_hash(raw_url)),
            )
            conn.commit()
            migrated = repository.migrate_plaintext_feed_urls(conn, secret_store=self.store)
            row = conn.execute(
                "SELECT url, keychain_ref FROM calendar_feeds WHERE id = 'legacy-feed'"
            ).fetchone()

        self.assertEqual(1, migrated)
        self.assertEqual("https://calendar.example.com/***", row["url"])
        self.assertEqual(raw_url, self.store.values[row["keychain_ref"]])

    def test_missing_secret_produces_recoverable_sync_error(self) -> None:
        raw_url = "https://calendar.example.com/private/basic.ics?token=abc"
        with main.get_db() as conn:
            feed = repository.insert_feed(conn, label="Private", url=raw_url, color=None)
            self.store.values.clear()
            outcome = sync_service.run_one_feed(conn, feed.id)

        self.assertEqual("error", outcome.status)
        self.assertIn("missing_secret", outcome.error or "")

    def test_upload_apple_ics_imports_events_without_storing_filename(self) -> None:
        # Date the event a few days out so it always lands inside the parser's
        # forward expansion window (now .. now+90d, see ical_parser.py). A hard
        # coded past date made this a time-bomb: it passed until "now" moved past
        # it, then imported 0 events.
        start = datetime.now(timezone.utc) + timedelta(days=2)
        dtstart = start.strftime("%Y%m%dT%H%M%SZ")
        dtend = (start + timedelta(hours=1)).strftime("%Y%m%dT%H%M%SZ")
        body = (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//apple-calendar-export//\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:apple-1@example\r\n"
            f"DTSTART:{dtstart}\r\n"
            f"DTEND:{dtend}\r\n"
            "SUMMARY:Corporate Finance\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        ).encode("utf-8")

        response = self.client.post(
            "/api/calendar/ics-upload",
            data={"label": "Apple Calendar", "color": "#4f8cff"},
            files={"file": ("private-apple-export.ics", io.BytesIO(body), "text/calendar")},
        )

        self.assertEqual(200, response.status_code, response.text)
        payload = response.json()
        self.assertEqual(1, payload["items_seen"])
        self.assertEqual("Uploaded .ics file", payload["feed"]["url"])
        self.assertNotIn("private-apple-export", response.text)

        with main.get_db() as conn:
            feed_row = conn.execute(
                "SELECT url, keychain_ref, url_hash FROM calendar_feeds WHERE id = ?",
                (payload["feed"]["id"],),
            ).fetchone()
            event_count = conn.execute(
                "SELECT COUNT(*) AS count FROM calendar_events WHERE feed_id = ?",
                (payload["feed"]["id"],),
            ).fetchone()["count"]

        self.assertEqual("Uploaded .ics file", feed_row["url"])
        self.assertIsNone(feed_row["keychain_ref"])
        self.assertTrue(feed_row["url_hash"].startswith("uploaded-ics:"))
        self.assertEqual(1, event_count)

    def test_upload_rejects_non_ics_suffix(self) -> None:
        response = self.client.post(
            "/api/calendar/ics-upload",
            data={"label": "Apple Calendar"},
            files={
                "file": (
                    "calendar.txt",
                    io.BytesIO(b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"),
                    "text/plain",
                )
            },
        )

        self.assertEqual(400, response.status_code)
        self.assertIn(".ics", response.text)


if __name__ == "__main__":
    unittest.main()
