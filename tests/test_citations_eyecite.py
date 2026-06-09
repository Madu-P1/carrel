"""Tests for the eyecite citation adapter and the case-verifier pre-filter.

The legacy `_CITATION_SHAPE` regex silently missed every reporter whose
abbreviation contains a digit (F.3d, F.Supp.2d, Cal.4th, N.Y.2d) because
its reporter character class excluded digits. eyecite catches them. These
tests pin both the adapter and the `_looks_like_legal_text` pre-filter.
"""

from __future__ import annotations

import unittest

from services.legal.case_verification import _looks_like_legal_text
from services.legal.citations_eyecite import (
    CitationRef,
    caption_match_state,
    caption_matches,
    find_citations,
    has_citation,
)


def _ref(plaintiff: str | None = None, defendant: str | None = None) -> CitationRef:
    """A CitationRef carrying only the caption fields caption_matches reads."""
    return CitationRef(
        matched_text="347 U.S. 483",
        start=0,
        end=12,
        kind="case",
        volume="347",
        reporter="U.S.",
        page="483",
        parenthetical=None,
        plaintiff=plaintiff,
        defendant=defendant,
    )


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


class CaptionMatchTests(unittest.TestCase):
    """caption_matches must tolerate legal abbreviation (so a correct cite is
    never flagged as a mismatch) while still catching a fabricated caption on a
    real reporter number (disjoint party names)."""

    def test_exact_caption_matches(self) -> None:
        self.assertTrue(
            caption_matches(_ref("Brown", "Board of Education"), "Brown v. Board of Education")
        )

    def test_partial_caption_matches(self) -> None:
        # Plaintiff only is a correct, terse caption, not a mismatch.
        self.assertTrue(caption_matches(_ref("Brown", None), "Brown v. Board of Education"))

    def test_abbreviated_sole_token_is_not_a_mismatch(self) -> None:
        # The only caption token is an abbreviation ("Educ." for "Education").
        # Exact set-intersection wrongly flags this; abbreviation-aware matching
        # must not. This is the narrow false-flag the review found.
        self.assertTrue(caption_matches(_ref(None, "Bd. of Educ."), "Board of Education"))

    def test_corporate_abbreviations_match(self) -> None:
        self.assertTrue(
            caption_matches(_ref("Acme Corp.", "Widget Co."), "Acme Corporation v. Widget Company")
        )
        self.assertTrue(caption_matches(_ref(None, "Dep't of Educ."), "Department of Education"))

    def test_fabricated_disjoint_caption_is_a_mismatch(self) -> None:
        self.assertFalse(caption_matches(_ref("Fake", "Nobody"), "Brown v. Board of Education"))

    def test_fabricated_caption_colliding_by_subsequence_is_a_mismatch(self) -> None:
        # The malpractice trap: keep a real reporter number, swap in fabricated
        # parties whose tokens are merely a subsequence/longer-form of the real
        # case's tokens ("bard" vs "board", "brownstein" vs "brown"). These MUST
        # flag as a mismatch, never pass as a clean verified citation.
        for plaintiff, defendant in [
            ("Bard", "Nook"),
            ("Brownstein", "Zelman"),
            ("Boardwalk", "Atlantic"),
            ("Brownie", "Smith"),
            ("Brownstone", "Carcosa"),
        ]:
            with self.subTest(caption=f"{plaintiff} v. {defendant}"):
                self.assertFalse(
                    caption_matches(_ref(plaintiff, defendant), "Brown v. Board of Education")
                )

    def test_nonprefix_legal_abbreviations_still_match(self) -> None:
        # Abbreviations that are consonant skeletons, not prefixes, must still match
        # via the curated table so a real abbreviated caption is never flagged.
        self.assertTrue(caption_matches(_ref(None, "Mfg."), "Manufacturing"))
        self.assertTrue(caption_matches(_ref(None, "Twp."), "Township"))
        self.assertTrue(caption_matches(_ref("Bros.", None), "Brothers"))

    def test_no_drafted_caption_is_never_a_mismatch(self) -> None:
        self.assertTrue(caption_matches(_ref(None, None), "Brown v. Board of Education"))

    def test_property_fabricated_unmarked_surnames_all_flag(self) -> None:
        # Property sweep, not 5 pinned strings: any fabricated party name (no period
        # mark) that merely prefixes / contains / subsequences a real Brown token must
        # be flagged when paired with a non-matching second party. This is the
        # malpractice-direction class the prefix matcher failed on.
        fabricated = [
            "Boar",
            "Bro",
            "Brow",
            "Educ",
            "Edu",
            "Educa",
            "Bard",
            "Beoward",
            "Brownie",
            "Brownstein",
            "Brownstone",
            "Boardwalk",
            "Educat",
            "Boa",
        ]
        for name in fabricated:
            with self.subTest(name=name):
                self.assertFalse(
                    caption_matches(_ref(name, "Zzqqx"), "Brown v. Board of Education"),
                    f"fabricated caption {name!r} passed as verified",
                )

    def test_property_marked_prefix_collisions_still_flag(self) -> None:
        # Adding a period does not launder a fabricated party: a near-equal marked
        # prefix ("Brow." for "Brown", "Boar." for "Board", "Bro." for "Brown") is a
        # collision, not an abbreviation (ratio >= 0.6), and must still flag.
        for name in ["Brow.", "Boar.", "Bro.", "Boar.'s"]:
            with self.subTest(name=name):
                self.assertFalse(
                    caption_matches(_ref(name, "Zzqqx"), "Brown v. Board of Education"),
                    f"marked-prefix fabrication {name!r} passed as verified",
                )

    def test_property_real_abbreviations_never_false_flag(self) -> None:
        # The other direction: real legal abbreviations (with their period/apostrophe
        # mark) must match their expansion, so a correct abbreviated caption is never
        # flagged.
        cases = [
            ("Educ.", "Education"),
            ("Corp.", "Corporation"),
            ("Dep't", "Department"),
            ("Comm'n", "Commission"),
            ("Ass'n", "Association"),
            ("Nat'l", "National"),
            ("Int'l", "International"),
            ("Univ.", "University"),
            ("Mfg.", "Manufacturing"),
            ("Twp.", "Township"),
            ("Bros.", "Brothers"),
            ("Inc.", "Incorporated"),
            ("Sec'y", "Secretary"),
            ("Comm'r", "Commissioner"),
        ]
        for abbrev, full in cases:
            with self.subTest(abbrev=abbrev):
                self.assertTrue(
                    caption_matches(_ref(abbrev, None), full),
                    f"real abbreviation {abbrev!r} wrongly flagged against {full!r}",
                )


class CaptionMatchStateTests(unittest.TestCase):
    """Per-side caption matching, three-state.

    The old any-token rule passed a caption when ANY draft token was compatible
    with ANY resolved token, so 'Smith v. Board' on Brown's number read verified
    off the single generic token 'board'. The state machine instead requires
    every POPULATED caption side to land at least one compatible token:
      - every populated side matches        -> "match" (verified path unchanged)
      - some side matches, some side fails  -> "unconfirmed" (refuse, never accuse)
      - no side matches anything            -> "mismatch" (the existing hard flag)
    A caption with no significant tokens on a side (initials like 'U.S.') leaves
    that side vacuous, and a bare cite with no caption is always a match, so a
    citation is never punished for what it does not say.
    """

    def test_half_matching_caption_is_unconfirmed_not_a_match(self) -> None:
        state = caption_match_state(_ref("Smith", "Board"), "Brown v. Board of Education")
        self.assertEqual("unconfirmed", state)

    def test_correct_caption_is_a_match(self) -> None:
        state = caption_match_state(
            _ref("Brown", "Board of Education"), "Brown v. Board of Education"
        )
        self.assertEqual("match", state)

    def test_abbreviated_caption_is_a_match(self) -> None:
        state = caption_match_state(_ref("Brown", "Bd. of Educ."), "Brown v. Board of Education")
        self.assertEqual("match", state)

    def test_wholly_wrong_caption_is_a_mismatch(self) -> None:
        state = caption_match_state(_ref("Loving", "Virginia"), "Brown v. Board of Education")
        self.assertEqual("mismatch", state)

    def test_bare_cite_without_caption_is_a_match(self) -> None:
        self.assertEqual("match", caption_match_state(_ref(None, None), "Brown v. Board"))

    def test_initialism_side_is_a_match(self) -> None:
        # 'NLRB' carries no abbreviation mark and is no token prefix, but it is
        # the initialism of the resolved plaintiff; the stricter per-side rule
        # must not flag the most common initialism captions.
        state = caption_match_state(
            _ref("NLRB", "Jones & Laughlin Steel Corp."),
            "National Labor Relations Board v. Jones & Laughlin Steel Corp.",
        )
        self.assertEqual("match", state)

    def test_initials_only_side_is_vacuous(self) -> None:
        # 'U.S.' yields no significant tokens, so the plaintiff side is vacuous
        # and the defendant side decides alone.
        state = caption_match_state(
            _ref("U.S.", "Carolene Products Co."),
            "United States v. Carolene Products Co.",
        )
        self.assertEqual("match", state)

    def test_reversed_parties_stay_a_match(self) -> None:
        # A reversed caption (cert posture) still names both real parties; each
        # side finds its token in the resolved name, so it is not punished.
        state = caption_match_state(
            _ref("Board of Education", "Brown"), "Brown v. Board of Education"
        )
        self.assertEqual("match", state)


if __name__ == "__main__":
    unittest.main()
