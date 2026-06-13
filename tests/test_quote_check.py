"""Cry-wolf test suite for the draft-quote-verbatim check (Cachet PR4).

This suite GATES PR4. The check's entire risk is false positives: a verification
tool that flags a correctly-quoted passage destroys the trust it sells. So the
bulk of these tests assert NOT-FLAGGED on legitimate Bluebook editing
conventions, a few assert FLAGGED on genuine alterations, and a few assert
COULD-NOT-CHECK (never flag) when the tool cannot honestly see the source.

Rule numbers map to the PR4 design's parser_rules.
"""

from __future__ import annotations

import unittest

from services.legal.quote_check import (
    QuoteCheckResult,
    SourceText,
    check_quote_against_sources,
    extract_draft_quotes,
    split_runs,
)

# A realistic opinion passage used as the source pool for most cases.
SOURCE = (
    "We review the District Court's grant of summary judgment de novo. "
    "The court held that the statute was unconstitutional as applied to the "
    "petitioner, and that due process requires notice and an opportunity to "
    "be heard. It reasoned that the deprivation was not de minimis."
)


def check(quote: str, sources=None) -> QuoteCheckResult:
    return check_quote_against_sources(quote, sources if sources is not None else [SOURCE])


class NotFlaggedTests(unittest.TestCase):
    """Legitimate quotes + Bluebook edits must never be flagged as altered."""

    def test_rule1_bracketed_capitalization(self) -> None:
        # "[T]he court held" for a source mid-sentence "the court held"
        r = check("[T]he court held that the statute was unconstitutional as applied")
        self.assertFalse(r.altered)
        self.assertFalse(r.unplaceable)

    def test_rule2_bracketed_insertion_absent_from_source(self) -> None:
        # "[allegedly]" is the author's interpolation; not in source, not flagged
        r = check("the statute was [allegedly] unconstitutional as applied")
        self.assertFalse(r.altered)
        self.assertNotIn("allegedly", " ".join(r.runs))

    def test_rule3_ascii_ellipsis_omission(self) -> None:
        r = check(
            "The court held that the statute was unconstitutional ... due process requires notice"
        )
        self.assertFalse(r.altered)

    def test_rule4_spaced_and_unicode_ellipsis(self) -> None:
        spaced = check("the statute was unconstitutional . . . due process requires notice")
        self.assertFalse(spaced.altered)
        unicode_ell = check("the statute was unconstitutional … due process requires notice")
        self.assertFalse(unicode_ell.altered)

    def test_rule5_editorial_brackets(self) -> None:
        for mark in [
            "[sic]",
            "[emphasis added]",
            "[citation omitted]",
            "[internal quotation marks omitted]",
        ]:
            r = check(f"due process requires notice {mark}")
            self.assertFalse(r.altered, f"{mark} must not be flagged")

    def test_rule6_smart_quotes_and_apostrophes(self) -> None:
        # curly apostrophe in the draft quote vs straight in source
        r = check("the District Court’s grant of summary judgment de novo")
        self.assertFalse(r.altered)

    def test_rule7_whitespace_and_linebreaks(self) -> None:
        r = check("due process requires notice    and an\nopportunity to be heard")
        self.assertFalse(r.altered)

    def test_rule8_dash_variants_fold(self) -> None:
        src = ["a cost–benefit analysis controls the de minimis inquiry"]  # en dash
        r = check("cost—benefit", src)  # em dash in the draft
        self.assertFalse(r.altered)

    def test_rule9_footnote_call_dropped(self) -> None:
        # Source has a footnote call "applied.5 It"; the correct quote drops it.
        src = ["the statute was unconstitutional as applied.5 It reasoned that the deprivation"]
        r = check("the statute was unconstitutional as applied. It reasoned", src)
        self.assertFalse(r.altered)

    def test_rule10_nested_attribution_words_present(self) -> None:
        src = ["the panel, quoting Mathews v. Eldridge, set out the balancing test"]
        r = check("quoting Mathews v. Eldridge", src)
        self.assertFalse(r.altered)

    def test_rule14_unbalanced_quotes_are_skipped(self) -> None:
        # An unbalanced quote mark in the draft yields no extracted span.
        self.assertEqual(
            [], extract_draft_quotes('the court said "the statute was unconstitutional')
        )

    def test_rule14_paraphrase_outside_quotes_not_checked(self) -> None:
        # Text with no quote marks is never extracted, so never checked.
        self.assertEqual([], extract_draft_quotes("the court basically said the law was bad"))

    def test_trailing_period_inside_closing_quote(self) -> None:
        # The dominant real-world false positive (review blocker): American
        # convention puts the period INSIDE the closing quote, but the source
        # continues mid-sentence. The run's edge period is trimmed before match.
        r = check("the statute was unconstitutional as applied to the petitioner.")
        self.assertFalse(r.altered, "a terminal period inside the quote must not flag")

    def test_nested_double_quotation_is_one_outer_span(self) -> None:
        # A block quote containing an internal quotation must be captured as ONE
        # outer span, not fragmented at the inner marks (review blocker).
        spans = extract_draft_quotes(
            'The panel wrote: "the statute defines a "vehicle" to include aircraft."'
        )
        self.assertEqual(1, len(spans))
        self.assertIn("to include aircraft", spans[0])

    def test_five_dot_ellipsis_leaves_no_residue_run(self) -> None:
        # 3+ dots collapse to one omission mark; no stray ".opportunity" run.
        self.assertEqual(
            ["due process requires notice", "an opportunity to be heard"],
            split_runs("due process requires notice ..... an opportunity to be heard"),
        )

    def test_nested_bracket_leaves_no_residue_run(self) -> None:
        # An interpolation containing a bracket leaves no "] applies" residue.
        self.assertEqual(["the rule", "applies"], split_runs("the rule [the Act [former]] applies"))

    def test_word_welded_digit_token_not_footnote_stripped(self) -> None:
        # A verbatim quote of a letter+digit token (statute names, product
        # marks) must not be corrupted by footnote stripping on the source.
        for token, src in [
            ("WD40", "the WD40 lubricant was at issue"),
            ("COVID19", "during the COVID19 pandemic the agency"),
            ("Chapter7", "a Chapter7 petition was filed"),
        ]:
            r = check(token, [src])
            self.assertFalse(r.altered, f"{token} must not be flagged (footnote over-strip)")


class FlaggedTests(unittest.TestCase):
    """Genuine alterations must be flagged."""

    def test_rule11_word_substitution_outside_marks(self) -> None:
        # "constitutional" where the source says "unconstitutional"
        r = check("the statute was constitutional as applied")
        self.assertTrue(r.altered)
        self.assertFalse(r.unplaceable)

    def test_rule12_fabricated_quotation(self) -> None:
        r = check("the court awarded treble damages to the plaintiff")
        self.assertTrue(r.altered)

    def test_real_misstatement_between_legit_edits_is_flagged(self) -> None:
        # Bracketed cap is fine, but "reversed" is not in the source ("held").
        r = check("[T]he court reversed that the statute was unconstitutional")
        self.assertTrue(r.altered)


class CouldNotCheckTests(unittest.TestCase):
    """When the tool cannot honestly see the source, degrade, never flag."""

    def test_rule13_no_source_pool(self) -> None:
        r = check("the statute was unconstitutional as applied", [])
        self.assertFalse(r.altered)
        self.assertTrue(r.unplaceable)

    def test_rule13_only_whitespace_sources(self) -> None:
        r = check("the statute was unconstitutional", ["", "   "])
        self.assertTrue(r.unplaceable)
        self.assertFalse(r.altered)

    def test_rule13_truncated_source_missing_run_is_unplaceable(self) -> None:
        # Source carries an explicit truncated=True flag; the run is absent from
        # the visible head, so it MAY live past the cut: could_not_check, not
        # altered. Truncation is a per-source FLAG now (not sentinel-sniffing).
        truncated = [
            SourceText("We review de novo. The court held that the statute", truncated=True)
        ]
        r = check("the deprivation was not de minimis", truncated)
        self.assertFalse(r.altered)
        self.assertTrue(r.unplaceable)

    def test_truncated_source_but_run_present_is_clean(self) -> None:
        # A truncated source does not force unplaceable when the run IS found.
        truncated = [SourceText("We review de novo. The court held the statute", truncated=True)]
        r = check("We review de novo.", truncated)
        self.assertFalse(r.altered)
        self.assertFalse(r.unplaceable)

    def test_misquote_masked_when_a_different_truncated_source_is_in_the_pool(self) -> None:
        # Brief-level pooling: a misquote of a complete source CANNOT be
        # distinguished from a correct quote of a truncated source's cut-off
        # tail, so the honest verdict is could_not_check, never altered. This is
        # the cry-wolf-safe resolution of finding [4] (no false flag).
        pool = [
            SourceText("The contract is governed by the laws of Delaware.", truncated=False),
            SourceText("In a sweeping opinion the panel concluded", truncated=True),
        ]
        r = check("the contract was rescinded by the parties", pool)
        self.assertFalse(r.altered)
        self.assertTrue(r.unplaceable)

    def test_cross_chunk_partial_sources_never_flag(self) -> None:
        # A quote straddling two adjacent retrieval chunks is in NEITHER single
        # chunk. Partial (complete=False) sources can never ground an altered
        # verdict: degrade to could_not_check (finding [3]).
        chunks = [
            SourceText("the court held that the statute", complete=False),
            SourceText("was unconstitutional as applied", complete=False),
        ]
        r = check("the statute was unconstitutional as applied", chunks)
        self.assertFalse(r.altered)
        self.assertTrue(r.unplaceable)


class ScopeLimitTests(unittest.TestCase):
    """The check confirms verbatim presence, not whether an omission misleads."""

    def test_rule15_ellipsis_juxtaposition_not_judged(self) -> None:
        # Both runs are verbatim; the ellipsis joins two true fragments in a
        # possibly-misleading way. The check is grounding, not truth: NOT flagged.
        r = check("due process requires notice ... the deprivation was not de minimis")
        self.assertFalse(r.altered)


class SplitRunsTests(unittest.TestCase):
    """Direct tests of the runs-between-edits parser."""

    def test_trailing_bracket_leaves_no_empty_run(self) -> None:
        self.assertEqual(
            ["due process requires notice"], split_runs("due process requires notice [sic]")
        )

    def test_leading_bracket_capitalization(self) -> None:
        self.assertEqual(["he court held"], split_runs("[T]he court held"))

    def test_ellipsis_splits_into_two_runs(self) -> None:
        self.assertEqual(
            ["the statute was unconstitutional", "due process requires notice"],
            split_runs("the statute was unconstitutional ... due process requires notice"),
        )

    def test_only_ellipsis_yields_no_runs(self) -> None:
        self.assertEqual([], split_runs("..."))


class PanelEnvelopeParityTests(unittest.TestCase):
    """The brief-level panel must accept what the sentence-level check accepts.

    The greedy straight-quote span regex deliberately merges two quoted phrases
    in one paragraph into a single span (the lawyer's connecting prose between
    them retained, with the inner marks). The sentence-level check splits that
    merged span back into its quoted phrases before matching; the panel check
    must do the same, or two individually verbatim quotes read "Not found
    verbatim" (the false accusation the product exists to never make). Same
    story for a quote whose leading capital was lowercased to embed
    mid-sentence: a universally accepted edit, accepted at the sentence level,
    must be accepted at the panel.
    """

    def test_two_straight_quoted_spans_in_one_paragraph_read_verbatim(self) -> None:
        draft = (
            'The court held "the statute was unconstitutional as applied to the '
            'petitioner" in plain terms. It added "due process requires notice and '
            'an opportunity to be heard" as well.'
        )
        quotes = extract_draft_quotes(draft)
        self.assertEqual(1, len(quotes))  # the deliberate greedy merge
        r = check(quotes[0])
        self.assertFalse(r.altered)
        self.assertFalse(r.unplaceable)

    def test_connecting_prose_between_merged_quotes_is_not_checked(self) -> None:
        # The prose between the two quoted phrases is the lawyer's own and may
        # say anything; it must never be matched against the source.
        draft = (
            'The court held "the statute was unconstitutional as applied to the '
            'petitioner" which utterly disposes of the appeal. It added "due process '
            'requires notice and an opportunity to be heard" too.'
        )
        quotes = extract_draft_quotes(draft)
        self.assertEqual(1, len(quotes))
        r = check(quotes[0])
        self.assertFalse(r.altered)
        self.assertFalse(r.unplaceable)

    def test_leading_capital_lowercased_to_embed_reads_verbatim(self) -> None:
        # Source sentence opens "The court held that ..."; the draft embeds it
        # mid-sentence as "the court held that ..." without the bracket
        # convention. Accepted at the sentence level; the panel must agree.
        r = check("the court held that the statute was unconstitutional as applied")
        self.assertFalse(r.altered)
        self.assertFalse(r.unplaceable)

    def test_interior_substitution_inside_a_quoted_phrase_still_flags(self) -> None:
        # Parity must not weaken the detector: a substituted interior word in a
        # single quoted phrase is still an alteration.
        draft = (
            'The court held "the statute was perfectly constitutional as applied to '
            'the petitioner" in plain terms. It added "due process requires notice '
            'and an opportunity to be heard" as well.'
        )
        quotes = extract_draft_quotes(draft)
        self.assertEqual(1, len(quotes))
        r = check(quotes[0])
        self.assertTrue(r.altered)

    def test_interior_case_substitution_still_flags(self) -> None:
        # Only the LEADING letter of a phrase may flex; interior case stays
        # strict so a rewritten interior word is caught.
        r = check("the court held that THE STATUTE was unconstitutional as applied")
        self.assertTrue(r.altered)


class PrepareSourcePoolTests(unittest.TestCase):
    """E1: the source pool is normalized ONCE per request and reused across every
    draft quote. `prepare_source_pool` + `check_quote_against_pool` must produce a
    result byte-identical to the single-shot `check_quote_against_sources`."""

    def test_pooled_check_matches_single_shot_for_every_quote(self) -> None:
        from services.legal.quote_check import (
            check_quote_against_pool,
            prepare_source_pool,
        )

        sources = [
            SOURCE,
            SourceText(text="An unrelated complete passage about venue and jurisdiction."),
            SourceText(text="A truncated fetch tail …", truncated=True),
            SourceText(text="A single retrieval chunk", complete=False),
        ]
        quotes = [
            "the court held that the statute was unconstitutional as applied",  # verbatim
            "the court held that THE STATUTE was unconstitutional as applied",  # altered
            "venue and jurisdiction",  # verbatim in a second source
            "language present in no source whatsoever",  # absent
            '"de novo" and "de minimis"',  # two phrases in one span
        ]
        # Normalize the pool exactly once, then check each quote against it.
        pool = prepare_source_pool(sources)
        for q in quotes:
            pooled = check_quote_against_pool(q, pool)
            single = check_quote_against_sources(q, sources)
            self.assertEqual(pooled.altered, single.altered, msg=f"altered diverged: {q!r}")
            self.assertEqual(
                pooled.unplaceable, single.unplaceable, msg=f"unplaceable diverged: {q!r}"
            )
            self.assertEqual(pooled.runs, single.runs, msg=f"runs diverged: {q!r}")

    def test_dedupe_does_not_change_verdict(self) -> None:
        from services.legal.quote_check import (
            check_quote_against_pool,
            prepare_source_pool,
        )

        # The same source repeated must not change any verdict (dedup is
        # behavior-preserving: a membership test is unaffected by duplicates).
        deduped = prepare_source_pool([SOURCE, SOURCE, SOURCE])
        single = prepare_source_pool([SOURCE])
        for q in ("the court held that the statute was unconstitutional as applied", "fabricated"):
            self.assertEqual(
                check_quote_against_pool(q, deduped).altered,
                check_quote_against_pool(q, single).altered,
            )

    def test_empty_pool_is_unplaceable(self) -> None:
        from services.legal.quote_check import (
            check_quote_against_pool,
            prepare_source_pool,
        )

        pool = prepare_source_pool([])
        self.assertFalse(pool.has_sources)
        r = check_quote_against_pool("anything at all here", pool)
        self.assertTrue(r.unplaceable)
        self.assertFalse(r.altered)


if __name__ == "__main__":
    unittest.main()
