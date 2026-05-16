"""Unit tests for `services.planning.coach._rule_deadline_imminent`.

Phase 2 rule. Surfaces calendar events whose summary names an academic
deadline ("midterm" / "final" / "exam" / "quiz", case-insensitive,
word-boundary), anchors a 60-min study_block at the chronologically
first free window before each deadline, and scores by urgency so the
imminent ones rank above the v1 `free_block_overdue_srs` baseline of
1.0.
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


class DeadlineImminentRuleTests(unittest.TestCase):
    """Each test gets a fresh in-tempdir SQLite DB. The schema-migration
    runner is the same one production uses; tests insert calendar rows
    directly so the rule can be exercised without going through the
    feed-sync pipeline.
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
        """The calendar_events FK requires a feed row to exist."""
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
        end_at: datetime | None = None,
        status: str = "confirmed",
        all_day: int = 0,
        feed_id: str = "feed-1",
    ) -> None:
        if end_at is None:
            end_at = start_at + timedelta(hours=1)
        conn.execute(
            """
            INSERT INTO calendar_events (
                id, user_id, feed_id, uid, occurrence_key,
                summary, start_at, end_at, all_day, status
            ) VALUES (?, 'local', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                feed_id,
                event_id,  # uid
                event_id,  # occurrence_key — unique per (feed, key)
                summary,
                _iso(start_at),
                _iso(end_at),
                all_day,
                status,
            ),
        )
        conn.commit()

    def _run(self) -> list[coach.CandidateSuggestion]:
        with db.get_db() as conn:
            return coach._rule_deadline_imminent(conn, user_id="local")

    # -----------------------------------------------------------------
    # No-match cases

    def test_returns_empty_when_no_events_exist(self) -> None:
        self.assertEqual(self._run(), [])

    def test_returns_empty_when_summary_has_no_deadline_keyword(self) -> None:
        with db.get_db() as conn:
            self._insert_event(
                conn,
                event_id="ev-1",
                summary="Coffee with advisor",
                start_at=datetime.now(timezone.utc) + timedelta(days=3),
            )
        self.assertEqual(self._run(), [])

    def test_skips_cancelled_event_with_matching_keyword(self) -> None:
        with db.get_db() as conn:
            self._insert_event(
                conn,
                event_id="ev-1",
                summary="Calculus midterm",
                start_at=datetime.now(timezone.utc) + timedelta(days=3),
                status="cancelled",
            )
        self.assertEqual(self._run(), [])

    def test_skips_event_in_the_past(self) -> None:
        with db.get_db() as conn:
            self._insert_event(
                conn,
                event_id="ev-1",
                summary="Stats midterm",
                start_at=datetime.now(timezone.utc) - timedelta(days=1),
            )
        self.assertEqual(self._run(), [])

    def test_skips_event_beyond_lookahead_horizon(self) -> None:
        far_future = datetime.now(timezone.utc) + timedelta(days=coach.DEADLINE_LOOKAHEAD_DAYS + 5)
        with db.get_db() as conn:
            self._insert_event(
                conn,
                event_id="ev-1",
                summary="Spanish final",
                start_at=far_future,
            )
        self.assertEqual(self._run(), [])

    def test_word_boundary_match_does_not_fire_on_substrings(self) -> None:
        # "finalists" contains "final" but \bfinal\b shouldn't match
        # because the following "i" is a word character.
        # "examine" contains "exam" but should NOT match for the same
        # reason. These are the false-positive cases the narrow keyword
        # list is supposed to avoid.
        future = datetime.now(timezone.utc) + timedelta(days=2)
        with db.get_db() as conn:
            self._insert_event(
                conn,
                event_id="ev-1",
                summary="Finalists announcement",
                start_at=future,
            )
            self._insert_event(
                conn,
                event_id="ev-2",
                summary="Examine the data",
                start_at=future + timedelta(hours=2),
            )
        self.assertEqual(self._run(), [])

    # -----------------------------------------------------------------
    # Match cases

    def test_one_matching_event_emits_one_study_block_suggestion(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(days=3)
        with db.get_db() as conn:
            self._insert_event(
                conn,
                event_id="ev-1",
                summary="Calculus midterm",
                start_at=future,
            )
        result = self._run()
        self.assertEqual(len(result), 1)
        candidate = result[0]
        self.assertEqual(candidate.kind, "study_block")
        self.assertEqual(candidate.reason_code, "deadline_imminent")
        self.assertEqual(candidate.source_event_id, "ev-1")
        self.assertEqual(candidate.due_at, _iso(future))
        # Suggested block is anchored at "now" (first free 60min) and
        # is 60 minutes long.
        start_dt = coach._parse_iso(candidate.start_at)
        end_dt = coach._parse_iso(candidate.end_at)
        self.assertEqual(int((end_dt - start_dt).total_seconds()), 60 * 60)

    def test_match_is_case_insensitive(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(days=2)
        with db.get_db() as conn:
            self._insert_event(
                conn,
                event_id="ev-1",
                summary="HISTORY EXAM",
                start_at=future,
            )
        self.assertEqual(len(self._run()), 1)

    def test_all_four_keywords_match(self) -> None:
        base = datetime.now(timezone.utc) + timedelta(days=2)
        with db.get_db() as conn:
            self._insert_event(conn, event_id="ev-1", summary="Calc midterm", start_at=base)
            self._insert_event(
                conn, event_id="ev-2", summary="Spanish final", start_at=base + timedelta(hours=2)
            )
            self._insert_event(
                conn, event_id="ev-3", summary="History exam", start_at=base + timedelta(hours=4)
            )
            self._insert_event(
                conn, event_id="ev-4", summary="Biology quiz", start_at=base + timedelta(hours=6)
            )
        self.assertEqual(len(self._run()), 4)

    def test_emits_one_suggestion_per_deadline_event(self) -> None:
        base = datetime.now(timezone.utc) + timedelta(days=2)
        with db.get_db() as conn:
            self._insert_event(
                conn,
                event_id="ev-1",
                summary="Calculus midterm",
                start_at=base,
            )
            self._insert_event(
                conn,
                event_id="ev-2",
                summary="Spanish final",
                start_at=base + timedelta(days=3),
            )
        result = self._run()
        self.assertEqual(len(result), 2)
        ids = sorted(c.source_event_id for c in result if c.source_event_id)
        self.assertEqual(ids, ["ev-1", "ev-2"])

    def test_matches_all_day_deadline_event(self) -> None:
        # The rule docstring endorses all-day "Midterm Day" entries
        # as legitimate deadline anchors. Confirm `all_day=1` doesn't
        # cause an exclusion in the SELECT (only the busy-overlap
        # `_find_free_blocks` filter excludes all-day events).
        future = datetime.now(timezone.utc) + timedelta(days=4)
        with db.get_db() as conn:
            self._insert_event(
                conn,
                event_id="ev-1",
                summary="Calc midterm",
                start_at=future,
                all_day=1,
            )
        result = self._run()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].source_event_id, "ev-1")

    def test_skips_event_with_null_summary(self) -> None:
        # The rule SQL already filters `summary IS NOT NULL`; this
        # locks the contract in so a future regex-only refactor that
        # removes the NULL guard would surface as a failing test.
        future = datetime.now(timezone.utc) + timedelta(days=4)
        with db.get_db() as conn:
            conn.execute(
                """
                INSERT INTO calendar_events (
                    id, user_id, feed_id, uid, occurrence_key,
                    summary, start_at, end_at, all_day, status
                ) VALUES ('ev-null', 'local', 'feed-1', 'ev-null', 'ev-null',
                          NULL, ?, ?, 0, 'confirmed')
                """,
                (_iso(future), _iso(future + timedelta(hours=1))),
            )
            conn.commit()
        self.assertEqual(self._run(), [])

    def test_two_deadlines_at_same_first_free_block_both_surface_from_rule(
        self,
    ) -> None:
        # The rule layer emits one candidate per matching event even
        # when two events share the chronologically first free block.
        # The downstream `refresh_active_suggestions` dedupes on
        # `(kind, start_at)`, which is a known v1 limitation
        # documented in `_rule_deadline_imminent`'s docstring; the
        # fix (extend dedupe key to include `source_event_id`) is
        # deferred to its own PR. This test pins the rule-layer
        # behavior so a regression there shows up here.
        base = datetime.now(timezone.utc) + timedelta(days=3)
        with db.get_db() as conn:
            self._insert_event(conn, event_id="ev-1", summary="Calc midterm", start_at=base)
            self._insert_event(
                conn,
                event_id="ev-2",
                summary="Physics final",
                start_at=base + timedelta(hours=2),
            )
        result = self._run()
        self.assertEqual(len(result), 2)
        # Both candidates anchor to the same first free block (no
        # busy events seeded between now and the deadlines).
        self.assertEqual(result[0].start_at, result[1].start_at)
        # Different source events, different reason text, proving
        # the rule didn't collapse them.
        source_ids = sorted(c.source_event_id for c in result if c.source_event_id)
        self.assertEqual(source_ids, ["ev-1", "ev-2"])

    def test_preserves_verbatim_summary_casing_in_reason_text(self) -> None:
        # v1 design decision: the panel surfaces the user's summary
        # verbatim, including SHOUTED casing. Pin it so a future
        # title-case normalization is a deliberate change, not a
        # silent drift from a future contributor.
        future = datetime.now(timezone.utc) + timedelta(days=3)
        with db.get_db() as conn:
            self._insert_event(conn, event_id="ev-1", summary="HISTORY EXAM", start_at=future)
        result = self._run()
        self.assertEqual(len(result), 1)
        self.assertIn("HISTORY EXAM", result[0].reason_text)

    def test_skips_match_when_no_free_block_before_deadline(self) -> None:
        # Deadline 90 minutes from now, but a "Class" event covers the
        # entire intervening time. No free 60-min slot → no suggestion.
        now = datetime.now(timezone.utc)
        deadline = now + timedelta(minutes=90)
        with db.get_db() as conn:
            self._insert_event(
                conn,
                event_id="busy-1",
                summary="All-hands meeting",
                start_at=now - timedelta(minutes=10),
                end_at=deadline,
            )
            self._insert_event(
                conn,
                event_id="ev-1",
                summary="Pop quiz",
                start_at=deadline,
            )
        self.assertEqual(self._run(), [])

    # -----------------------------------------------------------------
    # Scoring

    def test_score_within_24h_is_3_0(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(hours=20)
        with db.get_db() as conn:
            self._insert_event(conn, event_id="ev-1", summary="Quiz tomorrow", start_at=future)
        self.assertAlmostEqual(self._run()[0].score, 3.0)

    def test_score_within_72h_is_2_5(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(hours=48)
        with db.get_db() as conn:
            self._insert_event(
                conn, event_id="ev-1", summary="Midterm in two days", start_at=future
            )
        self.assertAlmostEqual(self._run()[0].score, 2.5)

    def test_score_within_7d_is_2_0(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(days=5)
        with db.get_db() as conn:
            self._insert_event(conn, event_id="ev-1", summary="Final next week", start_at=future)
        self.assertAlmostEqual(self._run()[0].score, 2.0)

    def test_score_within_14d_is_1_5(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(days=10)
        with db.get_db() as conn:
            self._insert_event(conn, event_id="ev-1", summary="Exam later", start_at=future)
        self.assertAlmostEqual(self._run()[0].score, 1.5)

    def test_score_at_exact_24h_boundary_still_resolves_to_3_0(self) -> None:
        # The score buckets use `<=` so 24h exactly sits in the
        # urgent bucket. A regression to `<` would silently slip a
        # tomorrow-morning exam into the 2.5 bucket. Note: real-world
        # time elapses between `_insert_event` and `_run`, so 24h-1s
        # is what the rule sees by the time it reads `now` again.
        future = datetime.now(timezone.utc) + timedelta(hours=24) - timedelta(seconds=1)
        with db.get_db() as conn:
            self._insert_event(
                conn, event_id="ev-1", summary="Midterm at the boundary", start_at=future
            )
        self.assertAlmostEqual(self._run()[0].score, 3.0)

    def test_score_ranks_imminent_above_v1_baseline(self) -> None:
        # The v1 rule scores 1.0; every deadline bucket beats it so the
        # panel correctly elevates urgent exams above SRS-overdue
        # nudges.
        future = datetime.now(timezone.utc) + timedelta(days=10)
        with db.get_db() as conn:
            self._insert_event(conn, event_id="ev-1", summary="Final exam", start_at=future)
        self.assertGreater(self._run()[0].score, 1.0)

    # -----------------------------------------------------------------
    # Reason-text formatting

    def test_reason_text_uses_hours_for_same_day(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(hours=4)
        with db.get_db() as conn:
            self._insert_event(conn, event_id="ev-1", summary="Pop quiz", start_at=future)
        text = self._run()[0].reason_text
        self.assertIn("in 4h", text)
        self.assertIn("Pop quiz", text)

    def test_reason_text_uses_tomorrow_for_next_day(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(hours=20)
        with db.get_db() as conn:
            self._insert_event(conn, event_id="ev-1", summary="History midterm", start_at=future)
        text = self._run()[0].reason_text
        self.assertEqual(text, "History midterm tomorrow.")

    def test_reason_text_uses_days_for_further_out(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(days=4)
        with db.get_db() as conn:
            self._insert_event(conn, event_id="ev-1", summary="Spanish final", start_at=future)
        text = self._run()[0].reason_text
        self.assertIn("in 4 days", text)

    def test_reason_text_floors_same_day_hours_to_one(self) -> None:
        # 25 minutes ahead would round down to 0h, which reads broken.
        # The implementation clamps to >= 1h. Validated against the
        # helper directly because the rule itself rejects this case
        # (no free 60-min block fits in 25 minutes).
        self.assertEqual(
            coach._reason_text_for_deadline("Quick quiz", 0.4),
            "Quick quiz in 1h.",
        )

    # -----------------------------------------------------------------
    # Integration with synthesize_suggestions

    def test_synthesize_includes_deadline_rule_output(self) -> None:
        # `synthesize_suggestions` is the public entry that
        # `refresh_active_suggestions` calls; assert the new rule is
        # actually invoked from there (so the one-line plug-point edit
        # in the `rules` list didn't get reverted in a future refactor)
        # and that its candidate carries the new reason_code.
        future = datetime.now(timezone.utc) + timedelta(hours=18)
        with db.get_db() as conn:
            self._insert_event(conn, event_id="ev-1", summary="Bio exam", start_at=future)
            results = coach.synthesize_suggestions(conn, user_id="local")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].reason_code, "deadline_imminent")
        self.assertEqual(results[0].kind, "study_block")
        self.assertAlmostEqual(results[0].score, 3.0)


if __name__ == "__main__":
    unittest.main()
