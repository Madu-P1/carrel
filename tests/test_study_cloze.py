"""Tests for cloze deletion card support — PR 5.1 of flashcards-focus.

Pin the contract from ADR 0002:
1. The new `kind` column defaults to 'qa' for existing rows (migration safety).
2. `services.study.create_card(kind='cloze')` requires at least one
   `{{cN::term}}` marker; rejects otherwise.
3. `services.study.create_card(kind='qa')` is unchanged.
4. `services.study.fetch_due_cards` and `list_cards` return `kind`.
5. `_normalize_card_text` does NOT corrupt cloze markers when a concept
   is literally named `"c1"` (or any other marker-shaped string).
6. `list_cards`' search projection strips cloze markers so a search for
   the hidden term matches and a search for the marker token (`c1`)
   does not pollute results.
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
    _CLOZE_MARKER_RE,
    _normalize_card_text,
    _strip_cloze_markers,
    create_card,
    fetch_due_cards,
    list_cards,
)

_SAMPLE_TEXT = (
    "The mitochondrion is the powerhouse of the cell, producing ATP through "
    "oxidative phosphorylation."
)


def _insert_concept(conn: sqlite3.Connection, *, doc_id: str, name: str) -> str:
    concept_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO concepts (id, doc_id, name) VALUES (?, ?, ?)",
        (concept_id, doc_id, name),
    )
    return concept_id


def _insert_raw_card(
    conn: sqlite3.Connection,
    *,
    front: str,
    back: str,
    concept_id: str | None = None,
    kind: str = "qa",
    due_offset_days: int = -1,
) -> str:
    """Insert a card directly (skipping create_card validation) for cases
    where the test seeds the row shape — e.g. for read-path tests."""
    card_id = str(uuid.uuid4())
    due = (date.today() + timedelta(days=due_offset_days)).isoformat()
    conn.execute(
        """
        INSERT INTO srs_cards (id, concept_id, front, back, state, due_date, kind)
        VALUES (?, ?, ?, ?, 'review', ?, ?)
        """,
        (card_id, concept_id, front, back, due, kind),
    )
    return card_id


class ClozeBackendTests(unittest.TestCase):
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
                filename="biology.txt",
                file_type="txt",
                extracted_text=_SAMPLE_TEXT,
                page_count=None,
                subject_name="Biology",
            )["doc_id"]
            self.concept_id = _insert_concept(conn, doc_id=self.doc_id, name="Mitochondrion")
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

    # ------------------------------------------------------------------
    # Migration safety
    # ------------------------------------------------------------------

    def test_existing_card_defaults_to_kind_qa(self) -> None:
        """ADR 0002 — migration adds kind with DEFAULT 'qa' so legacy
        rows back-compat without a backfill. Pins the default."""
        with main.get_db() as conn:
            card_id = _insert_raw_card(
                conn,
                front="Q",
                back="A",
                concept_id=self.concept_id,
                kind="qa",
            )
            # Read back via fetch_due_cards: the SELECT must include kind.
            conn.commit()
            rows = fetch_due_cards(conn)

        match = [r for r in rows if r["id"] == card_id]
        self.assertEqual(len(match), 1)
        self.assertEqual(match[0]["kind"], "qa")

    # ------------------------------------------------------------------
    # create_card validation
    # ------------------------------------------------------------------

    def test_create_card_qa_unchanged(self) -> None:
        """The qa default path must behave exactly as before this PR."""
        with main.get_db() as conn:
            card = create_card(
                conn,
                front="What's the powerhouse of the cell?",
                back="Mitochondrion.",
                concept_id=self.concept_id,
            )
        self.assertEqual(card["kind"], "qa")
        self.assertEqual(card["front"], "What's the powerhouse of the cell?")

    def test_create_card_cloze_requires_marker(self) -> None:
        """Cloze without a {{cN::term}} marker is a 400 — the entire
        rendering contract assumes one marker per card. The route layer
        translates ValueError to HTTPException(400)."""
        with main.get_db() as conn:
            with self.assertRaises(ValueError) as ctx:
                create_card(
                    conn,
                    front="The mitochondrion is the powerhouse of the cell.",
                    back="The mitochondrion is the powerhouse of the cell.",
                    concept_id=self.concept_id,
                    kind="cloze",
                )
        self.assertIn("marker", str(ctx.exception).lower())

    def test_create_card_cloze_with_marker_succeeds(self) -> None:
        with main.get_db() as conn:
            card = create_card(
                conn,
                front="The mitochondrion is the {{c1::powerhouse}} of the cell.",
                back="The mitochondrion is the {{c1::powerhouse}} of the cell.",
                concept_id=self.concept_id,
                kind="cloze",
            )
        self.assertEqual(card["kind"], "cloze")
        self.assertIn("{{c1::powerhouse}}", card["front"])

    def test_create_card_rejects_unknown_kind(self) -> None:
        """Defense in depth: api_models.CardCreateRequest enums kind to
        a fixed Literal, but the service must reject anything else in
        case a future caller bypasses the route layer. PR 5.2 widened
        the allowlist to include 'reverse'; this test now uses an
        always-unknown sentinel so it stays meaningful as the allowlist
        grows."""
        with main.get_db() as conn:
            with self.assertRaises(ValueError):
                create_card(
                    conn,
                    front="x",
                    back="y",
                    kind="image-occlusion",
                )

    # ------------------------------------------------------------------
    # Mandatory scope additions from ADR 0002
    # ------------------------------------------------------------------

    def test_normalize_preserves_cloze_markers_when_concept_named_c1(self) -> None:
        """ADR 0002 mandatory scope addition: a concept literally named
        "c1" (financial coupon labels, chemistry compound identifiers,
        etc.) must NOT corrupt `{{c1::...}}` cloze markers via the
        replace pass in _normalize_card_text.

        Construct a replacements list where the raw_name `"c1"` would
        rewrite to `"coupon"` if applied naively, and assert the marker
        is preserved.
        """
        replacements = [("c1", "coupon")]
        text = "The {{c1::powerhouse}} of the cell. (also c1 of the bond)"
        normalized = _normalize_card_text(text, replacements)
        # Marker preserved verbatim.
        self.assertIn("{{c1::powerhouse}}", normalized)
        # Prose c1 IS rewritten (we only protect inside markers).
        self.assertIn("(also coupon of the bond)", normalized)

    def test_normalize_preserves_multi_marker_text(self) -> None:
        replacements = [("c1", "X"), ("c2", "Y")]
        text = "Pre {{c1::a}} mid {{c2::b}} post c1 c2."
        normalized = _normalize_card_text(text, replacements)
        self.assertIn("{{c1::a}}", normalized)
        self.assertIn("{{c2::b}}", normalized)
        self.assertIn("post X Y.", normalized)

    def test_strip_cloze_markers_extracts_terms(self) -> None:
        text = "The {{c1::mitochondrion}} produces {{c2::ATP}}."
        self.assertEqual(
            _strip_cloze_markers(text),
            "The mitochondrion produces ATP.",
        )

    def test_strip_cloze_markers_passes_through_plain_text(self) -> None:
        self.assertEqual(_strip_cloze_markers("plain text"), "plain text")
        self.assertEqual(_strip_cloze_markers(""), "")

    def test_list_cards_search_strips_cloze_markers(self) -> None:
        """ADR 0002 mandatory scope addition: a search for the hidden
        term ('powerhouse') matches a cloze card whose source is
        "The {{c1::powerhouse}} of the cell". A search for the marker
        token ('c1') does NOT pollute results.
        """
        with main.get_db() as conn:
            cloze_id = _insert_raw_card(
                conn,
                front="The {{c1::powerhouse}} of the cell.",
                back="The {{c1::powerhouse}} of the cell.",
                concept_id=self.concept_id,
                kind="cloze",
            )
            _insert_raw_card(
                conn,
                front="An unrelated qa card about photosynthesis.",
                back="Light reactions and Calvin cycle.",
                concept_id=self.concept_id,
                kind="qa",
            )
            conn.commit()

            hit = list_cards(conn, search="powerhouse")
            ids = {c["id"] for c in hit["cards"]}
            self.assertIn(cloze_id, ids, "search should match hidden cloze term")

            miss = list_cards(conn, search="c1")
            ids = {c["id"] for c in miss["cards"]}
            self.assertNotIn(
                cloze_id,
                ids,
                "search for the marker token must not match cloze cards",
            )

    def test_list_cards_returns_kind(self) -> None:
        """The Manage Cards view needs `kind` in the row to render the
        correct face. Pin its presence in the SELECT projection."""
        with main.get_db() as conn:
            card_id = _insert_raw_card(
                conn,
                front="The {{c1::ATP}} synthase complex.",
                back="The {{c1::ATP}} synthase complex.",
                concept_id=self.concept_id,
                kind="cloze",
            )
            conn.commit()
            result = list_cards(conn)
        match = [c for c in result["cards"] if c["id"] == card_id]
        self.assertEqual(len(match), 1)
        self.assertEqual(match[0]["kind"], "cloze")


class ClozeRegexTests(unittest.TestCase):
    """Cheap regex-only checks that pin the marker pattern shape."""

    def test_matches_single_digit_index(self) -> None:
        self.assertIsNotNone(_CLOZE_MARKER_RE.search("foo {{c1::bar}} baz"))

    def test_matches_multi_digit_index(self) -> None:
        self.assertIsNotNone(_CLOZE_MARKER_RE.search("foo {{c12::bar}} baz"))

    def test_rejects_no_index(self) -> None:
        self.assertIsNone(_CLOZE_MARKER_RE.search("foo {{c::bar}} baz"))

    def test_rejects_unclosed_marker(self) -> None:
        self.assertIsNone(_CLOZE_MARKER_RE.search("foo {{c1::bar baz"))


if __name__ == "__main__":
    unittest.main()
