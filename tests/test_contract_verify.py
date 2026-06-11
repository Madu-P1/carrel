"""Phase 6: deterministic contract-claim verification (the gold parametric case)."""

from __future__ import annotations

import unittest

from services.legal.anchors import Anchor
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

    def test_word_form_money_match_is_present(self) -> None:
        # The same spelled-out amount agreeing with the contract numeral is a match.
        v = verify_claim_against_clause(
            "The liability cap is one million dollars.",
            "liability is capped at $1,000,000 in the aggregate",
        )
        self.assertEqual("present", v.disposition)

    def test_duration_mismatch_is_a_contradiction(self) -> None:
        v = verify_claim_against_clause(
            "Confidentiality survives termination for 5 years.",
            "the confidentiality obligations shall survive for two (2) years",
        )
        self.assertEqual("parametric_contradiction", v.disposition)
        self.assertEqual("duration", v.anchor_type)

    def test_equivalent_durations_are_not_a_contradiction(self) -> None:
        # 12 months and 1 year are the same term; the day-count approximation
        # must not flag them as a contradiction.
        v = verify_claim_against_clause(
            "The term is 12 months.",
            "this Agreement shall continue for a period of 1 year",
        )
        self.assertEqual("present", v.disposition)

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
    def test_matching_money_value_is_present(self) -> None:
        v = verify_claim_against_clause(
            "The cap is $500,000.",
            "liability shall not exceed $500,000 in the aggregate",
        )
        self.assertEqual("present", v.disposition)
        self.assertIn("review the full passage", v.detail)

    def test_quoted_language_present_verbatim(self) -> None:
        v = verify_claim_against_clause(
            'The agreement says it will "survive termination" of the contract.',
            "These obligations survive termination of this Agreement for any reason.",
        )
        self.assertEqual("present", v.disposition)
        self.assertEqual("quote", v.anchor_type)

    def test_present_detail_never_asserts_text_the_clause_lacks(self) -> None:
        # Filing-grade detail strings must be literally true. When the matched
        # values agree but the written forms differ, the detail says "matches",
        # never "appears in" (the clause does not contain the summary's form).
        v = verify_claim_against_clause(
            "The liability cap is one million dollars.",
            "liability is capped at $1,000,000 in the aggregate",
        )
        self.assertEqual("present", v.disposition)
        self.assertNotIn("appears in", v.detail)
        self.assertIn("matches", v.detail)
        self.assertIn("$1,000,000", v.detail)

    def test_cross_unit_tolerant_match_reads_consistent_with(self) -> None:
        # A tolerant cross-unit duration match is an approximation, and the
        # detail must say so: "consistent with", never "appears in" and never
        # a bare "matches".
        v = verify_claim_against_clause(
            "The term is 12 months.",
            "this Agreement shall continue for a period of 1 year",
        )
        self.assertEqual("present", v.disposition)
        self.assertNotIn("appears in", v.detail)
        self.assertIn("consistent with", v.detail)
        self.assertIn("1 year", v.detail)

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

    def test_identical_written_value_still_reads_appears_in(self) -> None:
        v = verify_claim_against_clause(
            "The cap is $500,000.",
            "liability shall not exceed $500,000 in the aggregate",
        )
        self.assertEqual("present", v.disposition)
        self.assertIn("appears in", v.detail)


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


if __name__ == "__main__":
    unittest.main()
