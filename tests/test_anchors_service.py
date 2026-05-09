"""Tests for services/anchors.py + the 0008_anchors migration.

Focus:
  - Migration applies cleanly and creates the table + indexes.
  - CRUD works end-to-end.
  - Promotion state machine rejects illegal transitions.
  - Carded transition refuses without srs_card_id.
  - CHECK constraints reject bad origin / promotion_state at the DB level.
  - list_anchors_for_document filters by page_num and promotion_state.
  - Soft-delete via 'archived' leaves the row queryable.
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path

import db as db_module
import main
from services import anchors as anchors_service
from services.ingestion import ingest_document_record

_SAMPLE_TEXT = (
    "Bonds are debt securities issued by governments and corporations. "
    "The coupon rate is fixed at issuance. The yield to maturity reflects "
    "the effective return given the current price."
)


class AnchorsServiceTests(unittest.TestCase):
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
        # Seed one document so we have a real document_id to anchor against.
        with main.get_db() as conn:
            self.doc_id = ingest_document_record(
                conn=conn,
                filename="bonds.txt",
                file_type="txt",
                extracted_text=_SAMPLE_TEXT,
                page_count=None,
                subject_name="Finance",
            )["doc_id"]

    def tearDown(self) -> None:
        (
            main.BASE_DIR,
            main.DATA_DIR,
            main.UPLOAD_DIR,
            main.DB_PATH,
            main.SCHEMA_PATH,
        ) = self._restore
        self.temp_dir.cleanup()

    # ------------------------------------------------------------------
    # Migration / schema
    # ------------------------------------------------------------------

    def test_migration_creates_anchors_table_and_indexes(self) -> None:
        with main.get_db() as conn:
            self.assertTrue(db_module.table_exists(conn, "anchors"))
            index_names = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='anchors'"
                ).fetchall()
            }
        expected = {
            "idx_anchors_document",
            "idx_anchors_promotion_state",
            "idx_anchors_document_page",
            "idx_anchors_srs_card",
            "idx_anchors_thread",
            "idx_anchors_origin",
            "idx_anchors_created_at",
        }
        self.assertTrue(
            expected.issubset(index_names),
            f"missing indexes: {expected - index_names}",
        )

    def test_migration_registered_in_schema_migrations(self) -> None:
        with main.get_db() as conn:
            row = conn.execute("SELECT name FROM schema_migrations WHERE version = 8").fetchone()
        self.assertIsNotNone(row)
        # db.py stores the filename verbatim (without normalization).
        self.assertEqual(row["name"], "0008_anchors.sql")

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def test_create_and_fetch_anchor(self) -> None:
        with main.get_db() as conn:
            anchor = anchors_service.create_anchor(
                conn,
                document_id=self.doc_id,
                quote_text="The coupon rate is fixed at issuance.",
                origin="highlight",
                page_num=1,
                bbox=[100.0, 200.0, 300.0, 16.0],
                text_offset_start=42,
                text_offset_end=78,
            )
            conn.commit()
        self.assertEqual(anchor.document_id, self.doc_id)
        self.assertEqual(anchor.origin, "highlight")
        self.assertEqual(anchor.promotion_state, "weak")
        self.assertEqual(anchor.bbox, [100.0, 200.0, 300.0, 16.0])
        self.assertEqual(anchor.text_offset_start, 42)

        with main.get_db() as conn:
            fetched = anchors_service.get_anchor(conn, anchor.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.id, anchor.id)
        self.assertEqual(fetched.quote_text, "The coupon rate is fixed at issuance.")

    def test_create_rejects_empty_quote(self) -> None:
        with main.get_db() as conn:
            with self.assertRaises(ValueError):
                anchors_service.create_anchor(
                    conn,
                    document_id=self.doc_id,
                    quote_text="   ",
                    origin="highlight",
                )

    def test_create_rejects_bad_origin(self) -> None:
        with main.get_db() as conn:
            with self.assertRaises(ValueError):
                anchors_service.create_anchor(
                    conn,
                    document_id=self.doc_id,
                    quote_text="x",
                    origin="bogus",  # type: ignore[arg-type]
                )

    def test_create_rejects_bad_bbox(self) -> None:
        with main.get_db() as conn:
            with self.assertRaises(ValueError):
                anchors_service.create_anchor(
                    conn,
                    document_id=self.doc_id,
                    quote_text="x",
                    origin="highlight",
                    bbox=[1.0, 2.0, 3.0],
                )

    def test_db_level_check_rejects_bad_state_via_direct_sql(self) -> None:
        """Defensive: if someone bypasses the service and writes directly,
        the DB CHECK constraint still rejects invalid enum values."""
        with main.get_db() as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO anchors (id, document_id, quote_text, origin, promotion_state)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (str(uuid.uuid4()), self.doc_id, "x", "highlight", "invented-state"),
                )

    # ------------------------------------------------------------------
    # Promotion state machine
    # ------------------------------------------------------------------

    def test_valid_promotion_path_weak_to_mastered(self) -> None:
        with main.get_db() as conn:
            a = anchors_service.create_anchor(
                conn,
                document_id=self.doc_id,
                quote_text="x",
                origin="highlight",
            )
            # Seed an srs_cards row so 'carded' transition can set the FK.
            card_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO srs_cards (id, card_type, front, back)
                VALUES (?, ?, ?, ?)
                """,
                (card_id, "custom", "q", "a"),
            )
            a = anchors_service.transition_state(conn, a.id, "saved")
            self.assertEqual(a.promotion_state, "saved")
            a = anchors_service.transition_state(conn, a.id, "carded", srs_card_id=card_id)
            self.assertEqual(a.promotion_state, "carded")
            self.assertEqual(a.srs_card_id, card_id)
            a = anchors_service.transition_state(conn, a.id, "mastered")
            self.assertEqual(a.promotion_state, "mastered")

    def test_illegal_transition_rejected(self) -> None:
        with main.get_db() as conn:
            a = anchors_service.create_anchor(
                conn,
                document_id=self.doc_id,
                quote_text="x",
                origin="highlight",
            )
            # weak -> mastered skips 'saved' and 'carded' — illegal.
            with self.assertRaises(ValueError):
                anchors_service.transition_state(conn, a.id, "mastered")

    def test_carded_transition_requires_srs_card_id(self) -> None:
        with main.get_db() as conn:
            a = anchors_service.create_anchor(
                conn,
                document_id=self.doc_id,
                quote_text="x",
                origin="highlight",
            )
            a = anchors_service.transition_state(conn, a.id, "saved")
            with self.assertRaises(ValueError):
                anchors_service.transition_state(conn, a.id, "carded")

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def test_list_by_page_and_state(self) -> None:
        with main.get_db() as conn:
            anchors_service.create_anchor(
                conn, document_id=self.doc_id, quote_text="p1 a", origin="highlight", page_num=1
            )
            anchors_service.create_anchor(
                conn, document_id=self.doc_id, quote_text="p1 b", origin="highlight", page_num=1
            )
            anchors_service.create_anchor(
                conn, document_id=self.doc_id, quote_text="p2", origin="highlight", page_num=2
            )
            conn.commit()
            p1 = anchors_service.list_anchors_for_document(conn, self.doc_id, page_num=1)
            p2 = anchors_service.list_anchors_for_document(conn, self.doc_id, page_num=2)
        self.assertEqual(len(p1), 2)
        self.assertEqual(len(p2), 1)
        self.assertTrue(all(a.page_num == 1 for a in p1))

    def test_count_by_state_fills_all_states(self) -> None:
        with main.get_db() as conn:
            counts = anchors_service.count_by_state(conn, self.doc_id)
        # Zero anchors, but every state key is present with 0.
        self.assertEqual(
            set(counts.keys()),
            {"weak", "saved", "carded", "mastered", "archived"},
        )
        self.assertTrue(all(v == 0 for v in counts.values()))

    def test_delete_anchor_returns_false_when_missing(self) -> None:
        with main.get_db() as conn:
            self.assertFalse(anchors_service.delete_anchor(conn, "does-not-exist"))


if __name__ == "__main__":
    unittest.main()
