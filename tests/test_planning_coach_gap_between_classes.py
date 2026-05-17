"""Unit tests for `services.planning.coach._rule_gap_between_classes`.

Phase 2 rule. Emits a `catchup` micro-session when two adjacent
calendar events at the same location are 30-120 minutes apart.
Anchors at the first event's `end_at`. Duration is
`gap - GAP_TRANSITION_BUFFER_MINUTES`, capped at
`GAP_MAX_SESSION_MINUTES`.
"""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import db
from services.planning import coach

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_SOURCE = REPO_ROOT / "migrations"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class GapBetweenClassesRuleTests(unittest.TestCase):
    """Each test gets a fresh in-tempdir SQLite DB. Events are
    inserted via direct SQL so the rule can be exercised without
    going through the feed-sync pipeline.
    """

    def setUp(self) -> None:
        self._original_paths = (
            db.BASE_DIR,
            db.DATA_DIR,
            db.UPLOAD_DIR,
            db.DB_PATH,
            db.SCHEMA_PATH,
        )
        self._temp_dir = tempfile.TemporaryDirectory()
        root = Path(self._temp_dir.name)
        data_dir = root / "data"
        upload_dir = data_dir / "uploads"
        data_dir.mkdir(parents=True, exist_ok=True)
        upload_dir.mkdir(parents=True, exist_ok=True)
        (root / "schema.sql").write_text("-- historical reference only\n", encoding="utf-8")
        shutil.copytree(MIGRATIONS_SOURCE, root / "migrations", dirs_exist_ok=True)
        db.configure_paths(
            base_dir=root,
            data_dir=data_dir,
            upload_dir=upload_dir,
            db_path=data_dir / "test.db",
            schema_path=root / "schema.sql",
        )
        with db.get_db() as conn:
            db.apply_migrations(conn)
            self._seed_feed(conn)

    def tearDown(self) -> None:
        db.configure_paths(
            base_dir=self._original_paths[0],
            data_dir=self._original_paths[1],
            upload_dir=self._original_paths[2],
            db_path=self._original_paths[3],
            schema_path=self._original_paths[4],
        )
        self._temp_dir.cleanup()

    # -----------------------------------------------------------------
    # Fixture helpers

    def _seed_feed(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            INSERT INTO calendar_feeds (
                id, user_id, label, url, url_hash, created_at, updated_at
            ) VALUES (?, 'local', ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            ("feed-1", "Test Feed", "https://example.test/feed.ics", "hash-1"),
        )
        conn.commit()

    def _insert_event(
        self,
        conn: sqlite3.Connection,
        *,
        event_id: str,
        summary: str,
        start_at: datetime,
        end_at: datetime,
        location: str | None,
        status: str = "confirmed",
        all_day: int = 0,
    ) -> None:
        conn.execute(
            """
            INSERT INTO calendar_events (
                id, user_id, feed_id, uid, occurrence_key,
                summary, start_at, end_at, location, all_day, status
            ) VALUES (?, 'local', 'feed-1', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                event_id,
                event_id,
                summary,
                _iso(start_at),
                _iso(end_at),
                location,
                all_day,
                status,
            ),
        )
        conn.commit()

    def _run(self) -> list[coach.CandidateSuggestion]:
        with db.get_db() as conn:
            return coach._rule_gap_between_classes(conn, user_id="local")

    def _seed_pair(
        self,
        *,
        gap_minutes: int,
        first_location: str = "Math Building",
        second_location: str | None = None,
        first_start_in_hours: float = 1.0,
    ) -> None:
        if second_location is None:
            second_location = first_location
        first_start = datetime.now(timezone.utc) + timedelta(hours=first_start_in_hours)
        first_end = first_start + timedelta(hours=1)
        second_start = first_end + timedelta(minutes=gap_minutes)
        second_end = second_start + timedelta(hours=1)
        with db.get_db() as conn:
            self._insert_event(
                conn,
                event_id="first",
                summary="Calc 101",
                start_at=first_start,
                end_at=first_end,
                location=first_location,
            )
            self._insert_event(
                conn,
                event_id="second",
                summary="Linear Algebra",
                start_at=second_start,
                end_at=second_end,
                location=second_location,
            )

    # -----------------------------------------------------------------
    # No-match cases

    def test_returns_empty_with_no_events(self) -> None:
        self.assertEqual(self._run(), [])

    def test_returns_empty_with_single_event(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        with db.get_db() as conn:
            self._insert_event(
                conn,
                event_id="solo",
                summary="Calc",
                start_at=future,
                end_at=future + timedelta(hours=1),
                location="Math Building",
            )
        self.assertEqual(self._run(), [])

    def test_skips_pair_with_different_locations(self) -> None:
        self._seed_pair(
            gap_minutes=45,
            first_location="Math Building",
            second_location="Physics Building",
        )
        self.assertEqual(self._run(), [])

    def test_skips_pair_when_first_has_null_location(self) -> None:
        self._seed_pair(gap_minutes=45, first_location="Math Building")
        # Override with a null location for the first event.
        with db.get_db() as conn:
            conn.execute("UPDATE calendar_events SET location = NULL WHERE id = 'first'")
            conn.commit()
        self.assertEqual(self._run(), [])

    def test_skips_pair_when_first_has_empty_location(self) -> None:
        self._seed_pair(gap_minutes=45, first_location="   ")
        self.assertEqual(self._run(), [])

    def test_skips_pair_when_second_has_null_location(self) -> None:
        # Symmetry with the first-NULL-location case. Both events
        # must have a non-empty location for a pair to match.
        self._seed_pair(gap_minutes=45, first_location="Math Building")
        with db.get_db() as conn:
            conn.execute("UPDATE calendar_events SET location = NULL WHERE id = 'second'")
            conn.commit()
        self.assertEqual(self._run(), [])

    def test_intervening_null_location_event_blocks_pairing(self) -> None:
        # Regression guard: an event with no location sitting between
        # two same-location events MUST break adjacency. Otherwise
        # filtering out non-location events at the SQL layer (an
        # earlier mistake) would let the rule pair A with C and emit
        # a catchup that overlaps B.
        now = datetime.now(timezone.utc)
        with db.get_db() as conn:
            self._insert_event(
                conn,
                event_id="a",
                summary="Calc",
                start_at=now + timedelta(hours=2),
                end_at=now + timedelta(hours=3),
                location="Math Building",
            )
            self._insert_event(
                conn,
                event_id="b-no-location",
                summary="Doctors appointment",
                start_at=now + timedelta(hours=3, minutes=15),
                end_at=now + timedelta(hours=3, minutes=45),
                location=None,
            )
            self._insert_event(
                conn,
                event_id="c",
                summary="Linear Algebra",
                start_at=now + timedelta(hours=4),
                end_at=now + timedelta(hours=5),
                location="Math Building",
            )
        self.assertEqual(self._run(), [])

    def test_intervening_different_location_event_blocks_pairing(self) -> None:
        # Same shape as the NULL-intervening case but with a real
        # location on the middle event. Adjacency-based pairing
        # rejects (a, b) and (b, c) on location mismatch, so the
        # rule does NOT pair (a, c) across b.
        now = datetime.now(timezone.utc)
        with db.get_db() as conn:
            self._insert_event(
                conn,
                event_id="a",
                summary="Calc",
                start_at=now + timedelta(hours=2),
                end_at=now + timedelta(hours=3),
                location="Math Building",
            )
            self._insert_event(
                conn,
                event_id="b-other",
                summary="Office hours",
                start_at=now + timedelta(hours=3, minutes=15),
                end_at=now + timedelta(hours=3, minutes=45),
                location="Library",
            )
            self._insert_event(
                conn,
                event_id="c",
                summary="Linear Algebra",
                start_at=now + timedelta(hours=4),
                end_at=now + timedelta(hours=5),
                location="Math Building",
            )
        self.assertEqual(self._run(), [])

    def test_skips_pair_with_gap_below_min_threshold(self) -> None:
        # GAP_MIN_MINUTES is 30; a 25-min gap is too short.
        self._seed_pair(gap_minutes=25)
        self.assertEqual(self._run(), [])

    def test_skips_pair_with_gap_at_or_above_max_threshold(self) -> None:
        # GAP_MAX_MINUTES is 120; the range is `[30, 120)`, so a
        # 120-minute gap falls outside.
        self._seed_pair(gap_minutes=coach.GAP_MAX_MINUTES)
        self.assertEqual(self._run(), [])

    def test_skips_pair_when_first_event_is_cancelled(self) -> None:
        self._seed_pair(gap_minutes=45)
        with db.get_db() as conn:
            conn.execute("UPDATE calendar_events SET status = 'cancelled' WHERE id = 'first'")
            conn.commit()
        self.assertEqual(self._run(), [])

    def test_skips_pair_when_events_overlap(self) -> None:
        # Defensive: if the calendar has overlapping back-to-back
        # events at the same location, there's no gap to fill.
        now = datetime.now(timezone.utc)
        with db.get_db() as conn:
            self._insert_event(
                conn,
                event_id="first",
                summary="Calc",
                start_at=now + timedelta(hours=1),
                end_at=now + timedelta(hours=3),  # ends after second starts
                location="Math Building",
            )
            self._insert_event(
                conn,
                event_id="second",
                summary="Linear Algebra",
                start_at=now + timedelta(hours=2),
                end_at=now + timedelta(hours=4),
                location="Math Building",
            )
        self.assertEqual(self._run(), [])

    def test_skips_event_beyond_24h_lookahead(self) -> None:
        far = datetime.now(timezone.utc) + timedelta(hours=coach.LOOKAHEAD_HOURS + 5)
        with db.get_db() as conn:
            self._insert_event(
                conn,
                event_id="far-a",
                summary="Calc",
                start_at=far,
                end_at=far + timedelta(hours=1),
                location="Math Building",
            )
            self._insert_event(
                conn,
                event_id="far-b",
                summary="Linear Algebra",
                start_at=far + timedelta(hours=2),
                end_at=far + timedelta(hours=3),
                location="Math Building",
            )
        self.assertEqual(self._run(), [])

    # -----------------------------------------------------------------
    # Match cases

    def test_one_qualifying_pair_emits_one_catchup_suggestion(self) -> None:
        self._seed_pair(gap_minutes=45)
        result = self._run()
        self.assertEqual(len(result), 1)
        candidate = result[0]
        self.assertEqual(candidate.kind, "catchup")
        self.assertEqual(candidate.reason_code, "gap_between_classes")
        self.assertEqual(candidate.source_event_id, "first")
        self.assertAlmostEqual(candidate.score, 1.2)

    def test_match_is_case_insensitive_on_location(self) -> None:
        self._seed_pair(
            gap_minutes=45,
            first_location="MATH BUILDING",
            second_location="math building",
        )
        self.assertEqual(len(self._run()), 1)

    def test_match_trims_whitespace_on_location(self) -> None:
        self._seed_pair(
            gap_minutes=45,
            first_location=" Math Building ",
            second_location="Math Building",
        )
        self.assertEqual(len(self._run()), 1)

    def test_session_duration_subtracts_transition_buffer(self) -> None:
        # gap = 45 min; session = 45 - 5 = 40, then capped at 30.
        self._seed_pair(gap_minutes=45)
        candidate = self._run()[0]
        start = coach._parse_iso(candidate.start_at)
        end = coach._parse_iso(candidate.end_at)
        minutes = int((end - start).total_seconds() // 60)
        self.assertEqual(minutes, coach.GAP_MAX_SESSION_MINUTES)

    def test_session_duration_uses_short_gap_minus_buffer_when_below_cap(self) -> None:
        # gap = 32 min; session = 32 - 5 = 27 (below the 30 cap).
        self._seed_pair(gap_minutes=32)
        candidate = self._run()[0]
        start = coach._parse_iso(candidate.start_at)
        end = coach._parse_iso(candidate.end_at)
        minutes = int((end - start).total_seconds() // 60)
        self.assertEqual(minutes, 32 - coach.GAP_TRANSITION_BUFFER_MINUTES)

    def test_gap_at_exact_min_threshold_emits_suggestion(self) -> None:
        # GAP_MIN_MINUTES is 30 and the predicate uses `>=`.
        self._seed_pair(gap_minutes=coach.GAP_MIN_MINUTES)
        self.assertEqual(len(self._run()), 1)

    def test_gap_just_below_max_threshold_emits_suggestion(self) -> None:
        self._seed_pair(gap_minutes=coach.GAP_MAX_MINUTES - 1)
        self.assertEqual(len(self._run()), 1)

    def test_anchored_at_first_event_end_at(self) -> None:
        first_start = datetime.now(timezone.utc) + timedelta(hours=2)
        first_end = first_start + timedelta(hours=1)
        second_start = first_end + timedelta(minutes=45)
        second_end = second_start + timedelta(hours=1)
        with db.get_db() as conn:
            self._insert_event(
                conn,
                event_id="first",
                summary="Calc",
                start_at=first_start,
                end_at=first_end,
                location="Math Building",
            )
            self._insert_event(
                conn,
                event_id="second",
                summary="Linear Algebra",
                start_at=second_start,
                end_at=second_end,
                location="Math Building",
            )
        candidate = self._run()[0]
        self.assertEqual(candidate.start_at, _iso(first_end))

    def test_reason_text_mentions_gap_minutes_and_location(self) -> None:
        self._seed_pair(gap_minutes=45, first_location="Library North")
        text = self._run()[0].reason_text
        self.assertIn("45-min gap", text)
        self.assertIn("Library North", text)

    def test_multiple_qualifying_pairs_emit_multiple_suggestions(self) -> None:
        base = datetime.now(timezone.utc) + timedelta(hours=2)
        with db.get_db() as conn:
            # Pair 1: 9am-10am + 10:45am-11:45am at Math Building.
            self._insert_event(
                conn,
                event_id="a1",
                summary="Calc",
                start_at=base,
                end_at=base + timedelta(hours=1),
                location="Math Building",
            )
            self._insert_event(
                conn,
                event_id="a2",
                summary="Linear Algebra",
                start_at=base + timedelta(hours=1, minutes=45),
                end_at=base + timedelta(hours=2, minutes=45),
                location="Math Building",
            )
            # Pair 2 (different building, but adjacent to a2):
            # a2 ends at +2h45, then b1 at +5h at Physics. Gap is 2h15
            # which is above max — no match. Use a different time so
            # b1 and b2 form an in-range pair.
            self._insert_event(
                conn,
                event_id="b1",
                summary="Physics 101",
                start_at=base + timedelta(hours=5),
                end_at=base + timedelta(hours=6),
                location="Physics Building",
            )
            self._insert_event(
                conn,
                event_id="b2",
                summary="Optics Lab",
                start_at=base + timedelta(hours=6, minutes=40),
                end_at=base + timedelta(hours=7, minutes=40),
                location="Physics Building",
            )
        result = self._run()
        # Two same-location pairs: (a1, a2) and (b1, b2). Each emits
        # one suggestion.
        ids = sorted(c.source_event_id for c in result if c.source_event_id)
        self.assertEqual(ids, ["a1", "b1"])

    # -----------------------------------------------------------------
    # Synthesize integration

    def test_synthesize_includes_gap_between_classes_when_pair_present(self) -> None:
        self._seed_pair(gap_minutes=45)
        with db.get_db() as conn:
            results = coach.synthesize_suggestions(conn, user_id="local")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].reason_code, "gap_between_classes")
        self.assertEqual(results[0].kind, "catchup")


if __name__ == "__main__":
    unittest.main()
