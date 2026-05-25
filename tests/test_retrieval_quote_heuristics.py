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

    def test_section_numbered_long_heading_fires(self) -> None:
        # T3 extension: section-numbered prefix bypasses length cap.
        long_chapter = (
            "Chapter 14: Modern Trial Procedure In Contemporary American Courts And Their Origins"
        )
        self.assertGreater(len(long_chapter), 80)
        self.assertTrue(is_heading_shape(long_chapter))

    def test_section_numbered_variants_fire(self) -> None:
        # T3: each section-numbered prefix bypasses length when other
        # gates are clean.
        long_tail = (
            "Definitions And Their Practical Application In Federal Litigation "
            "And Contemporary Jurisprudence"
        )
        for prefix in ("Chapter 3", "Section 4.2", "Part IV", "§ 7", "Sec. 12.1", "Pt. 3"):
            with self.subTest(prefix=prefix):
                quote = f"{prefix}: {long_tail}"
                self.assertGreater(len(quote), 80)
                self.assertTrue(is_heading_shape(quote))

    def test_section_numbered_with_terminal_period_keeps(self) -> None:
        # T3 false-drop guard: a long sentence opening "Chapter 3 ..."
        # that ends in a period stays. The terminal-punctuation gate
        # still applies on the bypass path.
        sentence = "Chapter 3 covers contract formation across the major common-law jurisdictions in detail."
        self.assertGreater(len(sentence), 80)
        self.assertFalse(is_heading_shape(sentence))

    def test_section_numbered_with_finite_verb_keeps(self) -> None:
        # T3 false-drop guard: even without terminal punctuation, a
        # verb-bearing sentence beginning with a section reference
        # keeps when the closed-class verb detector fires. The
        # detector is intentionally narrow (irregular list plus the
        # -ed/-ing/-en suffix set, no -s/-es so plural nouns don't
        # false-positive), so the test uses an irregular finite
        # verb (`has`) the detector recognises. The plan documents
        # that -s verbs ("covers", "offers") slip through; a
        # labeled-slice empirical run is the gate on a spaCy add.
        sentence_no_period = (
            "Chapter 3 has many sections on contract formation across the major "
            "common-law jurisdictions worldwide"
        )
        self.assertGreater(len(sentence_no_period), 80)
        self.assertFalse(is_heading_shape(sentence_no_period))

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

    def test_chapter_section_part_patterns_fire(self) -> None:
        # T3: chapter/section/part references in their bare form.
        for q in (
            "Chapter 3",
            "Ch. 5a",
            "Chap. 12",
            "Section 2.1",
            "Sec. 4.2.3",
            "Part IV",
            "Pt. 3",
            "§ 7",
            "§ 4.2",
        ):
            with self.subTest(q=q):
                self.assertTrue(is_bare_reference(q))

    def test_page_range_patterns_fire(self) -> None:
        # T3: page ranges with ASCII / en-dash / em-dash.
        for q in (
            "pp. 22-25",
            "pp 100-105",
            "pages 22-25",
            "p. 12-14",
            "pp. 22–25",
            "pp. 22—25",
        ):
            with self.subTest(q=q):
                self.assertTrue(is_bare_reference(q))

    def test_equation_formula_patterns_fire(self) -> None:
        # T3: equation / formula references.
        for q in (
            "Eq. 3",
            "Eq. 3.2",
            "Equation 12",
            "Equation 4.2a",
            "Formula 7",
            "Formula 1.1",
        ):
            with self.subTest(q=q):
                self.assertTrue(is_bare_reference(q))

    def test_appendix_exhibit_patterns_fire(self) -> None:
        # T3: appendix / exhibit references with single-letter or
        # numeric identifiers.
        for q in (
            "Appendix A",
            "App. B",
            "Exhibit 3",
            "Exh. 4",
            "Exhibit 4.2",
        ):
            with self.subTest(q=q):
                self.assertTrue(is_bare_reference(q))

    def test_real_sentence_does_not_fire(self) -> None:
        for q in (
            "Smith ran across the field",
            "12 apples are red",
            "See the figure for details",
            "The contract was formed in 2019",
            # T3 false-drop guards: prose that uses the same opening
            # word as a reference but is a real sentence.
            "Chapter 3 covers contract formation in detail",
            "Section 2.1 explains the next step",
            "The equation balances on both sides",
            "Appendix A contains the raw data tables",
            "Pages 22 to 25 cover the methodology",
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

    def test_chapter_reference_drives_structural(self) -> None:
        # T3: chapter / section / page-range / equation / appendix
        # references all funnel through `is_bare_reference` and
        # surface as structural.
        for q in (
            "Chapter 3",
            "Section 4.2",
            "Part IV",
            "pp. 22-25",
            "Eq. 3",
            "Equation 12",
            "Appendix A",
            "Exhibit 4.2",
        ):
            with self.subTest(q=q):
                self.assertTrue(is_structural_quote(q))

    def test_long_section_numbered_heading_drives_structural(self) -> None:
        # T3: the heading-shape length bypass exposes long
        # chapter-titled headings to the structural gate.
        long_chapter = "Chapter 14: Modern Trial Procedure In Contemporary American Courts"
        self.assertGreater(len(long_chapter), 60)
        self.assertTrue(is_structural_quote(long_chapter))

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
    def test_default_on(self) -> None:
        # T4 flipped the default-on 2026-05-25. Operators opt out by
        # setting RETRIEVAL_CHUNKS_HEURISTIC=false explicitly.
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RETRIEVAL_CHUNKS_HEURISTIC", None)
            self.assertTrue(chunks_heuristic_enabled())

    def test_true_keeps_on(self) -> None:
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
