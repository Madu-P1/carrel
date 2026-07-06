"""Tests for services/temporal_graph.py, the whole-document temporal graph.

Loads the detector's own corpus (evals/temporal_graph/corpus.jsonl) and asserts
every expected verdict, kind, and must_name substring, then locks the campaign
invariants directly:

* ZERO-GREEN / SILENT-BY-DEFAULT: no code path returns a supported/green
  verdict. The finding dataclass rejects any verdict outside {contradicted,
  could_not_verify} at construction; every jointly-satisfiable document -- and
  every adversarial set that only LOOKS circular -- produces zero findings.
* ARITHMETIC CERTAINTY: an ordering cycle and a three-clause date-arithmetic
  impossibility spanning separate paragraphs are both detected via the
  difference-constraint negative-cycle engine, each naming the full chain, its
  figures, and the day deficit.
* AMBIGUITY IS A REFUSAL: a locale-ambiguous date, a yearless date, a
  spelled/written day-count mismatch, and a business-day bound all refuse with
  specifics; none is ever turned into an accusation.
* QUOTE GUARD: a contradiction carried verbatim from the source refuses as a
  source defect; verbatim_run_present forces either disposition.
* EXACT-STRING EVENT IDENTITY: 'the Closing Date' never merges with 'Closing',
  so the engine cannot invent a cycle by guessing two references are one event.
* ZERO FALSE ACCUSATION: over every satisfiable corpus case, no contradicted
  verdict is ever emitted.
* DETERMINISM: same input twice produces byte-identical findings.

Run directly:

    ./.venv/bin/python -m pytest tests/test_temporal_graph.py -q
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services import date_duration_conflict as _dd  # noqa: E402
from services import temporal_graph as tg  # noqa: E402
from services.temporal_graph import (  # noqa: E402
    ALLOWED_VERDICTS,
    CONTRADICTED,
    COULD_NOT_VERIFY,
    TemporalFinding,
    detect_temporal_contradictions,
    extract_constraints,
)

_CORPUS = _REPO_ROOT / "evals" / "temporal_graph" / "corpus.jsonl"


def _load_corpus() -> list[dict]:
    return [json.loads(line) for line in _CORPUS.read_text().splitlines() if line.strip()]


def _haystack(finding: dict) -> str:
    return " ".join(str(v) for v in finding.values())


class CorpusTests(unittest.TestCase):
    """Every case in the frozen corpus disposes exactly as recorded."""

    def test_corpus_dispositions(self) -> None:
        cases = _load_corpus()
        self.assertGreaterEqual(len(cases), 12, "corpus must carry at least 12 cases")
        for case in cases:
            with self.subTest(case=case["id"]):
                findings = detect_temporal_contradictions(case["text"], case.get("source", ""))
                exp = case["expected"]
                if exp["verdict"] == "silent":
                    self.assertEqual(findings, [], f"{case['id']} must be silent (satisfiable)")
                    continue
                match = [f for f in findings if f["kind"] == exp["kind"]]
                self.assertTrue(
                    match,
                    f"{case['id']} expected a {exp['kind']} finding; got "
                    f"{[f['kind'] for f in findings]}",
                )
                finding = match[0]
                self.assertEqual(finding["verdict"], exp["verdict"], case["id"])
                self.assertIn(finding["verdict"], ALLOWED_VERDICTS)
                hay = _haystack(finding)
                for name in exp["must_name"]:
                    self.assertIn(name, hay, f"{case['id']} must name {name!r}")

    def test_corpus_has_required_shapes(self) -> None:
        ids = {c["id"] for c in _load_corpus()}
        # The brief's required shapes are all present by id.
        self.assertIn("contra_ordering_cycle_2clause", ids)
        self.assertIn("contra_arithmetic_3clause_hero", ids)
        self.assertIn("sat_within_of_chain", ids)  # adversarial bait 1
        self.assertIn("sat_mutual_on_or_before", ids)  # adversarial bait 2
        self.assertIn("refuse_ambiguous_date_locale", ids)
        # At least four satisfiable true-negative cases.
        sat = [c for c in _load_corpus() if c["expected"]["verdict"] == "silent"]
        self.assertGreaterEqual(len(sat), 4)


class ZeroGreenInvariant(unittest.TestCase):
    """No supported/green state exists anywhere in the module."""

    def test_finding_rejects_foreign_verdict(self) -> None:
        for bad in ("supported", "verified", "green", "ok", ""):
            with self.assertRaises(ValueError):
                TemporalFinding(
                    verdict=bad,
                    kind="x",
                    detail="d",
                    deficit_days=None,
                    chain=(),
                    events=(),
                    span="",
                    start=0,
                    end=0,
                )

    def test_allowed_verdicts_are_exactly_two(self) -> None:
        self.assertEqual(ALLOWED_VERDICTS, frozenset({CONTRADICTED, COULD_NOT_VERIFY}))

    def test_every_finding_is_non_green(self) -> None:
        for case in _load_corpus():
            for f in detect_temporal_contradictions(case["text"], case.get("source", "")):
                self.assertIn(f["verdict"], ALLOWED_VERDICTS)


class SilentOnSatisfiable(unittest.TestCase):
    """Satisfiable schedules, including circular-looking baits, stay silent."""

    def test_within_of_chain_is_silent(self) -> None:
        text = (
            "The Alpha Date must fall within 30 days of the Beta Date. "
            "The Beta Date must fall within 30 days of the Gamma Date."
        )
        self.assertEqual(detect_temporal_contradictions(text), [])

    def test_mutual_on_or_before_is_silent(self) -> None:
        # A <= B and B <= A is satisfied by A == B: not a contradiction.
        text = (
            "The First Date shall be on or before the Second Date. "
            "The Second Date shall be on or before the First Date."
        )
        self.assertEqual(detect_temporal_contradictions(text), [])

    def test_ordering_dag_is_silent(self) -> None:
        text = (
            "The Filing shall occur before the Review. "
            "The Review shall occur before the Hearing. "
            "The Filing shall occur before the Hearing."
        )
        self.assertEqual(detect_temporal_contradictions(text), [])

    def test_consistent_anchors_are_silent(self) -> None:
        text = (
            "The Notice Date must fall at least 30 days before the Hearing Date. "
            "The Notice Date is March 1, 2026. The Hearing Date shall be June 1, 2026."
        )
        self.assertEqual(detect_temporal_contradictions(text), [])

    def test_at_least_chain_without_cycle_is_silent(self) -> None:
        text = (
            "The Notice must fall at least 30 days before the Termination. "
            "The Termination must fall at least 45 days before the Hearing."
        )
        self.assertEqual(detect_temporal_contradictions(text), [])

    def test_empty_and_bare_text_is_silent(self) -> None:
        self.assertEqual(detect_temporal_contradictions(""), [])
        self.assertEqual(
            detect_temporal_contradictions("This paragraph has no temporal constraints."), []
        )

    def test_zero_false_accusation_over_all_satisfiable_cases(self) -> None:
        for case in _load_corpus():
            if case["expected"]["verdict"] != "silent":
                continue
            findings = detect_temporal_contradictions(case["text"], case.get("source", ""))
            accusations = [f for f in findings if f["verdict"] == CONTRADICTED]
            self.assertEqual(accusations, [], f"{case['id']} must never be accused")


class OrderingCycles(unittest.TestCase):
    def test_two_clause_cycle(self) -> None:
        text = (
            "The Filing shall occur before the Hearing. "
            "The Hearing must be completed before the Filing."
        )
        findings = detect_temporal_contradictions(text)
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f["verdict"], CONTRADICTED)
        self.assertEqual(f["kind"], "temporal_ordering_cycle")
        self.assertEqual(f["deficit_days"], 2)
        self.assertIn("Filing", f["detail"])
        self.assertIn("Hearing", f["detail"])

    def test_three_clause_cycle(self) -> None:
        text = (
            "The Complaint must fall before the Answer. "
            "The Answer must fall before the Judgment. "
            "The Judgment must fall before the Complaint."
        )
        findings = detect_temporal_contradictions(text)
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f["kind"], "temporal_ordering_cycle")
        for name in ("Complaint", "Answer", "Judgment"):
            self.assertIn(name, f["detail"])
        # The chain records every contributing clause.
        self.assertEqual(len(f["chain"]), 3)


class ArithmeticImpossibility(unittest.TestCase):
    def test_three_paragraph_composition(self) -> None:
        text = (
            "Section 4. The Notice Date must fall at least 30 days before the Termination Date. "
            "Section 9. The Termination Date shall be at least 45 days before the Hearing Date. "
            "Section 12. The Notice Date is March 1, 2026. "
            "Section 15. The Hearing Date shall be April 15, 2026."
        )
        findings = detect_temporal_contradictions(text)
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f["verdict"], CONTRADICTED)
        self.assertEqual(f["kind"], "temporal_arithmetic_impossibility")
        # 30 + 45 = 75 days required; explicit dates leave 45; deficit is 30.
        self.assertEqual(f["deficit_days"], 30)
        self.assertIn("2026-03-01", f["detail"])
        self.assertIn("2026-04-15", f["detail"])
        self.assertIn("over-constrained by 30 days", f["detail"])
        # Both anchors are enumerated in the events payload.
        anchored = {e["event"] for e in f["events"]}
        self.assertEqual(anchored, {"Notice Date", "Hearing Date"})

    def test_anchor_contradicts_ordering(self) -> None:
        text = (
            "The Notice Date must fall before the Delivery Date. "
            "The Notice Date is May 1, 2026, and the Delivery Date shall be April 1, 2026."
        )
        findings = detect_temporal_contradictions(text)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["kind"], "temporal_arithmetic_impossibility")

    def test_exact_days_contradicts_anchors(self) -> None:
        text = (
            "The Payment Date must fall 30 days after the Invoice Date. "
            "The Invoice Date is January 1, 2026. The Payment Date shall be January 15, 2026."
        )
        f = detect_temporal_contradictions(text)[0]
        self.assertEqual(f["kind"], "temporal_arithmetic_impossibility")
        # exact +30 required; the anchors are 14 days apart; deficit 16.
        self.assertEqual(f["deficit_days"], 16)

    def test_multiple_independent_contradictions_each_surface(self) -> None:
        text = (
            "The Filing must fall before the Hearing. "
            "The Hearing must fall before the Filing. "
            "The Motion must fall before the Order. "
            "The Order must fall before the Motion."
        )
        findings = detect_temporal_contradictions(text)
        kinds = [f["kind"] for f in findings]
        self.assertEqual(kinds.count("temporal_ordering_cycle"), 2)


class Refusals(unittest.TestCase):
    def test_locale_ambiguous_date_refuses(self) -> None:
        text = (
            "The Closing Date must fall before the Delivery Date. The Closing Date is 03/04/2026."
        )
        f = detect_temporal_contradictions(text)[0]
        self.assertEqual(f["verdict"], COULD_NOT_VERIFY)
        self.assertEqual(f["kind"], "temporal_ambiguous_date")
        self.assertIn("2026-03-04", f["detail"])
        self.assertIn("2026-04-03", f["detail"])

    def test_yearless_date_refuses(self) -> None:
        text = "The Closing Date must fall before the Delivery Date. The Closing Date is January 5."
        f = detect_temporal_contradictions(text)[0]
        self.assertEqual(f["kind"], "temporal_ambiguous_date")
        self.assertIn("no year", f["detail"])

    def test_isolated_ambiguous_date_is_silent(self) -> None:
        # No relative constraint references it, so there is nothing to verify.
        self.assertEqual(detect_temporal_contradictions("The Closing Date is 03/04/2026."), [])

    def test_count_word_figure_conflict_refuses(self) -> None:
        text = "The Alpha Date must fall at least thirty (45) days before the Beta Date."
        f = detect_temporal_contradictions(text)[0]
        self.assertEqual(f["kind"], "temporal_ambiguous_count")
        self.assertIn("30", f["detail"])
        self.assertIn("45", f["detail"])

    def test_business_days_refuses_never_accuses(self) -> None:
        text = (
            "The Filing must fall at least 10 business days before the Review. "
            "The Review must fall at least 10 days before the Filing."
        )
        f = detect_temporal_contradictions(text)[0]
        self.assertEqual(f["verdict"], COULD_NOT_VERIFY)
        self.assertEqual(f["kind"], "temporal_business_days")
        self.assertIn("holiday calendar", f["detail"])


class QuoteGuard(unittest.TestCase):
    _CHAIN = (
        "The Opening Date must fall before the Closing Date. "
        "The Closing Date must fall before the Opening Date."
    )

    def test_verbatim_in_source_is_a_refusal(self) -> None:
        f = detect_temporal_contradictions(self._CHAIN, "Recited: " + self._CHAIN)[0]
        self.assertEqual(f["verdict"], COULD_NOT_VERIFY)
        self.assertEqual(f["kind"], "temporal_source_defect")
        self.assertIn("faithful copier", f["detail"])

    def test_not_in_source_is_an_accusation(self) -> None:
        f = detect_temporal_contradictions(self._CHAIN, "unrelated source text")[0]
        self.assertEqual(f["verdict"], CONTRADICTED)

    def test_verbatim_override_forces_refusal(self) -> None:
        f = detect_temporal_contradictions(self._CHAIN, "", verbatim_run_present=True)[0]
        self.assertEqual(f["verdict"], COULD_NOT_VERIFY)

    def test_verbatim_override_false_forces_accusation(self) -> None:
        f = detect_temporal_contradictions(
            self._CHAIN, "Recited: " + self._CHAIN, verbatim_run_present=False
        )[0]
        self.assertEqual(f["verdict"], CONTRADICTED)


class EventIdentity(unittest.TestCase):
    def test_distinct_surfaces_do_not_merge(self) -> None:
        # "Closing" and "Closing Date" are different keys, so no cycle is forged.
        text = (
            "The Closing must fall before the Hearing. "
            "The Hearing must fall before the Closing Date."
        )
        self.assertEqual(detect_temporal_contradictions(text), [])

    def test_the_prefix_and_case_are_normalized(self) -> None:
        # "the Filing" and "Filing" ARE the same event once normalized.
        text = "The Filing must fall before the Order. Order must fall before Filing."
        findings = detect_temporal_contradictions(text)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["kind"], "temporal_ordering_cycle")


class ExtractionAndValidation(unittest.TestCase):
    def test_extract_returns_constraints_and_edges(self) -> None:
        text = "The Notice must fall at least 30 days before the Hearing."
        constraints, ambiguities = extract_constraints(text)
        self.assertEqual(len(constraints), 1)
        self.assertEqual(ambiguities, [])
        c = constraints[0]
        self.assertFalse(c.is_anchor)
        self.assertEqual(c.days, 30)
        self.assertTrue(c.edges)

    def test_non_str_text_raises(self) -> None:
        with self.assertRaises(TypeError):
            detect_temporal_contradictions(None)  # type: ignore[arg-type]

    def test_non_str_source_raises(self) -> None:
        with self.assertRaises(TypeError):
            detect_temporal_contradictions("x", 5)  # type: ignore[arg-type]

    def test_oversized_text_raises(self) -> None:
        with self.assertRaises(ValueError):
            extract_constraints("a" * (tg._MAX_TEXT + 1))


class DeterminismAndReuse(unittest.TestCase):
    def test_determinism(self) -> None:
        text = (
            "The Notice Date must fall at least 30 days before the Termination Date. "
            "The Termination Date shall be at least 45 days before the Hearing Date. "
            "The Notice Date is March 1, 2026. The Hearing Date shall be April 15, 2026."
        )
        self.assertEqual(detect_temporal_contradictions(text), detect_temporal_contradictions(text))

    def test_helpers_are_reused_by_import_not_duplicated(self) -> None:
        # The module reuses the date/duration sibling's parsing helpers rather
        # than shipping its own copies.
        self.assertIs(tg._parse_date, _dd._parse_date)
        self.assertIs(tg._spelled_value, _dd._spelled_value)
        self.assertIs(tg._run_in_source, _dd._run_in_source)


if __name__ == "__main__":
    unittest.main()
