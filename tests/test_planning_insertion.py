"""Tests for the deadline-aware study session insertion engine."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

import db
import main
from services.calendar.secrets import set_default_secret_store_for_testing
from services.planning import insertion as insertion_engine
from services.planning.deadlines import detect_upcoming_deadlines


class _FakeStore:
    def store_url(self, feed_id: str, raw_url: str) -> str:
        return f"fake:{feed_id}"

    def get_url(self, reference: str) -> str | None:
        return None

    def delete_url(self, reference: str) -> None:
        return None


def _seed_event(conn: sqlite3.Connection, *, feed_id: str, uid: str, summary: str,
                start_at: str, end_at: str, all_day: bool = False,
                status: str = "confirmed") -> None:
    conn.execute(
        """
        INSERT INTO calendar_events (
            id, feed_id, uid, occurrence_key, summary, start_at, end_at,
            timezone, all_day, location, categories, status, rrule,
            recurrence_id, source_updated_at, source_hash,
            user_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL, NULL, ?, NULL,
                  NULL, NULL, ?, 'local', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        (
            uid, feed_id, uid, uid, summary, start_at, end_at,
            1 if all_day else 0, status, uid,  # source_hash = uid for stability
        ),
    )


def _seed_feed(conn: sqlite3.Connection, *, feed_id: str = "f1") -> None:
    conn.execute(
        """
        INSERT INTO calendar_feeds (
            id, user_id, label, url, url_hash, color,
            is_enabled, consecutive_failures, kind, created_at, updated_at
        ) VALUES (?, 'local', 'Work', 'https://example.com/feed.ics',
                  ?, NULL, 1, 0, 'url', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        (feed_id, "hash-" + feed_id),
    )


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


class InsertionEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        set_default_secret_store_for_testing(_FakeStore())
        self.temp_dir = tempfile.TemporaryDirectory()
        base = Path(self.temp_dir.name)
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

    def tearDown(self) -> None:
        set_default_secret_store_for_testing(None)
        for k, v in self.originals.items():
            setattr(main, k, v)
        self.temp_dir.cleanup()

    def test_no_events_returns_one_or_more_free_block_suggestions(self) -> None:
        """Empty calendar = the whole horizon is free; engine should
        propose afternoon blocks even with no deadlines."""
        with db.get_db() as conn:
            insertions = insertion_engine.best_study_session_insertions(conn)
        # Without events, the engine returns up to MAX_INSERTIONS slots.
        # All carry reason_code='free_block' since there are no deadlines.
        self.assertGreater(len(insertions), 0)
        for ins in insertions:
            self.assertEqual(ins.reason_code, "free_block")
            self.assertIsNone(ins.deadline_label)
            # Score normalized to top=1.0
            self.assertGreaterEqual(ins.score, 0.0)
            self.assertLessEqual(ins.score, 1.0)

    def test_calendar_event_with_midterm_keyword_anchors_insertion(self) -> None:
        """A 'Bio midterm' event in 5 days should produce
        deadline_imminent insertions."""
        with db.get_db() as conn:
            _seed_feed(conn)
            now = datetime.now(UTC)
            five_days = now + timedelta(days=5)
            _seed_event(
                conn,
                feed_id="f1",
                uid="bio-midterm",
                summary="Bio midterm",
                start_at=_iso(five_days),
                end_at=_iso(five_days + timedelta(hours=1)),
            )
            conn.commit()
            insertions = insertion_engine.best_study_session_insertions(conn)
        # At least one insertion should be deadline-anchored.
        deadline_anchored = [
            i for i in insertions if i.reason_code == "deadline_imminent"
        ]
        self.assertGreater(len(deadline_anchored), 0,
                           f"Expected deadline-anchored insertion; got {insertions}")
        for ins in deadline_anchored:
            self.assertEqual(ins.deadline_label, "Bio midterm")
            self.assertIsNotNone(ins.deadline_at)

    def test_busy_calendar_yields_no_or_few_insertions(self) -> None:
        """If the next 14 days are wall-to-wall events, there shouldn't
        be any large free blocks to propose."""
        with db.get_db() as conn:
            _seed_feed(conn)
            now = datetime.now(UTC).replace(microsecond=0)
            # Carpet the next 14 days with 1-hour-on, 5-min-off events.
            # 5 minutes is below MIN_BLOCK_MINUTES so no blocks qualify.
            cursor = now
            horizon = now + timedelta(days=14)
            i = 0
            while cursor < horizon:
                end = cursor + timedelta(minutes=60)
                _seed_event(
                    conn, feed_id="f1", uid=f"e-{i}",
                    summary="Work meeting",
                    start_at=_iso(cursor), end_at=_iso(end),
                )
                cursor = end + timedelta(minutes=5)
                i += 1
            conn.commit()
            insertions = insertion_engine.best_study_session_insertions(conn)
        self.assertEqual(insertions, [])

    def test_results_capped_at_max_insertions(self) -> None:
        """Open calendar should produce <= MAX_INSERTIONS results."""
        with db.get_db() as conn:
            insertions = insertion_engine.best_study_session_insertions(conn)
        self.assertLessEqual(len(insertions), insertion_engine.MAX_INSERTIONS)

    def test_overdue_srs_aggregate_appears_as_deadline(self) -> None:
        """Cards with due_date <= today should aggregate into a
        srs_overdue deadline."""
        with db.get_db() as conn:
            today = datetime.now(UTC).date().isoformat()
            for i in range(7):
                conn.execute(
                    """
                    INSERT INTO srs_cards (
                        id, card_type, front, back, state, due_date
                    ) VALUES (?, 'anchor', ?, ?, 'review', ?)
                    """,
                    (f"card-{i}", f"Q{i}", f"A{i}", today),
                )
            conn.commit()
            deadlines = detect_upcoming_deadlines(conn)
            srs_deadlines = [d for d in deadlines if d.source == "srs_overdue"]
        self.assertEqual(len(srs_deadlines), 1)
        self.assertEqual(srs_deadlines[0].label, "7 cards overdue")

    def test_time_of_day_fit_prefers_afternoon(self) -> None:
        """A 3 PM block should score higher than a 4 AM block of the
        same size with the same deadline."""
        # We test the helper directly because seeding-events to control
        # exact block boundaries against `now` would be flaky.
        from zoneinfo import ZoneInfo

        from services.planning.insertion import _time_of_day_fit

        utc = ZoneInfo("UTC")
        afternoon_iso = "2026-05-05T15:00:00Z"
        early_morning_iso = "2026-05-05T04:00:00Z"
        afternoon_score = _time_of_day_fit(afternoon_iso, tz=utc)
        morning_score = _time_of_day_fit(early_morning_iso, tz=utc)
        self.assertGreater(afternoon_score, morning_score)

    def test_urgency_discount_when_user_has_allocated_study_blocks(self) -> None:
        """A deadline the user has already scheduled prep for should
        produce a lower urgency factor than the same deadline with no
        prep scheduled. Pin the contract directly on the helper.
        """
        from services.planning.deadlines import Deadline
        from services.planning.insertion import _urgency_factor

        # Deadline 2 days out → base factor 1/(2+1) = 0.33, comfortably
        # above the 0.2 floor so the discount is observable.
        deadline = Deadline(
            label="Bio midterm",
            deadline_at="2026-05-07T15:00:00Z",
            days_until=2.0,
            source="calendar_event",
            event_id="evt-bio",
            severity="normal",
        )
        now = datetime(2026, 5, 5, tzinfo=UTC)
        baseline = _urgency_factor(deadline, now=now, allocated_minutes=0)
        well_prepared = _urgency_factor(
            deadline, now=now, allocated_minutes=120,  # 2 days × 60 min target
        )
        self.assertLess(well_prepared, baseline)
        # Floor lands at the no-deadline baseline (0.2). The user still
        # sees supplemental suggestions even when fully prepared — they
        # just rank below open free blocks rather than above them.
        self.assertGreaterEqual(well_prepared, 0.2)

    def test_study_keyword_event_counts_as_allocated_prep(self) -> None:
        """Events whose summary matches `study|revision|revise` should
        be counted by `_allocated_study_minutes_in_window`. This is the
        signal-detection layer the user explicitly asked for: typing
        'Study Bio' on the calendar tells Carrel they've blocked time.
        """
        from services.planning.insertion import _allocated_study_minutes_in_window

        with db.get_db() as conn:
            _seed_feed(conn)
            now = datetime.now(UTC)
            # Two prep blocks (60 + 90 = 150 min) in the next 7 days.
            _seed_event(
                conn, feed_id="f1", uid="prep-1", summary="Study Bio chapter 4",
                start_at=_iso(now + timedelta(days=1, hours=14)),
                end_at=_iso(now + timedelta(days=1, hours=15)),
            )
            _seed_event(
                conn, feed_id="f1", uid="prep-2", summary="Revise calculus problem set",
                start_at=_iso(now + timedelta(days=2, hours=10)),
                end_at=_iso(now + timedelta(days=2, hours=11, minutes=30)),
            )
            # Decoy: a normal class block; should NOT count.
            _seed_event(
                conn, feed_id="f1", uid="lecture", summary="Bio lecture",
                start_at=_iso(now + timedelta(days=1, hours=9)),
                end_at=_iso(now + timedelta(days=1, hours=10)),
            )
            conn.commit()
            allocated = _allocated_study_minutes_in_window(
                conn, user_id="local", now=now,
                until_iso=_iso(now + timedelta(days=7)),
            )
        self.assertEqual(allocated, 150)


class StudySessionInsertionsRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        from fastapi.testclient import TestClient

        from services.local_api_security import HEADER_NAME, get_local_api_token

        set_default_secret_store_for_testing(_FakeStore())
        self.temp_dir = tempfile.TemporaryDirectory()
        base = Path(self.temp_dir.name)
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

    def test_get_returns_insertions_with_user_timezone(self) -> None:
        response = self.client.get(
            "/api/plan/insertions?tz=America/New_York"
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["user_timezone"], "America/New_York")
        self.assertIsInstance(body["insertions"], list)

    def test_unknown_timezone_falls_through_silently(self) -> None:
        response = self.client.get(
            "/api/plan/insertions?tz=Mars/Olympus_Mons"
        )
        # The route accepts the typo and the engine downgrades to UTC.
        self.assertEqual(response.status_code, 200, response.text)


if __name__ == "__main__":
    unittest.main()
