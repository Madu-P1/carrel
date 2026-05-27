"""Regression tests for the AFM hollow-answer guard (T64 Phase 4).

Pins the OR semantics documented in `ai/afm_client.py::_answer_looks_substantive`
and ADR-0009 §Risk. The canonical pass case `"Mitochondria produce ATP."` (25
chars) must pass via the sentence-shape branch; heading-shaped output like
`"MITOSIS"` must fail.

Auditor finding (verdict de4ba41f4f01eb73, 2026-05-27): the initial implementation
shipped strict-AND semantics that would have false-rejected the documented
canonical example. This file pins the contract so future tuning preserves the
shape.
"""

from __future__ import annotations

import unittest

from ai.afm_client import _answer_looks_substantive


class AnswerLooksSubstantiveTests(unittest.TestCase):
    """Pin the OR semantics described in the helper docstring + ADR-0009."""

    def test_canonical_one_line_sentence_passes_via_sentence_shape(self) -> None:
        """The exact example cited in the helper docstring + ADR-0009."""
        self.assertTrue(_answer_looks_substantive("Mitochondria produce ATP."))

    def test_long_answer_passes_via_length_branch(self) -> None:
        """An answer >= 40 chars passes even without terminal punctuation."""
        answer = "this is a long enough explanation without any trailing dot"
        assert len(answer) >= 40
        self.assertTrue(_answer_looks_substantive(answer))

    def test_pure_heading_fails(self) -> None:
        """The original hollow-answer bug: a single-token uppercase heading."""
        self.assertFalse(_answer_looks_substantive("MITOSIS"))

    def test_multi_word_heading_without_terminal_punct_fails(self) -> None:
        """Heading-style fragment with a space but no period."""
        self.assertFalse(_answer_looks_substantive("Chapter 3 Section A"))

    def test_empty_answer_fails(self) -> None:
        """Empty string never passes."""
        self.assertFalse(_answer_looks_substantive(""))

    def test_short_sentence_with_question_mark_passes(self) -> None:
        """? and ! terminal punctuation are honored alongside period."""
        self.assertTrue(_answer_looks_substantive("Why ATP?"))
        self.assertTrue(_answer_looks_substantive("Right answer!"))

    def test_single_word_with_period_fails_no_space(self) -> None:
        """A single token with a trailing period still has no space, so it fails the sentence-shape branch."""
        self.assertFalse(_answer_looks_substantive("Mitochondria."))

    def test_sentence_shape_with_trailing_whitespace_passes(self) -> None:
        """rstrip applies before the terminal-punctuation check."""
        self.assertTrue(_answer_looks_substantive("Cells divide.   "))


if __name__ == "__main__":
    unittest.main()
