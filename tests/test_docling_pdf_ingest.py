"""End-to-end Docling parse → walker test against real PDF fixtures.

Slow: each parse spins up rapidocr + the table-structure model, ~15-30s
per PDF on M-series. Skipped automatically when Docling isn't installed
so contributors who don't run the new ingest path don't pay the cost.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from services.ingestion import docling_parser, typed_walker

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@unittest.skipUnless(docling_parser.is_available(), "docling not installed")
class DoclingPdfIngestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Parse each fixture exactly once for the whole suite — Docling
        # initialization is the costly part.
        cls.single_nodes = typed_walker.walk(
            docling_parser.parse_document(FIXTURES_DIR / "single_column.pdf")
        )
        cls.two_col_nodes = typed_walker.walk(
            docling_parser.parse_document(FIXTURES_DIR / "two_column.pdf")
        )

    def test_single_column_emits_a_heading_and_at_least_one_body(self) -> None:
        types = [n.node_type for n in self.single_nodes]
        self.assertIn("heading", types)
        self.assertIn("body", types)

    def test_single_column_reading_order_is_monotonic(self) -> None:
        orders = [n.reading_order for n in self.single_nodes]
        self.assertEqual(orders, sorted(orders))
        self.assertEqual(orders, list(range(len(orders))))

    def test_single_column_char_offsets_do_not_overlap(self) -> None:
        for prev, curr in zip(self.single_nodes, self.single_nodes[1:]):
            self.assertLessEqual(prev.char_end, curr.char_start)

    def test_single_column_heading_seeds_heading_path(self) -> None:
        body_nodes = [n for n in self.single_nodes if n.node_type == "body"]
        self.assertTrue(body_nodes, "no body nodes parsed from fixture")
        for body in body_nodes:
            self.assertNotEqual(body.heading_path, "")

    def test_two_column_reading_order_is_monotonic(self) -> None:
        orders = [n.reading_order for n in self.two_col_nodes]
        self.assertEqual(orders, sorted(orders))

    def test_two_column_left_body_precedes_right_body(self) -> None:
        body_nodes = [n for n in self.two_col_nodes if n.node_type == "body"]
        self.assertGreaterEqual(len(body_nodes), 2, "expected two body paragraphs")
        # The fixture left column starts with "Mitosis", right with "Meiosis".
        # If reading order leaks across columns, Meiosis would land before
        # Mitosis — that's the citation-chip-lands-in-wrong-column bug from
        # the parent algorithm spec. This test pins it.
        mitosis_idx = next(
            i for i, n in enumerate(body_nodes) if n.verbatim_text.startswith("Mitosis")
        )
        meiosis_idx = next(
            i for i, n in enumerate(body_nodes) if n.verbatim_text.startswith("Meiosis")
        )
        self.assertLess(mitosis_idx, meiosis_idx)

    def test_pages_are_one_indexed(self) -> None:
        # Every fixture node lives on page 1. Catches the off-by-one
        # that would shift page numbers if the walker zero-indexed.
        pages = {n.page for n in self.single_nodes if n.page is not None}
        self.assertEqual(pages, {1})


if __name__ == "__main__":
    unittest.main()
