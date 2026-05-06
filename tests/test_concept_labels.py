"""Direct tests for `services.concept_labels`.

Covers the label-cleanup pipeline, the selector scoring, the cache
hit / miss behavior of `build_concept_options`, and the fallback
when no concepts pass the curator.
"""

from __future__ import annotations

import sqlite3
import unittest

from services.concept_labels import (
    SELECTOR_LIMIT,
    _fallback_concept_options,
    _selector_score,
    build_concept_options,
    clean_concept_label,
    collect_document_concepts,
)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE app_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE documents (
            id TEXT PRIMARY KEY,
            filename TEXT,
            subject_name TEXT
        );
        CREATE TABLE concepts (
            id TEXT PRIMARY KEY,
            doc_id TEXT,
            name TEXT,
            description TEXT,
            mastery REAL,
            source_chunks TEXT
        );
        """
    )
    return conn


class CleanConceptLabelTests(unittest.TestCase):
    def test_camelcase_split(self) -> None:
        self.assertEqual("Mitosis Phase", clean_concept_label("MitosisPhase"))

    def test_underscore_collapse(self) -> None:
        self.assertEqual("cell biology", clean_concept_label("cell_biology"))

    def test_dash_and_slash_collapse(self) -> None:
        self.assertEqual("part one two", clean_concept_label("part-one/two"))

    def test_letter_digit_split(self) -> None:
        self.assertEqual("Q 1 Lab 2", clean_concept_label("Q1Lab2"))

    def test_copyright_noise_stripped(self) -> None:
        # Boilerplate the OCR layer leaks into concept names.
        result = clean_concept_label("Mitosis (Copyright Pearson Education)")
        self.assertNotIn("Copyright", result)
        self.assertNotIn("Pearson", result)
        self.assertIn("Mitosis", result)

    def test_adjacent_duplicate_words_deduped(self) -> None:
        # OCR sometimes repeats the same word.
        self.assertEqual(
            "Mitosis is a process",
            clean_concept_label("Mitosis Mitosis is a process"),
        )

    def test_empty_returns_study_concept(self) -> None:
        self.assertEqual("Study concept", clean_concept_label(""))
        self.assertEqual("Study concept", clean_concept_label("   "))
        self.assertEqual("Study concept", clean_concept_label(None))  # type: ignore[arg-type]

    def test_punctuation_trimmed_from_edges(self) -> None:
        self.assertEqual("Mitosis", clean_concept_label("...Mitosis..."))


class SelectorScoreTests(unittest.TestCase):
    def test_goal_token_overlap_boosts_score(self) -> None:
        concept = {
            "name": "Mitosis",
            "description": "How a cell divides during mitosis.",
        }
        with_goal = _selector_score(concept, "study mitosis cell division")
        without_goal = _selector_score(concept, "")
        self.assertGreater(with_goal, without_goal)

    def test_short_clean_name_penalised(self) -> None:
        # A clean name under 4 chars carries -25; "Mitosis" is fine.
        ok = _selector_score({"name": "Mitosis", "description": "x"}, "")
        bad = _selector_score({"name": "DNA"}, "")
        self.assertGreater(ok, bad)

    def test_noise_pattern_penalised(self) -> None:
        # The penalty makes copyright-heavy concepts sink to the
        # bottom of the curated picker list.
        clean = _selector_score({"name": "Mitosis", "description": "x"}, "")
        noisy = _selector_score(
            {"name": "Mitosis (All Rights Reserved)", "description": "x"}, ""
        )
        self.assertGreater(clean, noisy)


class FallbackConceptOptionsTests(unittest.TestCase):
    def test_caps_at_selector_limit(self) -> None:
        concepts = [
            {"id": f"c{i}", "name": f"Concept {i:02d}", "description": "x"}
            for i in range(SELECTOR_LIMIT * 2)
        ]
        result = _fallback_concept_options(concepts, "")
        self.assertEqual(SELECTOR_LIMIT, len(result))

    def test_dedupes_by_cleaned_label(self) -> None:
        # Two concepts that clean to the same label collapse into one
        # picker entry. (Otherwise the user sees "Mitosis" twice.)
        concepts = [
            {"id": "a", "name": "Mitosis", "description": "x"},
            {"id": "b", "name": "MITOSIS", "description": "y"},
        ]
        result = _fallback_concept_options(concepts, "")
        self.assertEqual(1, len(result))
        self.assertEqual("Mitosis", result[0]["display_name"])


class BuildConceptOptionsTests(unittest.TestCase):
    def test_empty_concepts_returns_empty(self) -> None:
        conn = _connect()
        result = build_concept_options(
            conn,
            document_row={"id": "d1", "filename": "x.pdf"},
            concepts=[],
            chunk_items=[],
        )
        self.assertEqual([], result)

    def test_caches_selector_options_in_app_settings(self) -> None:
        conn = _connect()
        document_row = {"id": "d1", "filename": "x.pdf"}
        concepts = [
            {"id": "c1", "name": "Mitosis", "description": "x"},
            {"id": "c2", "name": "Meiosis", "description": "y"},
        ]
        build_concept_options(
            conn, document_row=document_row, concepts=concepts, chunk_items=[]
        )
        # The cache row exists keyed by `concept_selector:<doc_id>`.
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = ?",
            ("concept_selector:d1",),
        ).fetchone()
        self.assertIsNotNone(row)
        # Second call should be a cache hit (signature matches) — return
        # value should still be a non-empty list with the same shape.
        result2 = build_concept_options(
            conn, document_row=document_row, concepts=concepts, chunk_items=[]
        )
        self.assertEqual(2, len(result2))
        names = {item["name"] for item in result2}
        self.assertEqual({"Mitosis", "Meiosis"}, names)

    def test_selected_carries_rank_and_reason(self) -> None:
        conn = _connect()
        result = build_concept_options(
            conn,
            document_row={"id": "d1", "filename": "x.pdf"},
            concepts=[
                {"id": "c1", "name": "Mitosis", "description": "explanation"},
            ],
            chunk_items=[],
        )
        self.assertEqual(1, len(result))
        self.assertEqual(0, result[0]["selector_rank"])
        self.assertIn("selector_reason", result[0])
        self.assertEqual("Mitosis", result[0]["raw_name"])


class CollectDocumentConceptsTests(unittest.TestCase):
    def test_empty_doc_id_returns_empty(self) -> None:
        conn = _connect()
        self.assertEqual([], collect_document_concepts(conn, ""))

    def test_parses_source_chunks_json(self) -> None:
        conn = _connect()
        conn.execute(
            "INSERT INTO documents (id, filename, subject_name) VALUES (?, ?, ?)",
            ("d1", "x.pdf", "Bio"),
        )
        conn.execute(
            """INSERT INTO concepts (id, doc_id, name, description, mastery, source_chunks)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("c1", "d1", "Mitosis", "...", 0.5, '["chunk-a","chunk-b"]'),
        )
        result = collect_document_concepts(conn, "d1")
        self.assertEqual(1, len(result))
        self.assertEqual(["chunk-a", "chunk-b"], result[0]["source_chunk_ids"])
        # source_chunks raw column is stripped from the dict.
        self.assertNotIn("source_chunks", result[0])

    def test_display_name_uses_clean_concept_label(self) -> None:
        conn = _connect()
        conn.execute(
            "INSERT INTO documents (id, filename, subject_name) VALUES (?, ?, ?)",
            ("d1", "x.pdf", "Bio"),
        )
        conn.execute(
            """INSERT INTO concepts (id, doc_id, name, description, mastery, source_chunks)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("c1", "d1", "MitosisPhase", "x", 0.0, "[]"),
        )
        result = collect_document_concepts(conn, "d1")
        self.assertEqual("Mitosis Phase", result[0]["display_name"])


if __name__ == "__main__":
    unittest.main()
