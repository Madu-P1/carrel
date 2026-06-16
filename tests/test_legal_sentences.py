"""Phase 3: the legal-aware sentence splitter must not fragment citations."""

from __future__ import annotations

import unittest

from services.legal.sentences import split_sentences, split_sentences_with_groups


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

    def test_newlines_split_punctuation_free_slide_text(self) -> None:
        # Slide / bullet drafts carry no terminal punctuation. A [.!?]-only split
        # would collapse the whole draft into ONE sentence, which is the root cause
        # of the verify surface flagging the whole draft as a single claim. Hard
        # line boundaries must split it into the three bullets the reader sees.
        draft = (
            "For Covered Group, 16% - 10%= 6% (60 billion for 6%= 1,2 billion) are "
            "extra margins to be partially allocated to Market States based on a 25% "
            "Formula: so, 300 mln to be allocated to Market States exceeding the threshold\n"
            "Allocation key: turnover (10% Italy, 20% France, 10% Spain, 10% Germany)\n"
            "Result: 30 mln Amount A taxable in Italy, 30 mln Amount A taxable in France"
        )
        out = split_sentences(draft)
        self.assertEqual(3, len(out))
        self.assertTrue(out[1].startswith("Allocation key:"))
        self.assertTrue(out[2].startswith("Result:"))

    def test_blank_lines_and_crlf_do_not_yield_empty_sentences(self) -> None:
        # \r\n and runs of blank lines must collapse, never emit an empty segment
        # (an empty claim would mis-align and pollute the coverage denominator).
        out = split_sentences("First line\r\n\r\n\nSecond line\n   \nThird line")
        self.assertEqual(["First line", "Second line", "Third line"], out)

    def test_multi_sentence_line_still_splits_within_the_line(self) -> None:
        # Newline splitting is additive: a line carrying real terminal punctuation
        # is still sentence-split within the line, so prose drafts are unchanged.
        out = split_sentences("First point. Second point.\nA third on its own line.")
        self.assertEqual(["First point.", "Second point.", "A third on its own line."], out)

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


class SlideBulletSegmentationTests(unittest.TestCase):
    """Property-style coverage for slide / bullet / outline drafts (S1).

    These pin the CURRENT splitter contract on the inputs a lawyer actually
    pastes from a deck: leading bullet glyphs, leading tabs, blank-line and
    CRLF runs, and the degenerate single-line paste. They are characterization
    tests: they assert what the splitter does today so a future change to the
    segmentation contract has to update them on purpose, not by accident.
    """

    # The six bullet/list glyphs a slide paste puts at the start of a line.
    BULLET_GLYPHS = ("•", "-", "*", "◦", "–", "—")

    # A corpus exercised by the invariant properties below. Each entry is a
    # realistic slide / outline draft; mixed glyphs, tabs, CRLF, and blank-line
    # runs are all represented so the properties hold across the whole space,
    # not one happy path.
    def _corpus(self) -> list[str]:
        glyph_blocks = [f"{g} First point\n{g} Second point" for g in self.BULLET_GLYPHS]
        return [
            *glyph_blocks,
            "\tFirst point\n\tSecond point",
            "  \t • Indented bullet\n\t- Tabbed bullet",
            "Alpha line\r\n\r\nBeta line\r\nGamma line",
            "Alpha\r\n   \n\nBeta",
            "Intro line.\n• bullet one\n• bullet two\nClose. Done.",
            "• one • two • three",
        ]

    def test_every_segment_is_stripped_and_nonempty(self) -> None:
        # No returned sentence carries edge whitespace or is empty. An empty or
        # padded segment would mis-align and pollute the coverage denominator.
        for draft in self._corpus():
            for seg in split_sentences(draft):
                self.assertTrue(seg, f"empty segment from {draft!r}")
                self.assertEqual(seg, seg.strip(), f"unstripped segment from {draft!r}")

    def test_no_segment_carries_a_line_break(self) -> None:
        # Line breaks are segment boundaries, so no boundary character may
        # survive inside a returned sentence.
        for draft in self._corpus():
            for seg in split_sentences(draft):
                self.assertNotIn("\n", seg, f"newline survived in segment from {draft!r}")
                self.assertNotIn("\r", seg, f"carriage return survived from {draft!r}")

    def test_every_segment_is_a_substring_of_the_draft(self) -> None:
        # The alignment layer (services.legal.align) relies on each returned
        # sentence being a verbatim, whitespace-collapsed substring of the draft
        # so it can place every line back in the document. Pin that invariant.
        for draft in self._corpus():
            for seg in split_sentences(draft):
                self.assertIn(seg, draft, f"segment {seg!r} is not a substring of {draft!r}")

    def test_leading_bullet_glyph_is_preserved_one_segment_per_line(self) -> None:
        # A bullet glyph at the start of a line is NOT whitespace: it stays on
        # the segment. Each bullet line becomes exactly one sentence, with the
        # glyph intact, for every glyph variant.
        for glyph in self.BULLET_GLYPHS:
            draft = f"{glyph} First point\n{glyph} Second point\n{glyph} Third point"
            self.assertEqual(
                [f"{glyph} First point", f"{glyph} Second point", f"{glyph} Third point"],
                split_sentences(draft),
                f"glyph {glyph!r}",
            )

    def test_leading_tabs_are_stripped(self) -> None:
        # Tabs ARE whitespace, so a leading tab is removed (unlike a bullet
        # glyph). A tab does not itself split a line; only \r and \n do.
        self.assertEqual(
            ["First point", "Second point"],
            split_sentences("\tFirst point\n\t\tSecond point"),
        )
        # A tab between two fragments on a single line is preserved (it is
        # neither a line boundary nor edge whitespace) and yields one segment.
        self.assertEqual(["First\tSecond"], split_sentences("First\tSecond"))

    def test_blank_line_and_crlf_runs_yield_one_segment_per_content_line(self) -> None:
        # Runs of blank lines and CRLF pairs collapse: the segment count equals
        # the number of non-blank physical lines, with no empty segments.
        draft = "Alpha\r\n\r\n\nBeta\n   \n\tGamma\r\n"
        self.assertEqual(["Alpha", "Beta", "Gamma"], split_sentences(draft))

    def test_single_line_slide_paste_is_the_known_limitation(self) -> None:
        # KNOWN LIMITATION: when a slide paste arrives as one physical line with
        # no terminal punctuation, there is no boundary to split on, so the whole
        # line collapses to ONE segment even though it reads as three bullets.
        # Splitting mid-line on a bullet glyph is not done because a leading "-"
        # is ambiguous with a hyphenated phrase and a "*" with emphasis; only a
        # hard line break is treated as an authoritative boundary. Pin the
        # collapse so a future intra-line bullet splitter is a deliberate change.
        draft = "• First point • Second point • Third point"
        self.assertEqual([draft], split_sentences(draft))
        # The same content WITH newlines does segment, confirming the limitation
        # is specifically the missing line break, not the glyph.
        self.assertEqual(
            ["• First point", "• Second point", "• Third point"],
            split_sentences("• First point\n• Second point\n• Third point"),
        )


class SplitSentencesWithGroupsTests(unittest.TestCase):
    """The grouping map merges segments a SOFT line wrap split, while keeping the
    surface per-line and never merging across a real sentence boundary. This is the
    attribution unit the altered-quote check pools by; a hard-wrapped quote and its
    citation must land in one group or the litigator refusal silently stops firing.
    """

    def test_segments_match_split_sentences_exactly(self) -> None:
        # The surface is unchanged: the segments returned are byte-identical to
        # split_sentences, so the per-line claim surface and alignment are untouched.
        draft = 'A quoted holding "is split" across\ntwo lines here, Brown, 347 U.S. 483.'
        segments, groups = split_sentences_with_groups(draft)
        self.assertEqual(split_sentences(draft), segments)
        self.assertEqual(len(segments), len(groups))

    def test_soft_wrapped_sentence_segments_share_one_group(self) -> None:
        # A single logical sentence hard-wrapped across two physical lines: two
        # surface segments, ONE logical group, so an attribution pass can pool them.
        segments, groups = split_sentences_with_groups(
            'The Court observed that "X is Y" in\nthe modern context, Brown, 347 U.S. 483.'
        )
        self.assertEqual(2, len(segments))
        self.assertEqual([0, 0], groups)

    def test_real_period_boundary_on_one_line_stays_two_groups(self) -> None:
        # Proximity is not attribution: two real sentences sharing one physical line
        # are two groups, so a quote in one is never pooled with a cite in the other.
        # (A period followed by a closing quote is deliberately NOT a boundary, per
        # the closing-quote rule, so this uses a plain period boundary.)
        segments, groups = split_sentences_with_groups(
            "It announced the rule plainly. The authority is Brown, 347 U.S. 483."
        )
        self.assertEqual(2, len(segments))
        self.assertEqual([0, 1], groups)

    def test_blank_line_paragraphs_are_distinct_groups(self) -> None:
        segments, groups = split_sentences_with_groups(
            "First sentence ends here.\n\nSecond sentence begins anew."
        )
        self.assertEqual(2, len(segments))
        self.assertEqual([0, 1], groups)

    def test_single_line_input_is_identity_grouped(self) -> None:
        # No newline -> segments == logical sentences -> each its own group, so the
        # litigator-only single-line path is byte-identical to the pre-fix behavior.
        segments, groups = split_sentences_with_groups("One sentence. Two sentence.")
        self.assertEqual(["One sentence.", "Two sentence."], segments)
        self.assertEqual([0, 1], groups)

    def test_empty_input_is_empty(self) -> None:
        self.assertEqual(([], []), split_sentences_with_groups("   \n  "))

    def test_citation_bearing_soft_wrap_still_groups(self) -> None:
        # Guard against silent re-regression. The grouping relies on the per-line
        # splitter and the whole-draft splitter agreeing after whitespace-collapse;
        # both call find_citations on DIFFERENT text (one line vs the whole draft),
        # so a future change to citation detection could make a per-line segment stop
        # being a prefix of its logical sentence, firing the identity fallback and
        # silently re-stranding a wrapped quote from the cite that grounds it. Pin
        # that a citation-bearing soft wrap stays ONE group (fallback does NOT fire).
        for draft in (
            'The Court wrote "A is B" in\nBrown v. Board of Education, 347 U.S. 483 (1954).',
            'It announced that "A is B," see\nBrown v. Board of Education, 347 U.S. 483.',
        ):
            segments, groups = split_sentences_with_groups(draft)
            self.assertEqual(2, len(segments), draft)
            self.assertEqual([0, 0], groups, f"identity fallback wrongly fired on: {draft!r}")

    def test_groups_are_contiguous_and_monotonic(self) -> None:
        # A group never reappears after a later group starts (segments stay in
        # reading order), so members of a group are always a contiguous run.
        _, groups = split_sentences_with_groups(
            'Held that "A is B" in\nthe text, Brown, 347 U.S. 483. '
            "A new point begins.\nAnd it wraps on, too."
        )
        for earlier, later in zip(groups, groups[1:]):
            self.assertIn(later, (earlier, earlier + 1))


if __name__ == "__main__":
    unittest.main()
