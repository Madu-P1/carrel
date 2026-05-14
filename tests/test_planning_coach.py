"""Tests for the study-coach rules in services.planning.coach.

Setup mirrors tests/test_db_migrations.py: temp directory, configure_paths,
apply migrations. Each test gets a fresh DB so rule outputs are
deterministic regardless of run order.

Phase 2 first holistic loop ('rebalance_on_miss') added in migration 0019.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import db
from services.planning import coach

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_SOURCE = REPO_ROOT / "migrations"


class _CoachTestCase(unittest.TestCase):
    """Shared fixture: temp DB with all migrations applied."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.original_paths = (
            db.BASE_DIR,
            db.DATA_DIR,
            db.UPLOAD_DIR,
            db.DB_PATH,
            db.SCHEMA_PATH,
        )
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
            base_dir=self.original_paths[0],
            data_dir=self.original_paths[1],
            upload_dir=self.original_paths[2],
            db_path=self.original_paths[3],
            schema_path=self.original_paths[4],
        )
        self.temp_dir.cleanup()

    def _seed_overdue_cards(self, conn, count: int) -> None:
        """Insert `count` SRS cards whose due_date is yesterday."""
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
        for _ in range(count):
            conn.execute(
                "INSERT INTO srs_cards (id, front, back, due_date) VALUES (?, ?, ?, ?)",
                (str(uuid.uuid4()), "front", "back", yesterday),
            )
        conn.commit()


class CoachRebalanceOnMissTests(_CoachTestCase):
    """Coach Phase 2 first holistic loop.

    Senses overdue SRS count past the catchup threshold, reasons about
    available 24h capacity, acts by surfacing a longer catchup block.
    Below the threshold, the routine free_block_overdue_srs rule handles
    things and rebalance stays quiet.
    """

    def test_emits_catchup_suggestion_when_overdue_exceeds_threshold(self) -> None:
        with db.get_db() as conn:
            self._seed_overdue_cards(conn, count=coach.CATCHUP_OVERDUE_THRESHOLD + 3)
            results = coach._rule_rebalance_on_miss(conn, user_id="local")
        self.assertEqual(len(results), 1)
        suggestion = results[0]
        self.assertEqual(suggestion.kind, "catchup")
        self.assertEqual(suggestion.reason_code, "rebalance_on_miss")
        self.assertGreater(suggestion.score, 1.0)
        self.assertIn("cards overdue", suggestion.reason_text)

    def test_no_suggestion_at_or_below_threshold(self) -> None:
        with db.get_db() as conn:
            self._seed_overdue_cards(conn, count=coach.CATCHUP_OVERDUE_THRESHOLD)
            results = coach._rule_rebalance_on_miss(conn, user_id="local")
        self.assertEqual(results, [])

    def test_no_suggestion_when_no_overdue_cards(self) -> None:
        with db.get_db() as conn:
            results = coach._rule_rebalance_on_miss(conn, user_id="local")
        self.assertEqual(results, [])

    def test_rebalance_outranks_routine_rule_when_both_fire(self) -> None:
        """synthesize_suggestions sorts by score desc; rebalance must lead."""
        with db.get_db() as conn:
            self._seed_overdue_cards(conn, count=coach.CATCHUP_OVERDUE_THRESHOLD + 3)
            candidates = coach.synthesize_suggestions(conn, user_id="local")
        codes = [c.reason_code for c in candidates]
        self.assertIn("rebalance_on_miss", codes)
        self.assertIn("free_block_overdue_srs", codes)
        self.assertEqual(candidates[0].reason_code, "rebalance_on_miss")

    def test_score_scales_with_backlog_up_to_cap(self) -> None:
        """Bigger backlog ranks higher than smaller backlog, capped at BASE + 1.0."""
        with db.get_db() as conn:
            self._seed_overdue_cards(conn, count=coach.CATCHUP_OVERDUE_THRESHOLD + 1)
            small = coach._rule_rebalance_on_miss(conn, user_id="local")
            self._seed_overdue_cards(conn, count=20)
            big = coach._rule_rebalance_on_miss(conn, user_id="local")
        self.assertGreater(big[0].score, small[0].score)
        self.assertLessEqual(big[0].score, coach.REBALANCE_BASE_SCORE + 1.0)


class CoachStressAwareDurationTests(_CoachTestCase):
    """Coach Phase 2.B rule.

    Senses recent high stress from session_check_ins; reasons that the
    routine 60-min block is the wrong mode; acts by surfacing a 25-min
    Pomodoro. Below-threshold stress or no recent check-in lets the
    routine rule fire as before.
    """

    def _seed_check_in(self, stress: int, energy: int = 3) -> None:
        from services.calendar import repository

        with db.get_db() as conn:
            repository.insert_check_in(
                conn, stress_level=stress, energy_level=energy
            )

    def test_recent_high_stress_helper_no_check_ins(self) -> None:
        with db.get_db() as conn:
            self.assertFalse(coach._recent_high_stress(conn, user_id="local"))

    def test_recent_high_stress_helper_low_stress_false(self) -> None:
        self._seed_check_in(stress=2)
        with db.get_db() as conn:
            self.assertFalse(coach._recent_high_stress(conn, user_id="local"))

    def test_recent_high_stress_helper_high_stress_true(self) -> None:
        self._seed_check_in(stress=5)
        with db.get_db() as conn:
            self.assertTrue(coach._recent_high_stress(conn, user_id="local"))

    def test_recent_high_stress_helper_stale_signal_false(self) -> None:
        """Check-in older than STRESS_RECENT_HOURS doesn't trigger."""
        stale_iso = (
            datetime.now(timezone.utc)
            - timedelta(hours=coach.STRESS_RECENT_HOURS + 2)
        ).isoformat().replace("+00:00", "Z")
        with db.get_db() as conn:
            conn.execute(
                """
                INSERT INTO session_check_ins
                (id, user_id, stress_level, energy_level, created_at)
                VALUES (?, 'local', 5, 3, ?)
                """,
                ("stale-id", stale_iso),
            )
            conn.commit()
            self.assertFalse(coach._recent_high_stress(conn, user_id="local"))

    def test_rule_emits_pomodoro_when_high_stress_and_overdue(self) -> None:
        self._seed_check_in(stress=4)
        with db.get_db() as conn:
            self._seed_overdue_cards(conn, count=3)
            results = coach._rule_stress_aware_duration(conn, user_id="local")
        self.assertEqual(len(results), 1)
        suggestion = results[0]
        self.assertEqual(suggestion.kind, "review_block")
        self.assertEqual(suggestion.reason_code, "stress_aware_duration")
        self.assertAlmostEqual(suggestion.score, coach.STRESS_AWARE_SCORE)

    def test_rule_skips_when_no_high_stress(self) -> None:
        with db.get_db() as conn:
            self._seed_overdue_cards(conn, count=3)
            results = coach._rule_stress_aware_duration(conn, user_id="local")
        self.assertEqual(results, [])

    def test_rule_skips_when_high_stress_but_no_overdue(self) -> None:
        self._seed_check_in(stress=5)
        with db.get_db() as conn:
            results = coach._rule_stress_aware_duration(conn, user_id="local")
        self.assertEqual(results, [])

    def test_routine_rule_defers_when_high_stress_recent(self) -> None:
        """_rule_free_block_overdue_srs skips when stress_aware will fire."""
        self._seed_check_in(stress=5)
        with db.get_db() as conn:
            self._seed_overdue_cards(conn, count=3)
            routine_results = coach._rule_free_block_overdue_srs(
                conn, user_id="local"
            )
            stress_results = coach._rule_stress_aware_duration(
                conn, user_id="local"
            )
        self.assertEqual(routine_results, [])
        self.assertEqual(len(stress_results), 1)

    def test_synthesize_returns_stress_aware_not_routine(self) -> None:
        """End-to-end: high stress flips the routine block to a Pomodoro."""
        self._seed_check_in(stress=5)
        with db.get_db() as conn:
            self._seed_overdue_cards(conn, count=3)
            candidates = coach.synthesize_suggestions(conn, user_id="local")
        codes = [c.reason_code for c in candidates]
        self.assertIn("stress_aware_duration", codes)
        self.assertNotIn("free_block_overdue_srs", codes)


class CoachRebalanceMigrationTests(_CoachTestCase):
    """Pin the reason_code CHECK constraint accepts 'rebalance_on_miss'.

    Catches the case where migration 0019 silently failed to run, so a
    fresh DB still has the four-code enum and inserts via the repository
    would error at write time rather than at synthesize time.
    """

    def test_reason_code_check_accepts_rebalance(self) -> None:
        from services.calendar import repository

        with db.get_db() as conn:
            now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            soon_iso = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
            sug_id = repository.insert_suggestion(
                conn,
                kind="catchup",
                start_at=now_iso,
                end_at=soon_iso,
                reason_code="rebalance_on_miss",
                reason_text="Test insert.",
                score=2.5,
            )
            row = conn.execute(
                "SELECT reason_code FROM study_suggestions WHERE id = ?", (sug_id,)
            ).fetchone()
        self.assertEqual(row["reason_code"], "rebalance_on_miss")


class CoachScoreNormalizationTests(unittest.TestCase):
    """Pin the score-normalization contract for the API layer.

    Rules emit raw scores in arbitrary positive ranges so multi-rule
    pipelines can rank candidates against each other (free_block uses
    1.0, rebalance uses 2.5+). The API contract clamps score to [0, 1]
    via the Pydantic Field on StudySuggestionRow. routes/plan.py
    normalizes raw scores against the batch max before serializing so
    Pydantic doesn't reject the response. Ranking is preserved.

    No DB setup needed: these tests call the normalization function
    directly against synthetic SuggestionRow instances.
    """

    def _row(self, **overrides):
        from services.calendar import repository as cal_repo

        defaults = dict(
            id="suggestion-id",
            user_id="local",
            kind="review_block",
            status="pending",
            start_at="2026-05-14T10:00:00Z",
            end_at="2026-05-14T11:00:00Z",
            due_at=None,
            doc_id=None,
            source_event_id=None,
            reason_code="free_block_overdue_srs",
            reason_text="routine.",
            score=1.0,
            accepted_at=None,
            dismissed_at=None,
            created_at="2026-05-14T00:00:00Z",
        )
        defaults.update(overrides)
        return cal_repo.SuggestionRow(**defaults)

    def test_normalizes_against_batch_max(self) -> None:
        from routes.plan import _suggestions_to_response

        rows = [
            self._row(id="a", reason_code="free_block_overdue_srs", score=1.0),
            self._row(
                id="b",
                kind="catchup",
                reason_code="rebalance_on_miss",
                reason_text="catchup.",
                score=2.5,
            ),
        ]
        result = _suggestions_to_response(rows)
        scores = {r.reason_code: r.score for r in result}
        # Max raw score (2.5) becomes 1.0; the 1.0 raw becomes 0.4.
        self.assertAlmostEqual(scores["rebalance_on_miss"], 1.0)
        self.assertAlmostEqual(scores["free_block_overdue_srs"], 0.4)

    def test_handles_empty_input(self) -> None:
        from routes.plan import _suggestions_to_response

        self.assertEqual(_suggestions_to_response([]), [])

    def test_passes_through_none_scores(self) -> None:
        from routes.plan import _suggestions_to_response

        result = _suggestions_to_response([self._row(score=None)])
        self.assertIsNone(result[0].score)

    def test_rebalance_reason_code_serializes(self) -> None:
        """Pydantic Literal must include rebalance_on_miss or this errors."""
        from routes.plan import _suggestions_to_response

        result = _suggestions_to_response(
            [
                self._row(
                    kind="catchup",
                    reason_code="rebalance_on_miss",
                    reason_text="catchup.",
                    score=2.5,
                )
            ]
        )
        self.assertEqual(result[0].reason_code, "rebalance_on_miss")


class CoachDeadlineImminentTests(_CoachTestCase):
    """Cherry-picked Phase 1 deadline_imminent rule.

    Senses calendar events whose summary matches DEADLINE_KEYWORDS
    via services.planning.deadlines, reasons about prep time before
    each, acts by surfacing a 60-min study_block at the soonest free
    slot. Low-severity (>7 days out) deadlines are suppressed.
    """

    def _seed_deadline_event(
        self,
        conn,
        *,
        summary: str,
        days_from_now: float,
        event_id: str = "test-deadline-event",
        feed_id: str = "test-deadline-feed",
    ) -> None:
        """Seed a calendar feed + a deadline-keyword event in the window."""
        deadline_dt = (
            datetime.now(timezone.utc) + timedelta(days=days_from_now)
        ).replace(microsecond=0)
        # Idempotent feed insert.
        existing = conn.execute(
            "SELECT 1 FROM calendar_feeds WHERE id = ?", (feed_id,)
        ).fetchone()
        if not existing:
            conn.execute(
                """
                INSERT INTO calendar_feeds (
                    id, user_id, label, url, url_hash,
                    is_enabled, consecutive_failures
                ) VALUES (?, 'local', ?, ?, ?, 1, 0)
                """,
                (
                    feed_id,
                    f"Feed {feed_id}",
                    f"http://test/{feed_id}",
                    f"hash-{feed_id}",
                ),
            )
        end_dt = deadline_dt + timedelta(hours=1)
        conn.execute(
            """
            INSERT INTO calendar_events (
                id, user_id, feed_id, uid, occurrence_key, summary,
                start_at, end_at, all_day, status
            ) VALUES (?, 'local', ?, ?, ?, ?, ?, ?, 0, 'confirmed')
            """,
            (
                event_id,
                feed_id,
                f"uid-{event_id}",
                f"occ-{event_id}",
                summary,
                deadline_dt.isoformat().replace("+00:00", "Z"),
                end_dt.isoformat().replace("+00:00", "Z"),
            ),
        )
        conn.commit()

    def test_emits_study_block_for_high_severity_deadline(self) -> None:
        with db.get_db() as conn:
            self._seed_deadline_event(
                conn, summary="Bio midterm", days_from_now=2,
            )
            results = coach._rule_deadline_imminent(conn, user_id="local")
        self.assertEqual(len(results), 1)
        suggestion = results[0]
        self.assertEqual(suggestion.kind, "study_block")
        self.assertEqual(suggestion.reason_code, "deadline_imminent")
        self.assertIn("Bio midterm", suggestion.reason_text)
        self.assertGreaterEqual(suggestion.score, coach.DEADLINE_SCORE_HIGH_BASE)
        self.assertEqual(suggestion.source_event_id, "test-deadline-event")

    def test_skips_low_severity_deadline_beyond_seven_days(self) -> None:
        with db.get_db() as conn:
            self._seed_deadline_event(
                conn, summary="Final exam", days_from_now=14,
            )
            results = coach._rule_deadline_imminent(conn, user_id="local")
        self.assertEqual(results, [])

    def test_normal_severity_uses_flat_normal_score(self) -> None:
        with db.get_db() as conn:
            self._seed_deadline_event(
                conn, summary="Calc test", days_from_now=5,
            )
            results = coach._rule_deadline_imminent(conn, user_id="local")
        self.assertEqual(len(results), 1)
        self.assertAlmostEqual(results[0].score, coach.DEADLINE_SCORE_NORMAL)

    def test_caps_at_max_deadline_suggestions(self) -> None:
        """Many imminent deadlines stack inside one week; cap protects UX."""
        with db.get_db() as conn:
            for i in range(coach.MAX_DEADLINE_SUGGESTIONS + 2):
                self._seed_deadline_event(
                    conn,
                    summary=f"Exam {i}",
                    days_from_now=1 + i * 0.05,
                    event_id=f"deadline-event-{i}",
                )
            results = coach._rule_deadline_imminent(conn, user_id="local")
        self.assertEqual(len(results), coach.MAX_DEADLINE_SUGGESTIONS)

    def test_emits_nothing_when_no_deadline_events(self) -> None:
        with db.get_db() as conn:
            results = coach._rule_deadline_imminent(conn, user_id="local")
        self.assertEqual(results, [])

    def test_format_relative_days_phrasing(self) -> None:
        self.assertEqual(coach._format_relative_days(0), "today")
        self.assertEqual(coach._format_relative_days(0.4), "today")
        self.assertEqual(coach._format_relative_days(1), "tomorrow")
        self.assertEqual(coach._format_relative_days(1.4), "tomorrow")
        self.assertEqual(coach._format_relative_days(5), "in 5 days")
        self.assertEqual(coach._format_relative_days(10.3), "in 10 days")


class CoachApiE2ETests(unittest.TestCase):
    """End-to-end verification of rebalance_on_miss through GET /api/plan.

    Exercises the full chain: route handler -> coach.refresh_active_suggestions
    -> rule fires -> repository.insert_suggestion -> repository.list_active
    -> _suggestions_to_response (score normalization) -> Pydantic response
    serialization. This is the chain that would explode at deploy time if
    the Pydantic Literal or the score Field bounds were misaligned with
    the new rule's outputs.

    Setup mirrors tests/test_calendar_local_sync.py: monkey-patch main
    module paths to a temp dir, call main.initialize_database, hand the
    TestClient the local API token.
    """

    def setUp(self) -> None:
        from fastapi.testclient import TestClient

        import main
        from services.calendar.secrets import set_default_secret_store_for_testing
        from services.local_api_security import HEADER_NAME, get_local_api_token

        # Mute keychain access; calendar feeds aren't part of this test
        # but the lookup runs as a side effect of repository.list_feeds.
        class _FakeStore:
            def __init__(self):
                self.values: dict[str, str] = {}

            def store_url(self, feed_id: str, raw_url: str) -> str:
                ref = f"fake:{feed_id}"
                self.values[ref] = raw_url
                return ref

            def get_url(self, reference: str):
                return self.values.get(reference)

            def delete_url(self, reference: str) -> None:
                self.values.pop(reference, None)

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

        self.main = main
        self.HEADER_NAME = HEADER_NAME
        self.client = TestClient(main.app, headers={HEADER_NAME: get_local_api_token()})

    def tearDown(self) -> None:
        from services.calendar.secrets import set_default_secret_store_for_testing

        set_default_secret_store_for_testing(None)
        for k, v in self.originals.items():
            setattr(self.main, k, v)
        self.temp_dir.cleanup()

    def _seed_overdue_cards(self, count: int) -> None:
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
        with db.get_db() as conn:
            for _ in range(count):
                conn.execute(
                    "INSERT INTO srs_cards (id, front, back, due_date) VALUES (?, ?, ?, ?)",
                    (str(uuid.uuid4()), "front", "back", yesterday),
                )
            conn.commit()

    def test_rebalance_appears_in_plan_response_with_normalized_score(self) -> None:
        self._seed_overdue_cards(coach.CATCHUP_OVERDUE_THRESHOLD + 3)

        response = self.client.get("/api/plan")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()

        codes = [s["reason_code"] for s in body["suggestions"]]
        self.assertIn(
            "rebalance_on_miss", codes, f"expected rebalance suggestion, got: {codes}"
        )

        rebalance = next(
            s for s in body["suggestions"] if s["reason_code"] == "rebalance_on_miss"
        )
        self.assertEqual(rebalance["kind"], "catchup")
        self.assertIsNotNone(rebalance["score"])
        # Score is normalized against batch max. Rebalance carries the
        # highest raw score in the batch, so it lands at 1.0.
        self.assertGreaterEqual(rebalance["score"], 0.0)
        self.assertLessEqual(rebalance["score"], 1.0)
        self.assertAlmostEqual(rebalance["score"], 1.0)

    def test_no_rebalance_below_threshold(self) -> None:
        self._seed_overdue_cards(coach.CATCHUP_OVERDUE_THRESHOLD)

        response = self.client.get("/api/plan")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()

        codes = [s["reason_code"] for s in body["suggestions"]]
        self.assertNotIn("rebalance_on_miss", codes)


if __name__ == "__main__":
    unittest.main()
