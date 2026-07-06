"""Tests for services/bound_pairs.py, the bound-pair coherence detector.

Loads the detector's own corpus (evals/bound_pairs/corpus.jsonl) and asserts
every expected verdict plus every must_name substring, then locks the
campaign invariants directly:

* ZERO-GREEN / SILENT-ON-CONSISTENT: no code path returns a supported/green
  verdict. The finding dataclass rejects any verdict outside {contradicted,
  could_not_verify} at construction, and floor <= ceiling (including floor ==
  ceiling) produces zero findings.
* FIGURE-NAMING: every contradiction and every refusal names, in its own
  detail text, both figures it disposed over.
* SAME-QUANTITY GATE: different quantity kinds (duration vs money) and a
  duration pair spanning day/week vs month/year never contradict; the former
  is silent, the latter refuses naming both figures.
* NEVER ACCUSE A FAITHFUL COPIER: a conflict the source carries verbatim is
  the source's defect (could_not_verify), never an accusation of the draft.
* DETERMINISM: same input twice produces byte-identical findings.

Run directly:

    ./.venv/bin/python -m pytest tests/test_bound_pairs.py -q
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.bound_pairs import (  # noqa: E402
    ALLOWED_VERDICTS,
    CONTRADICTED,
    COULD_NOT_VERIFY,
    BoundPairFinding,
    detect_bound_pair_conflicts,
    find_bound_pairs,
)

_CORPUS = _REPO_ROOT / "evals" / "bound_pairs" / "corpus.jsonl"


def _load_corpus() -> list[dict]:
    return [json.loads(line) for line in _CORPUS.read_text().splitlines() if line.strip()]


def _haystack(finding: dict) -> str:
    return " ".join(str(v) for v in finding.values())


class CorpusTest(unittest.TestCase):
    """Every corpus case: exact verdict, every must_name substring present."""

    def setUp(self) -> None:
        self.corpus = _load_corpus()

    def test_corpus_has_required_mix(self) -> None:
        verdicts = [c["expected"]["verdict"] for c in self.corpus]
        self.assertGreaterEqual(len(self.corpus), 12, "corpus must hold >= 12 cases")
        self.assertGreaterEqual(verdicts.count("contradicted"), 5)
        self.assertGreaterEqual(verdicts.count("none"), 5)
        self.assertGreaterEqual(verdicts.count("could_not_verify"), 4)
        verbatim = [c for c in self.corpus if c.get("source")]
        self.assertGreaterEqual(len(verbatim), 1, "need >= 1 verbatim source-defect case")

    def test_every_case_matches_expectation(self) -> None:
        for case in self.corpus:
            with self.subTest(case=case["id"]):
                findings = detect_bound_pair_conflicts(case["text"], case.get("source", ""))
                expected = case["expected"]["verdict"]
                if expected == "none":
                    self.assertEqual(findings, [], f"{case['id']} must be silent, got {findings}")
                    continue
                matching = [f for f in findings if f["verdict"] == expected]
                self.assertTrue(
                    matching,
                    f"{case['id']} expected {expected}, got {[f['verdict'] for f in findings]}",
                )
                hay = _haystack(matching[0])
                for substring in case["expected"]["must_name"]:
                    self.assertIn(substring, hay, f"{case['id']} finding must name {substring!r}")

    def test_no_finding_is_ever_green(self) -> None:
        for case in self.corpus:
            findings = detect_bound_pair_conflicts(case["text"], case.get("source", ""))
            for finding in findings:
                self.assertIn(
                    finding["verdict"],
                    ALLOWED_VERDICTS,
                    f"{case['id']} emitted a non-allowed verdict {finding['verdict']!r}",
                )

    def test_every_finding_names_both_figures(self) -> None:
        for case in self.corpus:
            findings = detect_bound_pair_conflicts(case["text"], case.get("source", ""))
            for finding in findings:
                if finding["kind"] == "bound_pair_figure_conflict":
                    continue  # names its own numerals, checked directly below
                self.assertIn(
                    finding["floor_surface"],
                    finding["detail"],
                    f"{case['id']} detail must name floor figure {finding['floor_surface']!r}",
                )
                self.assertIn(
                    finding["ceiling_surface"],
                    finding["detail"],
                    f"{case['id']} detail must name ceiling figure {finding['ceiling_surface']!r}",
                )

    def test_consistent_cases_are_silent(self) -> None:
        for case in self.corpus:
            if case["expected"]["verdict"] != "none":
                continue
            self.assertEqual(
                detect_bound_pair_conflicts(case["text"]),
                [],
                f"consistent case {case['id']} must produce zero findings",
            )


class ZeroGreenGuardTest(unittest.TestCase):
    """The zero-green invariant is structural, not merely observed on the corpus."""

    def test_finding_rejects_non_allowed_verdict(self) -> None:
        with self.assertRaises(ValueError):
            BoundPairFinding(
                verdict="supported",
                kind="x",
                floor_marker="at least",
                ceiling_marker="not more than",
                floor_surface="$10",
                ceiling_surface="$5",
                floor_value="USD 10.00",
                ceiling_value="USD 5.00",
                detail="d",
                start=0,
                end=0,
                span="",
            )

    def test_allowed_verdicts_are_exactly_two(self) -> None:
        self.assertEqual(ALLOWED_VERDICTS, frozenset({CONTRADICTED, COULD_NOT_VERIFY}))

    def test_empty_and_siteless_input_is_silent(self) -> None:
        self.assertEqual(detect_bound_pair_conflicts(""), [])
        self.assertEqual(
            detect_bound_pair_conflicts("No bound pairs here, nothing to compare."),
            [],
        )


class MixedUnitSilenceTest(unittest.TestCase):
    """Mismatched quantity kinds are never a comparable pair: silent, not a refusal."""

    def test_duration_vs_money_is_silent(self) -> None:
        self.assertEqual(
            detect_bound_pair_conflicts(
                "The adjustment shall be at least 24 months and not more than $10,000."
            ),
            [],
        )

    def test_percent_vs_money_is_silent(self) -> None:
        self.assertEqual(
            detect_bound_pair_conflicts("The fee shall be a minimum of 5% and a maximum of $500."),
            [],
        )

    def test_two_different_quantities_is_not_a_site(self) -> None:
        # "in fees" / "in costs" break contiguity: never a site at all.
        self.assertEqual(
            find_bound_pairs(
                "The Purchaser shall pay not less than $5,000 in filing fees and "
                "not more than $2,000 in court costs."
            ),
            [],
        )

    def test_between_descending_range_is_never_a_site(self) -> None:
        self.assertEqual(
            find_bound_pairs("The discount rate ranges between 20% and 10% depending on volume."),
            [],
        )


class IncommensurableDurationTest(unittest.TestCase):
    """Values the engine cannot order exactly refuse; never contradict."""

    def test_months_vs_days_refuses_never_contradicts(self) -> None:
        findings = detect_bound_pair_conflicts(
            "The cure period shall be not less than six (6) months nor more than 150 days."
        )
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f["verdict"], COULD_NOT_VERIFY)
        self.assertEqual(f["kind"], "bound_pair_incommensurable_units")
        self.assertIn("six (6) months", f["detail"])
        self.assertIn("150 days", f["detail"])

    def test_day_week_exact_factor_is_comparable(self) -> None:
        # week x7 -> days IS a provable conversion, so this compares and
        # correctly contradicts (14 days > 10 days).
        findings = detect_bound_pair_conflicts(
            "The window shall be not less than two (2) weeks nor more than 10 days."
        )
        self.assertEqual([f["verdict"] for f in findings], [CONTRADICTED])

    def test_month_year_exact_factor_is_comparable_and_silent_when_consistent(self) -> None:
        self.assertEqual(
            detect_bound_pair_conflicts(
                "The term shall be at least one (1) year and not more than 24 months."
            ),
            [],
        )

    def test_qualified_business_days_refuses(self) -> None:
        findings = detect_bound_pair_conflicts(
            "The response window shall be not less than ten (10) business days nor more than 12 days."
        )
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f["verdict"], COULD_NOT_VERIFY)
        self.assertEqual(f["kind"], "bound_pair_qualified_duration")


class FigureConflictTest(unittest.TestCase):
    """A bound whose own word and numeral disagree refuses naming both."""

    def test_internal_word_figure_conflict_refuses(self) -> None:
        findings = detect_bound_pair_conflicts(
            "The period shall be not less than thirty (60) days nor more than fifty (50) days."
        )
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f["verdict"], COULD_NOT_VERIFY)
        self.assertEqual(f["kind"], "bound_pair_figure_conflict")
        self.assertIn("thirty", f["detail"])
        self.assertIn("60", f["detail"])


class VerbatimGuardTest(unittest.TestCase):
    """A conflict the source carries verbatim is the source's defect."""

    CLAIM = "The indemnity basket shall be a minimum of $50,000 and a maximum of $10,000."

    def test_verbatim_source_yields_could_not_verify(self) -> None:
        source = f"Executed original: {self.CLAIM} In witness whereof."
        findings = detect_bound_pair_conflicts(self.CLAIM, source)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["verdict"], COULD_NOT_VERIFY)
        self.assertEqual(findings[0]["kind"], "bound_pair_source_defect")
        self.assertIn("source", findings[0]["detail"])

    def test_same_inversion_without_source_contradicts(self) -> None:
        findings = detect_bound_pair_conflicts(self.CLAIM)
        self.assertEqual([f["verdict"] for f in findings], [CONTRADICTED])

    def test_explicit_verbatim_flag_overrides_source_scan(self) -> None:
        findings = detect_bound_pair_conflicts(self.CLAIM, "", verbatim_run_present=True)
        self.assertEqual(findings[0]["verdict"], COULD_NOT_VERIFY)

    def test_explicit_false_flag_overrides_matching_source(self) -> None:
        source = f"Executed original: {self.CLAIM}"
        findings = detect_bound_pair_conflicts(self.CLAIM, source, verbatim_run_present=False)
        self.assertEqual(findings[0]["verdict"], CONTRADICTED)


class EqualBoundsTest(unittest.TestCase):
    """floor == ceiling is legitimate 'exactly N' drafting: consistent, silent."""

    def test_equal_duration_bounds_are_silent(self) -> None:
        self.assertEqual(
            detect_bound_pair_conflicts(
                "The cure period shall be not less than thirty (30) days nor more than thirty (30) days."
            ),
            [],
        )

    def test_equal_money_bounds_are_silent(self) -> None:
        self.assertEqual(
            detect_bound_pair_conflicts(
                "The deposit shall be a minimum of $1,000 and a maximum of $1,000."
            ),
            [],
        )


class SpelledFigureTest(unittest.TestCase):
    """Fully spelled-out money parses and compares correctly."""

    def test_spelled_money_inversion_is_detected(self) -> None:
        findings = detect_bound_pair_conflicts(
            "The penalty shall be a minimum of five hundred thousand dollars and a maximum of $250,000."
        )
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f["verdict"], CONTRADICTED)
        self.assertIn("five hundred thousand dollars", f["detail"])
        self.assertIn("USD 500000.00", f["detail"])

    def test_spelled_money_consistent_range_is_silent(self) -> None:
        self.assertEqual(
            detect_bound_pair_conflicts(
                "The penalty shall be a minimum of one hundred thousand dollars and a maximum of "
                "five hundred thousand dollars."
            ),
            [],
        )


class DeterminismTest(unittest.TestCase):
    """Same input twice: byte-identical findings, stable ordering."""

    TEXT = (
        "The indemnity basket shall be a minimum of $50,000 and a maximum of $10,000. "
        "The royalty rate shall be at least 10% but not more than 5%."
    )

    def test_repeated_calls_are_byte_identical(self) -> None:
        first = json.dumps(detect_bound_pair_conflicts(self.TEXT), sort_keys=True)
        second = json.dumps(detect_bound_pair_conflicts(self.TEXT), sort_keys=True)
        self.assertEqual(first, second)

    def test_findings_are_ordered_by_document_position(self) -> None:
        findings = detect_bound_pair_conflicts(self.TEXT)
        starts = [f["start"] for f in findings]
        self.assertEqual(starts, sorted(starts))
        self.assertEqual(len(findings), 2)

    def test_input_type_and_size_guards(self) -> None:
        with self.assertRaises(TypeError):
            detect_bound_pair_conflicts(None)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            detect_bound_pair_conflicts("text", source=42)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            detect_bound_pair_conflicts("x" * 2_000_001)


if __name__ == "__main__":
    unittest.main()
