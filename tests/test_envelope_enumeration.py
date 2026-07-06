"""Integration: enumeration count vs enumerated list rides the structural_findings channel.

Wired 2026-07-06. A lead-in declaring N items ("the following three (3) conditions:") whose
enumerated markers count a different number surfaces as a FLAGGED enumeration_count_conflict
structural finding. A matching count surfaces NOTHING (the no-false-accusation guard). Every
finding MUST satisfy StructuralFindingItem or /api/verify's response_model 500s (the
regression lock). The detector keeps no single end offset, so start/end/span are adapted at
the wire from frame_start + declared_surface; test_offsets_are_a_real_range locks that. The
detector's own logic is in tests/test_enumeration_count.py.
"""

import unittest

from api_models import StructuralFindingItem
from services.legal.deterministic_envelope import build_deterministic_envelope

CONFLICT = "Termination requires the following three (3) conditions: (a) notice; (b) cure period; (c) failure to cure; and (d) a certificate."
CONSISTENT = "Termination requires the following three (3) conditions: (a) notice; (b) cure period; (c) failure to cure."


def _findings(draft: str) -> list[dict]:
    return list(build_deterministic_envelope(draft).get("structural_findings", []))


def _en(findings: list[dict]) -> list[dict]:
    return [f for f in findings if str(f.get("kind", "")).startswith("enumeration_count")]


class EnumerationEnvelopeWiring(unittest.TestCase):
    def test_count_mismatch_is_flagged(self):
        fs = _en(_findings(CONFLICT))
        self.assertEqual(len(fs), 1)
        self.assertEqual(fs[0]["kind"], "enumeration_count_conflict")
        self.assertEqual(fs[0]["disposition"], "flagged")

    def test_every_finding_satisfies_the_api_contract(self):
        # REGRESSION LOCK: each finding must validate against StructuralFindingItem.
        for draft in (CONFLICT, CONSISTENT, "The parties agree to cooperate in good faith."):
            for f in _findings(draft):
                StructuralFindingItem.model_validate(f)

    def test_matching_count_never_accuses(self):
        # HONESTY GUARD: declared count == enumerated count produces no finding.
        self.assertEqual(_en(_findings(CONSISTENT)), [])

    def test_clean_prose_adds_nothing(self):
        self.assertEqual(_en(_findings("The parties agree to cooperate in good faith.")), [])

    def test_adds_no_green(self):
        for f in _findings(CONFLICT):
            self.assertIn(f["disposition"], ("flagged", "could_not_check"))

    def test_offsets_index_the_real_frame(self):
        # REGRESSION (Mythos 2026-07-06): start/end must be REAL draft offsets (the frame's
        # m.start/m.end), so the whitespace-collapsed draft[start:end] equals span -- the same
        # invariant the other structural findings uphold. A frame with internal whitespace and a
        # newline locks it (the earlier synthesized end = start + len(collapsed) sliced mid-word).
        import re

        draft = "The following  three   (3)\nconditions: (a) x; (b) y; (c) z; and (d) w."
        fs = _en(_findings(draft))
        self.assertEqual(len(fs), 1)
        s, e = fs[0]["start"], fs[0]["end"]
        self.assertGreater(e, s)
        self.assertEqual(re.sub(r"\s+", " ", draft[s:e]).strip(), fs[0]["span"])


if __name__ == "__main__":
    unittest.main()
