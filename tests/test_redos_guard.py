"""ReDoS guard: the engine's scan cost stays linear on adversarial inputs.

CodeQL (PR #194) flagged five polynomial-backtracking regexes on the
user-input hot path. The fix is structural -- possessive quantifiers plus
run-boundary lookbehinds, so a match can only start at the head of a
digit/punctuation run and every interior position fails in O(1). These tests
pin the property with pathological inputs that ran 2-15 SECONDS before the
fix and single-digit milliseconds after; the one-second ceilings carry ~30x
headroom so they catch a quadratic regression, never a loaded machine.
"""

from __future__ import annotations

import time
import unittest

from services.legal.anchors import extract_anchors
from services.legal.contract_verify import verify_claim_against_clause
from services.legal.sentences import split_sentences

_FLOOD = 40_000


def _timed(fn) -> float:
    t0 = time.perf_counter()
    fn()
    return time.perf_counter() - t0


class RedosGuardTests(unittest.TestCase):
    def test_digit_flood_anchors_stay_linear(self) -> None:
        self.assertLess(_timed(lambda: extract_anchors("9" * _FLOOD)), 1.0)
        self.assertLess(_timed(lambda: extract_anchors("9" * _FLOOD + "x")), 1.0)

    def test_digit_flood_clause_verify_stays_linear(self) -> None:
        self.assertLess(
            _timed(lambda: verify_claim_against_clause("9" * _FLOOD, "9" * _FLOOD)), 2.0
        )

    def test_punctuation_flood_splitter_stays_linear(self) -> None:
        self.assertLess(_timed(lambda: split_sentences("!" * _FLOOD)), 1.0)

    def test_whitespace_flood_percent_subject_stays_linear(self) -> None:
        self.assertLess(_timed(lambda: extract_anchors("5% " + " " * _FLOOD)), 1.0)

    def test_normal_inputs_unaffected(self) -> None:
        # The guards must not change what the detectors find on real text.
        anchors = extract_anchors("a fee of $2.5 million and a 12.5% rate over 30 days")
        types = sorted(a.type for a in anchors)
        self.assertIn("money", types)
        self.assertIn("percent", types)
        self.assertIn("duration", types)


if __name__ == "__main__":
    unittest.main()
