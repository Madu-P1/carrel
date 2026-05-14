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


if __name__ == "__main__":
    unittest.main()
