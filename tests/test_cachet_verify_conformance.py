"""Batch D: the conformance suite is the executable spec, and this kernel
passes it. Locks the corpus loader's validation, the floor semantics (a
deliberately dishonest fake implementation must FAIL), and this repo's
adapter's conformance against the shared JSONL corpus."""

from __future__ import annotations

import unittest

from cachet_verify.adapter import verify_claim
from cachet_verify.conformance import (
    DEFAULT_CORPUS,
    ConformanceCase,
    load_corpus,
    run_conformance,
)


def _kernel_verify(claim: str, sources: list[str]) -> str:
    return verify_claim(claim, sources).state


class CorpusLoaderTests(unittest.TestCase):
    def test_default_corpus_loads_and_is_balanced(self) -> None:
        cases = load_corpus(DEFAULT_CORPUS)
        self.assertGreaterEqual(len(cases), 24)
        truths = {c.truth for c in cases}
        self.assertEqual({"altered", "faithful", "uncheckable"}, truths)

    def test_duplicate_ids_are_rejected(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            f.write('{"id": "X", "truth": "altered", "claim": "a", "source": "b"}\n')
            f.write('{"id": "X", "truth": "faithful", "claim": "c", "source": "c"}\n')
        with self.assertRaises(ValueError):
            load_corpus(f.name)


class FloorSemanticsTests(unittest.TestCase):
    CASES = [
        ConformanceCase(id="A1", truth="altered", claim="x is 5", source="x is 3"),
        ConformanceCase(id="F1", truth="faithful", claim="x is 3", source="x is 3"),
        ConformanceCase(id="U1", truth="uncheckable", claim="all is well", source="x is 3"),
    ]

    def test_false_green_fails_conformance(self) -> None:
        report = run_conformance(lambda c, s: "verified", self.CASES)
        self.assertFalse(report.conformant)
        self.assertTrue(any("FALSE GREEN" in v for v in report.violations))

    def test_false_accusation_fails_conformance(self) -> None:
        report = run_conformance(lambda c, s: "altered", self.CASES)
        self.assertFalse(report.conformant)
        self.assertTrue(any("FALSE ACCUSATION" in v for v in report.violations))

    def test_off_vocabulary_state_fails_conformance(self) -> None:
        report = run_conformance(lambda c, s: "probably_fine", self.CASES)
        self.assertFalse(report.conformant)

    def test_always_refusing_is_conformant_but_zero_catch(self) -> None:
        # Honesty floors allow a maximally conservative implementation; the
        # catch rate exposes its uselessness without calling it dishonest.
        report = run_conformance(lambda c, s: "could_not_check", self.CASES)
        self.assertTrue(report.conformant)
        self.assertEqual(0.0, report.catch_rate)

    def test_vacuous_pass_is_refused(self) -> None:
        # mythos batchE-20260702 (high), locked: a zero-case (or truth-class-
        # missing) corpus proves nothing and must NOT read as conformant.
        empty = run_conformance(lambda c, s: "verified", [])
        self.assertFalse(empty.conformant)
        self.assertTrue(any("vacuous" in v for v in empty.violations))
        one_class = run_conformance(lambda c, s: "could_not_check", [self.CASES[2]])
        self.assertFalse(one_class.conformant)


class KernelConformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_conformance(_kernel_verify, load_corpus(DEFAULT_CORPUS))

    def test_this_kernel_is_conformant(self) -> None:
        self.assertEqual((), self.report.violations)

    def test_this_kernel_catches_every_anchored_alteration(self) -> None:
        # The batch-A baseline, now enforced through the SHARED corpus so a
        # future port inherits the same bar.
        self.assertEqual(self.report.altered_total, self.report.altered_caught)

    def test_this_kernel_confirms_every_faithful_case(self) -> None:
        self.assertEqual(self.report.faithful_total, self.report.faithful_confirmed)


if __name__ == "__main__":
    unittest.main()
