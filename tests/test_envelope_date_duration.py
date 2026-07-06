"""Integration: date-range vs stated-duration conflicts ride the structural_findings channel.

Wired 2026-07-06. A period whose endpoint dates cannot match the stated duration under any
recognized counting convention surfaces as a FLAGGED date_duration_conflict structural
finding (real weight, never a claim-vs-source verdict). A consistent period surfaces NOTHING
(the no-false-accusation guard). Every finding MUST satisfy StructuralFindingItem, or
/api/verify's response_model 500s (the regression lock, per the words_figures Mythos catch).
The detector's own logic is in tests/test_date_duration_conflict.py.
"""

import unittest

from api_models import StructuralFindingItem
from services.legal.deterministic_envelope import build_deterministic_envelope

CONFLICT = "The term runs from January 1, 2025 to June 30, 2025, a period of nine (9) months."
CONSISTENT = (
    "The term runs from January 1, 2025 to December 31, 2025, a period of twelve (12) months."
)


def _findings(draft: str) -> list[dict]:
    return list(build_deterministic_envelope(draft).get("structural_findings", []))


def _dd(findings: list[dict]) -> list[dict]:
    return [f for f in findings if str(f.get("kind", "")).startswith("date_duration")]


class DateDurationEnvelopeWiring(unittest.TestCase):
    def test_definite_conflict_is_flagged(self):
        fs = _dd(_findings(CONFLICT))
        self.assertEqual(len(fs), 1)
        self.assertEqual(fs[0]["kind"], "date_duration_conflict")
        self.assertEqual(fs[0]["disposition"], "flagged")  # confirmed conflict, real weight

    def test_every_finding_satisfies_the_api_contract(self):
        # REGRESSION LOCK: each structural finding must validate against StructuralFindingItem
        # or /api/verify 500s (same class of bug Mythos caught on words_figures).
        for draft in (CONFLICT, CONSISTENT, "The parties agree to cooperate in good faith."):
            for f in _findings(draft):
                StructuralFindingItem.model_validate(f)

    def test_consistent_period_never_accuses(self):
        # HONESTY GUARD: a period whose dates and duration agree produces no finding.
        self.assertEqual(_dd(_findings(CONSISTENT)), [])

    def test_clean_prose_adds_nothing(self):
        self.assertEqual(_dd(_findings("The parties agree to cooperate in good faith.")), [])

    def test_adds_no_green(self):
        for f in _findings(CONFLICT):
            self.assertIn(f["disposition"], ("flagged", "could_not_check"))

    def test_calendar_overflow_refuses_not_crashes(self):
        # REGRESSION (Mythos 2026-07-06): a stated interval too large for the calendar
        # (e.g. "9999 years") must refuse could-not-check, never raise into the sealed path.
        fs = _dd(_findings("From January 1, 2026 to June 30, 2026, a period of 9999 years."))
        self.assertEqual(len(fs), 1)
        self.assertEqual(fs[0]["disposition"], "could_not_check")

    def test_overflow_frame_does_not_swallow_a_real_conflict(self):
        # REGRESSION (Mythos 2026-07-06): a draft with BOTH a real conflict AND an overflow
        # frame must keep the real FLAGGED conflict -- the guard must never drop the pass.
        draft = (
            "The term runs from January 1, 2025 to June 30, 2025, a period of nine (9) months. "
            "A later term runs from January 1, 2026 to June 30, 2026, a period of 9999 years."
        )
        fs = _dd(_findings(draft))
        self.assertTrue(any(f["disposition"] == "flagged" for f in fs))
        self.assertTrue(any(f["disposition"] == "could_not_check" for f in fs))


if __name__ == "__main__":
    unittest.main()
