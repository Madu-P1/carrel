"""ADR-0013 flag-gated disposer (`CARREL_SUBJECT_LABELER`).

These run with the labeler ON and pin the truth table: green only on a confirmed
same-subject match, refuse a cross-subject value coincidence, keep the altered-figure
catch via the value-absent fall-through, and leave the default (flag off) untouched.
The regex floor cannot bind every shape (bare-role / multi-word subjects need AFM), so
the assertions use the qualified shapes the floor handles; the collision canary tracks
the rest as the AFM-pending gap.
"""

from __future__ import annotations

import os
import unittest
from contextlib import contextmanager

from services.legal.contract_verify import verify_claim_against_clause


@contextmanager
def _labeler(value="regex"):
    prev = os.environ.get("CARREL_SUBJECT_LABELER")
    os.environ["CARREL_SUBJECT_LABELER"] = value
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop("CARREL_SUBJECT_LABELER", None)
        else:
            os.environ["CARREL_SUBJECT_LABELER"] = prev


class FlagOnDisposerTests(unittest.TestCase):
    def test_collision_is_not_a_false_green(self):
        with _labeler():
            v = verify_claim_against_clause(
                "The liability cap is $5,000,000.",
                "The indemnification cap is $5,000,000.",
            )
        self.assertNotEqual("present", v.disposition)
        self.assertEqual("not_found", v.disposition)

    def test_collision_with_unbindable_clause_is_not_a_false_green(self):
        # The claim is bound; the clause subject is unbindable ("capped at"); the value
        # coincides. Must NOT green just because the clause subject is unconfirmed.
        with _labeler():
            v = verify_claim_against_clause(
                "The liability cap is $5,000,000.",
                "The Seller's indemnification shall be capped at $5,000,000.",
            )
        self.assertNotEqual("present", v.disposition)

    def test_same_subject_match_is_not_affirmed(self):
        # ADR-0013 scope-out: even a confirmed same-subject match does not affirm a
        # figure; only a contradiction is a definite figure verdict.
        with _labeler():
            v = verify_claim_against_clause(
                "The liability cap is $5,000,000.",
                "The liability cap is $5,000,000.",
            )
        self.assertNotEqual("present", v.disposition)

    def test_same_subject_mismatch_is_a_contradiction(self):
        with _labeler():
            v = verify_claim_against_clause(
                "The liability cap is $10,000,000.",
                "The liability cap is $5,000,000.",
            )
        self.assertEqual("parametric_contradiction", v.disposition)

    def test_value_absent_catch_survives_via_fallthrough(self):
        # Claim bound to a different subject than the clause, and the claim value is
        # ABSENT from the clause: the value-only path still raises the contradiction.
        with _labeler():
            v = verify_claim_against_clause(
                "The liability cap is $10,000,000.",
                "The aggregate liability shall not exceed $5,000,000.",
            )
        self.assertEqual("parametric_contradiction", v.disposition)

    def test_recall_cost_unbindable_clause_subject_refuses(self):
        # The documented recall cost: a legit match whose clause subject the regex floor
        # cannot bind drops to could-not-check (AFM recovers it). Honest, not a green.
        with _labeler():
            v = verify_claim_against_clause(
                "The aggregate liability cap is $5,000,000.",
                "In no event shall the aggregate liability of either party exceed $5,000,000.",
            )
        self.assertNotEqual("present", v.disposition)

    def test_scope_out_is_the_default(self):
        # ADR-0013 scope-out is the DEFAULT: with no labeler flag at all, a cross-subject
        # value coincidence is could-not-check, not a green. The live false green is
        # closed in the default path (figures are never affirmed).
        prev = os.environ.pop("CARREL_SUBJECT_LABELER", None)
        try:
            v = verify_claim_against_clause(
                "The liability cap is $5,000,000.",
                "The indemnification cap is $5,000,000.",
            )
        finally:
            if prev is not None:
                os.environ["CARREL_SUBJECT_LABELER"] = prev
        self.assertNotEqual("present", v.disposition)


if __name__ == "__main__":
    unittest.main()
