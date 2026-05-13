"""Tests for reverse-pair card support — PR 5.2 of flashcards-focus.

Pin the contract from ADR 0003:
1. Migration 0018 drops the kind CHECK on srs_cards and adds the
   card_pairs(card_a_id, card_b_id) join table.
2. The 12-step rebuild preserves all existing srs_cards rows and their
   columns; the idx_srs_cards_due_state index survives.
3. `services.study.create_card(kind='reverse')` is now allowed by the
   widened allowlist.
4. `services.study.create_card_pair` inserts two cards (qa + reverse,
   front/back swapped) plus one card_pairs row in a single transaction.
5. card_pairs invariants enforced by SQLite:
   - (A, A) violates CHECK (card_a_id < card_b_id)
   - (B, A) where A < B violates the same CHECK
   - (A, B) is the unique canonical ordering and is accepted
6. ON DELETE CASCADE on both card_pairs FKs collapses the pair when
   either card is deleted; the surviving card stays alive.
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
import uuid
from datetime import date, timedelta
from pathlib import Path

import main
from services.ingestion import ingest_document_record
from services.study import (
    bulk_delete_cards,
    create_card,
    create_card_pair,
    delete_card,
)

_SAMPLE_TEXT = "Anatomy: the femur is the longest bone in the human body."


def _insert_concept(conn: sqlite3.Connection, *, doc_id: str, name: str) -> str:
    concept_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO concepts (id, doc_id, name) VALUES (?, ?, ?)",
        (concept_id, doc_id, name),
    )
    return concept_id


class ReverseCardSchemaTests(unittest.TestCase):
    """Migration-level invariants of 0018."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        base = Path(self.temp_dir.name)
        self._restore = (
            main.BASE_DIR,
            main.DATA_DIR,
            main.UPLOAD_DIR,
            main.DB_PATH,
            main.SCHEMA_PATH,
        )
        main.BASE_DIR = base
        main.DATA_DIR = base / "data"
        main.UPLOAD_DIR = main.DATA_DIR / "uploads"
        main.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        main.DB_PATH = main.DATA_DIR / "test.db"
        main.SCHEMA_PATH = self._restore[4]
        main.initialize_database()

    def tearDown(self) -> None:
        (
            main.BASE_DIR,
            main.DATA_DIR,
            main.UPLOAD_DIR,
            main.DB_PATH,
            main.SCHEMA_PATH,
        ) = self._restore
        self.temp_dir.cleanup()

    def test_kind_check_dropped(self) -> None:
        """The CHECK on srs_cards.kind from 0017 is gone — a raw insert
        of kind='reverse' bypassing application validation must succeed
        at the SQL layer. (Application-level allowlist is tested
        separately.)"""
        with main.get_db() as conn:
            today = date.today().isoformat()
            card_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO srs_cards (
                    id, card_type, kind, front, back,
                    state, stability, difficulty,
                    elapsed_days, scheduled_days, reps, lapses,
                    due_date, confidence
                )
                VALUES (?, 'custom', 'reverse', 'q', 'a', 'new', 1.0, 0.3,
                        0, 0, 0, 0, ?, 1.0)
                """,
                (card_id, today),
            )
            conn.commit()
            row = conn.execute(
                "SELECT kind FROM srs_cards WHERE id = ?", (card_id,)
            ).fetchone()
        self.assertEqual(row["kind"], "reverse")

    def test_idx_srs_cards_due_state_survives_rebuild(self) -> None:
        """The rebuild in 0018 must recreate idx_srs_cards_due_state —
        without it every list_due_cards query would full-scan."""
        with main.get_db() as conn:
            indexes = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index'"
                ).fetchall()
            }
        self.assertIn("idx_srs_cards_due_state", indexes)
        self.assertIn("idx_card_pairs_b", indexes)

    def test_card_pairs_check_rejects_self_pair(self) -> None:
        with main.get_db() as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO card_pairs (card_a_id, card_b_id) VALUES (?, ?)",
                    ("same-id", "same-id"),
                )

    def test_card_pairs_check_rejects_reverse_ordering(self) -> None:
        """The canonical ordering is card_a_id < card_b_id. Inserting
        (B, A) where A < B violates the CHECK."""
        with main.get_db() as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO card_pairs (card_a_id, card_b_id) VALUES (?, ?)",
                    ("zzz", "aaa"),
                )

    def test_card_pairs_primary_key_rejects_duplicate(self) -> None:
        """The composite PRIMARY KEY blocks two rows for the same pair.
        We seed two srs_cards first so the FKs satisfy."""
        with main.get_db() as conn:
            today = date.today().isoformat()
            for cid in ("aaa", "bbb"):
                conn.execute(
                    """
                    INSERT INTO srs_cards (
                        id, card_type, kind, front, back, state,
                        stability, difficulty,
                        elapsed_days, scheduled_days, reps, lapses,
                        due_date, confidence
                    )
                    VALUES (?, 'custom', 'qa', 'q', 'a', 'new', 1.0, 0.3,
                            0, 0, 0, 0, ?, 1.0)
                    """,
                    (cid, today),
                )
            conn.execute(
                "INSERT INTO card_pairs (card_a_id, card_b_id) VALUES ('aaa', 'bbb')"
            )
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO card_pairs (card_a_id, card_b_id) VALUES ('aaa', 'bbb')"
                )

    def test_card_pairs_on_delete_cascade(self) -> None:
        """Deleting either card of the pair removes the card_pairs row;
        the surviving card stays alive.

        Note: the app does NOT currently enable PRAGMA foreign_keys=ON
        on every connection (see db.py::_apply_connection_pragmas).
        This test enables FK enforcement explicitly to pin the schema's
        design intent — the CASCADE will fire if/when the app opts into
        global FK enforcement. Tracked as a follow-up; the structural
        FK + CASCADE still document the relationship even without
        runtime enforcement.
        """
        with main.get_db() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            today = date.today().isoformat()
            for cid in ("aaa", "bbb"):
                conn.execute(
                    """
                    INSERT INTO srs_cards (
                        id, card_type, kind, front, back, state,
                        stability, difficulty,
                        elapsed_days, scheduled_days, reps, lapses,
                        due_date, confidence
                    )
                    VALUES (?, 'custom', 'qa', 'q', 'a', 'new', 1.0, 0.3,
                            0, 0, 0, 0, ?, 1.0)
                    """,
                    (cid, today),
                )
            conn.execute(
                "INSERT INTO card_pairs (card_a_id, card_b_id) VALUES ('aaa', 'bbb')"
            )
            conn.commit()

            conn.execute("DELETE FROM srs_cards WHERE id = 'aaa'")
            conn.commit()

            pair_rows = conn.execute(
                "SELECT card_a_id, card_b_id FROM card_pairs"
            ).fetchall()
            surviving = conn.execute(
                "SELECT id FROM srs_cards WHERE id = 'bbb'"
            ).fetchone()
        self.assertEqual(pair_rows, [])
        self.assertIsNotNone(surviving)


class ReverseCardServiceTests(unittest.TestCase):
    """services.study.create_card_pair and the widened kind allowlist."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        base = Path(self.temp_dir.name)
        self._restore = (
            main.BASE_DIR,
            main.DATA_DIR,
            main.UPLOAD_DIR,
            main.DB_PATH,
            main.SCHEMA_PATH,
        )
        main.BASE_DIR = base
        main.DATA_DIR = base / "data"
        main.UPLOAD_DIR = main.DATA_DIR / "uploads"
        main.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        main.DB_PATH = main.DATA_DIR / "test.db"
        main.SCHEMA_PATH = self._restore[4]
        main.initialize_database()
        with main.get_db() as conn:
            self.doc_id = ingest_document_record(
                conn=conn,
                filename="anatomy.txt",
                file_type="txt",
                extracted_text=_SAMPLE_TEXT,
                page_count=None,
                subject_name="Anatomy",
            )["doc_id"]
            self.concept_id = _insert_concept(
                conn, doc_id=self.doc_id, name="Femur"
            )
            conn.commit()

    def tearDown(self) -> None:
        (
            main.BASE_DIR,
            main.DATA_DIR,
            main.UPLOAD_DIR,
            main.DB_PATH,
            main.SCHEMA_PATH,
        ) = self._restore
        self.temp_dir.cleanup()

    def test_create_card_reverse_kind_accepted(self) -> None:
        """The application allowlist must include 'reverse' so the
        Pydantic + service guard pair stays consistent."""
        with main.get_db() as conn:
            card = create_card(
                conn,
                front="Femur",
                back="The thigh bone",
                concept_id=self.concept_id,
                kind="reverse",
            )
        self.assertEqual(card["kind"], "reverse")

    def test_create_card_rejects_unknown_kind(self) -> None:
        """The allowlist is now {qa, cloze, reverse}; anything else
        raises ValueError."""
        with main.get_db() as conn:
            with self.assertRaises(ValueError) as ctx:
                create_card(
                    conn,
                    front="Femur",
                    back="The thigh bone",
                    kind="image-occlusion",
                )
        self.assertIn("kind must be", str(ctx.exception))

    def test_create_card_pair_inserts_two_cards_and_one_pair(self) -> None:
        with main.get_db() as conn:
            result = create_card_pair(
                conn,
                front="Femur",
                back="The thigh bone",
                concept_id=self.concept_id,
            )
            count = conn.execute(
                "SELECT COUNT(*) AS n FROM srs_cards"
            ).fetchone()["n"]
            pair_count = conn.execute(
                "SELECT COUNT(*) AS n FROM card_pairs"
            ).fetchone()["n"]
            primary = conn.execute(
                "SELECT front, back, kind FROM srs_cards WHERE id = ?",
                (result["primary_id"],),
            ).fetchone()
            reverse = conn.execute(
                "SELECT front, back, kind FROM srs_cards WHERE id = ?",
                (result["reverse_id"],),
            ).fetchone()

        self.assertEqual(count, 2)
        self.assertEqual(pair_count, 1)
        self.assertEqual(primary["front"], "Femur")
        self.assertEqual(primary["back"], "The thigh bone")
        self.assertEqual(primary["kind"], "qa")
        self.assertEqual(reverse["front"], "The thigh bone")
        self.assertEqual(reverse["back"], "Femur")
        self.assertEqual(reverse["kind"], "reverse")

    def test_create_card_pair_canonical_ordering(self) -> None:
        """The card_pairs row must use the lexicographically smaller id
        as card_a_id to satisfy CHECK (card_a_id < card_b_id)."""
        with main.get_db() as conn:
            result = create_card_pair(
                conn,
                front="A",
                back="B",
                concept_id=self.concept_id,
            )
            row = conn.execute(
                "SELECT card_a_id, card_b_id FROM card_pairs"
            ).fetchone()
        ids = {result["primary_id"], result["reverse_id"]}
        self.assertEqual({row["card_a_id"], row["card_b_id"]}, ids)
        self.assertLess(row["card_a_id"], row["card_b_id"])

    def test_create_card_pair_rolls_back_on_concept_failure(self) -> None:
        """If the concept lookup fails, no cards and no pair row land."""
        with main.get_db() as conn:
            with self.assertRaises(ValueError):
                create_card_pair(
                    conn,
                    front="Femur",
                    back="The thigh bone",
                    concept_id="does-not-exist",
                )
            count = conn.execute(
                "SELECT COUNT(*) AS n FROM srs_cards"
            ).fetchone()["n"]
            pair_count = conn.execute(
                "SELECT COUNT(*) AS n FROM card_pairs"
            ).fetchone()["n"]
        self.assertEqual(count, 0)
        self.assertEqual(pair_count, 0)

    def test_create_card_pair_rejects_empty_fields(self) -> None:
        with main.get_db() as conn:
            with self.assertRaises(ValueError):
                create_card_pair(conn, front="", back="something")
            with self.assertRaises(ValueError):
                create_card_pair(conn, front="something", back="   ")

    def test_create_card_pair_orphan_allowed(self) -> None:
        """Orphan pairs (no concept) are allowed, mirroring create_card."""
        with main.get_db() as conn:
            result = create_card_pair(
                conn,
                front="Femur",
                back="The thigh bone",
            )
            count = conn.execute(
                "SELECT COUNT(*) AS n FROM srs_cards"
            ).fetchone()["n"]
        self.assertEqual(count, 2)
        self.assertIsNotNone(result["primary_id"])
        self.assertIsNotNone(result["reverse_id"])

    def test_delete_card_cleans_card_pairs_row(self) -> None:
        """delete_card must remove the card_pairs row that references
        the deleted card. The schema declares ON DELETE CASCADE, but
        the app does not enable PRAGMA foreign_keys globally — so the
        cleanup has to live in application code. This test hits the
        production code path with no PRAGMA toggle."""
        with main.get_db() as conn:
            result = create_card_pair(conn, front="Femur", back="Thigh bone")
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS n FROM card_pairs").fetchone()["n"],
                1,
            )
            self.assertTrue(delete_card(conn, result["primary_id"]))
            pair_count = conn.execute(
                "SELECT COUNT(*) AS n FROM card_pairs"
            ).fetchone()["n"]
            surviving = conn.execute(
                "SELECT id FROM srs_cards WHERE id = ?", (result["reverse_id"],)
            ).fetchone()
        self.assertEqual(pair_count, 0)
        self.assertIsNotNone(surviving)

    def test_bulk_delete_cards_cleans_card_pairs(self) -> None:
        """bulk_delete_cards removes card_pairs rows referencing any
        deleted card."""
        with main.get_db() as conn:
            pair_a = create_card_pair(conn, front="A1", back="A2")
            pair_b = create_card_pair(conn, front="B1", back="B2")
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS n FROM card_pairs").fetchone()["n"],
                2,
            )
            removed = bulk_delete_cards(
                conn, [pair_a["primary_id"], pair_b["reverse_id"]]
            )
            pair_count = conn.execute(
                "SELECT COUNT(*) AS n FROM card_pairs"
            ).fetchone()["n"]
        self.assertEqual(removed, 2)
        self.assertEqual(pair_count, 0)

    def test_existing_qa_rows_preserved_after_rebuild(self) -> None:
        """The 12-step rebuild in 0018 must preserve every srs_cards row
        and every column. setUp ran on a fresh DB so 0018 already
        applied — we seed a pre-existing-style row, then verify it
        round-trips correctly."""
        with main.get_db() as conn:
            today = date.today().isoformat()
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            conn.execute(
                """
                INSERT INTO srs_cards (
                    id, concept_id, card_type, kind, front, back,
                    state, stability, difficulty,
                    elapsed_days, scheduled_days, reps, lapses,
                    due_date, last_review, artifact_id, source_snapshot_hash,
                    confidence
                )
                VALUES (?, ?, 'anchor', 'qa', 'q', 'a', 'review',
                        2.5, 0.4, 3, 5, 2, 1, ?, ?, 'art-1', 'hash-1', 0.85)
                """,
                ("legacy-card", self.concept_id, today, yesterday),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM srs_cards WHERE id = 'legacy-card'"
            ).fetchone()
        self.assertEqual(row["artifact_id"], "art-1")
        self.assertEqual(row["source_snapshot_hash"], "hash-1")
        self.assertAlmostEqual(row["confidence"], 0.85)
        self.assertEqual(row["state"], "review")
        self.assertEqual(row["kind"], "qa")


if __name__ == "__main__":
    unittest.main()
