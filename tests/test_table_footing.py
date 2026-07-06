"""Tests for services/table_footing.py, the financial-table footing detector.

Two levels are exercised:

* the PURE layer -- ``parse_figure`` -- directly, on the exact figure grammar
  (thousands separators, currency symbols/codes/words, parenthesized
  negatives, magnitude suffixes, percents, malformed inputs);
* the DOCUMENT layer -- ``detect_footing_conflicts`` -- against the module's
  own corpus, asserting every expected verdict and every must_name substring,
  plus the campaign invariants: zero green, silence on tables that foot,
  named stated total + computed sum + line items on every accusation,
  never-accuse-on-ambiguity, verbatim source defect never accused,
  determinism.

Run directly:

    ./.venv/bin/python -m pytest tests/test_table_footing.py -q
"""

from __future__ import annotations

import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.table_footing import (  # noqa: E402
    ALLOWED_VERDICTS,
    CONTRADICTED,
    COULD_NOT_VERIFY,
    TableFootingFinding,
    detect_footing_conflicts,
    parse_figure,
)

_CORPUS = _REPO_ROOT / "evals" / "table_footing" / "corpus.jsonl"


def _load_corpus() -> list[dict]:
    return [json.loads(line) for line in _CORPUS.read_text().splitlines() if line.strip()]


def _haystack(finding: dict) -> str:
    return " ".join(str(v) for v in finding.values())


class ParseFigureTest(unittest.TestCase):
    """The pure cell parser reduces a figure to an exact Decimal, or refuses."""

    def test_plain_money(self) -> None:
        self.assertEqual(parse_figure("$10,000").value, Decimal(10_000))
        self.assertEqual(parse_figure("$1,234.56").value, Decimal("1234.56"))
        self.assertEqual(parse_figure("€40,000").currency, "eur")
        self.assertEqual(parse_figure("£250").currency, "gbp")

    def test_currency_codes_and_words(self) -> None:
        self.assertEqual(parse_figure("USD 500").currency, "usd")
        self.assertEqual(parse_figure("500 dollars").currency, "usd")
        self.assertEqual(parse_figure("500 euros").currency, "eur")

    def test_magnitude_suffixes_exact(self) -> None:
        self.assertEqual(parse_figure("$1.5M").value, Decimal(1_500_000))
        self.assertEqual(parse_figure("$500k").value, Decimal(500_000))
        self.assertEqual(parse_figure("$1.2bn").value, Decimal(1_200_000_000))
        self.assertEqual(parse_figure("$2 million").value, Decimal(2_000_000))
        self.assertEqual(parse_figure("2 million").value, Decimal(2_000_000))

    def test_bare_single_letter_magnitude_refused(self) -> None:
        # A bare "5 m" could be metres; only currency figures accept letters.
        self.assertIsNone(parse_figure("5 m"))
        self.assertIsNone(parse_figure("5 k"))

    def test_parenthesized_negative(self) -> None:
        self.assertEqual(parse_figure("($1,200)").value, Decimal(-1_200))
        self.assertEqual(parse_figure("(1,200)").value, Decimal(-1_200))
        self.assertEqual(parse_figure("-$300").value, Decimal(-300))

    def test_percent(self) -> None:
        fig = parse_figure("12.5%")
        self.assertEqual(fig.kind, "percent")
        self.assertEqual(fig.value, Decimal("12.5"))

    def test_bare_number(self) -> None:
        fig = parse_figure("1,234")
        self.assertEqual(fig.kind, "bare")
        self.assertIsNone(fig.currency)
        self.assertEqual(fig.value, Decimal(1_234))

    def test_malformed_refused(self) -> None:
        self.assertIsNone(parse_figure(""))
        self.assertIsNone(parse_figure("abc"))
        self.assertIsNone(parse_figure("$2,5O0"))
        self.assertIsNone(parse_figure("12,34"))
        self.assertIsNone(parse_figure("()"))

    def test_type_guard(self) -> None:
        with self.assertRaises(TypeError):
            parse_figure(None)  # type: ignore[arg-type]


class CorpusTest(unittest.TestCase):
    """Every corpus case: exact verdict, every must_name substring present."""

    def setUp(self) -> None:
        self.corpus = _load_corpus()

    def test_corpus_has_required_mix(self) -> None:
        verdicts = [c["expected"]["verdict"] for c in self.corpus]
        self.assertGreaterEqual(len(self.corpus), 12, "corpus must hold >= 12 cases")
        self.assertGreaterEqual(verdicts.count("contradicted"), 4)
        self.assertGreaterEqual(verdicts.count("none"), 4)
        self.assertGreaterEqual(verdicts.count("could_not_verify"), 4)
        verbatim = [c for c in self.corpus if c.get("source")]
        self.assertGreaterEqual(len(verbatim), 1, "need >= 1 verbatim source-defect case")

    def test_every_case_matches_expectation(self) -> None:
        for case in self.corpus:
            with self.subTest(case=case["id"]):
                findings = detect_footing_conflicts(case["text"], case.get("source", ""))
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
            findings = detect_footing_conflicts(case["text"], case.get("source", ""))
            for finding in findings:
                self.assertIn(
                    finding["verdict"],
                    ALLOWED_VERDICTS,
                    f"{case['id']} emitted a non-allowed verdict {finding['verdict']!r}",
                )

    def test_every_accusation_names_total_sum_and_items(self) -> None:
        for case in self.corpus:
            findings = detect_footing_conflicts(case["text"], case.get("source", ""))
            for finding in findings:
                if finding["verdict"] != CONTRADICTED:
                    continue
                self.assertIn(finding["stated_total"], finding["detail"])
                self.assertIsNotNone(finding["computed_sum"])
                self.assertIn(finding["computed_sum"], finding["detail"])
                for row in finding["rows"]:
                    if row["role"] == "item":
                        self.assertIn(
                            row["figure"],
                            finding["detail"],
                            f"{case['id']} accusation must name item figure {row['figure']!r}",
                        )

    def test_footing_tables_are_silent(self) -> None:
        for case in self.corpus:
            if case["expected"]["verdict"] != "none":
                continue
            self.assertEqual(
                detect_footing_conflicts(case["text"]),
                [],
                f"footing case {case['id']} must produce zero findings",
            )


class NeverAccuseOnAmbiguityTest(unittest.TestCase):
    """Every ambiguity class yields silence or a refusal, never contradicted."""

    def _no_accusation(self, text: str) -> list[dict]:
        findings = detect_footing_conflicts(text)
        self.assertEqual(
            [f for f in findings if f["verdict"] == CONTRADICTED],
            [],
            f"must not accuse on ambiguous input, got {findings}",
        )
        return findings

    def test_mixed_currency_refuses(self) -> None:
        findings = self._no_accusation(
            "Berlin office     €40,000\nBoston office     $35,000\nTotal             $75,000"
        )
        self.assertEqual(findings[0]["kind"], "table_footing_mixed_currency")

    def test_unparseable_row_refuses(self) -> None:
        findings = self._no_accusation(
            "Consulting        $10,000\nTravel            $2,5O0\nTotal             $14,000"
        )
        self.assertEqual(findings[0]["kind"], "table_footing_unparseable_row")
        self.assertIn("$2,5O0", findings[0]["detail"])

    def test_elision_refuses(self) -> None:
        findings = self._no_accusation(
            "Rent              $1,000\n...\nUtilities         $300\nTotal             $2,100"
        )
        self.assertEqual(findings[0]["kind"], "table_footing_possible_omission")

    def test_multi_numeric_column_refuses(self) -> None:
        findings = self._no_accusation(
            "| Chairs | 10 | $45 |\n| Tables | 4 | $120 |\n| Total |  | $930 |"
        )
        self.assertEqual(findings[0]["kind"], "table_footing_multi_column")

    def test_all_percent_table_is_silent(self) -> None:
        self.assertEqual(
            detect_footing_conflicts(
                "Engineering       62.5%\nSales             24.1%\n"
                "Administration    13.3%\nTotal             100%"
            ),
            [],
        )

    def test_percent_mixed_into_money_refuses(self) -> None:
        findings = self._no_accusation(
            "Base fee          $1,000\nSuccess fee       15%\nTotal             $1,150"
        )
        self.assertEqual(findings[0]["kind"], "table_footing_mixed_kinds")

    def test_single_item_total_is_silent(self) -> None:
        self.assertEqual(
            detect_footing_conflicts("Deposit         $500\nTotal           $600"),
            [],
        )

    def test_stacked_tables_never_merge_into_false_accusation(self) -> None:
        # Two independent tables with no blank line between them: the second
        # Total covers only its own segment and must stay silent.
        self.assertEqual(
            detect_footing_conflicts(
                "Phase 1 design    $1,000\nPhase 1 build     $2,000\nTotal             $3,000\n"
                "Phase 2 audit     $400\nPhase 2 fixes     $500\nTotal             $900"
            ),
            [],
        )

    def test_stacked_single_item_second_table_silent(self) -> None:
        self.assertEqual(
            detect_footing_conflicts("Fees    $1\nCosts   $2\nTotal   $3\nExtras  $4\nTotal   $4"),
            [],
        )

    def test_subtotal_then_total_with_trailing_items_refuses_not_accuses(self) -> None:
        # Total after a subtotal plus trailing items has multiple defensible
        # readings; when they disagree and none matches, refuse with each
        # candidate named -- never accuse.
        findings = self._no_accusation(
            "Fees              $100\nCosts             $200\nSubtotal          $300\n"
            "Tax               $50\nTotal             $360"
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["kind"], "table_footing_ambiguous_aggregation")
        self.assertIn("$350", findings[0]["detail"])

    def test_prose_sentence_ending_in_figure_never_joins_table(self) -> None:
        # The prose line ends with a parseable figure but has no cell
        # separator, so it cannot inflate the sum of the table below it.
        self.assertEqual(
            detect_footing_conflicts(
                "The deposit already paid was $600.\n"
                "Room hire       $600\nAV equipment    $400\nTotal           $1,000"
            ),
            [],
        )


class FootingArithmeticTest(unittest.TestCase):
    """Accusations carry the exact Decimal arithmetic, named end to end."""

    def test_simple_mismatch_names_figures(self) -> None:
        findings = detect_footing_conflicts(
            "Consulting fees      $10,000\nTravel               $2,500\n"
            "Software licences    $1,200\nTotal                $14,000"
        )
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f["verdict"], CONTRADICTED)
        self.assertEqual(f["stated_total"], "$14,000")
        self.assertEqual(f["computed_sum"], "$13,700")
        for figure in ("$14,000", "$13,700", "$10,000", "$2,500", "$1,200"):
            self.assertIn(figure, f["detail"])

    def test_magnitude_arithmetic_is_exact(self) -> None:
        findings = detect_footing_conflicts(
            "Licence fee       $1.5M\nImplementation    $500k\nTotal             $2.5M"
        )
        self.assertEqual(findings[0]["computed_sum"], "$2,000,000")

    def test_negative_items_subtract(self) -> None:
        findings = detect_footing_conflicts(
            "Gross fees        $5,000\nLess: credits     ($1,200)\n"
            "Adjustments       $3,000\nTotal             $7,000"
        )
        self.assertEqual(findings[0]["computed_sum"], "$6,800")

    def test_grand_total_over_clean_chain_accuses(self) -> None:
        findings = detect_footing_conflicts(
            "Fees            $100\nExpenses        $200\nSubtotal        $300\n"
            "VAT             $30\nGrand Total     $340"
        )
        self.assertEqual([f["verdict"] for f in findings], [CONTRADICTED])
        self.assertEqual(findings[0]["computed_sum"], "$330")

    def test_cents_sum_exactly(self) -> None:
        # 0.1 + 0.2 style float traps must not exist: Decimal only.
        findings = detect_footing_conflicts(
            "Item one        $0.10\nItem two        $0.20\nTotal           $0.31"
        )
        self.assertEqual(findings[0]["verdict"], CONTRADICTED)
        self.assertEqual(findings[0]["computed_sum"], "$0.3")


class ZeroGreenGuardTest(unittest.TestCase):
    """The zero-green invariant is structural, not merely observed on the corpus."""

    def test_finding_rejects_non_allowed_verdict(self) -> None:
        with self.assertRaises(ValueError):
            TableFootingFinding(
                verdict="supported",
                kind="x",
                total_label="Total",
                stated_total="$1",
                computed_sum="$1",
                detail="d",
                rows=(),
            )

    def test_allowed_verdicts_are_exactly_two(self) -> None:
        self.assertEqual(ALLOWED_VERDICTS, frozenset({CONTRADICTED, COULD_NOT_VERIFY}))

    def test_empty_and_tableless_input_is_silent(self) -> None:
        self.assertEqual(detect_footing_conflicts(""), [])
        self.assertEqual(
            detect_footing_conflicts("This agreement contains no tables at all, only $500."),
            [],
        )

    def test_table_without_total_row_is_silent(self) -> None:
        self.assertEqual(
            detect_footing_conflicts("Rent        $1,000\nUtilities   $300\nParking     $50"),
            [],
        )


class VerbatimGuardTest(unittest.TestCase):
    """A defect the source carries verbatim is the source's, not an accusation."""

    TABLE = (
        "Consulting fees      $10,000\nTravel               $2,500\n"
        "Software licences    $1,200\nTotal                $14,000"
    )

    def test_verbatim_source_yields_could_not_verify(self) -> None:
        source = f"Executed schedule:\n{self.TABLE}\nIn witness whereof."
        findings = detect_footing_conflicts(self.TABLE, source)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["verdict"], COULD_NOT_VERIFY)
        self.assertEqual(findings[0]["kind"], "table_footing_source_defect")

    def test_same_table_without_source_contradicts(self) -> None:
        findings = detect_footing_conflicts(self.TABLE)
        self.assertEqual([f["verdict"] for f in findings], [CONTRADICTED])

    def test_explicit_verbatim_flag_overrides_source_scan(self) -> None:
        findings = detect_footing_conflicts(self.TABLE, "", verbatim_run_present=True)
        self.assertEqual(findings[0]["verdict"], COULD_NOT_VERIFY)

    def test_partial_source_match_still_accuses(self) -> None:
        source = "Executed schedule:\nConsulting fees      $10,000"
        findings = detect_footing_conflicts(self.TABLE, source)
        self.assertEqual(findings[0]["verdict"], CONTRADICTED)


class DeterminismTest(unittest.TestCase):
    """Same input twice: byte-identical findings, stable ordering."""

    TEXT = (
        "Alpha       $100\nBeta        $200\nTotal       $400\n\n"
        "Gamma       $10\nDelta       $20\nTotal       $50"
    )

    def test_repeated_calls_are_byte_identical(self) -> None:
        first = json.dumps(detect_footing_conflicts(self.TEXT), sort_keys=True)
        second = json.dumps(detect_footing_conflicts(self.TEXT), sort_keys=True)
        self.assertEqual(first, second)

    def test_findings_ordered_by_document_position(self) -> None:
        findings = detect_footing_conflicts(self.TEXT)
        self.assertEqual([f["stated_total"] for f in findings], ["$400", "$50"])

    def test_input_type_and_size_guards(self) -> None:
        with self.assertRaises(TypeError):
            detect_footing_conflicts(None)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            detect_footing_conflicts("text", source=42)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            detect_footing_conflicts("x" * 2_000_001)


if __name__ == "__main__":
    unittest.main()
