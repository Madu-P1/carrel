"""Unit tests for docling_parser PDF probes (T12, Phase 4.3).

`has_rich_text_layer` decides whether script/reingest_all.py runs Docling
OCR over a PDF. It must report a rich text layer for born-digital PDFs,
so OCR is skipped (OCR over a complete text layer is wasted compute that
scales with page count), and report none for scanned PDFs, so OCR stays
on.

`pdf_page_count` decides whether a PDF is long enough to need sliced
parsing — Docling's peak memory scales with page count, so a very large
textbook is parsed in page-range slices.

Both probes read only pypdf, never Docling, so this suite is not gated
on the optional Docling install.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pypdf import PdfWriter

from services.ingestion import docling_parser

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class HasRichTextLayerTests(unittest.TestCase):
    def test_born_digital_pdf_is_detected(self) -> None:
        # single_column.pdf is generated with a real text layer
        # (~425 chars on its page), far above the probe threshold.
        self.assertTrue(docling_parser.has_rich_text_layer(FIXTURES_DIR / "single_column.pdf"))

    def test_two_column_born_digital_pdf_is_detected(self) -> None:
        self.assertTrue(docling_parser.has_rich_text_layer(FIXTURES_DIR / "two_column.pdf"))

    def test_pdf_with_no_text_layer_is_rejected(self) -> None:
        # Blank pages stand in for a scanned document: pypdf extracts no
        # text, so the probe must keep OCR on by returning False.
        with tempfile.TemporaryDirectory() as tmp:
            blank = Path(tmp) / "scanned.pdf"
            writer = PdfWriter()
            for _ in range(3):
                writer.add_blank_page(width=612, height=792)
            with blank.open("wb") as handle:
                writer.write(handle)
            self.assertFalse(docling_parser.has_rich_text_layer(blank))

    def test_missing_file_falls_back_to_ocr_on(self) -> None:
        # An unreadable path must not crash the reingest worker; the safe
        # default is "leave OCR on", so the probe returns False.
        self.assertFalse(docling_parser.has_rich_text_layer(FIXTURES_DIR / "does_not_exist.pdf"))

    def test_threshold_drives_the_decision(self) -> None:
        # A high enough min_avg_chars rejects even a born-digital page,
        # confirming the mean-chars comparison is what decides.
        self.assertFalse(
            docling_parser.has_rich_text_layer(
                FIXTURES_DIR / "single_column.pdf", min_avg_chars=10_000
            )
        )


class PdfPageCountTests(unittest.TestCase):
    def test_counts_pages_of_a_multipage_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "five_pages.pdf"
            writer = PdfWriter()
            for _ in range(5):
                writer.add_blank_page(width=612, height=792)
            with pdf.open("wb") as handle:
                writer.write(handle)
            self.assertEqual(docling_parser.pdf_page_count(pdf), 5)

    def test_counts_pages_of_a_fixture_pdf(self) -> None:
        # The single_column fixture is a one-page born-digital PDF.
        self.assertEqual(docling_parser.pdf_page_count(FIXTURES_DIR / "single_column.pdf"), 1)

    def test_non_pdf_extension_returns_none(self) -> None:
        # A real, readable file whose extension is not .pdf: pdf_page_count
        # must short-circuit on the suffix check and return None without
        # trying to parse it. test_missing_file_returns_none covers the
        # absent-file case; this proves the suffix check fires even when
        # the file is present on disk.
        with tempfile.TemporaryDirectory() as tmp:
            docx = Path(tmp) / "lecture.docx"
            docx.write_bytes(b"PK\x03\x04 stand-in for a .docx; only the suffix matters")
            self.assertIsNone(docling_parser.pdf_page_count(docx))

    def test_missing_file_returns_none(self) -> None:
        # An unreadable path must not crash the reingest worker.
        self.assertIsNone(docling_parser.pdf_page_count(FIXTURES_DIR / "does_not_exist.pdf"))


if __name__ == "__main__":
    unittest.main()
