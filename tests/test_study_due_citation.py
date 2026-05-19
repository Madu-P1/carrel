"""Tests for services.study.fetch_due_cards citation enrichment.

PR 4 (flashcards-focus plan, 2026-05-09): the SRS review loop renders a
source citation on the back of every card that has a bound anchor. The
backend surfaces the citation by LEFT JOINing the most-recent anchor row
keyed on srs_card_id. Cards without an anchor still appear in the due
queue; their citation fields are NULL and the UI hides the citation row.

These tests pin the contract: shape of the returned dict, presence of
the four new keys (document_id, chunk_id, page_num, quote_text), and the
"most recent anchor wins" tie-break for cards with multiple anchors.
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
import uuid
from datetime import date, timedelta
from pathlib import Path

import main
from services import anchors as anchors_service
from services.ingestion import ingest_document_record
from services.study import fetch_due_cards

_SAMPLE_TEXT = (
    "A duration-matched portfolio neutralizes first-order interest-rate risk. "
    "Convexity captures the residual sensitivity at large rate moves."
)


def _insert_card(
    conn: sqlite3.Connection,
    *,
    front: str,
    back: str,
    concept_id: str | None,
    due_offset_days: int = -1,
) -> str:
    card_id = str(uuid.uuid4())
    due = (date.today() + timedelta(days=due_offset_days)).isoformat()
    conn.execute(
        """
        INSERT INTO srs_cards (id, concept_id, front, back, state, due_date)
        VALUES (?, ?, ?, ?, 'review', ?)
        """,
        (card_id, concept_id, front, back, due),
    )
    return card_id


def _insert_concept(conn: sqlite3.Connection, *, doc_id: str, name: str) -> str:
    concept_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO concepts (id, doc_id, name) VALUES (?, ?, ?)",
        (concept_id, doc_id, name),
    )
    return concept_id


class FetchDueCardsCitationTests(unittest.TestCase):
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
                filename="bonds.txt",
                file_type="txt",
                extracted_text=_SAMPLE_TEXT,
                page_count=None,
                subject_name="Finance",
            )["doc_id"]
            self.chunk_id = conn.execute(
                "SELECT id FROM chunks WHERE doc_id = ? ORDER BY chunk_index LIMIT 1",
                (self.doc_id,),
            ).fetchone()["id"]
            self.concept_id = _insert_concept(conn, doc_id=self.doc_id, name="Duration matching")
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

    def test_card_with_anchor_returns_chunk_page_quote(self) -> None:
        with main.get_db() as conn:
            card_id = _insert_card(
                conn,
                front="What does duration measure?",
                back="First-order interest-rate sensitivity.",
                concept_id=self.concept_id,
            )
            anchors_service.create_anchor(
                conn,
                document_id=self.doc_id,
                quote_text="A duration-matched portfolio neutralizes first-order interest-rate risk.",
                origin="manual",
                page_num=7,
                chunk_id=self.chunk_id,
                srs_card_id=card_id,
            )
            conn.commit()

        with main.get_db() as conn:
            rows = fetch_due_cards(conn)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["id"], card_id)
        self.assertEqual(row["document_id"], self.doc_id)
        self.assertEqual(row["chunk_id"], self.chunk_id)
        self.assertEqual(row["page_num"], 7)
        self.assertEqual(
            row["quote_text"],
            "A duration-matched portfolio neutralizes first-order interest-rate risk.",
        )

    def test_card_without_anchor_returns_null_citation_fields(self) -> None:
        with main.get_db() as conn:
            _insert_card(
                conn,
                front="What does convexity capture?",
                back="Residual sensitivity at large rate moves.",
                concept_id=self.concept_id,
            )
            conn.commit()

        with main.get_db() as conn:
            rows = fetch_due_cards(conn)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["document_id"], self.doc_id)
        self.assertIsNone(row["chunk_id"])
        self.assertIsNone(row["page_num"])
        self.assertIsNone(row["quote_text"])

    def test_most_recent_anchor_wins_when_card_has_multiple(self) -> None:
        with main.get_db() as conn:
            card_id = _insert_card(
                conn,
                front="What does duration measure?",
                back="First-order interest-rate sensitivity.",
                concept_id=self.concept_id,
            )
            anchors_service.create_anchor(
                conn,
                document_id=self.doc_id,
                quote_text="Old, weak anchor that should lose to the carded one.",
                origin="ai_answer_citation",
                page_num=2,
                chunk_id=self.chunk_id,
                srs_card_id=card_id,
            )
            anchors_service.create_anchor(
                conn,
                document_id=self.doc_id,
                quote_text="Convexity captures the residual sensitivity at large rate moves.",
                origin="manual",
                page_num=9,
                chunk_id=self.chunk_id,
                srs_card_id=card_id,
            )
            conn.commit()

        with main.get_db() as conn:
            rows = fetch_due_cards(conn)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["chunk_id"], self.chunk_id)
        self.assertEqual(row["page_num"], 9)

    def test_orphan_card_with_no_concept_still_returns_row(self) -> None:
        """Cards without a concept_id (and therefore no document) should
        still appear in the due queue. Citation fields are all NULL."""
        with main.get_db() as conn:
            card_id = _insert_card(
                conn,
                front="Manual card",
                back="No source.",
                concept_id=None,
            )
            conn.commit()

        with main.get_db() as conn:
            rows = fetch_due_cards(conn)

        ids = {r["id"] for r in rows}
        self.assertIn(card_id, ids)
        row = next(r for r in rows if r["id"] == card_id)
        self.assertIsNone(row["document_id"])
        self.assertIsNone(row["chunk_id"])
        self.assertIsNone(row["page_num"])
        self.assertIsNone(row["quote_text"])


if __name__ == "__main__":
    unittest.main()
