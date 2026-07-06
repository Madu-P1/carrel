"""Integration: words_figures conflicts ride the structural_findings channel.

Wired 2026-07-06 (branch cachet/slice-words-figures-live). A word-vs-figure self-
contradiction surfaces as a FLAGGED words_figures_conflict structural finding (real
weight, never a claim-vs-source verdict). A consistent pair surfaces NOTHING (the
no-false-accusation guard, honesty-critical).

Every produced finding MUST satisfy the StructuralFindingItem API contract that the
/api/verify response_model enforces -- a shape break there 500s the route on the very
finding it produces. Mythos caught exactly that on the first draft (the dict was missing
disposition/start/end); test_every_finding_satisfies_the_api_contract is the regression
lock. The detector's own logic lives in tests/test_words_figures.py; this proves the wire
+ the contract + the honesty invariants.
"""

import unittest

from api_models import StructuralFindingItem
from services.legal.deterministic_envelope import build_deterministic_envelope


def _findings(draft: str) -> list[dict]:
    return list(build_deterministic_envelope(draft).get("structural_findings", []))


def _wf(findings: list[dict]) -> list[dict]:
    return [f for f in findings if str(f.get("kind", "")).startswith("words_figures")]


class WordsFiguresEnvelopeWiring(unittest.TestCase):
    def test_definite_conflict_is_flagged_with_both_figures_named(self):
        fs = _wf(_findings("The initial term is thirty (40) days from the Effective Date."))
        self.assertEqual(len(fs), 1)
        self.assertEqual(fs[0]["kind"], "words_figures_conflict")
        self.assertEqual(fs[0]["disposition"], "flagged")  # real weight (B), not advisory
        self.assertIn("40", fs[0]["detail"])  # names the pair's own figures verbatim

    def test_every_finding_satisfies_the_api_contract(self):
        # REGRESSION LOCK (Mythos 2026-07-06): each structural finding must validate
        # against StructuralFindingItem, or /api/verify's response_model 500s in production.
        for draft in (
            "The initial term is thirty (40) days.",
            "The rate is twenty (25) percent per annum.",
            "The parties agree to cooperate in good faith.",
        ):
            for f in _findings(draft):
                StructuralFindingItem.model_validate(f)  # raises on any shape drift

    def test_consistent_pair_never_accuses(self):
        # HONESTY GUARD: a matching word/figure pair must produce no words_figures finding.
        # Any finding here would be a false accusation -- the cardinal sin.
        self.assertEqual(_wf(_findings("The initial term is thirty (30) days.")), [])

    def test_clean_prose_adds_nothing(self):
        self.assertEqual(_wf(_findings("The parties agree to cooperate in good faith.")), [])

    def test_multiple_conflicts_all_surface(self):
        fs = _wf(_findings("Term is thirty (40) days and the rate is twenty (25) percent."))
        self.assertGreaterEqual(len(fs), 2)
        self.assertTrue(all(f["disposition"] == "flagged" for f in fs))

    def test_only_this_detector_adds_no_green(self):
        # The wire can only ADD contradicted/could-not-check findings, never a supported one.
        for f in _findings("The initial term is thirty (40) days."):
            self.assertIn(f["disposition"], ("flagged", "could_not_check"))


if __name__ == "__main__":
    unittest.main()
