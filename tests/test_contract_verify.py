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


class PresentTests(unittest.TestCase):
    def test_matching_money_value_is_present(self) -> None:
        v = verify_claim_against_clause(
            "The cap is $500,000.",
            "liability shall not exceed $500,000 in the aggregate",
        )
        self.assertEqual("present", v.disposition)
        self.assertIn("review the full clause", v.detail)

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


if __name__ == "__main__":
    unittest.main()
