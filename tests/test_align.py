"""Never-mis-pin test suite for claim-to-draft alignment (Cachet PR5a).

This suite GATES PR5a. A mis-pinned claim is a trust failure exactly like a
mis-flag, so the rule is: a claim is PLACED only when its key resolves to ONE
unambiguous draft range; every ambiguity goes to the unplaced tray. The bulk of
these tests assert that ambiguity degrades to the tray, never to a wrong pin.
"""

from __future__ import annotations

import unittest

from services.legal.align import align_claims_to_draft, placement_to_dict


def claim(text: str, citations=None) -> dict:
    return {"text": text, "citations": citations or []}


def placed_segment(draft: str, placement) -> str | None:
    if not placement.placed:
        return None
    return draft[placement.char_start : placement.char_end]


class ExactPlacementTests(unittest.TestCase):
    def test_unique_long_claim_places_at_correct_offset(self) -> None:
        draft = "The panel reasoned that due process requires notice and a hearing."
        pl, unplaced = align_claims_to_draft(
            draft, [claim("due process requires notice and a hearing")]
        )
        self.assertEqual([], unplaced)
        self.assertTrue(pl[0].placed)
        self.assertEqual("exact", pl[0].method)
        self.assertEqual("due process requires notice and a hearing", placed_segment(draft, pl[0]))

    def test_quoted_span_in_claim_is_the_preferred_key(self) -> None:
        # The claim text carries a verbatim quoted span; it should locate via it.
        draft = (
            'The court wrote that the statute was "unconstitutional as applied" to the petitioner.'
        )
        c = claim('the opinion says it was "unconstitutional as applied" here')
        pl, unplaced = align_claims_to_draft(draft, [c])
        self.assertTrue(pl[0].placed)
        self.assertEqual("unconstitutional as applied", placed_segment(draft, pl[0]))

    def test_citation_quote_used_when_claim_text_is_paraphrase(self) -> None:
        draft = "The deprivation was not de minimis, the court concluded."
        c = claim(
            "the harm was more than trivial",  # paraphrase, not in draft
            citations=[{"quote": "The deprivation was not de minimis"}],
        )
        pl, unplaced = align_claims_to_draft(draft, [c])
        self.assertTrue(pl[0].placed)
        self.assertEqual("The deprivation was not de minimis", placed_segment(draft, pl[0]))


class NeverMisPinTests(unittest.TestCase):
    def test_no_match_goes_to_tray(self) -> None:
        draft = "The court held the statute valid."
        pl, unplaced = align_claims_to_draft(
            draft, [claim("an entirely different proposition about damages")]
        )
        self.assertFalse(pl[0].placed)
        self.assertEqual("unplaced", pl[0].method)
        self.assertEqual([0], unplaced)

    def test_repeated_short_key_without_disambiguator_goes_to_tray(self) -> None:
        # "the statute" appears 3x and is shorter than the min-key floor; with no
        # forward disambiguation it must NOT be pinned to a guess.
        draft = "the statute, the statute, and again the statute."
        pl, unplaced = align_claims_to_draft(draft, [claim("the statute")])
        self.assertFalse(pl[0].placed, "a generic repeated short key must go to the tray")
        self.assertEqual([0], unplaced)

    def test_two_claims_sharing_an_indistinguishable_phrase_both_tray(self) -> None:
        # The engine does NOT guarantee claims arrive in draft order, so two
        # claims sharing one long repeated phrase cannot be safely assigned to
        # the two occurrences (which one came from which sentence is unknowable
        # from content alone). The never-mis-pin rule sends both to the tray
        # rather than guess an assignment. (If the claims carried distinct
        # citation quotes, those would disambiguate and place them.)
        phrase = "the regulation exceeded the agency's statutory authority"
        draft = f"First, {phrase}. Later, {phrase}, the dissent agreed."
        pl, unplaced = align_claims_to_draft(draft, [claim(phrase), claim(phrase)])
        self.assertEqual([0, 1], unplaced)
        self.assertFalse(pl[0].placed or pl[1].placed)

    def test_distinct_claims_each_unique_phrase_place_independently(self) -> None:
        # The common case: two claims with different (unique) phrases each place
        # at their sole occurrence, order-independent.
        draft = "The statute was unconstitutional. Separately, the fee was unlawful."
        pl, unplaced = align_claims_to_draft(
            draft, [claim("the fee was unlawful"), claim("The statute was unconstitutional")]
        )
        self.assertEqual([], unplaced)
        self.assertTrue(pl[0].placed and pl[1].placed)
        # claim 0 ("the fee...") places later in the draft than claim 1, proving
        # placement follows the DRAFT, not the claim list order.
        self.assertGreater(pl[0].char_start, pl[1].char_start)

    def test_repeated_phrase_disambiguated_by_distinct_citation_quotes(self) -> None:
        # When claims sharing a repeated phrase carry DISTINCT citation quotes
        # whose text appears at the respective occurrences, the citation quote
        # (a higher-priority, more specific key) places each correctly.
        a = "the levy was upheld as a valid tax"
        draft = f"In 2019, {a}. In 2021, {a} once more."
        c0 = claim("paraphrase one", citations=[{"quote": f"In 2019, {a}"}])
        c1 = claim("paraphrase two", citations=[{"quote": f"In 2021, {a}"}])
        pl, unplaced = align_claims_to_draft(draft, [c0, c1])
        self.assertEqual([], unplaced)
        self.assertLess(pl[0].char_start, pl[1].char_start)


class NormalizationTests(unittest.TestCase):
    def test_smart_quote_and_whitespace_variance_still_places(self) -> None:
        # Draft has curly apostrophe + collapsed double space; key is straight.
        draft = "The District Court’s ruling   was reviewed de novo by the panel."
        pl, _ = align_claims_to_draft(
            draft, [claim("the District Court's ruling was reviewed de novo")]
        )
        self.assertTrue(pl[0].placed)
        # Segment maps back to the ORIGINAL draft form (curly apostrophe kept).
        self.assertIn("District Court", placed_segment(draft, pl[0]))

    def test_ligature_index_map_round_trip(self) -> None:
        # NFKC expands the fi-ligature; the offset must map back to the original.
        draft = "The oﬃce of the clerk filed the brief on time."  # "oﬃce" has U+FB03
        pl, _ = align_claims_to_draft(draft, [claim("office of the clerk filed the brief")])
        self.assertTrue(pl[0].placed)
        seg = placed_segment(draft, pl[0])
        self.assertIn("ce of the clerk filed the brief", seg)


class FuzzyPathTests(unittest.TestCase):
    """The 0-exact-occurrence fuzzy branch + its guards (finding [4])."""

    def test_fuzzy_unique_placement(self) -> None:
        # Key has a trailing typo, so no exact match, but a single contiguous
        # longest-match clears the 0.95 floor and re-locates uniquely. Fuzzy
        # repairs to the real draft span and places with method 'fuzzy'.
        draft = "The panel concluded the regulation was arbitrary and capricious under the APA."
        pl, _ = align_claims_to_draft(
            draft, [claim("the regulation was arbitrary and capricious under the APAx")]
        )
        self.assertTrue(pl[0].placed)
        self.assertEqual("fuzzy", pl[0].method)
        self.assertEqual(
            "the regulation was arbitrary and capricious under the APA",
            placed_segment(draft, pl[0]),
        )

    def test_fuzzy_below_floor_goes_to_tray(self) -> None:
        # A key that overlaps the draft only weakly (< 0.95) must not place.
        draft = "The agency promulgated a rule about widget safety standards."
        pl, unplaced = align_claims_to_draft(
            draft, [claim("an entirely unrelated holding on tax liability")]
        )
        self.assertFalse(pl[0].placed)
        self.assertEqual([0], unplaced)

    def test_fuzzy_match_not_uniquely_relocatable_goes_to_tray(self) -> None:
        # If the fuzzy-repaired span would occur in more than one place, do not
        # guess which: tray.
        rep = "the same boilerplate clause appears"
        draft = f"{rep} here, and {rep} there too."
        pl, unplaced = align_claims_to_draft(draft, [claim(f"{rep} somewhere")])
        self.assertFalse(pl[0].placed)
        self.assertEqual([0], unplaced)


class DegenerateInputTests(unittest.TestCase):
    def test_empty_draft_all_unplaced(self) -> None:
        pl, unplaced = align_claims_to_draft("", [claim("anything")])
        self.assertFalse(pl[0].placed)
        self.assertEqual([0], unplaced)

    def test_empty_claim_unplaced_no_crash(self) -> None:
        pl, unplaced = align_claims_to_draft("Some draft text here.", [claim("")])
        self.assertFalse(pl[0].placed)
        self.assertEqual([0], unplaced)

    def test_key_longer_than_draft_unplaced(self) -> None:
        pl, unplaced = align_claims_to_draft(
            "short.", [claim("a key far longer than the entire draft text body")]
        )
        self.assertFalse(pl[0].placed)
        self.assertEqual([0], unplaced)

    def test_every_claim_gets_exactly_one_placement(self) -> None:
        draft = "Alpha holds. Beta dissents. Gamma concurs."
        claims = [claim("Alpha holds"), claim("nowhere phrase"), claim("Gamma concurs")]
        pl, unplaced = align_claims_to_draft(draft, claims)
        self.assertEqual(3, len(pl))
        self.assertEqual([p.claim_index for p in pl], [0, 1, 2])
        self.assertEqual([1], unplaced)

    def test_non_dict_claim_keeps_unfiltered_index_and_does_not_shift_others(self) -> None:
        # A non-dict entry before real claims must NOT desync placement indices:
        # each real claim keeps its own placement, keyed by UNFILTERED index.
        draft = "Alpha holds firmly. Gamma concurs fully."
        claims = [None, claim("Alpha holds firmly"), claim("Gamma concurs fully")]
        pl, unplaced = align_claims_to_draft(draft, claims)
        by_index = {p.claim_index: p for p in pl}
        self.assertEqual([p.claim_index for p in pl], [0, 1, 2])
        self.assertFalse(by_index[0].placed)  # the non-dict
        self.assertIn(0, unplaced)
        self.assertEqual("Alpha holds firmly", placed_segment(draft, by_index[1]))
        self.assertEqual("Gamma concurs fully", placed_segment(draft, by_index[2]))


class SerializationTests(unittest.TestCase):
    def test_placement_to_dict_shape(self) -> None:
        draft = "due process requires notice and a hearing for all parties."
        pl, _ = align_claims_to_draft(draft, [claim("due process requires notice and a hearing")])
        d = placement_to_dict(pl[0])
        self.assertEqual({"char_start", "char_end", "placed", "method"}, set(d))
        self.assertTrue(d["placed"])
        self.assertEqual("exact", d["method"])

    def test_unplaced_to_dict_has_null_offsets(self) -> None:
        pl, _ = align_claims_to_draft("x.", [claim("not present")])
        d = placement_to_dict(pl[0])
        self.assertIsNone(d["char_start"])
        self.assertIsNone(d["char_end"])
        self.assertFalse(d["placed"])


if __name__ == "__main__":
    unittest.main()
