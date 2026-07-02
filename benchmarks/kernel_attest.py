"""Attestation-kernel latency benchmark (ADR-0015 batch E).

Measures per-claim verify latency and whole-draft attestation latency over the
conformance corpus. The kernel's speed IS product surface: an ambient or
CI-gate embedder budgets milliseconds, and a silent 10x regression (an
accidental O(n^2) in the candidate fan-out, a pathological regex) should fail
loudly in review, not in a demo.

Run:  ./.venv/bin/python -m benchmarks.kernel_attest
"""

from __future__ import annotations

import statistics
import time

from cachet_verify.adapter import attest_draft, verify_claim
from cachet_verify.conformance import DEFAULT_CORPUS, load_corpus


def _quantiles(samples: list[float]) -> tuple[float, float, float]:
    ordered = sorted(samples)
    p50 = statistics.median(ordered)
    p95 = ordered[max(0, int(round(0.95 * (len(ordered) - 1))))]
    return p50, p95, statistics.fmean(ordered)


def run_benchmark(rounds: int = 3) -> dict[str, object]:
    cases = load_corpus(DEFAULT_CORPUS)
    per_claim: list[float] = []
    for _ in range(rounds):
        for case in cases:
            t0 = time.perf_counter()
            verify_claim(case.claim, [case.source])
            per_claim.append((time.perf_counter() - t0) * 1000)

    draft = "\n".join(c.claim for c in cases)
    sources: list[str | dict[str, object]] = ["\n".join(c.source for c in cases)]
    per_draft: list[float] = []
    for _ in range(rounds):
        t0 = time.perf_counter()
        attest_draft(draft, sources)
        per_draft.append((time.perf_counter() - t0) * 1000)

    c50, c95, cmean = _quantiles(per_claim)
    d50, d95, dmean = _quantiles(per_draft)
    return {
        "cases": len(cases),
        "rounds": rounds,
        "claim_ms": {"p50": round(c50, 2), "p95": round(c95, 2), "mean": round(cmean, 2)},
        "draft_ms": {
            "p50": round(d50, 1),
            "p95": round(d95, 1),
            "mean": round(dmean, 1),
            "claims": len(cases),
        },
    }


def main() -> int:
    result = run_benchmark()
    print(f"corpus: {result['cases']} cases x {result['rounds']} rounds")
    c = result["claim_ms"]
    d = result["draft_ms"]
    assert isinstance(c, dict) and isinstance(d, dict)
    print(f"verify_claim  p50 {c['p50']} ms   p95 {c['p95']} ms   mean {c['mean']} ms")
    print(
        f"attest_draft  p50 {d['p50']} ms   p95 {d['p95']} ms   mean {d['mean']} ms"
        f"   ({d['claims']}-claim draft, whole-corpus source)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
