"""Batch E: kernel latency guard.

Measured baseline (2026-07-02, M-series): verify_claim p50 0.44 ms / p95
0.96 ms; attest_draft 271 ms for a 25-claim draft against a whole-corpus
source. The ceilings below carry ~50x headroom -- they exist to catch a
pathological regression (an accidental O(n^2), a catastrophic regex), never to
flake on a loaded machine.
"""

from __future__ import annotations

import time
import unittest

from cachet_verify.adapter import verify_claim
from cachet_verify.conformance import DEFAULT_CORPUS, load_corpus


class KernelLatencyGuardTests(unittest.TestCase):
    def test_per_claim_latency_stays_sane(self) -> None:
        cases = load_corpus(DEFAULT_CORPUS)
        t0 = time.perf_counter()
        for case in cases:
            verify_claim(case.claim, [case.source])
        mean_ms = (time.perf_counter() - t0) * 1000 / len(cases)
        self.assertLess(
            mean_ms,
            50,
            f"mean per-claim verify latency {mean_ms:.1f} ms exceeds the 50 ms "
            "pathology ceiling (baseline: ~0.5 ms)",
        )


if __name__ == "__main__":
    unittest.main()
