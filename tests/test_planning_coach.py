"""Tests for the deadline-aware coach rule (`_rule_deadline_imminent`).

The detector itself (`services/planning/deadlines.py`) is exercised by
`test_planning_insertion.py`. These tests live one layer up, asserting
the rule body shapes its output correctly and that the synthesize
pipeline ranks it above the v1 SRS rule.
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

import db
import main
from services.calendar.secrets import set_default_secret_store_for_testing
from services.planning import coach


class _FakeStore:
    def store_url(self, feed_id: str, raw_url: str) -> str:
        return f"fake:{feed_id}"

    def get_url(self, reference: str) -> str | None:
        return None

    def delete_url(self, reference: str) -> None:
        return None


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


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


def _seed_event(
    conn: sqlite3.Connection,
    *,
    feed_id: str,
    uid: str,
    summary: str,
    start_at: str,
    end_at: str,
    all_day: bool = False,
    status: str = "confirmed",
) -> None:
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
            1 if all_day else 0, status, uid,
        ),
    )


class DeadlineImminentRuleTests(unittest.TestCase):
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

    def test_no_events_means_no_deadline_suggestions(self) -> None:
        with db.get_db() as conn:
            candidates = coach._rule_deadline_imminent(conn, user_id="local")
        self.assertEqual(candidates, [])

    def test_high_severity_deadline_emits_study_block_with_correct_metadata(self) -> None:
        """Bio midterm in 2 days, free time tonight: the rule should
        emit one study_block tagged 'deadline_imminent', linked to the
        event, with the deadline label inside reason_text."""
        now = datetime.now(UTC)
        deadline_at = now + timedelta(days=2, hours=4)
        with db.get_db() as conn:
            _seed_feed(conn)
            _seed_event(
                conn,
                feed_id="f1",
                uid="ev-bio-midterm",
                summary="Bio midterm",
                start_at=_iso(deadline_at),
                end_at=_iso(deadline_at + timedelta(hours=2)),
            )
            candidates = coach._rule_deadline_imminent(conn, user_id="local")

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.kind, "study_block")
        self.assertEqual(candidate.reason_code, "deadline_imminent")
        self.assertIn("Bio midterm", candidate.reason_text)
        self.assertEqual(candidate.source_event_id, "ev-bio-midterm")
        self.assertEqual(candidate.due_at, _iso(deadline_at))
        # high-severity outranks the v1 SRS rule (1.0)
        self.assertGreater(candidate.score, 1.0)

    def test_past_deadline_is_skipped(self) -> None:
        now = datetime.now(UTC)
        past = now - timedelta(days=1)
        with db.get_db() as conn:
            _seed_feed(conn)
            _seed_event(
                conn,
                feed_id="f1",
                uid="ev-past",
                summary="Calculus exam",
                start_at=_iso(past),
                end_at=_iso(past + timedelta(hours=2)),
            )
            candidates = coach._rule_deadline_imminent(conn, user_id="local")
        self.assertEqual(candidates, [])

    def test_low_severity_deadline_far_future_is_skipped(self) -> None:
        """A final exam 21 days out is too far for the rule to help.
        That's a planner question, not a "study tonight" question."""
        now = datetime.now(UTC)
        far = now + timedelta(days=21)
        with db.get_db() as conn:
            _seed_feed(conn)
            _seed_event(
                conn,
                feed_id="f1",
                uid="ev-final",
                summary="Final exam",
                start_at=_iso(far),
                end_at=_iso(far + timedelta(hours=2)),
            )
            candidates = coach._rule_deadline_imminent(conn, user_id="local")
        self.assertEqual(candidates, [])

    def test_more_imminent_deadline_scores_higher(self) -> None:
        """A midterm tomorrow should outrank a midterm in 3 days."""
        now = datetime.now(UTC)
        with db.get_db() as conn:
            _seed_feed(conn)
            # 3-day-out exam first so the order in the DB doesn't bias
            # the rule's iteration.
            _seed_event(
                conn, feed_id="f1", uid="ev-far",
                summary="Bio midterm",
                start_at=_iso(now + timedelta(days=3, hours=2)),
                end_at=_iso(now + timedelta(days=3, hours=4)),
            )
            _seed_event(
                conn, feed_id="f1", uid="ev-near",
                summary="Calc midterm",
                start_at=_iso(now + timedelta(days=1, hours=2)),
                end_at=_iso(now + timedelta(days=1, hours=4)),
            )
            candidates = coach._rule_deadline_imminent(conn, user_id="local")

        # Both fire (high-severity ≤3 days). The "tomorrow" deadline
        # must outscore the "in 3 days" one.
        self.assertEqual(len(candidates), 2)
        scores_by_label = {
            "Calc midterm" if "Calc midterm" in c.reason_text else "Bio midterm": c.score
            for c in candidates
        }
        self.assertGreater(scores_by_label["Calc midterm"], scores_by_label["Bio midterm"])

    def test_caps_at_three_suggestions(self) -> None:
        now = datetime.now(UTC)
        with db.get_db() as conn:
            _seed_feed(conn)
            for i, days in enumerate([1, 2, 3, 4, 5]):
                _seed_event(
                    conn, feed_id="f1", uid=f"ev-{i}",
                    summary=f"Test {i}",
                    start_at=_iso(now + timedelta(days=days, hours=2)),
                    end_at=_iso(now + timedelta(days=days, hours=4)),
                )
            candidates = coach._rule_deadline_imminent(conn, user_id="local")
        self.assertLessEqual(len(candidates), 3)

    def test_accepted_study_suggestion_does_not_become_a_deadline(self) -> None:
        """Regression: when the user accepts a deadline_imminent
        suggestion, the resulting calendar event is titled "Study —
        Deadline: <label>". The deadline keyword regex matches "deadline"
        in that string, so without the study-exclusion guard the
        accepted suggestion would itself surface as a fresh deadline,
        triggering yet another suggestion next refresh, ad infinitum."""
        from services.planning.deadlines import detect_upcoming_deadlines

        now = datetime.now(UTC)
        with db.get_db() as conn:
            _seed_feed(conn)
            # Original user-added deadline
            _seed_event(
                conn, feed_id="f1", uid="ev-orig",
                summary="Bio midterm",
                start_at=_iso(now + timedelta(days=2, hours=2)),
                end_at=_iso(now + timedelta(days=2, hours=4)),
            )
            # Simulated accepted study suggestion (what the coach
            # creates when the user clicks "Add" on a deadline_imminent
            # suggestion)
            _seed_event(
                conn, feed_id="f1", uid="ev-study-block",
                summary="Study — Deadline: Bio midterm",
                start_at=_iso(now + timedelta(hours=4)),
                end_at=_iso(now + timedelta(hours=5)),
            )
            deadlines = detect_upcoming_deadlines(conn)

        # Only the original "Bio midterm" should appear, not the
        # study-block twin.
        labels = [d.label for d in deadlines]
        self.assertIn("Bio midterm", labels)
        self.assertFalse(
            any("Study" in label for label in labels),
            f"Expected no study-prefixed deadlines; got {labels}",
        )

    def test_synthesize_ranks_deadline_above_v1_srs_rule(self) -> None:
        """Both rules fire; deadline candidate must be at the top."""
        now = datetime.now(UTC)
        with db.get_db() as conn:
            _seed_feed(conn)
            _seed_event(
                conn, feed_id="f1", uid="ev-mid",
                summary="Bio midterm",
                start_at=_iso(now + timedelta(days=2, hours=2)),
                end_at=_iso(now + timedelta(days=2, hours=4)),
            )
            # Seed an overdue SRS card so the v1 rule fires too.
            conn.execute(
                "INSERT INTO srs_cards (id, front, back, due_date) "
                "VALUES ('c1', 'Q', 'A', date('now','-1 day'))"
            )
            candidates = coach.synthesize_suggestions(conn, user_id="local")

        self.assertGreaterEqual(len(candidates), 2)
        self.assertEqual(candidates[0].reason_code, "deadline_imminent")


if __name__ == "__main__":
    unittest.main()
