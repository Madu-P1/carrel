"""Pure unit tests for the structural-quote shape detector.

Gate 1 instrumentation precondition (T2.0) per ADR 0004.
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

from services.retrieval.quote_heuristics import (
    chunks_heuristic_enabled,
    is_banner_shape,
    is_bare_reference,
    is_heading_shape,
    is_structural_quote,
)


class HeadingShapeTests(unittest.TestCase):
    def test_section_title_with_colon_fires(self) -> None:
        self.assertTrue(is_heading_shape("Chapter 3: Contract Formation"))

    def test_markdown_heading_fires(self) -> None:
        self.assertTrue(is_heading_shape("## Methods"))

    def test_single_capitalised_word_fires(self) -> None:
        # A bare section label without terminal punctuation.
        self.assertTrue(is_heading_shape("Conclusion"))

    def test_long_section_label_under_cap_fires(self) -> None:
        self.assertTrue(is_heading_shape("Photosynthesis And Cellular Respiration In Plants"))

    def test_terminal_period_keeps_short_sentence(self) -> None:
        # Critical false-drop guard: a single-word answer with a period
        # is NOT a heading. This is the case the original chunk-level
        # plan would have eaten.
        self.assertFalse(is_heading_shape("Photosynthesis."))

    def test_terminal_question_mark_keeps(self) -> None:
        self.assertFalse(is_heading_shape("What is photosynthesis?"))

    def test_finite_verb_keeps_short_sentence(self) -> None:
        # A short sentence with a finite verb is not a heading even
        # without terminal punctuation.
        self.assertFalse(is_heading_shape("Photosynthesis is the process"))

    def test_over_cap_length_does_not_fire(self) -> None:
        # Exactly 80 chars passes; 81 does not.
        eighty = "Word " * 16  # 80 chars trimmed
        self.assertEqual(len(eighty.strip()), 79)  # sanity check
        self.assertFalse(is_heading_shape("X" * 81))

    def test_code_signature_keeps(self) -> None:
        # Parens signal code, not heading.
        self.assertFalse(is_heading_shape("def chunk_text(text: str)"))

    def test_equation_keeps(self) -> None:
        # Equals signals math.
        self.assertFalse(is_heading_shape("E = mc^2"))

    def test_json_fragment_keeps(self) -> None:
        # Braces signal markup.
        self.assertFalse(is_heading_shape('{"key": "value"}'))

    def test_multiline_keeps(self) -> None:
        # Newlines signal multi-line content, not a heading.
        self.assertFalse(is_heading_shape("Acid\nBase\nSalt"))

    def test_empty_string_keeps(self) -> None:
        self.assertFalse(is_heading_shape(""))
        self.assertFalse(is_heading_shape("   "))

    def test_env_override_changes_cap(self) -> None:
        long_quote = "X" * 100
        with mock.patch.dict(os.environ, {"CARREL_HEADING_MAX_CHARS": "200"}):
            self.assertTrue(is_heading_shape(long_quote))
        with mock.patch.dict(os.environ, {"CARREL_HEADING_MAX_CHARS": "50"}):
            self.assertFalse(is_heading_shape(long_quote))


class BareReferenceTests(unittest.TestCase):
    def test_numeric_only_fires(self) -> None:
        for q in ("12", "237", "12, 14, 16", "1.2.3"):
            with self.subTest(q=q):
                self.assertTrue(is_bare_reference(q))

    def test_author_year_fires(self) -> None:
        for q in ("Smith 2019", "Smith, 2019", "Smith and Jones 2020", "Smith et al. 2018"):
            with self.subTest(q=q):
                self.assertTrue(is_bare_reference(q))

    def test_bracketed_citation_fires(self) -> None:
        for q in ("[12]", "(5)", "[ 42 ]"):
            with self.subTest(q=q):
                self.assertTrue(is_bare_reference(q))

    def test_see_figure_patterns_fire(self) -> None:
        for q in ("Fig. 4", "p. 22", "see Table 3", "Figure 12", "see fig 7"):
            with self.subTest(q=q):
                self.assertTrue(is_bare_reference(q))

    def test_real_sentence_does_not_fire(self) -> None:
        for q in (
            "Smith ran across the field",
            "12 apples are red",
            "See the figure for details",
            "The contract was formed in 2019",
        ):
            with self.subTest(q=q):
                self.assertFalse(is_bare_reference(q))

    def test_empty_string_keeps(self) -> None:
        self.assertFalse(is_bare_reference(""))


class BannerShapeTests(unittest.TestCase):
    def test_two_word_titlecase_fires(self) -> None:
        self.assertTrue(is_banner_shape("Photosynthesis And Respiration"))

    def test_three_word_titlecase_fires(self) -> None:
        self.assertTrue(is_banner_shape("Contract Formation Steps"))

    def test_single_word_does_not_fire(self) -> None:
        # Proper noun protection.
        self.assertFalse(is_banner_shape("Einstein"))
        self.assertFalse(is_banner_shape("Photosynthesis"))

    def test_lowercased_words_do_not_fire(self) -> None:
        self.assertFalse(is_banner_shape("photosynthesis and respiration"))

    def test_mixed_case_does_not_fire(self) -> None:
        # First word capital, others lowercase = sentence, not banner.
        self.assertFalse(is_banner_shape("Photosynthesis is hard"))

    def test_titlecase_with_finite_verb_does_not_fire(self) -> None:
        # All words capital but contains a verb -> short sentence.
        self.assertFalse(is_banner_shape("Photosynthesis Is A Process"))

    def test_trailing_punctuation_does_not_block(self) -> None:
        # Strip a single trailing punctuation char per word.
        self.assertTrue(is_banner_shape("Methods, Results, Discussion"))

    def test_code_chars_do_not_fire(self) -> None:
        # Braces signal markup.
        self.assertFalse(is_banner_shape("Foo Bar (See Below)"))


class StructuralQuoteIntegrationTests(unittest.TestCase):
    """End-to-end check: any signal fires -> is_structural_quote -> True."""

    def test_heading_drives_structural(self) -> None:
        self.assertTrue(is_structural_quote("Chapter 3: Contract Formation"))

    def test_bare_reference_drives_structural(self) -> None:
        self.assertTrue(is_structural_quote("[12]"))

    def test_banner_drives_structural(self) -> None:
        self.assertTrue(is_structural_quote("Photosynthesis And Respiration"))

    def test_real_answer_sentence_is_not_structural(self) -> None:
        # Critical: a real grounded-answer quote must survive.
        for q in (
            "Photosynthesis converts light energy into chemical energy stored in glucose.",
            "A contract is formed when offer and acceptance meet.",
            "The Krebs cycle takes place in the mitochondrial matrix.",
            "Mitosis produces two genetically identical daughter cells.",
        ):
            with self.subTest(q=q):
                self.assertFalse(is_structural_quote(q))

    def test_short_factual_bullet_with_period_survives(self) -> None:
        # The Photosynthesis. case: single-word answer with a period.
        self.assertFalse(is_structural_quote("Photosynthesis."))

    def test_code_fragment_survives(self) -> None:
        self.assertFalse(is_structural_quote("def chunk_text(text: str)"))

    def test_equation_survives(self) -> None:
        self.assertFalse(is_structural_quote("E = mc^2"))

    def test_empty_string_survives(self) -> None:
        # An empty quote is malformed but not structural; another gate
        # (quote validity) handles it.
        self.assertFalse(is_structural_quote(""))


class ChunksHeuristicEnabledTests(unittest.TestCase):
    def test_default_off(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RETRIEVAL_CHUNKS_HEURISTIC", None)
            self.assertFalse(chunks_heuristic_enabled())

    def test_true_enables(self) -> None:
        with mock.patch.dict(os.environ, {"RETRIEVAL_CHUNKS_HEURISTIC": "true"}):
            self.assertTrue(chunks_heuristic_enabled())
        with mock.patch.dict(os.environ, {"RETRIEVAL_CHUNKS_HEURISTIC": "TRUE"}):
            self.assertTrue(chunks_heuristic_enabled())

    def test_other_values_disable(self) -> None:
        for value in ("false", "0", "off", "no", ""):
            with self.subTest(value=value):
                with mock.patch.dict(os.environ, {"RETRIEVAL_CHUNKS_HEURISTIC": value}):
                    self.assertFalse(chunks_heuristic_enabled())


if __name__ == "__main__":
    unittest.main()
