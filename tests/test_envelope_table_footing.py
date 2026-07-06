"""Integration: table footing rides the structural_findings channel.

Wired 2026-07-06. A stated Total that does not equal the exact sum of the line items surfaces
as a FLAGGED table_footing_conflict structural finding. A correctly-footed table surfaces
NOTHING (the no-false-accusation guard). The detector is line-based (rows carry line numbers,
no char offsets); the wire converts line -> char span via the draft's own line boundaries,
so draft[start:end] == span holds (test_offsets_index_the_real_table locks it). Every finding
MUST satisfy StructuralFindingItem or /api/verify's response_model 500s (the regression lock).
The detector's own logic is in tests/test_table_footing.py.
"""

import unittest

from api_models import StructuralFindingItem
from services.legal.deterministic_envelope import build_deterministic_envelope

CONFLICT = (
    "Consulting fees      $10,000\n"
    "Travel               $2,500\n"
    "Software licences    $1,200\n"
    "Total                $14,000"  # 10,000 + 2,500 + 1,200 = 13,700, not 14,000
)
CONSISTENT = (
    "Consulting fees      $10,000\n"
    "Travel               $2,500\n"
    "Software licences    $1,200\n"
    "Total                $13,700"
)


def _findings(draft: str) -> list[dict]:
    return list(build_deterministic_envelope(draft).get("structural_findings", []))


def _tf(findings: list[dict]) -> list[dict]:
    return [f for f in findings if str(f.get("kind", "")).startswith("table_footing")]


class TableFootingEnvelopeWiring(unittest.TestCase):
    def test_footing_mismatch_is_flagged(self):
        fs = _tf(_findings(CONFLICT))
        self.assertEqual(len(fs), 1)
        self.assertEqual(fs[0]["kind"], "table_footing_conflict")
        self.assertEqual(fs[0]["disposition"], "flagged")

    def test_every_finding_satisfies_the_api_contract(self):
        # REGRESSION LOCK: each finding must validate against StructuralFindingItem.
        for draft in (CONFLICT, CONSISTENT, "The parties agree to cooperate in good faith."):
            for f in _findings(draft):
                StructuralFindingItem.model_validate(f)

    def test_correctly_footed_table_never_accuses(self):
        # HONESTY GUARD: a table whose Total equals the sum produces no finding.
        self.assertEqual(_tf(_findings(CONSISTENT)), [])

    def test_clean_prose_adds_nothing(self):
        self.assertEqual(_tf(_findings("The parties agree to cooperate in good faith.")), [])

    def test_adds_no_green(self):
        for f in _findings(CONFLICT):
            self.assertIn(f["disposition"], ("flagged", "could_not_check"))

    def test_offsets_index_the_real_table(self):
        # The line->char conversion must be exact: draft[start:end] == span verbatim.
        fs = _tf(_findings(CONFLICT))
        self.assertTrue(fs)
        f = fs[0]
        self.assertEqual(CONFLICT[f["start"] : f["end"]], f["span"])
        self.assertIn("Total", f["span"])  # the span reaches the total line

    def test_crlf_offsets_stay_aligned(self):
        # splitlines(keepends) handles CRLF; draft[start:end] == span must still hold.
        crlf = CONFLICT.replace("\n", "\r\n")
        fs = _tf(_findings(crlf))
        self.assertTrue(fs)
        f = fs[0]
        self.assertEqual(crlf[f["start"] : f["end"]], f["span"])


if __name__ == "__main__":
    unittest.main()
