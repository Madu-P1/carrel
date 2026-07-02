"""Locks the kernel-residue parity result (ADR-0015, revisit-trigger #3).

The council sized the kernel-extraction bet on this experiment: the
domain-agnostic residue (quote, money, percent, duration, magnitude, date)
against non-legal AI fabrications. These tests pin the result so a future
engine change that erodes it fails loudly instead of silently shrinking the
portable kernel's value.
"""

from __future__ import annotations

import unittest

from evals.kernel_residue.corpus import CASES
from evals.kernel_residue.harness import evaluate


class KernelResidueParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.summary = evaluate(CASES)

    def test_honesty_floor_no_false_greens(self) -> None:
        # An altered claim must NEVER read as supported. This is the floor the
        # whole product stands on; one failure here outweighs any catch rate.
        self.assertEqual(
            [],
            [r.case.id for r in self.summary.false_greens],
            "altered case(s) read as supported",
        )

    def test_honesty_floor_no_false_accusations(self) -> None:
        # A faithful claim must NEVER be flagged. False reds kill retention the
        # way false greens kill demos.
        self.assertEqual(
            [],
            [r.case.id for r in self.summary.false_accusations],
            "faithful case(s) flagged",
        )

    def test_every_anchored_alteration_is_caught(self) -> None:
        # Batch-A baseline (2026-07-02): 15/15 anchored near-verbatim
        # fabrications caught across finance, consulting, medical, tax,
        # operations, journalism -- including the three blind spots the first
        # run documented (mg dosage, tons, grouped counts), closed by the
        # kernel residue detectors. A drop below total is a regression in the
        # portable kernel's value.
        self.assertEqual(self.summary.altered_flagged, self.summary.altered_total)
        self.assertGreaterEqual(self.summary.altered_total, 15)

    def test_blind_spots_refuse_never_rule(self) -> None:
        # The NEXT documented gaps (ratio notation, word-form frequency,
        # temperature units) plus pure-semantic claims: the honest verdict is
        # refusal, never silence and never a guess.
        self.assertEqual(self.summary.uncheckable_refused, self.summary.uncheckable_total)
        self.assertGreaterEqual(self.summary.uncheckable_total, 4)

    def test_faithful_restatements_are_confirmed(self) -> None:
        # Batch-A baseline: every faithful case confirms (5/5) via the
        # exact-restatement rule and the residue near-copy confirmation. The
        # engine's topicality conservatism still governs anything looser.
        self.assertEqual(self.summary.faithful_supported, self.summary.faithful_total)
        self.assertGreaterEqual(self.summary.faithful_total, 5)

    def test_verbatim_quote_is_confirmed(self) -> None:
        q2 = next(r for r in self.summary.results if r.case.id == "Q2")
        self.assertEqual(q2.outcome, "supported")


if __name__ == "__main__":
    unittest.main()
