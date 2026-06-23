"""Held-out locking tests for the cachet-adversary red-team findings (2026-06-24).

Each finding here was surfaced by the adversarial discovery battery
(``evals/adversary``) running against the REAL deterministic engine. The fixes
touch gated truth-surface files (``contract_verify.py`` / ``anchors.py``) and are
REVIEW-gated per ``.claude/forge.contract.yaml`` — so these tests are committed as
the locking regressions, NOT the fixes.

The two open findings assert the DESIRED behavior and are decorated
``expectedFailure`` so the verify chain stays green while the bug exists. The day
the engine is fixed, unittest reports an UNEXPECTED SUCCESS (a failure), which
flags the reviewer to remove the decorator and promote the test to a permanent
guard. The positive controls lock the safe behavior that must never regress.

See ``docs/notes/2026-06-24-redteam-findings.md`` for the full write-up and
``.claude/forge.engine.tasks.md`` (Red-team findings section) for the queue entries.
"""

from __future__ import annotations

import unittest

from services.legal.contract_verify import verify_claim_against_clause


class PercentSubjectBindingTests(unittest.TestCase):
    """FINDING RT1 (P2, REVIEW — reproduces the operator-gated 'role-aligned clause
    matching' item). A single-value percent clause affirms ANY claim carrying that
    percent value, even when the claim's subject is absent from the clause. Money and
    duration scope this out (ADR-0013); percent does not, in either subject-labeler
    mode. A summary that re-attributes a contract's percentage to a different subject
    reads as supported — a false green.
    """

    @unittest.expectedFailure
    def test_percent_value_match_must_not_affirm_a_different_subject_royalty(self) -> None:
        # "audit fee 10%" vs a clause about a 10% ROYALTY. The source says nothing
        # about an audit fee; affirming it is subject-blind.
        verdict = verify_claim_against_clause(
            "The audit fee is 10% of Net Sales.",
            "Licensee shall pay Licensor a royalty of 10% of Net Sales",
        )
        self.assertNotEqual("present", verdict.disposition)

    @unittest.expectedFailure
    def test_percent_value_match_must_not_affirm_a_different_subject_interest(self) -> None:
        # "discount 8%" vs a clause about 8% default INTEREST.
        verdict = verify_claim_against_clause(
            "The early-payment discount is 8%.",
            "overdue amounts shall bear interest at a rate of 8% per annum",
        )
        self.assertNotEqual("present", verdict.disposition)

    def test_money_subject_mismatch_correctly_refuses(self) -> None:
        # Positive control: money is scoped out, so the identical attack holds.
        verdict = verify_claim_against_clause(
            "The breakup fee is $15,000,000.",
            "the Buyer shall pay the Seller a purchase price of $15,000,000 at Closing",
        )
        self.assertNotEqual("present", verdict.disposition)

    def test_duration_subject_mismatch_correctly_refuses(self) -> None:
        # Positive control: duration is scoped out, so the identical attack holds.
        verdict = verify_claim_against_clause(
            "The warranty period lasts 30 days.",
            "the breaching party shall have 30 days after written notice to cure the breach",
        )
        self.assertNotEqual("present", verdict.disposition)


class QuoteCaseSensitivityTests(unittest.TestCase):
    """FINDING RT2 (P3, honest-direction). A verbatim quote present in the clause but
    differing only in case at a sentence start is NOT confirmed (could-not-verify
    instead of supported). This is the SAFE direction (never a false green), but a
    coverage gap: a real quote the lawyer pasted lowercase is left unconfirmed.
    """

    @unittest.expectedFailure
    def test_verbatim_quote_should_match_case_insensitively(self) -> None:
        verdict = verify_claim_against_clause(
            'The contract states that "time is of the essence" for all deadlines.',
            "Time is of the essence with respect to each obligation under this Agreement.",
        )
        self.assertEqual("present", verdict.disposition)


if __name__ == "__main__":
    unittest.main()
