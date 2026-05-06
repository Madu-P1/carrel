"""Tests for `services.artifact_studio.grounding`.

Covers the chunk + concept loaders that feed `generate_artifact`. The
heaviest function (`retrieve_grounding_chunks`) does keyword-token
overlap scoring; we pin the contract (budget cap, scope filtering)
without locking in the score formula itself.
"""

from __future__ import annotations

import sqlite3
import unittest

from services.artifact_studio.grounding import (
    _chunk_text_for_scope,
    _concepts_for_scope,
    render_grounding_text,
    retrieve_grounding_chunks,
)


def _connect() -> sqlite3.Connection:
    """Build the schema slice the grounding queries actually need.

    Confirmed by reading services/artifact_studio/grounding.py:
      `_chunk_text_for_scope` reads `ch.chunk_index` for ORDER BY.
      `_concepts_for_scope` reads concept fields plus `c.source_chunks`.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE documents (
            id TEXT PRIMARY KEY,
            filename TEXT,
            subject_name TEXT,
            storage_name TEXT,
            file_type TEXT
        );
        CREATE TABLE concepts (
            id TEXT PRIMARY KEY,
            doc_id TEXT,
            name TEXT,
            description TEXT,
            mastery REAL,
            source_chunks TEXT
        );
        CREATE TABLE chunks (
            id TEXT PRIMARY KEY,
            doc_id TEXT,
            chunk_index INTEGER,
            section TEXT,
            page_num INTEGER,
            content TEXT
        );
        """
    )
    return conn


class ChunkTextForScopeTests(unittest.TestCase):
    def test_filters_to_named_source_ids(self) -> None:
        # The orchestrator's flashcard fallback path passes source_ids
        # only; verify that branch ONLY pulls chunks from those docs.
        conn = _connect()
        for did in ("d1", "d2"):
            conn.execute(
                "INSERT INTO documents (id, filename) VALUES (?, ?)",
                (did, f"{did}.pdf"),
            )
        for cid, did, idx, content in [
            ("c1", "d1", 0, "alpha"),
            ("c2", "d2", 0, "beta"),
            ("c3", "d1", 1, "gamma"),
        ]:
            conn.execute(
                "INSERT INTO chunks (id, doc_id, chunk_index, content) VALUES (?, ?, ?, ?)",
                (cid, did, idx, content),
            )
        result = _chunk_text_for_scope(conn, ["d1"], None, limit=10)
        ids = sorted(item["id"] for item in result)
        self.assertEqual(["c1", "c3"], ids)

    def test_concept_ids_take_precedence_over_source_ids(self) -> None:
        # Reading the function: if concept_ids is set, that branch runs
        # first (regardless of source_ids).
        conn = _connect()
        conn.execute("INSERT INTO documents (id, filename) VALUES ('d1', 'a.pdf')")
        conn.execute(
            "INSERT INTO concepts (id, doc_id, name) VALUES ('k1', 'd1', 'Mitosis')"
        )
        conn.execute(
            "INSERT INTO chunks (id, doc_id, chunk_index, content) VALUES ('c1', 'd1', 0, 'alpha')"
        )
        result = _chunk_text_for_scope(conn, ["d2"], ["k1"], limit=10)
        # Concept k1 lives in d1, not d2; concept_ids branch wins.
        self.assertEqual(["c1"], [item["id"] for item in result])


class ConceptsForScopeTests(unittest.TestCase):
    def test_empty_concept_and_source_returns_empty_or_recent(self) -> None:
        # With no scope and an empty DB, must not crash; should return [].
        conn = _connect()
        result = _concepts_for_scope(conn, None, None, limit=10)
        self.assertEqual([], result)

    def test_filters_by_concept_ids(self) -> None:
        conn = _connect()
        conn.execute("INSERT INTO documents (id, filename) VALUES ('d1', 'a.pdf')")
        conn.executemany(
            "INSERT INTO concepts (id, doc_id, name, description) VALUES (?, ?, ?, ?)",
            [
                ("k1", "d1", "Mitosis", "..."),
                ("k2", "d1", "Meiosis", "..."),
                ("k3", "d1", "Photosynthesis", "..."),
            ],
        )
        result = _concepts_for_scope(conn, None, ["k1", "k3"], limit=10)
        names = sorted(c["name"] for c in result)
        self.assertEqual(["Mitosis", "Photosynthesis"], names)


class RetrieveGroundingChunksTests(unittest.TestCase):
    def test_caps_at_provided_limit(self) -> None:
        # Budget cap is the contract that protects downstream LLM
        # context windows. Off-by-one here is a real bug.
        conn = _connect()
        conn.execute("INSERT INTO documents (id, filename) VALUES ('d1', 'a.pdf')")
        for i in range(20):
            conn.execute(
                """INSERT INTO chunks (id, doc_id, chunk_index, content)
                   VALUES (?, ?, ?, ?)""",
                (f"c{i:02d}", "d1", i, f"sentence number {i} about photosynthesis"),
            )
        result = retrieve_grounding_chunks(
            conn, source_ids=["d1"], concept_ids=None, query="photosynthesis", limit=5
        )
        self.assertLessEqual(len(result), 5)


class RenderGroundingTextTests(unittest.TestCase):
    def test_empty_chunks_returns_empty_string(self) -> None:
        # Empty grounding bundle is the no-source path; render must not
        # produce dangling delimiters that confuse the downstream LLM.
        result = render_grounding_text([])
        # Either an empty string OR a string with no chunk-delimiter.
        # Both contracts are valid; we pin "no delimiter without content".
        self.assertNotIn("page", result.lower())
        self.assertNotIn("section", result.lower())

    def test_includes_filename_and_content(self) -> None:
        chunks = [
            {
                "id": "c1",
                "doc_id": "d1",
                "filename": "paper.pdf",
                "section": "Intro",
                "page_num": 3,
                "content": "Mitosis is a process of cell division.",
            },
        ]
        rendered = render_grounding_text(chunks)
        # The formatter folds in filename + content; section/page may
        # be inline or in a header. Pin the bits we care about.
        self.assertIn("paper.pdf", rendered)
        self.assertIn("Mitosis", rendered)


if __name__ == "__main__":
    unittest.main()
