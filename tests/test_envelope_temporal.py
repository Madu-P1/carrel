"""Integration: document-scale temporal ordering rides the structural_findings channel.

Wired 2026-07-06. When stated before/after ordering constraints among events form an
impossible cycle ("A before B" and "B before A"), it surfaces as a FLAGGED temporal_conflict
structural finding. A consistent ordering surfaces NOTHING (the no-false-accusation guard).
Every finding MUST satisfy StructuralFindingItem or /api/verify's response_model 500s (the
regression lock). The detector's own logic is in tests/test_temporal_graph.py.
"""

import unittest

from api_models import StructuralFindingItem
from services.legal.deterministic_envelope import build_deterministic_envelope

CONFLICT = (
    "The Hearing must be completed before the Filing. The Filing shall occur before the Hearing."
)
CONSISTENT = (
    "The Hearing must be completed before the Filing. The Filing shall occur before the Trial."
)


def _findings(draft: str) -> list[dict]:
    return list(build_deterministic_envelope(draft).get("structural_findings", []))


def _tg(findings: list[dict]) -> list[dict]:
    return [f for f in findings if str(f.get("kind", "")).startswith("temporal")]


class TemporalEnvelopeWiring(unittest.TestCase):
    def test_ordering_cycle_is_flagged(self):
        fs = _tg(_findings(CONFLICT))
        self.assertTrue(any(f["kind"] == "temporal_conflict" for f in fs))
        self.assertTrue(any(f["disposition"] == "flagged" for f in fs))

    def test_every_finding_satisfies_the_api_contract(self):
        # REGRESSION LOCK: each finding must validate against StructuralFindingItem.
        for draft in (CONFLICT, CONSISTENT, "The parties agree to cooperate in good faith."):
            for f in _findings(draft):
                StructuralFindingItem.model_validate(f)

    def test_consistent_ordering_never_accuses(self):
        # HONESTY GUARD: an acyclic ordering produces no temporal conflict.
        self.assertFalse(any(f["disposition"] == "flagged" for f in _tg(_findings(CONSISTENT))))

    def test_clean_prose_adds_nothing(self):
        self.assertEqual(_tg(_findings("The parties agree to cooperate in good faith.")), [])

    def test_adds_no_green(self):
        for f in _findings(CONFLICT):
            self.assertIn(f["disposition"], ("flagged", "could_not_check"))

    def test_offsets_are_valid(self):
        # start/end are the detector's real envelope offsets; span is its curated cycle
        # description (not draft[start:end], per the crossref lesson). Assert a valid range.
        fs = _tg(_findings(CONFLICT))
        self.assertTrue(fs)
        f = fs[0]
        self.assertTrue(0 <= f["start"] <= f["end"] <= len(CONFLICT))
        self.assertTrue(f["span"])

    def test_oversized_draft_skips_temporal_no_hang(self):
        # DoS GUARD (Mythos 2026-07-06): temporal cycle detection is superlinear, so on the
        # sealed path it is bounded to drafts under _TEMPORAL_MAX_CHARS. A large draft must
        # complete fast (the other detectors still run) rather than hang on 32x Bellman-Ford.
        import time

        big = (CONFLICT + " ") * 700  # > 50KB
        self.assertGreater(len(big), 50_000)
        t0 = time.perf_counter()
        env = build_deterministic_envelope(big)
        self.assertLess(time.perf_counter() - t0, 5.0)  # bounded, not a hang
        self.assertEqual(_tg(env.get("structural_findings", [])), [])  # temporal skipped


if __name__ == "__main__":
    unittest.main()
