"""Direct tests for `services.library_subjects`.

Covers the WITH-subjects UNION (declared + implicit), the per-subject
summary aggregation, and `set_document_subject`'s 404 contract. Uses
an in-memory SQLite with a slice of the schema sufficient to drive
the queries.
"""

from __future__ import annotations

import json
import sqlite3
import unittest
from unittest import mock

from fastapi import HTTPException

from services.library_subjects import (
    fetch_subject_groups,
    list_subject_summaries,
)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE library_subjects (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE documents (
            id TEXT PRIMARY KEY,
            filename TEXT,
            storage_name TEXT,
            subject_name TEXT,
            file_type TEXT,
            upload_date TEXT,
            page_count INTEGER,
            status TEXT,
            source_kind TEXT,
            source_hash TEXT,
            parser_status TEXT,
            parser_diagnostics TEXT,
            duplicate_of TEXT,
            updated_at TEXT,
            extracted_at TEXT
        );
        CREATE TABLE concepts (
            id TEXT PRIMARY KEY,
            doc_id TEXT
        );
        CREATE TABLE srs_cards (
            id TEXT PRIMARY KEY,
            concept_id TEXT
        );
        CREATE TABLE study_events (
            id TEXT PRIMARY KEY,
            doc_id TEXT,
            created_at TEXT
        );
        """
    )
    return conn


def _insert_doc(
    conn: sqlite3.Connection,
    *,
    id: str,
    subject: str | None = None,
    parser_status: str = "ready",
    diagnostics: str | None = None,
    upload_date: str = "2026-01-01",
    filename: str = "x.pdf",
) -> None:
    conn.execute(
        """INSERT INTO documents (id, filename, subject_name, parser_status,
                                  parser_diagnostics, upload_date)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (id, filename, subject, parser_status, diagnostics, upload_date),
    )


class FetchSubjectGroupsTests(unittest.TestCase):
    def test_empty_db_returns_empty_list(self) -> None:
        conn = _connect()
        self.assertEqual([], fetch_subject_groups(conn))

    def test_declared_subject_appears_even_with_no_documents(self) -> None:
        # The user can create a subject card before any docs land.
        conn = _connect()
        conn.execute("INSERT INTO library_subjects (name) VALUES ('Calculus')")
        groups = fetch_subject_groups(conn)
        self.assertEqual(1, len(groups))
        self.assertEqual("Calculus", groups[0]["subject_name"])
        self.assertEqual(0, groups[0]["document_count"])

    def test_implicit_general_subject_for_null_or_blank(self) -> None:
        # Documents without a subject_name fall into the General bucket
        # — both NULL and whitespace-only get folded into the same group.
        conn = _connect()
        _insert_doc(conn, id="a", subject=None)
        _insert_doc(conn, id="b", subject="   ")
        _insert_doc(conn, id="c", subject="")
        groups = fetch_subject_groups(conn)
        self.assertEqual(1, len(groups))
        self.assertEqual("General", groups[0]["subject_name"])
        self.assertEqual(3, groups[0]["document_count"])

    def test_subjects_sorted_alphabetically(self) -> None:
        conn = _connect()
        _insert_doc(conn, id="a", subject="Zoology")
        _insert_doc(conn, id="b", subject="Anatomy")
        names = [g["subject_name"] for g in fetch_subject_groups(conn)]
        self.assertEqual(["Anatomy", "Zoology"], names)


class ListSubjectSummariesTests(unittest.TestCase):
    def test_empty_db_returns_empty_list(self) -> None:
        conn = _connect()
        self.assertEqual([], list_subject_summaries(conn))

    def test_failed_count_excludes_status_ready(self) -> None:
        conn = _connect()
        conn.execute("INSERT INTO library_subjects (name) VALUES ('General')")
        _insert_doc(conn, id="ok", parser_status="ready")
        _insert_doc(conn, id="bad1", parser_status="failed")
        _insert_doc(conn, id="bad2", parser_status="needs_attention")
        [summary] = list_subject_summaries(conn)
        self.assertEqual(3, summary["source_count"])
        self.assertEqual(2, summary["failed_count"])

    def test_first_failed_doc_extracts_quality_warning(self) -> None:
        conn = _connect()
        conn.execute("INSERT INTO library_subjects (name) VALUES ('General')")
        diagnostics = json.dumps(
            {"quality": {"warnings": ["scanned PDF with no extractable text"]}}
        )
        _insert_doc(
            conn,
            id="bad",
            parser_status="failed",
            diagnostics=diagnostics,
            upload_date="2026-02-01",
        )
        [summary] = list_subject_summaries(conn)
        first = summary["first_failed_doc"]
        self.assertIsNotNone(first)
        assert first is not None
        self.assertEqual("bad", first["id"])
        self.assertEqual("scanned PDF with no extractable text", first["error"])

    def test_first_failed_doc_default_message_when_no_warnings(self) -> None:
        # Parser failed but didn't populate quality.warnings — surface a
        # generic message rather than blowing up or returning empty.
        conn = _connect()
        conn.execute("INSERT INTO library_subjects (name) VALUES ('General')")
        _insert_doc(conn, id="bad", parser_status="failed", diagnostics="{}")
        [summary] = list_subject_summaries(conn)
        first = summary["first_failed_doc"]
        self.assertIsNotNone(first)
        assert first is not None
        self.assertIn("Parser reported a problem", first["error"])

    def test_sorted_by_source_count_desc_then_name(self) -> None:
        conn = _connect()
        conn.executemany(
            "INSERT INTO library_subjects (name) VALUES (?)",
            [("Anatomy",), ("Biology",), ("Chemistry",)],
        )
        _insert_doc(conn, id="a1", subject="Anatomy")
        _insert_doc(conn, id="b1", subject="Biology")
        _insert_doc(conn, id="b2", subject="Biology")
        # Chemistry has zero docs.
        names = [s["subject_name"] for s in list_subject_summaries(conn)]
        # Biology (2) > Anatomy (1) > Chemistry (0); ties break alphabetically
        # but here all counts differ.
        self.assertEqual(["Biology", "Anatomy", "Chemistry"], names)

    def test_flashcard_count_joins_through_concepts_and_documents(self) -> None:
        conn = _connect()
        conn.execute("INSERT INTO library_subjects (name) VALUES ('Anatomy')")
        _insert_doc(conn, id="d1", subject="Anatomy")
        conn.execute("INSERT INTO concepts (id, doc_id) VALUES ('c1', 'd1')")
        conn.execute("INSERT INTO concepts (id, doc_id) VALUES ('c2', 'd1')")
        conn.execute("INSERT INTO srs_cards (id, concept_id) VALUES ('s1', 'c1')")
        conn.execute("INSERT INTO srs_cards (id, concept_id) VALUES ('s2', 'c1')")
        conn.execute("INSERT INTO srs_cards (id, concept_id) VALUES ('s3', 'c2')")
        [summary] = list_subject_summaries(conn)
        self.assertEqual(3, summary["flashcard_count"])


class SetDocumentSubjectTests(unittest.TestCase):
    def test_404_when_doc_id_missing(self) -> None:
        # Late-binding `from services.documents import …` only runs
        # after the row update succeeds (rowcount > 0), so we can mock
        # those imports out and still trigger the 404 path.
        from services import library_subjects

        conn = _connect()
        conn.execute("INSERT INTO library_subjects (name) VALUES ('General')")

        with self.assertRaises(HTTPException) as ctx:
            library_subjects.set_document_subject(conn, "nonexistent", "General")
        self.assertEqual(404, ctx.exception.status_code)

    def test_normalize_and_ensure_subject_called_before_update(self) -> None:
        # set_document_subject normalises the subject name and writes
        # an `library_subjects` row before mutating documents — so a
        # typo'd subject doesn't leave dangling docs without a subject
        # header.
        from services import library_subjects

        conn = _connect()
        _insert_doc(conn, id="d1", subject="General")

        with mock.patch("services.documents.fetch_document_detail") as detail_mock, \
             mock.patch("services.documents._document_confidence", return_value=0.9):
            detail_mock.return_value = {
                "summary": "x",
                "counts": {"concepts": 0, "questions": 0},
            }
            library_subjects.set_document_subject(conn, "d1", "  Anatomy  ")

        rows = conn.execute("SELECT name FROM library_subjects").fetchall()
        self.assertIn("Anatomy", [r["name"] for r in rows])


if __name__ == "__main__":
    unittest.main()
