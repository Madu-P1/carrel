"""Integration: cross-reference integrity rides the structural_findings channel.

Wired 2026-07-06. A reference to a section/exhibit with no matching heading in the document
("as provided in Section 9" with no Section 9) surfaces as a FLAGGED crossref_conflict
structural finding. A resolving reference surfaces NOTHING (the no-false-accusation guard).
Every finding MUST satisfy StructuralFindingItem or /api/verify's response_model 500s (the
regression lock). The detector's own logic is in tests/test_crossref_integrity.py.
"""

import unittest

from api_models import StructuralFindingItem
from services.legal.deterministic_envelope import build_deterministic_envelope

CONFLICT = "Section 1. Purpose.\nSection 2. Term.\nSection 3. Fees. Fees are governed by Section 9."
CONSISTENT = (
    "Section 1. Purpose.\nSection 2. Term. This is governed by Section 1.\nSection 3. Fees."
)


def _findings(draft: str) -> list[dict]:
    return list(build_deterministic_envelope(draft).get("structural_findings", []))


def _cr(findings: list[dict]) -> list[dict]:
    return [f for f in findings if str(f.get("kind", "")).startswith("crossref")]


class CrossrefEnvelopeWiring(unittest.TestCase):
    def test_dangling_reference_is_flagged(self):
        fs = _cr(_findings(CONFLICT))
        self.assertTrue(any(f["kind"] == "crossref_conflict" for f in fs))
        self.assertTrue(any(f["disposition"] == "flagged" for f in fs))

    def test_every_finding_satisfies_the_api_contract(self):
        # REGRESSION LOCK: each finding must validate against StructuralFindingItem.
        for draft in (CONFLICT, CONSISTENT, "The parties agree to cooperate in good faith."):
            for f in _findings(draft):
                StructuralFindingItem.model_validate(f)

    def test_resolving_reference_never_accuses(self):
        # HONESTY GUARD: a reference that resolves to an existing section produces no
        # crossref conflict.
        self.assertFalse(any(f["disposition"] == "flagged" for f in _cr(_findings(CONSISTENT))))

    def test_clean_prose_adds_nothing(self):
        self.assertEqual(_cr(_findings("The parties agree to cooperate in good faith.")), [])

    def test_adds_no_green(self):
        for f in _findings(CONFLICT):
            self.assertIn(f["disposition"], ("flagged", "could_not_check"))

    def test_offsets_are_valid_and_span_nonempty(self):
        # crossref span is the detector's curated context (NOT draft[start:end]: for
        # multi-occurrence kinds start/end is a first-to-last envelope, verified by Mythos
        # 2026-07-06). So assert a real offset range + a non-empty curated span, not equality.
        fs = _cr(_findings(CONFLICT))
        self.assertTrue(fs)
        f = fs[0]
        self.assertTrue(0 <= f["start"] < f["end"] <= len(CONFLICT))
        self.assertTrue(f["span"])


if __name__ == "__main__":
    unittest.main()
