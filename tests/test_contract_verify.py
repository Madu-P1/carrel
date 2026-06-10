"""Phase 6: deterministic contract-claim verification (the gold parametric case)."""

from __future__ import annotations

import unittest

from services.legal.contract_verify import verify_claim_against_clause


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


if __name__ == "__main__":
    unittest.main()


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

    def test_two_percents_on_one_side_refuse_to_guess(self) -> None:
        v = verify_claim_against_clause(
            "Interest accrues at 5% and rises to 8% on default.",
            "Section 6. Interest accrues at 5% per annum.",
        )
        self.assertEqual("multi_value_unverifiable", v.disposition)
