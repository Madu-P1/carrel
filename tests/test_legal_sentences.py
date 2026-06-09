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

    def test_spaced_reporter_cite_and_parenthetical_stay_whole(self) -> None:
        # Spaced reporters ("F. Supp. 2d", "So. 3d", "B.R.") and their trailing
        # "(court year)" parenthetical carry internal periods the abbreviation list
        # does not cover; the citation-span guard must keep each whole.
        for draft in (
            "The rule is in Smith v. Jones, 100 F. Supp. 2d 200 (S.D.N.Y. 2000), and binds here.",
            "See Doe v. Roe, 123 So. 3d 456 (Fla. 2013).",
            "In re Acme, 500 B.R. 100 (Bankr. D. Del. 2014), is on point.",
        ):
            self.assertEqual([draft], split_sentences(draft), draft)

    def test_plain_prose_ending_in_so_still_splits(self) -> None:
        # The fix must not over-merge ordinary prose: "so." is a sentence end, not a
        # Southern Reporter, when there is no citation span around it.
        self.assertEqual(
            ["I think so.", "The next point is separate."],
            split_sentences("I think so. The next point is separate."),
        )

    def test_quoted_holding_keeps_its_following_citation(self) -> None:
        # A quoted holding ("...unequal.") followed by its citation is ONE sentence,
        # not two: the closing-quote boundary must not sever a holding from the cite
        # that grounds it. (This is why a brief of quoted holdings without inline
        # citations collapses into one claim; that is the accepted trade.)
        out = split_sentences(
            'The Court held that "Separate educational facilities are inherently '
            'unequal." Brown v. Board of Education, 347 U.S. 483.'
        )
        self.assertEqual(1, len(out))


if __name__ == "__main__":
    unittest.main()
