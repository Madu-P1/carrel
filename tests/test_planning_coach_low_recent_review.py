"""Unit tests for `services.planning.coach._rule_low_recent_review`.

Phase 2 rule. Emits one `review_block` suggestion when at least
`MIN_STALE_CARDS` cards have `last_review < now - REVIEW_STALE_DAYS`
AND are not currently overdue. The partition with the v1
`free_block_overdue_srs` rule is intentional; this rule covers the
"abandoned but not overdue" population.
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


class LowRecentReviewRuleTests(unittest.TestCase):
    """Each test gets a fresh in-tempdir SQLite DB. Cards are inserted
    via direct SQL so the rule can be exercised without going through
    `services.review_scheduler`.
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

    def _insert_card(
        self,
        conn: sqlite3.Connection,
        *,
        card_id: str,
        last_review: datetime | None,
        due_date: str | None,
        front: str = "front",
        back: str = "back",
    ) -> None:
        """Mirrors the writes from `services.review_scheduler`.

        `last_review` is stored as `isoformat()` with `+00:00` suffix.
        `due_date` is a YYYY-MM-DD date string.
        """
        last_review_str = last_review.isoformat() if last_review is not None else None
        conn.execute(
            """
            INSERT INTO srs_cards (id, front, back, last_review, due_date, state, reps)
            VALUES (?, ?, ?, ?, ?, 'review', 1)
            """,
            (card_id, front, back, last_review_str, due_date),
        )
        conn.commit()

    def _run(self) -> list[coach.CandidateSuggestion]:
        with db.get_db() as conn:
            return coach._rule_low_recent_review(conn, user_id="local")

    def _seed_stale_cards(
        self, conn: sqlite3.Connection, *, count: int, last_review_days_ago: int = 10
    ) -> None:
        """Insert N stale-but-not-overdue cards. Defaults: reviewed 10
        days ago (past the 7-day threshold) and due 30 days from now.
        """
        last_review = datetime.now(timezone.utc) - timedelta(days=last_review_days_ago)
        future_due = (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat()
        for i in range(count):
            self._insert_card(
                conn,
                card_id=f"stale-{i}",
                last_review=last_review,
                due_date=future_due,
            )

    # -----------------------------------------------------------------
    # No-match cases

    def test_returns_empty_when_no_cards(self) -> None:
        self.assertEqual(self._run(), [])

    def test_returns_empty_when_no_cards_are_stale(self) -> None:
        with db.get_db() as conn:
            recent = datetime.now(timezone.utc) - timedelta(days=2)
            future_due = (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat()
            for i in range(10):
                self._insert_card(
                    conn,
                    card_id=f"fresh-{i}",
                    last_review=recent,
                    due_date=future_due,
                )
        self.assertEqual(self._run(), [])

    def test_excludes_overdue_cards_from_stale_count(self) -> None:
        # Cards reviewed 30 days ago but overdue (due_date in the
        # past) belong to the v1 free_block_overdue_srs rule's
        # domain. This rule's filter must exclude them so the two
        # rules don't double-fire on the same population.
        with db.get_db() as conn:
            old_review = datetime.now(timezone.utc) - timedelta(days=30)
            past_due = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
            for i in range(10):
                self._insert_card(
                    conn,
                    card_id=f"overdue-{i}",
                    last_review=old_review,
                    due_date=past_due,
                )
        self.assertEqual(self._run(), [])

    def test_excludes_never_reviewed_cards_from_stale_count(self) -> None:
        # Cards with `last_review IS NULL` are new and have never
        # been touched. The v1 rule handles them via `due_date IS
        # NULL`; this rule's `last_review IS NOT NULL` guard skips
        # them.
        with db.get_db() as conn:
            future_due = (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat()
            for i in range(10):
                self._insert_card(
                    conn,
                    card_id=f"new-{i}",
                    last_review=None,
                    due_date=future_due,
                )
        self.assertEqual(self._run(), [])

    def test_below_min_stale_threshold_is_quiet(self) -> None:
        # MIN_STALE_CARDS is 5. Seed 4 stale cards: rule stays quiet
        # to avoid a chatty panel for users with only a handful of
        # cards.
        with db.get_db() as conn:
            self._seed_stale_cards(conn, count=4)
        self.assertEqual(self._run(), [])

    def test_returns_empty_when_no_free_block_in_24h(self) -> None:
        # Even with plenty of stale cards, skip the suggestion when
        # the calendar has no free 60-min window in the lookahead.
        with db.get_db() as conn:
            self._seed_stale_cards(conn, count=10)
            # Seed a calendar feed + a giant busy event spanning the
            # entire next 24h.
            conn.execute(
                """
                INSERT INTO calendar_feeds (id, user_id, label, url, url_hash)
                VALUES ('feed-1', 'local', 'Test', 'https://x.test', 'h1')
                """
            )
            now = datetime.now(timezone.utc)
            in_24h = now + timedelta(hours=25)
            conn.execute(
                """
                INSERT INTO calendar_events (
                    id, user_id, feed_id, uid, occurrence_key,
                    summary, start_at, end_at, all_day, status
                ) VALUES ('busy-1', 'local', 'feed-1', 'busy-1', 'busy-1',
                          'All-day workshop', ?, ?, 0, 'confirmed')
                """,
                (
                    now.isoformat().replace("+00:00", "Z"),
                    in_24h.isoformat().replace("+00:00", "Z"),
                ),
            )
            conn.commit()
        self.assertEqual(self._run(), [])

    # -----------------------------------------------------------------
    # Match cases

    def test_emits_one_review_block_at_first_free_slot(self) -> None:
        with db.get_db() as conn:
            self._seed_stale_cards(conn, count=8)
        result = self._run()
        self.assertEqual(len(result), 1)
        candidate = result[0]
        self.assertEqual(candidate.kind, "review_block")
        self.assertEqual(candidate.reason_code, "low_recent_review")
        # 60-min block.
        start_dt = coach._parse_iso(candidate.start_at)
        end_dt = coach._parse_iso(candidate.end_at)
        self.assertEqual(int((end_dt - start_dt).total_seconds()), 60 * 60)

    def test_at_exact_min_stale_threshold_emits_suggestion(self) -> None:
        # MIN_STALE_CARDS is 5; comparison is `< MIN_STALE_CARDS`.
        # Exactly 5 should fire.
        with db.get_db() as conn:
            self._seed_stale_cards(conn, count=coach.MIN_STALE_CARDS)
        self.assertEqual(len(self._run()), 1)

    def test_reason_text_includes_stale_count(self) -> None:
        with db.get_db() as conn:
            self._seed_stale_cards(conn, count=7)
        text = self._run()[0].reason_text
        self.assertIn("7 cards", text)
        self.assertIn(f"{coach.REVIEW_STALE_DAYS}+ days", text)

    def test_score_is_1_5_above_v1_baseline_and_at_deadline_floor(self) -> None:
        with db.get_db() as conn:
            self._seed_stale_cards(conn, count=10)
        score = self._run()[0].score
        self.assertAlmostEqual(score, 1.5)
        self.assertGreater(score, 1.0)  # above v1 free_block_overdue_srs

    def test_staleness_cutoff_is_inclusive_of_exactly_REVIEW_STALE_DAYS_ago(
        self,
    ) -> None:
        # A card reviewed exactly REVIEW_STALE_DAYS - 1 day ago is
        # NOT stale (< 7 days threshold), so 5 such cards should NOT
        # trigger.
        with db.get_db() as conn:
            recent = datetime.now(timezone.utc) - timedelta(days=coach.REVIEW_STALE_DAYS - 1)
            future_due = (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat()
            for i in range(coach.MIN_STALE_CARDS):
                self._insert_card(
                    conn,
                    card_id=f"borderline-{i}",
                    last_review=recent,
                    due_date=future_due,
                )
        self.assertEqual(self._run(), [])

    def test_does_not_double_fire_with_v1_overdue_rule(self) -> None:
        # When the user has BOTH overdue cards (v1 territory) AND
        # stale-not-overdue cards (this rule's territory),
        # synthesize_suggestions emits one candidate per rule with
        # distinct reason_codes. Verifies the partition holds end to
        # end via the public entry point.
        with db.get_db() as conn:
            # 6 overdue cards (v1 fires).
            old_review = datetime.now(timezone.utc) - timedelta(days=30)
            past_due = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
            for i in range(6):
                self._insert_card(
                    conn,
                    card_id=f"overdue-{i}",
                    last_review=old_review,
                    due_date=past_due,
                )
            # 6 stale-but-not-overdue cards (this rule fires).
            self._seed_stale_cards(conn, count=6)
            results = coach.synthesize_suggestions(conn, user_id="local")

        codes = {c.reason_code for c in results}
        self.assertIn("free_block_overdue_srs", codes)
        self.assertIn("low_recent_review", codes)

    # -----------------------------------------------------------------
    # Synthesize integration

    def test_synthesize_includes_low_recent_review_when_only_stale_cards(
        self,
    ) -> None:
        with db.get_db() as conn:
            self._seed_stale_cards(conn, count=8)
            results = coach.synthesize_suggestions(conn, user_id="local")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].reason_code, "low_recent_review")

    def test_excludes_cards_due_today_at_the_boundary(self) -> None:
        # SQLite TEXT comparison: `'2026-05-16' > '2026-05-16'` is
        # FALSE, so cards whose due_date equals today fall to the
        # v1 overdue rule's domain (which uses `due_date <= today`)
        # and not this one. Pins the boundary.
        with db.get_db() as conn:
            old_review = datetime.now(timezone.utc) - timedelta(days=30)
            today_iso = datetime.now(timezone.utc).date().isoformat()
            for i in range(coach.MIN_STALE_CARDS + 5):
                self._insert_card(
                    conn,
                    card_id=f"due-today-{i}",
                    last_review=old_review,
                    due_date=today_iso,
                )
        self.assertEqual(self._run(), [])

    def test_excludes_cards_with_null_due_date(self) -> None:
        # `due_date IS NULL` cards (never scheduled, e.g. new cards
        # the user hasn't seen yet) belong to v1's domain via its
        # `due_date IS NULL OR due_date <= today` clause. This
        # rule's `due_date IS NOT NULL` guard skips them.
        with db.get_db() as conn:
            old_review = datetime.now(timezone.utc) - timedelta(days=30)
            for i in range(coach.MIN_STALE_CARDS + 5):
                self._insert_card(
                    conn,
                    card_id=f"null-due-{i}",
                    last_review=old_review,
                    due_date=None,
                )
        self.assertEqual(self._run(), [])

    def test_emitted_start_at_is_inside_the_24h_lookahead_window(self) -> None:
        # Sanity: the suggested block starts at or after `now` and
        # ends at or before `now + LOOKAHEAD_HOURS`. Catches a
        # regression where the rule accidentally lifted the
        # `_find_free_blocks` window to something longer (the
        # deadline_imminent rule uses a different window; this one
        # must stay on the 24h v1 horizon).
        with db.get_db() as conn:
            self._seed_stale_cards(conn, count=10)
        candidate = self._run()[0]
        now = datetime.now(timezone.utc)
        horizon = now + timedelta(hours=coach.LOOKAHEAD_HOURS)
        start_dt = coach._parse_iso(candidate.start_at)
        end_dt = coach._parse_iso(candidate.end_at)
        # 2s slack for the elapsed time between _run() and now()
        self.assertGreaterEqual(start_dt, now - timedelta(seconds=2))
        self.assertLessEqual(end_dt, horizon + timedelta(seconds=2))

    def test_refresh_persists_both_v1_and_low_recent_review_signals(self) -> None:
        # End-to-end: when BOTH rules fire (overdue cards + stale-
        # but-not-overdue cards), `refresh_active_suggestions`
        # persists both signals. Under the new triple-key dedupe
        # `(kind, start_at, reason_code)`, two distinct rule outputs
        # with the same `(kind, start_at)` and different reason_codes
        # do NOT collide on subsequent refreshes; the pair-key it
        # replaced would have silently swallowed whichever rule
        # landed second.
        with db.get_db() as conn:
            # 6 overdue cards (v1 territory)
            old_review = datetime.now(timezone.utc) - timedelta(days=30)
            past_due = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
            for i in range(6):
                self._insert_card(
                    conn,
                    card_id=f"overdue-{i}",
                    last_review=old_review,
                    due_date=past_due,
                )
            # 6 stale-not-overdue cards (this rule's territory)
            self._seed_stale_cards(conn, count=6)

            # First refresh inserts both signals.
            first = coach.refresh_active_suggestions(conn, user_id="local")
            # Second refresh exercises the dedupe path; both
            # existing rows must be recognized so neither rule
            # double-inserts and neither signal is silently dropped.
            second = coach.refresh_active_suggestions(conn, user_id="local")

        self.assertEqual(
            sorted(s.reason_code for s in first),
            ["free_block_overdue_srs", "low_recent_review"],
        )
        self.assertEqual(
            sorted(s.reason_code for s in second),
            ["free_block_overdue_srs", "low_recent_review"],
            "Both signals must survive the second refresh through the triple-key dedupe",
        )


if __name__ == "__main__":
    unittest.main()
