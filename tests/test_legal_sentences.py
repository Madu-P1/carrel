"""Phase 3: the legal-aware sentence splitter must not fragment citations."""

from __future__ import annotations

import unittest

from services.legal.sentences import split_sentences


class SplitSentencesTests(unittest.TestCase):
    def test_does_not_split_inside_a_citation(self) -> None:
        out = split_sentences("See U.S. v. Smith, 410 F.3d 138. The court held X.")
        self.assertEqual(["See U.S. v. Smith, 410 F.3d 138.", "The court held X."], out)

    def test_does_not_split_inside_rule_abbreviations(self) -> None:
        out = split_sentences("Fed. R. Civ. P. 12 governs. It applies here.")
        self.assertEqual(["Fed. R. Civ. P. 12 governs.", "It applies here."], out)

    def test_single_sentence_is_returned_whole(self) -> None:
        self.assertEqual(["One sentence only."], split_sentences("One sentence only."))

    def test_empty_text_is_safe(self) -> None:
        self.assertEqual([], split_sentences(""))
        self.assertEqual([], split_sentences("   "))


if __name__ == "__main__":
    unittest.main()
