"""Tests for /api/calendar/local/sync — Apple Calendar (EventKit) bridge."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import db
import main
from services.calendar.secrets import set_default_secret_store_for_testing
from services.local_api_security import HEADER_NAME, get_local_api_token


class _FakeStore:
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


class LocalCalendarSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        set_default_secret_store_for_testing(_FakeStore())
        self.temp_dir = tempfile.TemporaryDirectory()
        base = Path(self.temp_dir.name)
        # Save originals so tearDown can restore.
        self.originals = {
            "BASE_DIR": main.BASE_DIR,
            "DATA_DIR": main.DATA_DIR,
            "UPLOAD_DIR": main.UPLOAD_DIR,
            "DB_PATH": main.DB_PATH,
        }
        main.BASE_DIR = base
        main.DATA_DIR = base / "data"
        main.UPLOAD_DIR = main.DATA_DIR / "uploads"
        main.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        main.DB_PATH = main.DATA_DIR / "test.db"
        main.initialize_database()
        self.client = TestClient(main.app, headers={HEADER_NAME: get_local_api_token()})

    def tearDown(self) -> None:
        set_default_secret_store_for_testing(None)
        for k, v in self.originals.items():
            setattr(main, k, v)
        self.temp_dir.cleanup()

    def _payload(self, *, calendar_id: str = "cal-1", events: list[dict] | None = None) -> dict:
        return {
            "calendar_identifier": calendar_id,
            "label": "Work",
            "color": "#FF0080",
            "events": events
            or [
                {
                    "uid": "evt-1",
                    "summary": "Standup",
                    "start_at": "2026-05-05T09:00:00Z",
                    "end_at": "2026-05-05T09:15:00Z",
                    "all_day": False,
                    "status": "confirmed",
                    "timezone": "America/New_York",
                }
            ],
        }

    def test_first_sync_creates_local_feed_and_inserts_event(self) -> None:
        response = self.client.post(
            "/api/calendar/local/sync", json=self._payload()
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["items_seen"], 1)
        self.assertEqual(body["items_upserted"], 1)
        self.assertEqual(body["items_deleted"], 0)
        feed_id = body["feed_id"]

        # Feed row carries kind='local' and the synthetic eventkit:// URL.
        with db.get_db() as conn:
            row = conn.execute(
                "SELECT kind, url FROM calendar_feeds WHERE id = ?", (feed_id,)
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["kind"], "local")
        self.assertTrue(row["url"].startswith("eventkit://local/"))

    def test_re_sync_same_calendar_dedupes_to_one_feed(self) -> None:
        first = self.client.post("/api/calendar/local/sync", json=self._payload()).json()
        second = self.client.post("/api/calendar/local/sync", json=self._payload()).json()
        self.assertEqual(first["feed_id"], second["feed_id"])

    def test_event_removal_tombstones_via_diff(self) -> None:
        """Re-syncing without a previously-seen UID should mark it deleted."""
        # First sync: 2 events.
        two = self._payload(events=[
            {
                "uid": "evt-A",
                "summary": "A",
                "start_at": "2026-05-05T09:00:00Z",
                "end_at": "2026-05-05T10:00:00Z",
                "all_day": False,
                "status": "confirmed",
            },
            {
                "uid": "evt-B",
                "summary": "B",
                "start_at": "2026-05-05T11:00:00Z",
                "end_at": "2026-05-05T12:00:00Z",
                "all_day": False,
                "status": "confirmed",
            },
        ])
        first = self.client.post("/api/calendar/local/sync", json=two).json()
        self.assertEqual(first["items_upserted"], 2)

        # Second sync: drop evt-B.
        one = self._payload(events=[two["events"][0]])
        second = self.client.post("/api/calendar/local/sync", json=one).json()
        # evt-A unchanged, evt-B tombstoned.
        self.assertGreaterEqual(second["items_deleted"], 1)

    def test_bad_payload_rejected_at_validator(self) -> None:
        response = self.client.post(
            "/api/calendar/local/sync",
            json={"calendar_identifier": "", "label": "x", "events": []},
        )
        # min_length=1 on calendar_identifier rejects.
        self.assertEqual(response.status_code, 422)

    def test_label_length_capped(self) -> None:
        big = self._payload()
        big["label"] = "x" * 200
        response = self.client.post("/api/calendar/local/sync", json=big)
        self.assertEqual(response.status_code, 422)

    def test_emits_local_calendar_synced_study_event_when_changed(self) -> None:
        self.client.post("/api/calendar/local/sync", json=self._payload())
        with db.get_db() as conn:
            row = conn.execute(
                """
                SELECT event_type FROM study_events
                WHERE event_type = 'local_calendar_synced'
                ORDER BY created_at DESC LIMIT 1
                """,
            ).fetchone()
        self.assertIsNotNone(row, "Expected a local_calendar_synced study event")


if __name__ == "__main__":
    unittest.main()
