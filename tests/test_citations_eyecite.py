"""Tests for the eyecite citation adapter and the case-verifier pre-filter.

The legacy `_CITATION_SHAPE` regex silently missed every reporter whose
abbreviation contains a digit (F.3d, F.Supp.2d, Cal.4th, N.Y.2d) because
its reporter character class excluded digits. eyecite catches them. These
tests pin both the adapter and the `_looks_like_legal_text` pre-filter.
"""

from __future__ import annotations

import unittest

from services.legal.case_verification import _looks_like_legal_text
from services.legal.citations_eyecite import CitationRef, find_citations, has_citation

# Reporters with an embedded digit: silently missed by the old regex.
DIGIT_REPORTERS = ["410 F.3d 138", "892 F.Supp.2d 1234", "22 Cal.4th 100", "123 N.Y.2d 456"]


class FindCitationsTests(unittest.TestCase):
    def test_digit_bearing_reporters_are_detected(self) -> None:
        for cite in DIGIT_REPORTERS:
            with self.subTest(cite=cite):
                refs = find_citations(f"See {cite} (holding X).")
                self.assertTrue(refs, f"expected a citation in {cite!r}")
                self.assertEqual("case", refs[0].kind)
                self.assertEqual(cite, refs[0].matched_text)

    def test_us_reporter_still_detected(self) -> None:
        refs = find_citations("Brown v. Board, 347 U.S. 483 (1954).")
        self.assertEqual(1, len(refs))
        self.assertEqual("347 U.S. 483", refs[0].matched_text)
        self.assertEqual("347", refs[0].volume)
        self.assertEqual("U.S.", refs[0].reporter)
        self.assertEqual("483", refs[0].page)

    def test_offsets_point_at_the_citation(self) -> None:
        text = "As held in 410 F.3d 138, the rule applies."
        refs = find_citations(text)
        self.assertEqual(1, len(refs))
        ref = refs[0]
        self.assertEqual(text[ref.start : ref.end], ref.matched_text)

    def test_plain_prose_has_no_citation(self) -> None:
        self.assertEqual([], find_citations("Mitosis separates duplicated chromosomes."))
        self.assertFalse(has_citation("No citations here at all."))

    def test_empty_text_is_safe(self) -> None:
        self.assertEqual([], find_citations(""))
        self.assertEqual([], find_citations("   "))

    def test_citation_ref_is_frozen(self) -> None:
        ref = find_citations("410 F.3d 138")[0]
        self.assertIsInstance(ref, CitationRef)
        with self.assertRaises(Exception):
            ref.page = "999"  # type: ignore[misc]


class PreFilterIntegrationTests(unittest.TestCase):
    def test_pre_filter_now_catches_digit_reporters(self) -> None:
        for cite in DIGIT_REPORTERS:
            with self.subTest(cite=cite):
                self.assertTrue(_looks_like_legal_text(f"See {cite}."))

    def test_pre_filter_still_catches_us_reporter(self) -> None:
        self.assertTrue(_looks_like_legal_text("Same-sex marriage was recognized in 576 U.S. 644."))

    def test_pre_filter_skips_plain_prose(self) -> None:
        self.assertFalse(_looks_like_legal_text("Mitosis separates duplicated chromosomes."))

    def test_pre_filter_skips_empty(self) -> None:
        self.assertFalse(_looks_like_legal_text(""))
        self.assertFalse(_looks_like_legal_text("   "))


if __name__ == "__main__":
    unittest.main()
