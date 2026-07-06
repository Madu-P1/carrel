"""Integration: inverted bound pairs ride the structural_findings channel.

Wired 2026-07-06. A two-sided constraint whose floor exceeds its ceiling ("not less than
sixty (60) days nor more than thirty (30) days") is unsatisfiable and surfaces as a FLAGGED
bound_pair_conflict structural finding. A consistent pair (floor <= ceiling) surfaces NOTHING
(the no-false-accusation guard). Every finding MUST satisfy StructuralFindingItem or
/api/verify's response_model 500s (the regression lock). Detector logic is locked by
tests/test_bound_pairs.py.
"""

import unittest

from api_models import StructuralFindingItem
from services.legal.deterministic_envelope import build_deterministic_envelope

CONFLICT = "Notice shall be given not less than sixty (60) days nor more than thirty (30) days before closing."
CONSISTENT = "Notice shall be given not less than thirty (30) days nor more than sixty (60) days before closing."


def _findings(draft: str) -> list[dict]:
    return list(build_deterministic_envelope(draft).get("structural_findings", []))


def _bp(findings: list[dict]) -> list[dict]:
    return [f for f in findings if str(f.get("kind", "")).startswith("bound_pair")]


class BoundPairsEnvelopeWiring(unittest.TestCase):
    def test_inverted_pair_is_flagged(self):
        fs = _bp(_findings(CONFLICT))
        self.assertEqual(len(fs), 1)
        self.assertEqual(fs[0]["kind"], "bound_pair_conflict")
        self.assertEqual(fs[0]["disposition"], "flagged")

    def test_every_finding_satisfies_the_api_contract(self):
        # REGRESSION LOCK: each finding must validate against StructuralFindingItem.
        for draft in (CONFLICT, CONSISTENT, "The parties agree to cooperate in good faith."):
            for f in _findings(draft):
                StructuralFindingItem.model_validate(f)

    def test_consistent_pair_never_accuses(self):
        # HONESTY GUARD: floor <= ceiling must produce no bound_pair finding.
        self.assertEqual(_bp(_findings(CONSISTENT)), [])

    def test_clean_prose_adds_nothing(self):
        self.assertEqual(_bp(_findings("The parties agree to cooperate in good faith.")), [])

    def test_adds_no_green(self):
        for f in _findings(CONFLICT):
            self.assertIn(f["disposition"], ("flagged", "could_not_check"))

    def test_offsets_are_real_range(self):
        # end must be a real offset past start (the surface span), not a degenerate point.
        fs = _bp(_findings(CONFLICT))
        self.assertGreater(fs[0]["end"], fs[0]["start"])


if __name__ == "__main__":
    unittest.main()
