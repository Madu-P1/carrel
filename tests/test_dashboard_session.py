"""Dashboard + active-session integration tests.

Covers the contract the frontend relies on:
  - /api/dashboard always returns `streak_target_days` and `week_minutes_by_day`
    as a 7-element array (oldest → newest).
  - /api/dashboard.active_session mirrors the current active session if one
    exists, null otherwise.
  - /api/sessions/active returns a full envelope with the active session or
    null.
  - Multiple rows with status='active' resolve to the most recent by
    started_at (defensive against schema drift).
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

import main
from api_models import SessionStartRequest
from routes.workspace import create_session as create_session_route


class DashboardSessionTests(unittest.TestCase):
    def setUp(self) -> None:
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
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        main.BASE_DIR = self.original_base_dir
        main.DATA_DIR = self.original_data_dir
        main.UPLOAD_DIR = self.original_upload_dir
        main.DB_PATH = self.original_db_path
        main.SCHEMA_PATH = self.original_schema_path
        self.temp_dir.cleanup()

    # ---------- dashboard payload shape ----------

    def test_dashboard_includes_streak_target_and_week_by_day(self) -> None:
        response = self.client.get("/api/dashboard")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        stats = body["stats"]
        self.assertIn("streak_target_days", stats)
        self.assertEqual(stats["streak_target_days"], 30)
        self.assertIn("week_minutes_by_day", stats)
        self.assertIsInstance(stats["week_minutes_by_day"], list)
        self.assertEqual(len(stats["week_minutes_by_day"]), 7)
        # Every entry is a number — serializing through JSON preserves float/int.
        for value in stats["week_minutes_by_day"]:
            self.assertIsInstance(value, (int, float))

    def test_dashboard_active_session_is_null_when_none(self) -> None:
        response = self.client.get("/api/dashboard")
        self.assertIsNone(response.json()["active_session"])

    def test_dashboard_surfaces_active_session_after_start(self) -> None:
        payload = SessionStartRequest(
            goal_id=None,
            source_scope=None,
            concept_scope=None,
            difficulty_target=0.5,
            duration_minutes=25,
            mode="focus_sprint",
            objective="Cover chapter 8",
        )
        create_session_route(payload)  # direct call commits via dependency

        response = self.client.get("/api/dashboard")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsNotNone(body["active_session"])
        self.assertEqual(body["active_session"]["objective"], "Cover chapter 8")
        self.assertEqual(body["active_session"]["mode"], "focus_sprint")
        self.assertEqual(body["active_session"]["duration_minutes"], 25)

    # ---------- /api/sessions/active endpoint ----------

    def test_active_endpoint_returns_null_envelope_when_none(self) -> None:
        response = self.client.get("/api/sessions/active")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"active_session": None})

    def test_active_endpoint_returns_session_after_start(self) -> None:
        payload = SessionStartRequest(
            goal_id=None,
            source_scope=None,
            concept_scope=None,
            difficulty_target=0.5,
            duration_minutes=20,
            mode="retrieval_practice",
            objective="Test recall",
        )
        create_session_route(payload)

        response = self.client.get("/api/sessions/active")
        body = response.json()
        self.assertIsNotNone(body["active_session"])
        self.assertEqual(body["active_session"]["mode"], "retrieval_practice")
        self.assertEqual(body["active_session"]["status"], "active")

    def test_active_endpoint_picks_most_recent_when_duplicates(self) -> None:
        """Defensive: schema doesn't enforce a single active row. If two
        exist (possible after a crash mid-completion), we return the most
        recent so the UI doesn't show stale state."""
        now = datetime.now(timezone.utc)
        earlier = (now - timedelta(hours=2)).isoformat()
        later = (now - timedelta(minutes=5)).isoformat()
        with main.get_db() as conn:
            conn.execute(
                """
                INSERT INTO sessions (id, objective, mode, duration_minutes, status, started_at)
                VALUES (?, ?, ?, ?, 'active', ?)
                """,
                ("old", "Old objective", "focus_sprint", 25, earlier),
            )
            conn.execute(
                """
                INSERT INTO sessions (id, objective, mode, duration_minutes, status, started_at)
                VALUES (?, ?, ?, ?, 'active', ?)
                """,
                ("new", "New objective", "focus_sprint", 25, later),
            )
            conn.commit()

        response = self.client.get("/api/sessions/active")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["active_session"]["id"], "new")

    def test_abandoned_sessions_are_not_surfaced(self) -> None:
        """A session marked 'active' but started > 12h ago is considered
        abandoned. Both /api/sessions/active and /api/dashboard should
        report no active session, regardless of how many stale rows
        exist in the table.

        This is the real-world case where the user started a session,
        closed the app, and came back days later. Surfacing it would
        resurrect a 96-hour timer and block fresh starts."""
        now = datetime.now(timezone.utc)
        ancient = (now - timedelta(days=4)).isoformat()
        old_but_recent = (now - timedelta(hours=18)).isoformat()
        with main.get_db() as conn:
            conn.execute(
                """
                INSERT INTO sessions (id, objective, mode, duration_minutes, status, started_at)
                VALUES (?, ?, ?, ?, 'active', ?)
                """,
                ("abandoned-a", "Forgotten study", "focus_sprint", 20, ancient),
            )
            conn.execute(
                """
                INSERT INTO sessions (id, objective, mode, duration_minutes, status, started_at)
                VALUES (?, ?, ?, ?, 'active', ?)
                """,
                ("abandoned-b", "Also forgotten", "focus_sprint", 20, old_but_recent),
            )
            conn.commit()

        active = self.client.get("/api/sessions/active").json()
        self.assertIsNone(active["active_session"])
        dash = self.client.get("/api/dashboard").json()
        self.assertIsNone(dash["active_session"])

    def test_started_at_includes_utc_timezone_marker(self) -> None:
        """Regression: sessions must serialize `started_at` as UTC-aware ISO
        strings (ending with `+00:00`). Without the timezone marker, the
        frontend's `Date.parse()` treats the value as LOCAL time — a user
        in UTC+2 sees every new session start 2 hours elapsed, the
        pomodoro timer renders `00:00 OVERTIME` immediately, and the whole
        timer UX breaks silently.

        The old code used `datetime.utcnow().isoformat()` which drops
        timezone info. The fix uses `datetime.now(timezone.utc).isoformat()`
        which always emits `+00:00`."""
        import re

        payload = SessionStartRequest(
            goal_id=None,
            source_scope=None,
            concept_scope=None,
            difficulty_target=0.5,
            duration_minutes=25,
            mode="focus_sprint",
            objective="TZ regression",
        )
        result = create_session_route(payload)
        started_at = str(result.get("started_at") or "")
        self.assertTrue(
            re.search(r"[+-]\d{2}:\d{2}$", started_at),
            f"started_at missing timezone marker: {started_at!r}",
        )

    def test_recent_session_still_surfaces_despite_older_abandoned(self) -> None:
        """If a legitimate recent session exists AND older abandoned rows
        also exist, we return the recent one. The filter doesn't penalize
        valid state just because stale state lives alongside it."""
        now = datetime.now(timezone.utc)
        ancient = (now - timedelta(days=3)).isoformat()
        recent = (now - timedelta(minutes=10)).isoformat()
        with main.get_db() as conn:
            conn.execute(
                """
                INSERT INTO sessions (id, objective, mode, duration_minutes, status, started_at)
                VALUES (?, ?, ?, ?, 'active', ?)
                """,
                ("ghost", "Ancient session", "focus_sprint", 20, ancient),
            )
            conn.execute(
                """
                INSERT INTO sessions (id, objective, mode, duration_minutes, status, started_at)
                VALUES (?, ?, ?, ?, 'active', ?)
                """,
                ("fresh", "Real session", "focus_sprint", 20, recent),
            )
            conn.commit()

        active = self.client.get("/api/sessions/active").json()
        self.assertEqual(active["active_session"]["id"], "fresh")
        dash = self.client.get("/api/dashboard").json()
        self.assertEqual(dash["active_session"]["id"], "fresh")


if __name__ == "__main__":
    unittest.main()
