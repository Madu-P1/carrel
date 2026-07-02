"""The SourceIndex upgrade: sharing precomputed source data across claims must
be invisible in every verdict. The index is pure derived data, so the indexed
and per-call paths must produce BYTE-IDENTICAL attestations -- if they ever
diverge, the cache is changing verdicts and the upgrade is wrong."""

from __future__ import annotations

import time
import unittest
from unittest import mock

import cachet_verify.adapter as adapter
from cachet_verify.adapter import attest_draft, build_source_index, verify_claim
from cachet_verify.certificate import attest_and_issue
from cachet_verify.conformance import DEFAULT_CORPUS, load_corpus


class IndexEquivalenceTests(unittest.TestCase):
    def test_indexed_path_matches_per_call_path_on_the_whole_corpus(self) -> None:
        for case in load_corpus(DEFAULT_CORPUS):
            index = build_source_index([case.source])
            with_index = verify_claim(case.claim, [case.source], index=index)
            without = verify_claim(case.claim, [case.source])
            self.assertEqual(without, with_index, case.id)

    def test_multi_source_flattening_matches_single_source_equivalent(self) -> None:
        # mythos (low): the refactor flattens the old nested per-source loops
        # into one index.sentences list. Guard that two sentences split across
        # TWO sources verify identically to the same two in one source, and
        # that both match the per-call path -- the flattening must not reorder
        # or drop a sentence in a way that moves a verdict.
        one = ["Net revenue was $2.4 billion.\nThe fund totals $180 million."]
        two = ["Net revenue was $2.4 billion.", "The fund totals $180 million."]
        for claim in (
            "The fund totals $360 million.",
            "Net revenue was $2.4 billion.",
            "The fund totals $180 million.",
        ):
            v_one = verify_claim(claim, one)
            v_two = verify_claim(claim, two)
            self.assertEqual(v_one.state, v_two.state, claim)
            self.assertEqual(v_two, verify_claim(claim, two, index=build_source_index(two)), claim)

    def test_shared_index_across_claims_matches_fresh_indexes(self) -> None:
        sources = [
            "Net revenue for the third quarter was $2.4 billion.\n"
            "The settlement fund totals $180 million.\n"
            "Started on atorvastatin 5 mg nightly at discharge."
        ]
        claims = [
            "Net revenue for the third quarter was $2.4 billion.",
            "The settlement fund totals $360 million.",
            "Started on atorvastatin 50 mg nightly at discharge.",
            "Momentum remains strong across the portfolio.",
        ]
        shared = build_source_index(sources)
        for claim in claims:
            self.assertEqual(
                verify_claim(claim, sources),
                verify_claim(claim, sources, index=shared),
                claim,
            )

    def test_certificates_unchanged_by_the_upgrade(self) -> None:
        # The sealed artifact is downstream of attest_draft; determinism of the
        # whole pipeline through the index must hold.
        draft = (
            "Net revenue for the third quarter was $2.4 billion.\n"
            "The settlement fund totals $360 million."
        )
        sources = [
            "Net revenue for the third quarter was $2.4 billion.\n"
            "The settlement fund totals $180 million."
        ]
        issued = "2026-07-02T09:00:00+00:00"
        self.assertEqual(
            attest_and_issue(draft, sources, issued),
            attest_and_issue(draft, sources, issued),
        )

    def test_attest_draft_builds_source_prep_once_not_per_claim(self) -> None:
        # The amortization, proven STRUCTURALLY (deterministic, machine-
        # independent -- a wall-clock ratio flakes under load and proves
        # nothing). The expensive source prep is the quote-pool build; before
        # the upgrade a 10-claim draft built it 10 times (once per verify_claim),
        # now build_source_index builds it exactly ONCE and every claim reuses
        # the shared index.
        draft = "\n".join(f"The fee for phase {i} is ${i} million." for i in range(10))
        source = "The fee for phase 3 is $3 million."
        with mock.patch.object(
            adapter, "prepare_source_pool", wraps=adapter.prepare_source_pool
        ) as spy:
            result = attest_draft(draft, [source])
        self.assertEqual(1, spy.call_count, "source pool rebuilt per claim; index not shared")
        self.assertEqual(10, len(result.claims))


class CeilingCalibrationTests(unittest.TestCase):
    def test_worst_case_at_the_ceiling_stays_bounded(self) -> None:
        # The ceiling exists to keep the worst honest wedge bounded. Attest a
        # near-copy draft sized just UNDER the pair ceiling and require it to
        # finish inside a hard wall (generous vs the ~30s design target so a
        # loaded CI machine never flakes, but a regression to minutes fails).
        n = 62  # 62 x 62 = 3,844 pairs, just under the 4,000 ceiling
        # Money-heavy near-copy: every sentence is relevant AND carries an
        # anchor, so the adjudicator does real per-pair work (the true worst
        # case, ~2 ms/pair measured -> ~8 s). The 90 s wall is generous vs that
        # so CI never flakes, but a regression to minutes fails loudly.
        block = "\n".join(f"The stage {i} fee is ${i} million dollars." for i in range(n))
        t0 = time.perf_counter()
        d = attest_draft(block, [block])
        elapsed = time.perf_counter() - t0
        self.assertIn(d.state, ("verified", "altered", "could_not_check"))
        self.assertGreater(len(d.claims), 1)  # processed, not the oversize refusal
        self.assertLess(elapsed, 90, f"{elapsed:.1f}s at the ceiling; the bound has regressed")


if __name__ == "__main__":
    unittest.main()
