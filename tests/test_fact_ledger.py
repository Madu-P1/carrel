"""Tests for services/fact_ledger.py, the document-scale fact-ledger detector.

Loads the detector's own corpus (evals/fact_ledger/corpus.jsonl) and asserts
every expected verdict plus every must_name substring, then locks the campaign
invariants directly:

* ZERO-GREEN / SILENT-ON-CONSISTENT: no code path returns a supported/green
  verdict. The finding dataclass rejects any verdict outside {contradicted,
  could_not_verify} at construction, and a consistent document produces zero
  findings.
* FIGURE-NAMING: every contradiction and every refusal names, in its own
  detail text, every figure surface it disposed over.
* VERBATIM GUARD: a conflict the source carries verbatim is the source's
  defect (could_not_verify), never an accusation of the drafter.
* AMBIGUOUS KEYS: exact-string term keying with the capitalized-neighbor
  guard; "Renewal Term" never feeds the "Term" key, and a term reused across
  unrelated dimensions never enters a comparison.
* NOT-PROVABLY-EQUAL: days vs months refuses (incommensurable units), and
  'approximately'-hedged differences refuse; neither ever contradicts.
* DETERMINISM: same input twice produces byte-identical findings.

Run directly:

    ./.venv/bin/python tests/test_fact_ledger.py
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.fact_ledger import (  # noqa: E402
    ALLOWED_VERDICTS,
    CONTRADICTED,
    COULD_NOT_VERIFY,
    LedgerFinding,
    build_fact_ledger,
    detect_fact_contradictions,
    extract_bindings,
)

_CORPUS = _REPO_ROOT / "evals" / "fact_ledger" / "corpus.jsonl"


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
        self.assertGreaterEqual(verdicts.count("contradicted"), 3)
        self.assertGreaterEqual(verdicts.count("none"), 3)
        self.assertGreaterEqual(verdicts.count("could_not_verify"), 4)
        verbatim = [c for c in self.corpus if c.get("source")]
        self.assertGreaterEqual(len(verbatim), 2, "need >= 2 verbatim source-defect cases")

    def test_every_case_matches_expectation(self) -> None:
        for case in self.corpus:
            with self.subTest(case=case["id"]):
                findings = detect_fact_contradictions(case["text"], case.get("source", ""))
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
            findings = detect_fact_contradictions(case["text"], case.get("source", ""))
            for finding in findings:
                self.assertIn(
                    finding["verdict"],
                    ALLOWED_VERDICTS,
                    f"{case['id']} emitted a non-allowed verdict {finding['verdict']!r}",
                )

    def test_every_finding_names_its_own_figures(self) -> None:
        # Invariant (b): no content-free message. Every figure surface a
        # finding disposed over must appear verbatim in its detail text.
        for case in self.corpus:
            findings = detect_fact_contradictions(case["text"], case.get("source", ""))
            for finding in findings:
                for figure in finding["figures"]:
                    self.assertIn(
                        figure["surface"],
                        finding["detail"],
                        f"{case['id']} detail must name figure {figure['surface']!r}",
                    )

    def test_consistent_cases_are_silent(self) -> None:
        for case in self.corpus:
            if case["expected"]["verdict"] != "none":
                continue
            self.assertEqual(
                detect_fact_contradictions(case["text"]),
                [],
                f"consistent case {case['id']} must produce zero findings",
            )


class ZeroGreenGuardTest(unittest.TestCase):
    """The zero-green invariant is structural, not merely observed on the corpus."""

    def test_finding_rejects_non_allowed_verdict(self) -> None:
        with self.assertRaises(ValueError):
            LedgerFinding(
                verdict="supported",
                kind="x",
                term="Term",
                dimension="duration_months",
                detail="d",
                figures=(),
            )

    def test_allowed_verdicts_are_exactly_two(self) -> None:
        self.assertEqual(ALLOWED_VERDICTS, frozenset({CONTRADICTED, COULD_NOT_VERIFY}))

    def test_empty_and_bindingless_input_is_silent(self) -> None:
        self.assertEqual(detect_fact_contradictions(""), [])
        self.assertEqual(
            detect_fact_contradictions("No defined terms, no figures, nothing to ledger."),
            [],
        )


class VerbatimGuardTest(unittest.TestCase):
    """A conflict the source carries verbatim is the source's defect."""

    CONFLICT = (
        'The "Purchase Price" shall be $1,500,000. The "Purchase Price" shall equal $1,250,000.'
    )

    def test_verbatim_source_yields_could_not_verify(self) -> None:
        source = f"Executed original: {self.CONFLICT} In witness whereof."
        findings = detect_fact_contradictions(self.CONFLICT, source)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["verdict"], COULD_NOT_VERIFY)
        self.assertEqual(findings[0]["kind"], "fact_ledger_source_defect")
        self.assertIn("source", findings[0]["detail"])

    def test_same_conflict_without_source_contradicts(self) -> None:
        findings = detect_fact_contradictions(self.CONFLICT)
        self.assertEqual([f["verdict"] for f in findings], [CONTRADICTED])

    def test_explicit_verbatim_flag_overrides_source_scan(self) -> None:
        findings = detect_fact_contradictions(self.CONFLICT, "", verbatim_run_present=True)
        self.assertEqual(findings[0]["verdict"], COULD_NOT_VERIFY)

    def test_explicit_false_flag_overrides_matching_source(self) -> None:
        source = f"Executed original: {self.CONFLICT}"
        findings = detect_fact_contradictions(self.CONFLICT, source, verbatim_run_present=False)
        self.assertEqual(findings[0]["verdict"], CONTRADICTED)

    def test_partial_source_match_still_accuses(self) -> None:
        # Only ONE side of the conflict appears in the source: the other
        # figure is the draft's own, so the contradiction stands.
        source = 'Executed original: The "Purchase Price" shall be $1,500,000.'
        findings = detect_fact_contradictions(self.CONFLICT, source)
        self.assertEqual(findings[0]["verdict"], CONTRADICTED)


class AmbiguousKeyTest(unittest.TestCase):
    """Exact-string keying: colliding or compound terms resolve to silence."""

    def test_longer_defined_name_never_feeds_shorter_key(self) -> None:
        findings = detect_fact_contradictions(
            'The "Term" shall mean twenty-four (24) months. Each Renewal Term shall be 12 months.'
        )
        self.assertEqual(findings, [])

    def test_following_capitalized_word_blocks_binding(self) -> None:
        # "Term Sheet" is a different exact string than "Term".
        findings = detect_fact_contradictions(
            'The "Term" shall mean twenty-four (24) months. The Term Sheet is 3 pages.'
        )
        self.assertEqual(findings, [])

    def test_unrelated_dimensions_never_compare(self) -> None:
        # Same surface term denoting two different fact kinds: a duration and
        # a count. No deterministic comparison exists; silence, not accusation.
        findings = detect_fact_contradictions(
            'The "Term" shall be twenty-four (24) months. The "Term" shall consist of five (5) phases.'
        )
        self.assertEqual(findings, [])

    def test_unbound_nearby_figure_is_not_a_binding(self) -> None:
        # A figure that merely co-occurs without the connective grammar never
        # enters the ledger, so it can never fuel an accusation.
        ledger = build_fact_ledger(
            'The "Deposit" shall be $1,000. Unrelatedly, the filing fee was $350.'
        )
        self.assertEqual(list(ledger), [("Deposit", "money_usd")])


class NotProvablyEqualTest(unittest.TestCase):
    """Values the engine cannot prove equal OR unequal refuse; never accuse."""

    def test_days_vs_months_refuses_never_contradicts(self) -> None:
        findings = detect_fact_contradictions(
            'The "Cure Period" shall be thirty (30) days. '
            'The "Cure Period" shall be a period of one (1) month.'
        )
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f["verdict"], COULD_NOT_VERIFY)
        self.assertEqual(f["kind"], "fact_ledger_incommensurable_units")
        self.assertIn("thirty (30) days", f["detail"])
        self.assertIn("one (1) month", f["detail"])

    def test_provable_unit_normalization_is_silent(self) -> None:
        # years x12 -> months and weeks x7 -> days ARE provable conversions.
        self.assertEqual(
            detect_fact_contradictions(
                'The "Initial Term" shall be two (2) years. The "Initial Term" is 24 months.'
            ),
            [],
        )
        self.assertEqual(
            detect_fact_contradictions(
                'The "Window" shall be two (2) weeks. The "Window" shall be 14 days.'
            ),
            [],
        )

    def test_money_format_normalization_is_provable_and_silent(self) -> None:
        self.assertEqual(
            detect_fact_contradictions(
                'The "Deposit" shall be $1,000. The "Deposit" is $1,000.00.'
            ),
            [],
        )

    def test_hedged_difference_refuses_with_figures_named(self) -> None:
        findings = detect_fact_contradictions(
            'The "Earnout" shall be approximately $2,000,000. The "Earnout" shall be $1,900,000.'
        )
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f["verdict"], COULD_NOT_VERIFY)
        self.assertEqual(f["kind"], "fact_ledger_hedged_figures")
        self.assertIn("approximately $2,000,000", f["detail"])
        self.assertIn("$1,900,000", f["detail"])

    def test_internally_conflicted_figure_never_enters_ledger(self) -> None:
        # 'thirty (36) months' is the words-figures detector's domain; this
        # module must not bind it at all, so it cannot fuel a ledger verdict.
        self.assertEqual(
            extract_bindings('The "Term" shall be thirty (36) months.'),
            [],
        )


class DeterminismTest(unittest.TestCase):
    """Same input twice: byte-identical findings, stable ordering."""

    TEXT = (
        'The "Term" shall mean twenty-four (24) months. Rent accrues during the '
        '36-month Term. The "Purchase Price" shall be $1,500,000. The '
        '"Purchase Price" shall equal $1,250,000.'
    )

    def test_repeated_calls_are_byte_identical(self) -> None:
        first = json.dumps(detect_fact_contradictions(self.TEXT), sort_keys=True)
        second = json.dumps(detect_fact_contradictions(self.TEXT), sort_keys=True)
        self.assertEqual(first, second)

    def test_findings_are_ordered_by_document_position(self) -> None:
        findings = detect_fact_contradictions(self.TEXT)
        self.assertEqual([f["term"] for f in findings], ["Term", "Purchase Price"])

    def test_input_type_and_size_guards(self) -> None:
        with self.assertRaises(TypeError):
            detect_fact_contradictions(None)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            detect_fact_contradictions("text", source=42)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            detect_fact_contradictions("x" * 2_000_001)


if __name__ == "__main__":
    unittest.main()
