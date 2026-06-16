"""Phase 6: deterministic contract-claim verification (the gold parametric case)."""

from __future__ import annotations

import unittest

from services.legal.anchors import Anchor, extract_anchors
from services.legal.contract_verify import (
    ClauseCandidate,
    ClauseVerdict,
    _durations_match,
    adjudicate_clause_candidates,
    verify_claim_against_clause,
)


class DurationUnitFallbackTests(unittest.TestCase):
    def test_unitless_anchor_falls_back_to_the_tolerant_compare(self) -> None:
        # Pins the documented fallback in _durations_match: when an anchor's
        # unit cannot be re-derived from its text (the detector normally
        # guarantees a unit word), the compare falls back to the tolerant
        # cross-unit rule, the lenient pre-existing behavior, rather than
        # silently failing closed into a contradiction.
        near = _durations_match(
            Anchor("duration", "approximately 360", 0, 17, 360.0),
            Anchor("duration", "365 days", 0, 8, 365.0),
        )
        far = _durations_match(
            Anchor("duration", "approximately 300", 0, 17, 300.0),
            Anchor("duration", "365 days", 0, 8, 365.0),
        )
        self.assertTrue(near)  # within 5%: the tolerant fallback accepts
        self.assertFalse(far)  # beyond 5%: still a contradiction


class ParametricContradictionTests(unittest.TestCase):
    def test_money_mismatch_is_a_contradiction(self) -> None:
        v = verify_claim_against_clause(
            "Liability is capped at $1,000,000.",
            "the aggregate liability of the parties shall not exceed $500,000",
        )
        self.assertEqual("parametric_contradiction", v.disposition)
        self.assertEqual("money", v.anchor_type)

    def test_word_form_money_mismatch_is_a_contradiction(self) -> None:
        # The AI summary drops the numeral ("one million dollars"); the executed
        # contract carries the digit ($500,000). The spelled-out claim must still be
        # caught as a contradiction, not slip to an honest could-not-check.
        v = verify_claim_against_clause(
            "The liability cap is one million dollars.",
            "in no event shall the aggregate liability exceed $500,000",
        )
        self.assertEqual("parametric_contradiction", v.disposition)
        self.assertEqual("money", v.anchor_type)

    def test_word_form_money_match_is_not_affirmed(self) -> None:
        # The spelled-out amount agrees with the numeral, but ADR-0013 scope-out never
        # affirms a figure; this is could-not-check, not a green.
        v = verify_claim_against_clause(
            "The liability cap is one million dollars.",
            "liability is capped at $1,000,000 in the aggregate",
        )
        self.assertEqual("not_found", v.disposition)

    def test_duration_mismatch_is_a_contradiction(self) -> None:
        v = verify_claim_against_clause(
            "Confidentiality survives termination for 5 years.",
            "the confidentiality obligations shall survive for two (2) years",
        )
        self.assertEqual("parametric_contradiction", v.disposition)
        self.assertEqual("duration", v.anchor_type)

    def test_equivalent_durations_are_not_a_contradiction(self) -> None:
        # 12 months and 1 year are the same term; the day-count approximation
        # must not flag them as a contradiction. (Scope-out: not affirmed either, so
        # the durable property is simply "never a contradiction".)
        v = verify_claim_against_clause(
            "The term is 12 months.",
            "this Agreement shall continue for a period of 1 year",
        )
        self.assertNotEqual("parametric_contradiction", v.disposition)

    def test_same_unit_near_miss_duration_is_a_contradiction(self) -> None:
        # The 5% tolerance exists ONLY to bridge the day-count approximation
        # across units (12 months vs 1 year). Within one unit there is no
        # approximation to bridge: 23 months and 24 months are simply different
        # terms, and reading the near-miss as "present" both verifies a wrong
        # value and prints a false detail ("23 months appears in ...").
        v = verify_claim_against_clause(
            "The non-compete lasts 23 months following termination.",
            "Section 9.1. The employee shall not compete for a period of 24 months.",
        )
        self.assertEqual("parametric_contradiction", v.disposition)
        self.assertEqual("duration", v.anchor_type)

    def test_same_unit_day_count_basis_is_a_contradiction(self) -> None:
        # 360 vs 365 days is a real financial term difference (day-count basis),
        # 1.4% apart; the blanket tolerance read it as "present".
        v = verify_claim_against_clause(
            "Interest accrues on a 360 days basis.",
            "Section 4.2. Interest shall be computed on the basis of a year of 365 days.",
        )
        self.assertEqual("parametric_contradiction", v.disposition)
        self.assertEqual("duration", v.anchor_type)

    def test_matching_amount_does_not_mask_a_falsified_date(self) -> None:
        # Cross-type: a matching $500,000 must NOT short-circuit to "present" and
        # hide a wrong date in the same sentence. A contradiction in ANY anchor type
        # wins, so the engine cannot be laundered by leading with a correct value.
        v = verify_claim_against_clause(
            "The cap is $500,000, effective March 11, 2024.",
            "liability shall not exceed $500,000; executed on March 11, 2023",
        )
        self.assertEqual("parametric_contradiction", v.disposition)
        self.assertEqual("date", v.anchor_type)


class PresentTests(unittest.TestCase):
    def test_matching_money_value_is_not_affirmed(self) -> None:
        # ADR-0013 scope-out: a matching money value is could-not-check, not a green.
        v = verify_claim_against_clause(
            "The cap is $500,000.",
            "liability shall not exceed $500,000 in the aggregate",
        )
        self.assertEqual("not_found", v.disposition)
        self.assertIn("not independently verified", v.detail)

    def test_quoted_language_present_verbatim(self) -> None:
        v = verify_claim_against_clause(
            'The agreement says it will "survive termination" of the contract.',
            "These obligations survive termination of this Agreement for any reason.",
        )
        self.assertEqual("present", v.disposition)
        self.assertEqual("quote", v.anchor_type)

    def test_word_form_money_match_routes_to_could_not_check(self) -> None:
        # Used to assert filing-grade "present" detail accuracy for a word-form match.
        # ADR-0013 scope-out: no figure present, so it is an honest could-not-check.
        v = verify_claim_against_clause(
            "The liability cap is one million dollars.",
            "liability is capped at $1,000,000 in the aggregate",
        )
        self.assertEqual("not_found", v.disposition)
        self.assertIn("not independently verified", v.detail)

    def test_cross_unit_tolerant_duration_match_is_not_affirmed(self) -> None:
        # A tolerant cross-unit duration match used to read "present (consistent with)".
        # ADR-0013 scope-out no longer affirms a figure, so it is could-not-check.
        v = verify_claim_against_clause(
            "The term is 12 months.",
            "this Agreement shall continue for a period of 1 year",
        )
        self.assertEqual("not_found", v.disposition)
        self.assertIn("not independently verified", v.detail)

    def test_polarity_present_detail_never_asserts_text_the_clause_lacks(self) -> None:
        # F2 (final pre-merge review): equal polarity canonicals can have
        # different surfaces ("non-exclusive" vs "nonexclusive"); the present
        # detail must say "matches", never that the claim's form appears in
        # the clause. Same filing-grade rule the other parametric types pin.
        v = verify_claim_against_clause(
            "The license granted is non-exclusive.",
            "Section 2.1. Licensor grants Licensee a nonexclusive license.",
        )
        self.assertEqual("present", v.disposition)
        self.assertNotIn("appears in", v.detail)
        self.assertIn("matches", v.detail)
        self.assertIn("nonexclusive", v.detail)

    def test_identical_written_value_is_not_affirmed(self) -> None:
        # Used to read a clean "present (appears in)". ADR-0013 scope-out: figures are
        # not affirmed -> could-not-check, with an honest detail.
        v = verify_claim_against_clause(
            "The cap is $500,000.",
            "liability shall not exceed $500,000 in the aggregate",
        )
        self.assertEqual("not_found", v.disposition)
        self.assertIn("not independently verified", v.detail)


class NotFoundTests(unittest.TestCase):
    def test_claim_value_absent_from_clause_is_not_found(self) -> None:
        v = verify_claim_against_clause(
            "The cap is $1,000,000.",
            "the parties agree to cooperate in good faith on all matters",
        )
        self.assertEqual("not_found", v.disposition)

    def test_unmatched_quote_is_not_found(self) -> None:
        v = verify_claim_against_clause(
            'It promises "perpetual exclusivity" to the buyer.',
            "the license granted herein is non-exclusive and revocable",
        )
        self.assertEqual("not_found", v.disposition)


class MultiValueTests(unittest.TestCase):
    """Multiple values of one type cannot be aligned to a clause deterministically, so
    the engine refuses to guess: no masked contradiction, no false accusation, just an
    honest could-not-check (multi_value_unverifiable). Role-aligned multi-value checking
    is T1 work; until then a guessed verdict would violate ADR-0012 invariant 2."""

    def test_multi_value_match_does_not_mask_a_contradiction(self) -> None:
        # any-matches-any would launder this to "present" on the shared $50,000, hiding
        # that the claim's $1,000,000 cap conflicts with the clause's $2,000,000 cap.
        v = verify_claim_against_clause(
            "The liability cap is $1,000,000 with a $50,000 deductible.",
            "a deductible of $50,000 applies; the aggregate cap shall not exceed $2,000,000",
        )
        self.assertEqual("multi_value_unverifiable", v.disposition)
        self.assertEqual("money", v.anchor_type)
        self.assertIn("not independently checked", v.detail)

    def test_multi_value_miss_is_not_a_false_contradiction(self) -> None:
        # Two claim amounts, two unrelated clause amounts: naming "$1,000,000 vs
        # $3,000,000" would be a guessed alignment (a false accusation). Could-not-check.
        v = verify_claim_against_clause(
            "Fees are $1,000,000 and $2,000,000 respectively.",
            "the fees are $3,000,000 and $4,000,000 respectively",
        )
        self.assertEqual("multi_value_unverifiable", v.disposition)

    def test_single_value_contradiction_wins_over_a_multi_value_type(self) -> None:
        # A clean single-value contradiction (duration) must still win outright even when
        # another type in the same sentence (money) is multi-value-unalignable.
        v = verify_claim_against_clause(
            "The term is 5 years; fees are $1,000,000 and $2,000,000.",
            "this Agreement continues for 2 years; fees are $1,000,000 and $3,000,000",
        )
        self.assertEqual("parametric_contradiction", v.disposition)
        self.assertEqual("duration", v.anchor_type)


class PercentClauseTests(unittest.TestCase):
    def test_percent_contradiction(self) -> None:
        v = verify_claim_against_clause(
            "Liability is capped at 99% of fees paid.",
            "Section 9.2. Liability shall not exceed 50% of fees paid.",
        )
        self.assertEqual("parametric_contradiction", v.disposition)
        self.assertIn("99%", v.detail)
        self.assertIn("50%", v.detail)

    def test_percent_contradiction_cannot_be_laundered_by_a_matching_duration(self) -> None:
        # THE case that motivated the percent build (verified live pre-fix): the
        # matching 12-month duration carried a green "present" over a falsified
        # cap, because percent was not a parametric type. A contradiction in ANY
        # carried type must win outright.
        v = verify_claim_against_clause(
            "Liability is capped at 99% of the fees paid in the prior 12 months.",
            "Section 9.2. Liability shall not exceed 50% of the fees paid in the prior 12 months.",
        )
        self.assertEqual("parametric_contradiction", v.disposition)
        self.assertEqual("percent", v.anchor_type)

    def test_percent_present_with_hedge_detail(self) -> None:
        v = verify_claim_against_clause(
            "The royalty is 12.5% of net revenue.",
            "Section 4.1. Licensee shall pay a royalty of 12.5% of net revenue.",
        )
        self.assertEqual("present", v.disposition)
        self.assertIn("review the full passage", v.detail)

    def test_percent_aligns_across_notations(self) -> None:
        # "0.5%" in the summary vs "50 bps" in the clause is the same rate; the
        # basis-point canonical makes the notations compare equal, exactly.
        v = verify_claim_against_clause(
            "The fee increases by 0.5% for each month of delay.",
            "Section 3. A late charge of 50 bps accrues for each month of delay.",
        )
        self.assertEqual("present", v.disposition)

    def test_percent_not_found_is_the_honest_exit(self) -> None:
        v = verify_claim_against_clause(
            "An early-termination discount of 15% applies.",
            "Section 12. Either party may terminate for convenience.",
        )
        self.assertEqual("not_found", v.disposition)

    def test_dual_notation_of_one_rate_is_present_not_a_refusal(self) -> None:
        # '0.5% (50 bps)' is ONE rate written twice; equal canonicals collapse
        # before the multi-value test, so the legal dual-notation convention
        # reads present instead of an unnecessary could-not-check.
        v = verify_claim_against_clause(
            "A late charge of 0.5% (50 bps) accrues monthly.",
            "Section 3. A late charge of 0.5% accrues monthly.",
        )
        self.assertEqual("present", v.disposition)

    def test_two_percents_on_one_side_refuse_to_guess(self) -> None:
        v = verify_claim_against_clause(
            "Interest accrues at 5% and rises to 8% on default.",
            "Section 6. Interest accrues at 5% per annum.",
        )
        self.assertEqual("multi_value_unverifiable", v.disposition)


class ClauseAdjudicationTests(unittest.TestCase):
    """The cross-clause adjudication rule (topicality decision, 2026-06-10).

    Pure logic, exhaustively pinned here so the safety-critical rule lives in
    tested code, not in the envelope's retrieval loop. The rule: a
    contradiction stands only when NO retrieved clause carries the claim's
    value for that anchor type; a same-type present anywhere (on-topic or not)
    makes accusing from a different clause a guess, so the engine refuses with
    both clauses named. Off-topic presents veto accusations but never earn a
    green (C3 unchanged).
    """

    @staticmethod
    def _present(anchor_type="percent", where="Section 4", on_topic=True, section="Section 4"):
        return ClauseCandidate(
            ClauseVerdict(
                "present",
                f"50% appears in {where}; review the full passage for context.",
                anchor_type,
                ("50",),
                ("50",),
                claim_span="50%",
                clause_span="50%",
                where=where,
            ),
            section=section,
            clause_text=f"{where}. The royalty equals 50% of net fees.",
            on_topic=on_topic,
        )

    @staticmethod
    def _contradiction(anchor_type="percent", where="Section 9", section="Section 9"):
        return ClauseCandidate(
            ClauseVerdict(
                "parametric_contradiction",
                f"The summary states 50%; {where} states 40%.",
                anchor_type,
                ("50",),
                ("40",),
                claim_span="50%",
                clause_span="40%",
                where=where,
            ),
            section=section,
            clause_text=f"{where}. The discount equals 40% of net fees.",
            on_topic=True,
        )

    @staticmethod
    def _multi(section="Section 2"):
        return ClauseCandidate(
            ClauseVerdict(
                "multi_value_unverifiable", "cannot be aligned", "money", ("1", "2"), ("1",)
            ),
            section=section,
            clause_text="Section 2. Fees of $1 and $2.",
            on_topic=True,
        )

    def test_same_type_conflict_refuses_with_both_clauses_named(self) -> None:
        # The decided rule: present + contradiction for the same type across
        # clauses is a deterministic unknown, never a guessed verdict in
        # either direction.
        for order in [
            [self._present(), self._contradiction()],
            [self._contradiction(), self._present()],
        ]:
            with self.subTest(first=order[0].verdict.disposition):
                verdict, section, clause_text = adjudicate_clause_candidates(order)
                self.assertEqual("conflicting_clauses", verdict.disposition)
                self.assertIn("Section 4", verdict.detail)
                self.assertIn("Section 9", verdict.detail)
                self.assertIn("40%", verdict.detail)
                self.assertIn("not independently checked", verdict.detail)

    def test_off_topic_present_vetoes_the_accusation_but_earns_no_green(self) -> None:
        # The claim's value is verbatim in SOME retrieved clause (off-topic):
        # accusing from a different clause is a guess. Refuse, never accuse.
        verdict, _, _ = adjudicate_clause_candidates(
            [self._contradiction(), self._present(on_topic=False)]
        )
        self.assertEqual("conflicting_clauses", verdict.disposition)

    def test_off_topic_present_alone_stays_not_found(self) -> None:
        # C3 preserved: an off-topic value coincidence never earns a green.
        verdict, _, _ = adjudicate_clause_candidates([self._present(on_topic=False)])
        self.assertEqual("not_found", verdict.disposition)

    def test_uncontested_contradiction_stands(self) -> None:
        # No clause anywhere carries the claim's value: the catch is preserved,
        # ungated by topicality (a falsified value LOWERS overlap with its true
        # clause, so a topicality gate would suppress exactly the true catches).
        verdict, section, _ = adjudicate_clause_candidates([self._contradiction()])
        self.assertEqual("parametric_contradiction", verdict.disposition)
        self.assertEqual("Section 9", section)

    def test_first_uncontested_contradiction_wins_by_rank(self) -> None:
        verdict, section, _ = adjudicate_clause_candidates(
            [
                self._contradiction(where="Section 9", section="Section 9"),
                self._contradiction(where="Section 12", section="Section 12"),
            ]
        )
        self.assertEqual("Section 9", section)

    def test_cross_type_present_does_not_veto(self) -> None:
        # A duration present says nothing about a percent accusation: the
        # contradiction is uncontested for its own type and stands.
        verdict, _, _ = adjudicate_clause_candidates(
            [self._present(anchor_type="duration"), self._contradiction(anchor_type="percent")]
        )
        self.assertEqual("parametric_contradiction", verdict.disposition)

    def test_on_topic_present_alone_is_present(self) -> None:
        verdict, section, clause_text = adjudicate_clause_candidates([self._present()])
        self.assertEqual("present", verdict.disposition)
        self.assertEqual("Section 4", section)
        self.assertIn("royalty", clause_text or "")

    def test_present_outranks_multi_value_which_outranks_not_found(self) -> None:
        verdict, _, _ = adjudicate_clause_candidates([self._multi(), self._present()])
        self.assertEqual("present", verdict.disposition)
        verdict2, _, _ = adjudicate_clause_candidates([self._multi()])
        self.assertEqual("multi_value_unverifiable", verdict2.disposition)
        verdict3, _, _ = adjudicate_clause_candidates([])
        self.assertEqual("not_found", verdict3.disposition)


class GoverningLawClauseTests(unittest.TestCase):
    """Governing law as a parametric type: a falsified choice of law is the
    contract path's most consequential single-token error, and it is pure
    string equality after lexicon normalization (no arithmetic at all)."""

    _BOILERPLATE_DE = (
        "This Agreement shall be governed by and construed in accordance with "
        "the laws of the State of Delaware, without regard to its conflict of "
        "laws principles."
    )

    def test_governing_law_mismatch_is_a_contradiction(self) -> None:
        v = verify_claim_against_clause(
            "The agreement is governed by New York law.",
            self._BOILERPLATE_DE,
        )
        self.assertEqual("parametric_contradiction", v.disposition)
        self.assertEqual("governing_law", v.anchor_type)
        self.assertIn("New York", v.detail)
        self.assertIn("Delaware", v.detail)

    def test_governing_law_match_is_present_across_forms(self) -> None:
        v = verify_claim_against_clause(
            "The agreement is governed by Delaware law.",
            self._BOILERPLATE_DE,
        )
        self.assertEqual("present", v.disposition)
        self.assertEqual("governing_law", v.anchor_type)

    def test_english_law_is_not_accused_against_england_and_wales(self) -> None:
        # The classic naming variant: a summary's "English law" against the
        # contract's "laws of England and Wales" is the SAME choice of law.
        # Flagging it would be a false accusation, the direction the engine
        # refuses by construction.
        v = verify_claim_against_clause(
            "The deed is governed by English law.",
            "This deed shall be governed by and construed in accordance with "
            "the laws of England and Wales.",
        )
        self.assertEqual("present", v.disposition)
        self.assertEqual("governing_law", v.anchor_type)

    def test_venue_jurisdiction_cannot_mask_the_contradiction(self) -> None:
        # The clause chooses New York law but selects Delaware courts. The venue
        # jurisdiction must not anchor: if it did, the clause would carry two
        # governing_law values and the multi-value refusal would swallow the
        # real catch (summary says Delaware governs; it does not).
        v = verify_claim_against_clause(
            "The agreement is governed by Delaware law.",
            "This Agreement shall be governed by the laws of the State of New "
            "York; the parties submit to the exclusive jurisdiction of the "
            "courts of Delaware.",
        )
        self.assertEqual("parametric_contradiction", v.disposition)
        self.assertEqual("governing_law", v.anchor_type)
        self.assertEqual(("new york",), v.clause_values)

    def test_two_governing_laws_in_one_claim_refuse_to_guess(self) -> None:
        # A summary sentence asserting two different choices of law cannot be
        # aligned one-to-one against a single clause deterministically.
        v = verify_claim_against_clause(
            "The escrow is governed by New York law and the indemnity is governed by English law.",
            self._BOILERPLATE_DE,
        )
        self.assertEqual("multi_value_unverifiable", v.disposition)
        self.assertEqual("governing_law", v.anchor_type)

    def test_container_member_pair_refuses_not_accuses(self) -> None:
        # DIFC sits inside the UAE and Delaware inside the United States: a
        # summary naming the container against a clause naming the member is a
        # relationship, not a flat contradiction. The engine refuses
        # (could-not-check) instead of accusing in either direction.
        cases = [
            (
                "The agreement is governed by UAE law.",
                "This Agreement shall be governed by the laws of the DIFC.",
            ),
            (
                "The agreement is governed by United States law.",
                "This Agreement shall be governed by the laws of the State of Delaware.",
            ),
        ]
        for claim, clause in cases:
            with self.subTest(claim=claim):
                v = verify_claim_against_clause(claim, clause)
                self.assertEqual("multi_value_unverifiable", v.disposition)
                self.assertEqual("governing_law", v.anchor_type)
                self.assertIn("contains the other", v.detail)

    def test_sibling_jurisdictions_still_contradict(self) -> None:
        # Two disjoint systems named against each other is the real catch; the
        # containment refusal must not soften it.
        v = verify_claim_against_clause(
            "The agreement is governed by the laws of the DIFC.",
            "This Agreement shall be governed by the laws of the ADGM.",
        )
        self.assertEqual("parametric_contradiction", v.disposition)

    def test_governing_law_not_found_is_the_honest_exit(self) -> None:
        v = verify_claim_against_clause(
            "The agreement is governed by French law.",
            "The aggregate liability of the parties shall not exceed $500,000.",
        )
        self.assertEqual("not_found", v.disposition)
        self.assertEqual("governing_law", v.anchor_type)

    def test_amended_contract_conflict_refuses_with_both_clauses_named(self) -> None:
        # An amendment changed the governing law: one retrieved clause still
        # says New York, another says Delaware. The claim's New York is verbatim
        # in the contract, so accusing from the Delaware clause is a guess; the
        # adjudicator refuses and names both.
        present = ClauseCandidate(
            ClauseVerdict(
                "present",
                "New York appears in Section 12; review the full passage for context.",
                "governing_law",
                ("new york",),
                ("new york",),
                claim_span="New York",
                clause_span="New York",
                where="Section 12",
            ),
            section="Section 12",
            clause_text="governed by the laws of the State of New York",
            on_topic=True,
        )
        contradiction = ClauseCandidate(
            ClauseVerdict(
                "parametric_contradiction",
                "The summary states New York; Section 12 (as amended) states Delaware.",
                "governing_law",
                ("new york",),
                ("delaware",),
                claim_span="New York",
                clause_span="Delaware",
                where="Section 12 (as amended)",
            ),
            section="Section 12 (as amended)",
            clause_text="governed by the laws of the State of Delaware",
            on_topic=True,
        )
        verdict, _, _ = adjudicate_clause_candidates([contradiction, present])
        self.assertEqual("conflicting_clauses", verdict.disposition)
        self.assertEqual("governing_law", verdict.anchor_type)


class PolarityClauseTests(unittest.TestCase):
    """Polarity flips (exclusive vs non-exclusive, binding vs non-binding,
    revocable vs irrevocable) adjudicated per stem, so a matching qualifier in
    the same sentence can never mask a flipped one."""

    def test_exclusivity_flip_is_a_contradiction(self) -> None:
        v = verify_claim_against_clause(
            "The agreement grants Licensee an exclusive license to the Software.",
            "Section 3. Licensor hereby grants Licensee a non-exclusive license "
            "to use the Software.",
        )
        self.assertEqual("parametric_contradiction", v.disposition)
        self.assertEqual("polarity:exclusive:license", v.anchor_type)
        self.assertIn("exclusive", v.detail)
        self.assertIn("non-exclusive", v.detail)

    def test_matching_polarity_is_present(self) -> None:
        v = verify_claim_against_clause(
            "The license to the Software is non-exclusive.",
            "Licensor grants Licensee a non-exclusive license to use the Software.",
        )
        self.assertEqual("present", v.disposition)
        self.assertEqual("polarity:exclusive:license", v.anchor_type)

    def test_asymmetric_subject_matter_refuses_a_green_too(self) -> None:
        # A bare claim against a clause that names its subject matter: WHICH
        # license the claim means is unknowable, so confirming would be a
        # guessed green (round-2 hardening, the asymmetry rule).
        v = verify_claim_against_clause(
            "The license granted is non-exclusive.",
            "Licensor grants Licensee a non-exclusive license to use the Software.",
        )
        self.assertEqual("multi_value_unverifiable", v.disposition)

    def test_matching_stem_does_not_mask_a_flipped_sibling(self) -> None:
        # transferable agrees on both sides; exclusivity is flipped. Per-stem
        # adjudication must surface the flip, not launder it through the match.
        v = verify_claim_against_clause(
            "Licensee receives an exclusive, non-transferable license.",
            "Licensor grants a non-exclusive, non-transferable license.",
        )
        self.assertEqual("parametric_contradiction", v.disposition)
        self.assertEqual("polarity:exclusive:license", v.anchor_type)

    def test_both_signs_of_one_stem_refuse_to_guess(self) -> None:
        # The clause grants exclusivity for one field and not another; aligning
        # the claim's single qualifier to either would be a guess.
        v = verify_claim_against_clause(
            "Licensee receives an exclusive license to the Trademarks.",
            "Licensor grants an exclusive license to the Trademarks in the "
            "Territory and a non-exclusive license to the Trademarks elsewhere.",
        )
        self.assertEqual("multi_value_unverifiable", v.disposition)
        self.assertEqual("polarity:exclusive:license", v.anchor_type)

    def test_polarity_not_found_is_the_honest_exit(self) -> None:
        # The clause grants a license without stating exclusivity: the claim's
        # qualifier cannot be confirmed from it, and accusing would be a guess.
        v = verify_claim_against_clause(
            "The agreement grants a non-exclusive license to the Software.",
            "Licensor grants Licensee a license to use the Software.",
        )
        self.assertEqual("not_found", v.disposition)
        self.assertEqual("polarity:exclusive:license", v.anchor_type)

    def test_matching_money_does_not_mask_a_polarity_flip(self) -> None:
        # The fee agrees; the exclusivity is flipped. A contradiction in ANY
        # type wins outright (the percent-laundering lesson, same shape).
        v = verify_claim_against_clause(
            "An exclusive license is granted for a fee of $50,000.",
            "Licensor grants a non-exclusive license for a fee of $50,000.",
        )
        self.assertEqual("parametric_contradiction", v.disposition)
        self.assertEqual("polarity:exclusive:license", v.anchor_type)

    def test_exclusive_remedy_cannot_green_an_exclusive_license(self) -> None:
        # The adversarial review's false-green blocker: "sole and exclusive
        # remedy" shares the stem but qualifies a different noun class, so it
        # must never confirm a claim about license exclusivity.
        v = verify_claim_against_clause(
            "Section 4 grants Licensee an exclusive license to exploit the Work.",
            "The remedies set forth in this Section shall be the sole and "
            "exclusive remedy of the parties.",
        )
        self.assertNotEqual("present", v.disposition)
        self.assertEqual("not_found", v.disposition)

    def test_different_subject_matter_refuses_not_accuses(self) -> None:
        # The adversarial review's false-accusation blocker: an exclusive
        # Software license and a non-exclusive Documentation license can both
        # be true. Disjoint post-noun subject matter on both sides refuses.
        v = verify_claim_against_clause(
            "Licensor grants an exclusive license to the Software.",
            "Licensor grants a non-exclusive license to the Documentation.",
        )
        self.assertEqual("multi_value_unverifiable", v.disposition)
        self.assertEqual("polarity:exclusive:license", v.anchor_type)
        self.assertIn("subject matter", v.detail)

    def test_different_subject_matter_blocks_a_false_green_too(self) -> None:
        # Same sign, different subject matter: confirming the Software claim
        # from the Documentation grant would be a false green.
        v = verify_claim_against_clause(
            "Licensor grants a non-exclusive license to the Software.",
            "Licensor grants a non-exclusive license to the Documentation.",
        )
        self.assertEqual("multi_value_unverifiable", v.disposition)

    def test_shared_subject_matter_still_contradicts(self) -> None:
        # The flagship catch survives the subject-matter gate: both sides
        # qualify the same Software license.
        v = verify_claim_against_clause(
            "The agreement grants an exclusive license to use the Software.",
            "Licensor grants Licensee a non-exclusive license to use the Software during the Term.",
        )
        self.assertEqual("parametric_contradiction", v.disposition)
        self.assertEqual("polarity:exclusive:license", v.anchor_type)

    def test_both_sides_bare_still_contradicts(self) -> None:
        # Neither side states subject matter: there is exactly one license in
        # play on the evidence, so the flip stays a catch.
        v = verify_claim_against_clause(
            "The license granted hereunder is exclusive.",
            "Licensor grants Licensee a non-exclusive license.",
        )
        self.assertEqual("parametric_contradiction", v.disposition)

    def test_pre_noun_subject_matter_is_read(self) -> None:
        # Round-2 escape 2: "the TRADEMARK license" puts the subject matter
        # before the noun. Against a non-exclusive SOURCE-CODE license the
        # qualifiers must refuse, not accuse; against a non-exclusive
        # TRADEMARK license the flip is the real catch and must survive.
        refused = verify_claim_against_clause(
            "The trademark license is exclusive.",
            "Licensor grants a non-exclusive license to the source code.",
        )
        self.assertEqual("multi_value_unverifiable", refused.disposition)
        caught = verify_claim_against_clause(
            "The trademark license is exclusive.",
            "Licensor grants a non-exclusive trademark license.",
        )
        self.assertEqual("parametric_contradiction", caught.disposition)

    def test_shared_generic_word_does_not_defeat_the_gate(self) -> None:
        # Round-2 escape 1: "Product" is shared, but source code and user
        # manual are different grants that can both be true. Each side carries
        # a word the other lacks, so the pair refuses in both directions.
        accusation = verify_claim_against_clause(
            "Vendor grants an exclusive license to the Product source code.",
            "Vendor grants a non-exclusive license to the Product user manual.",
        )
        self.assertEqual("multi_value_unverifiable", accusation.disposition)
        green = verify_claim_against_clause(
            "Vendor grants a non-exclusive license to the Product source code.",
            "Vendor grants a non-exclusive license to the Product user manual.",
        )
        self.assertEqual("multi_value_unverifiable", green.disposition)

    def test_compound_grant_noun_keys_stably(self) -> None:
        # Round-3 note 1: "exclusive license rights" must bind to the FIRST
        # grant noun and key the same grant as a bare "exclusive license", or
        # a real flip lands on different keys and goes unseen.
        v = verify_claim_against_clause(
            "Licensee receives exclusive license rights under this Section.",
            "Licensor grants Licensee a non-exclusive license.",
        )
        self.assertEqual("parametric_contradiction", v.disposition)
        self.assertEqual("polarity:exclusive:license", v.anchor_type)

    def test_sentence_subject_is_not_subject_matter(self) -> None:
        # Round-3 note 2: the pre-noun window stops at the granting verb, so
        # the grantor's name cannot register as subject matter and suppress a
        # real flip through the asymmetry rule.
        v = verify_claim_against_clause(
            "The Company hereby grants an exclusive license.",
            "The Vendor hereby grants a non-exclusive license.",
        )
        self.assertEqual("parametric_contradiction", v.disposition)

    def test_verbose_restatement_keeps_the_catch(self) -> None:
        # Subset objects are the same grant said longer; the gate only refuses
        # on mutual difference, so verbosity does not soften a flip.
        v = verify_claim_against_clause(
            "The agreement grants an exclusive license to use the Software.",
            "Licensor grants Licensee a non-exclusive license to use the "
            "Software during the Term in the Territory.",
        )
        self.assertEqual("parametric_contradiction", v.disposition)

    def test_cross_clause_same_stem_conflict_refuses(self) -> None:
        # Two clauses disagree on the same stem (an amended grant): the engine
        # refuses with both named rather than accusing or greenlighting.
        present = ClauseCandidate(
            ClauseVerdict(
                "present",
                "exclusive appears in Section 3; review the full passage for context.",
                "polarity:exclusive:license",
                ("exclusive+",),
                ("exclusive+",),
                claim_span="exclusive",
                clause_span="exclusive",
                where="Section 3",
            ),
            section="Section 3",
            clause_text="an exclusive license",
            on_topic=True,
        )
        contradiction = ClauseCandidate(
            ClauseVerdict(
                "parametric_contradiction",
                "The summary states exclusive; Section 3 (as amended) states non-exclusive.",
                "polarity:exclusive:license",
                ("exclusive+",),
                ("exclusive-",),
                claim_span="exclusive",
                clause_span="non-exclusive",
                where="Section 3 (as amended)",
            ),
            section="Section 3 (as amended)",
            clause_text="a non-exclusive license",
            on_topic=True,
        )
        verdict, _, _ = adjudicate_clause_candidates([contradiction, present])
        self.assertEqual("conflicting_clauses", verdict.disposition)

    def test_cross_clause_different_stems_do_not_veto(self) -> None:
        # A present on revocable in one clause must not veto an exclusivity
        # contradiction from another: the stem-qualified type keeps them apart.
        present = ClauseCandidate(
            ClauseVerdict(
                "present",
                "irrevocable appears in Section 2; review the full passage for context.",
                "polarity:revocable:license",
                ("revocable-",),
                ("revocable-",),
                claim_span="irrevocable",
                clause_span="irrevocable",
                where="Section 2",
            ),
            section="Section 2",
            clause_text="an irrevocable license",
            on_topic=True,
        )
        contradiction = ClauseCandidate(
            ClauseVerdict(
                "parametric_contradiction",
                "The summary states exclusive; Section 3 states non-exclusive.",
                "polarity:exclusive:license",
                ("exclusive+",),
                ("exclusive-",),
                claim_span="exclusive",
                clause_span="non-exclusive",
                where="Section 3",
            ),
            section="Section 3",
            clause_text="a non-exclusive license",
            on_topic=True,
        )
        verdict, _, _ = adjudicate_clause_candidates([present, contradiction])
        self.assertEqual("parametric_contradiction", verdict.disposition)


class ValueCarrierVetoTests(unittest.TestCase):
    """Rule 1 reads the clause TEXT, not the disposition label (the live Kellogg
    false contradiction, 2026-06-11).

    A draft sentence whose value was verbatim in the source read RED because the
    carrying clause bundled a second value: its verdict was
    multi_value_unverifiable, the old veto consulted only ``present`` verdicts,
    and an unrelated clause's contradiction stood uncontested. These tests pin
    the carrier veto at the adjudicator layer; the per-clause multi-value guard
    in verify_claim_against_clause is deliberately untouched (a multi-value
    clause still never earns a green).
    """

    CLAIM = (
        "The heavy advertising expenses associated with the product launch will "
        "generate operating losses of $20 million next year."
    )
    # The unrelated example whose lone money value accuses (the live accuser).
    ACCUSER = (
        "The marketing expenses associated with launching the new product will "
        "generate operating losses of $500 million next year for the product."
    )
    # The verbatim-correct clause: carries the claim's $20 million, plus a second
    # amount that makes its own verdict multi_value_unverifiable.
    CARRIER = (
        "The heavy advertising expenses associated with the product launch will "
        "generate operating losses of $20 million next year, against pre-tax "
        "income of $460 million."
    )

    def _candidates(self) -> list[ClauseCandidate]:
        accuser_v = verify_claim_against_clause(self.CLAIM, self.ACCUSER)
        carrier_v = verify_claim_against_clause(self.CLAIM, self.CARRIER)
        # Preconditions that make the test exercise the CARRIER path: the old
        # presents-only veto sees no present here and would accuse.
        assert accuser_v.disposition == "parametric_contradiction"
        assert carrier_v.disposition == "multi_value_unverifiable"
        return [
            ClauseCandidate(accuser_v, None, self.ACCUSER, True),
            ClauseCandidate(carrier_v, None, self.CARRIER, True),
        ]

    def test_multi_value_carrier_vetoes_the_accusation(self) -> None:
        # The Kellogg shape: the claim's value is verbatim in a retrieved clause,
        # so accusing from a different clause is a guess. Refuse with both named;
        # never the red contradiction, never a green.
        verdict, _section, clause_text = adjudicate_clause_candidates(self._candidates())
        self.assertEqual("conflicting_clauses", verdict.disposition)
        self.assertIn("$20 million", verdict.detail)
        self.assertIn("$500 million", verdict.detail)
        self.assertIn("not independently checked", verdict.detail)
        # The card points at the clause where the claim's value verifiably lives.
        self.assertEqual(self.CARRIER, clause_text)

    def test_multi_value_non_carrier_does_not_veto(self) -> None:
        # Recall preserved: a multi-value clause WITHOUT the claim's value is no
        # alibi, so the catch stands; the detail then names the unaligned
        # passages so the accusing clause is not mistaken for the claim's one
        # true counterpart (the live $360M-accused-with-$7B evidence gap).
        claim = (
            "Kellogg expects to earn pre-tax income of $360 million from "
            "operations other than the new pastries next year."
        )
        accuser_v = verify_claim_against_clause(claim, self.ACCUSER)
        carrier_v = verify_claim_against_clause(claim, self.CARRIER)
        assert accuser_v.disposition == "parametric_contradiction"
        assert carrier_v.disposition == "multi_value_unverifiable"
        verdict, _, _ = adjudicate_clause_candidates(
            [
                ClauseCandidate(accuser_v, None, self.ACCUSER, True),
                ClauseCandidate(carrier_v, None, self.CARRIER, True),
            ]
        )
        self.assertEqual("parametric_contradiction", verdict.disposition)
        self.assertIn("could not align", verdict.detail)
        self.assertIn("review them", verdict.detail)

    def test_uncontested_detail_stays_verbatim_without_unaligned_passages(self) -> None:
        # No same-type multi-value neighbors: the contradiction detail is the
        # per-clause wording, byte-identical (no note appended).
        accuser_v = verify_claim_against_clause(self.CLAIM, self.ACCUSER)
        verdict, _, _ = adjudicate_clause_candidates(
            [ClauseCandidate(accuser_v, None, self.ACCUSER, True)]
        )
        self.assertEqual("parametric_contradiction", verdict.disposition)
        self.assertEqual(accuser_v.detail, verdict.detail)

    def test_cross_type_disposition_carrier_vetoes(self) -> None:
        # A clause adjudicated under a DIFFERENT type (its final verdict is a
        # duration multi-value) still carries the claim's money value in its
        # text; the money accusation from another clause must refuse.
        claim = "The term is 24 months and the fee is $20 million."
        accuser = "The fee for the services is $500 million."
        carrier = (
            "The fee of $20 million is payable over a term of 24 months, "
            "with an option to extend by a further 36 months."
        )
        accuser_v = verify_claim_against_clause(claim, accuser)
        carrier_v = verify_claim_against_clause(claim, carrier)
        assert accuser_v.disposition == "parametric_contradiction"
        assert accuser_v.anchor_type == "money"
        assert carrier_v.anchor_type != "money"
        verdict, _, clause_text = adjudicate_clause_candidates(
            [
                ClauseCandidate(accuser_v, None, accuser, True),
                ClauseCandidate(carrier_v, None, carrier, True),
            ]
        )
        self.assertEqual("conflicting_clauses", verdict.disposition)
        self.assertEqual(carrier, clause_text)

    def test_governing_law_containment_refusal_is_no_alibi(self) -> None:
        # A containment refusal (UAE vs DIFC) is not a carrier of the claim's
        # jurisdiction, so a sibling clause's flipped choice of law still
        # contradicts. The veto must not over-fire on governing law.
        claim = "This Agreement is governed by the laws of the United Arab Emirates."
        accuser = "This Agreement shall be governed by the laws of England and Wales."
        containment = (
            "This Agreement shall be governed by the laws of the Dubai "
            "International Financial Centre."
        )
        accuser_v = verify_claim_against_clause(claim, accuser)
        containment_v = verify_claim_against_clause(claim, containment)
        assert accuser_v.disposition == "parametric_contradiction"
        assert containment_v.disposition == "multi_value_unverifiable"
        verdict, _, _ = adjudicate_clause_candidates(
            [
                ClauseCandidate(accuser_v, None, accuser, True),
                ClauseCandidate(containment_v, None, containment, True),
            ]
        )
        self.assertEqual("parametric_contradiction", verdict.disposition)

    def test_polarity_contradiction_keeps_the_present_only_veto(self) -> None:
        # Polarity values are noun-keyed grants adjudicated per stem; the text
        # re-read does not apply, so a polarity flip still stands against a
        # multi-value neighbor of any kind.
        claim = "The license granted hereunder is exclusive."
        accuser = "Licensor grants Licensee a non-exclusive license."
        accuser_v = verify_claim_against_clause(claim, accuser)
        assert accuser_v.disposition == "parametric_contradiction"
        carrier_v = verify_claim_against_clause(self.CLAIM, self.CARRIER)
        verdict, _, _ = adjudicate_clause_candidates(
            [
                ClauseCandidate(accuser_v, None, accuser, True),
                ClauseCandidate(carrier_v, None, self.CARRIER, True),
            ]
        )
        self.assertEqual("parametric_contradiction", verdict.disposition)


class AccuserSelectionTests(unittest.TestCase):
    """Rule 2 evidence selection: an on-topic accuser supplies the evidence
    before an off-topic one; selection only, never suppression."""

    @staticmethod
    def _contradiction(section: str, on_topic: bool) -> ClauseCandidate:
        return ClauseCandidate(
            ClauseVerdict(
                "parametric_contradiction",
                f"The summary states 50%; {section} states 40%.",
                "percent",
                ("50",),
                ("40",),
                claim_span="50%",
                clause_span="40%",
                where=section,
            ),
            section=section,
            clause_text=f"{section}. The discount equals 40% of net fees.",
            on_topic=on_topic,
        )

    def test_on_topic_accuser_supplies_the_evidence(self) -> None:
        verdict, section, _ = adjudicate_clause_candidates(
            [
                self._contradiction("Section 9", on_topic=False),
                self._contradiction("Section 12", on_topic=True),
            ]
        )
        self.assertEqual("parametric_contradiction", verdict.disposition)
        self.assertEqual("Section 12", section)

    def test_off_topic_only_accuser_still_accuses(self) -> None:
        # Never suppression: a falsified value lowers overlap with its true
        # clause, so an off-topic-only accuser must keep the catch.
        verdict, section, _ = adjudicate_clause_candidates(
            [self._contradiction("Section 9", on_topic=False)]
        )
        self.assertEqual("parametric_contradiction", verdict.disposition)
        self.assertEqual("Section 9", section)

    def test_rank_order_survives_within_a_topicality_band(self) -> None:
        verdict, section, _ = adjudicate_clause_candidates(
            [
                self._contradiction("Section 9", on_topic=True),
                self._contradiction("Section 12", on_topic=True),
            ]
        )
        self.assertEqual("Section 9", section)

    def test_topicality_never_picks_across_anchor_types(self) -> None:
        # Cold-review catch (2026-06-11): an off-topic money accuser at rank 0
        # must NOT be displaced by an on-topic duration accuser at rank 1. The
        # evidence swap is same-type only; across types the standing catch is
        # first by retrieval rank, exactly the pre-fix behavior.
        money = ClauseCandidate(
            ClauseVerdict(
                "parametric_contradiction",
                "The summary states $20 million; Section 2 states $90 million.",
                "money",
                (2000000000,),
                (9000000000,),
                claim_span="$20 million",
                clause_span="$90 million",
                where="Section 2",
            ),
            section="Section 2",
            clause_text="Section 2. The fee is $90 million.",
            on_topic=False,
        )
        duration = ClauseCandidate(
            ClauseVerdict(
                "parametric_contradiction",
                "The summary states 24 months; Section 5 states 72 months.",
                "duration",
                (720,),
                (2160,),
                claim_span="24 months",
                clause_span="72 months",
                where="Section 5",
            ),
            section="Section 5",
            clause_text="Section 5. The term is 72 months.",
            on_topic=True,
        )
        verdict, section, _ = adjudicate_clause_candidates([money, duration])
        self.assertEqual("parametric_contradiction", verdict.disposition)
        self.assertEqual("money", verdict.anchor_type)
        self.assertEqual("Section 2", section)

    def test_review_note_names_the_type_in_prose_not_machine_tokens(self) -> None:
        # Cold-review catch (2026-06-11): the unaligned-passages note renders
        # on a lawyer-facing card, so "governing_law" must not leak raw.
        claim = "This Agreement is governed by the laws of the United Arab Emirates."
        accuser = "This Agreement shall be governed by the laws of England and Wales."
        containment = (
            "This Agreement shall be governed by the laws of the Dubai "
            "International Financial Centre."
        )
        accuser_v = verify_claim_against_clause(claim, accuser)
        containment_v = verify_claim_against_clause(claim, containment)
        verdict, _, _ = adjudicate_clause_candidates(
            [
                ClauseCandidate(accuser_v, None, accuser, True),
                ClauseCandidate(containment_v, None, containment, True),
            ]
        )
        self.assertEqual("parametric_contradiction", verdict.disposition)
        self.assertIn("governing-law values", verdict.detail)
        self.assertNotIn("governing_law", verdict.detail)


class MagnitudeAnchorTests(unittest.TestCase):
    """Bare / non-$ magnitude quantities ("20 billion", "EUR 250 thousand") must
    become anchors so a single-figure non-USD claim can be checked. _MONEY only
    sees "$"-amounts, which silently dropped every euro / bare-billion figure."""

    def _types(self, text: str) -> list[str]:
        return [a.type for a in extract_anchors(text)]

    def test_bare_billion_is_a_magnitude_anchor(self) -> None:
        self.assertIn("magnitude", self._types("Revenues of 20 billion in the year."))

    def test_eur_prefixed_magnitude_is_an_anchor(self) -> None:
        self.assertIn("magnitude", self._types("a threshold of EUR 250 thousand"))

    def test_dollar_amount_stays_money_not_magnitude(self) -> None:
        # _MONEY owns "$5 billion"; it must NOT also anchor as a magnitude (double count).
        types = self._types("a cap of $5 billion")
        self.assertIn("money", types)
        self.assertNotIn("magnitude", types)

    def test_small_bare_integer_is_not_a_magnitude(self) -> None:
        # "23 States", "Section 8", "Pillar 1": a number without a scale word is an
        # identifier or a count, never a financial magnitude. No false anchor.
        self.assertNotIn("magnitude", self._types("the rest in the other 23 States"))

    def test_single_magnitude_mismatch_is_a_contradiction(self) -> None:
        v = verify_claim_against_clause("The fund totals 7 billion.", "The fund totals 2 billion.")
        self.assertEqual("parametric_contradiction", v.disposition)
        self.assertIn("7 billion", v.detail)
        self.assertIn("2 billion", v.detail)

    def test_single_magnitude_match_is_not_affirmed(self) -> None:
        # ADR-0013 scope-out: a figure is never AFFIRMED, even on an exact match.
        v = verify_claim_against_clause("The fund totals 2 billion.", "The fund totals 2 billion.")
        self.assertEqual("not_found", v.disposition)

    def test_european_decimal_comma_is_refused_not_misparsed(self) -> None:
        # "1,2 billion" is 1.2 billion (the BIM source writes it). A naive comma
        # strip read it as 12 billion. We refuse the ambiguous comma-decimal rather
        # than mint a 10x-wrong canonical: NO magnitude anchor (a miss, not a wrong
        # value). US grouping ("5,000 billion") still parses.
        eu = [a for a in extract_anchors("a residual of 1,2 billion") if a.type == "magnitude"]
        self.assertEqual([], eu)
        grouped = [
            a.canonical_value for a in extract_anchors("5,000 billion") if a.type == "magnitude"
        ]
        self.assertEqual([5_000_000_000_000], grouped)

    def test_us_and_eu_decimal_are_not_falsely_contradicted(self) -> None:
        # The dangerous case: a US-decimal draft against the EU-decimal source must
        # NOT read as a contradiction (1.2 vs a misparsed 12). The EU figure is
        # refused, so there is nothing to falsely diff.
        v = verify_claim_against_clause(
            "The residual is 1.2 billion.", "the residual equals 1,2 billion"
        )
        self.assertNotEqual("parametric_contradiction", v.disposition)


class AlteredFigureNearCopyTests(unittest.TestCase):
    """The lawyer pastes a slide / passage verbatim and an AI (or a typo) has
    altered one or more figures. The single-anchor path catches at most one of
    them and silently drops the rest; this pass diffs EVERY figure positionally
    on a near-verbatim copy and names every alteration. Safe by construction: it
    only fires when the two texts are near-identical with the figures masked, and
    refuses (returns to the normal path) on a paraphrase or a shape mismatch."""

    # The real BIM-lecture slide the user tested with.
    SOURCE = (
        "Turnover 20 billion (2 billion each generated in Italy, Germany, Spain "
        "and France, the rest in the other 23 States) PBT 16%"
    )

    def test_copied_slide_with_two_altered_figures_names_both(self) -> None:
        claim = (
            "Turnover 20 billion (7 billion each generated in Italy, Germany, Spain "
            "and France, the rest in the other 23 States) - PBT 26%"
        )
        v = verify_claim_against_clause(claim, self.SOURCE)
        self.assertEqual("parametric_contradiction", v.disposition)
        # BOTH alterations are named (the bug: only the % was reported).
        self.assertIn("7 billion", v.detail)
        self.assertIn("2 billion", v.detail)
        self.assertIn("26%", v.detail)
        self.assertIn("16%", v.detail)

    def test_copied_slide_single_altered_billion_is_caught(self) -> None:
        # Only the billion changed (the % matches). The billion miss was the bug.
        claim = (
            "Turnover 20 billion (7 billion each generated in Italy, Germany, Spain "
            "and France, the rest in the other 23 States) PBT 16%"
        )
        v = verify_claim_against_clause(claim, self.SOURCE)
        self.assertEqual("parametric_contradiction", v.disposition)
        self.assertIn("7 billion", v.detail)
        self.assertIn("2 billion", v.detail)

    def test_verbatim_copy_with_no_altered_figure_is_not_a_contradiction(self) -> None:
        v = verify_claim_against_clause(self.SOURCE, self.SOURCE)
        self.assertNotEqual("parametric_contradiction", v.disposition)

    def test_altered_year_on_a_copied_line_is_caught(self) -> None:
        src = "This Agreement is dated March 11, 2023, in the City of Milan."
        claim = "This Agreement is dated March 11, 2024, in the City of Milan."
        v = verify_claim_against_clause(claim, src)
        self.assertEqual("parametric_contradiction", v.disposition)

    def test_paraphrase_is_not_positionally_accused(self) -> None:
        # NOT a near-verbatim copy: the pass must not fire. The MSA money claim
        # still works through the normal single-anchor path (regression guard).
        v = verify_claim_against_clause(
            "Liability under this agreement is capped at $1,000,000.",
            "Section 8. Limitation of Liability. The aggregate liability of either "
            "party under this Agreement shall not exceed $500,000.",
        )
        self.assertEqual("parametric_contradiction", v.disposition)
        self.assertIn("$1,000,000", v.detail)
        self.assertIn("$500,000", v.detail)

    def test_different_sentence_with_same_figure_count_is_not_accused(self) -> None:
        # Adversarial: a genuinely different sentence whose figures are legitimately
        # different must NOT be positionally accused. Low skeleton similarity ->
        # the pass refuses and falls through.
        claim = "Our Q3 revenue reached 7 billion at a 26% margin this year."
        v = verify_claim_against_clause(claim, self.SOURCE)
        self.assertNotIn("differ from", (v.detail or ""))

    def test_reordered_same_figures_are_not_accused(self) -> None:
        # A near-verbatim copy whose figures are the SAME values in a different
        # order is not a tamper. Positional pairing would falsely accuse it; the
        # absent-value rule must never flag a value that appears in the source.
        v = verify_claim_against_clause(
            "Allocation: 10% Italy, 20% France, 30% Spain.",
            "Allocation: 30% Spain, 20% France, 10% Italy.",
        )
        self.assertNotEqual("parametric_contradiction", v.disposition)

    def test_no_shared_figure_falls_through_to_the_multi_value_refusal(self) -> None:
        # All figures differ and none is shared: the claim may be an unrelated
        # schedule, so naming a pairing would be a guess. The pass refuses (no
        # shared anchor) and the existing multi-value refusal stands.
        v = verify_claim_against_clause(
            "Fees are $1,000,000 and $2,000,000 respectively.",
            "the fees are $3,000,000 and $4,000,000 respectively",
        )
        self.assertEqual("multi_value_unverifiable", v.disposition)


class AlteredFigureNearCopyRegressionTests(unittest.TestCase):
    """The 2026-06-14 mln regression, locked.

    A near-verbatim slide line where ONE figure is altered must read
    parametric_contradiction naming the altered figure, NOT
    multi_value_unverifiable — even when the line also carries (a) a second
    magnitude that MATCHES the source and (b) an ambiguous comma-decimal the
    engine refuses to canonicalize. The original failure: adding the EU 'mln'
    abbreviation made the line multi-magnitude, the per-type path refused it as
    multi-value, and the altered-figure pre-pass had bailed on the comma-decimal
    '1,2 billion' — so the genuinely-altered '60 billion' silently escaped. The
    fix makes the pre-pass SKIP an uncanonical figure instead of aborting.
    """

    def test_one_altered_magnitude_among_a_matching_one_and_a_comma_decimal(self) -> None:
        # The exact BIM-slide shape: 60->20 billion altered, 300 mln matches, and
        # the ambiguous "1,2 billion" is present on both sides.
        claim = (
            "For Covered Group, 16% - 10%= 6% (60 billion for 6%= 1,2 billion) are extra "
            "margins, so 300 mln to be allocated to Market States exceeding the threshold"
        )
        clause = (
            "For Covered Group, 16% - 10%= 6% (20 billion for 6%= 1,2 billion) are extra "
            "margins, so 300 mln to be allocated to Market States exceeding the threshold"
        )
        v = verify_claim_against_clause(claim, clause)
        self.assertEqual("parametric_contradiction", v.disposition)
        self.assertIn("60 billion", v.detail)
        self.assertIn("20 billion", v.detail)
        # The matching 300 mln must NOT be accused, and the verdict must not be a
        # multi-value refusal that masks the real catch.
        self.assertNotEqual("multi_value_unverifiable", v.disposition)
        self.assertNotIn("300", v.detail)

    def test_comma_decimal_alone_does_not_disable_the_altered_figure_catch(self) -> None:
        # A comma-decimal beside a single altered round magnitude: the catch stands.
        v = verify_claim_against_clause(
            "The cap is 5 billion (1,2 billion reserve).",
            "The cap is 2 billion (1,2 billion reserve).",
        )
        self.assertEqual("parametric_contradiction", v.disposition)
        self.assertIn("5 billion", v.detail)

    def test_an_exact_reorder_with_a_comma_decimal_is_not_a_contradiction(self) -> None:
        # Safety: skipping the uncanonical figure must not manufacture a false
        # catch. Same figures, reordered, with a comma-decimal -> not flagged.
        v = verify_claim_against_clause(
            "Tranches of 2 billion and 5 billion (1,2 billion reserve).",
            "Tranches of 5 billion and 2 billion (1,2 billion reserve).",
        )
        self.assertNotEqual("parametric_contradiction", v.disposition)

    def test_decimal_point_vs_source_comma_decimal_is_not_accused(self) -> None:
        # Finding 7 (xhigh review, 2026-06-16): the claim writes a value with a decimal
        # POINT ("1.2 billion") that the source wrote as an ambiguous comma-decimal
        # ("1,2 billion"). Same value, different notation; the canonical path skips the
        # source's comma-decimal, which made the claim figure read "absent" -> a false
        # contradiction accusing a faithful figure. It must read could-not-check now.
        v = verify_claim_against_clause(
            "Revenue was 1.2 billion and costs were 60 billion.",
            "Revenue was 1,2 billion and costs were 60 billion.",
        )
        self.assertNotEqual("parametric_contradiction", v.disposition)

    def test_eu_magnitude_abbreviations_are_recognized(self) -> None:
        # mln/mn/bn/bln/mld canonicalize as magnitudes so a "30 mln" line becomes
        # checkable (the supported result line beside the flagged ones).
        from services.legal.anchors import extract_anchors as _ea

        for surface, scaled in (("30 mln", 30_000_000), ("2 bn", 2_000_000_000)):
            anchors = [a for a in _ea(f"Total is {surface} this year.") if a.type == "magnitude"]
            self.assertTrue(anchors, f"{surface} should anchor as a magnitude")
            self.assertEqual(scaled, anchors[0].canonical_value, surface)


class SubjectBoundPercentTests(unittest.TestCase):
    """D2/D3: percents compared by SUBJECT, not bare value.

    D3 — a same-subject percent mismatch is a contradiction ("20% France" vs
    source "10% France"). D2 — a different-subject percent is NOT a conflict
    ("10% France" vs "16% profitability"), so a clean allocation line is not
    refused just because an unrelated clause carries a different rate. Mis-binding
    fails toward could-not-check, never a green or a false accusation.
    """

    def test_same_subject_mismatch_is_a_contradiction(self) -> None:  # D3
        v = verify_claim_against_clause(
            "Allocation key is 20% France.",
            "Allocation key is 10% France.",
        )
        self.assertEqual("parametric_contradiction", v.disposition)
        self.assertIn("20%", v.detail)
        self.assertIn("France", v.detail)
        self.assertIn("10%", v.detail)

    def test_different_subject_percent_is_not_a_contradiction(self) -> None:  # D2
        # The over-refusal case: a clean France rate vs an unrelated profitability
        # rate. Different subjects are different facts -> never a contradiction.
        v = verify_claim_against_clause(
            "Allocation key is 10% France.",
            "Amount A applies above a 16% ordinary level of profitability.",
        )
        self.assertNotEqual("parametric_contradiction", v.disposition)

    def test_same_subject_match_is_present(self) -> None:  # D2 acceptance
        v = verify_claim_against_clause(
            "Allocation key is 10% France.",
            "Allocation key: turnover (10% Italy, 10% France, 10% Spain, 10% Germany).",
        )
        self.assertEqual("present", v.disposition)

    def test_subjectless_percents_still_contradict_by_value(self) -> None:
        # No proper-noun subject on either side -> the value-only path is unchanged,
        # so a bare rate mismatch is still caught (no regression).
        v = verify_claim_against_clause(
            "The ordinary level is 10%.",
            "The ordinary level is 20%.",
        )
        self.assertEqual("parametric_contradiction", v.disposition)

    def test_misbound_subject_fails_to_could_not_check_not_a_false_accusation(self) -> None:
        # A spuriously-bound subject the clause is silent on must read could-not-check
        # (not_found), never a contradiction. Mis-binding costs recall, never a green
        # or a false flag (the council's hard line).
        v = verify_claim_against_clause(
            "Growth reached 10% Henceforth.",
            "The threshold is a 16% ordinary level.",
        )
        self.assertNotEqual("parametric_contradiction", v.disposition)

    def test_amended_same_subject_conflict_still_flags(self) -> None:
        # The guard the conflicting-clauses rule protects: a SAME-subject value
        # change (an amended figure) must still contradict, not slip through.
        v = verify_claim_against_clause(
            "The Acme royalty is 12% Acme.",
            "The Acme royalty is 8% Acme.",
        )
        self.assertEqual("parametric_contradiction", v.disposition)

    def test_partial_subject_match_is_not_a_green(self) -> None:
        # Finding 1 (xhigh review, 2026-06-16): the prior code greened on ANY one
        # matched subject, so "10% France and 20% Germany" vs a clause stating only
        # "10% France" read present -- the unconfirmed 20% Germany rode the green.
        # A present requires EVERY claim percent confirmed; a subject the clause is
        # silent on makes the sentence could-not-check, never green.
        v = verify_claim_against_clause(
            "Allocation is 10% France and 20% Germany.",
            "Allocation is 10% France.",
        )
        self.assertNotEqual("present", v.disposition)
        self.assertNotEqual("parametric_contradiction", v.disposition)

    def test_subjectless_sibling_percent_is_not_a_green(self) -> None:
        # Finding 2: one subject-bound percent agrees, but a subject-LESS sibling
        # percent is unchecked. The agreement must not short-circuit the value-only
        # multi-value gate and green the whole sentence.
        v = verify_claim_against_clause(
            "The rate is 10% France and the surtax is 20%.",
            "The rate is 10% France.",
        )
        self.assertNotEqual("present", v.disposition)

    def test_full_multi_subject_match_is_still_present(self) -> None:
        # Regression guard for the fix above: when EVERY claim subject is confirmed
        # (reordered, clause may carry extras), the sentence is still present.
        v = verify_claim_against_clause(
            "Allocation: 10% Italy and 20% France.",
            "Allocation: 20% France, 10% Italy, 30% Spain.",
        )
        self.assertEqual("present", v.disposition)

    def test_non_figure_present_does_not_mask_an_unconfirmed_percent(self) -> None:
        # Cross-type partial match (xhigh review): a governing-law present must NOT
        # green a sentence whose sibling percent the clause is silent on. The
        # unconfirmed percent outranks the present -> could-not-check.
        v = verify_claim_against_clause(
            "This Agreement is governed by New York law and the royalty is 20% Germany.",
            "This Agreement is governed by New York law. The royalty is 10% France.",
        )
        self.assertNotEqual("present", v.disposition)

    def test_figure_scope_out_still_yields_to_a_real_present(self) -> None:
        # The deliberate counter-case the fix must preserve: a confirmed 50% royalty
        # in a sentence that also names a (scoped-out) 12-month window still reads
        # present -- a figure not_found yields to a sibling non-figure present.
        v = verify_claim_against_clause(
            "The royalty is 50% of fees over the prior 12 months.",
            "Section 9.2. The royalty is 50% of fees over the prior 12 months.",
        )
        self.assertEqual("present", v.disposition)


if __name__ == "__main__":
    unittest.main()
