"""Tests for services/cross_document.py, the cross-document consistency detector.

Loads the detector's own corpus (evals/cross_document/corpus.jsonl) and asserts
every expected verdict plus every must_name substring, then locks the campaign
invariants directly:

* ZERO-GREEN / SILENT-BY-DEFAULT: no code path returns a supported/green
  verdict. The finding dataclass rejects any verdict outside {contradicted,
  could_not_verify} at construction; a consistent document set, a term present
  in only one document, and a bindingless document set all produce zero
  findings.
* DOCUMENT-AND-FIGURE NAMING: every contradiction and every refusal names, in
  its own detail text, every document identifier and every figure surface it
  disposed over. Content-free findings fail review.
* ODD ONE OUT: when all documents but one agree, the finding names the odd
  document with its figures.
* QUOTE GUARD: a conflict that survives only through sentences one document
  carries verbatim from another refuses; it never accuses a faithful copier.
  ``verbatim_run_present`` forces either disposition.
* NOT-PROVABLY-EQUAL: days vs months across documents refuses
  (incommensurable units), hedged differences refuse, and an intra-document
  conflict poisons the cross-document comparison into a refusal; none of
  these ever contradicts.
* LEDGER CONSUMPTION: the detector consumes ``services.fact_ledger``'s own
  ``Binding`` structures (no parallel parser), and the primitive's additive
  ``extra_terms`` widening lets a term defined in one document key its
  unquoted usage in another.
* DETERMINISM: same input twice produces byte-identical findings.

Run directly:

    ./.venv/bin/python tests/test_cross_document.py
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.cross_document import (  # noqa: E402
    ALLOWED_VERDICTS,
    CONTRADICTED,
    COULD_NOT_VERIFY,
    CrossDocumentFinding,
    build_named_ledgers,
    compare_named_ledgers,
    detect_cross_document_contradictions,
)
from services.fact_ledger import Binding, build_fact_ledger  # noqa: E402

_CORPUS = _REPO_ROOT / "evals" / "cross_document" / "corpus.jsonl"

_CLEAN_CONFLICT = {
    "Agreement": 'Section 8.2. The "Termination Fee" shall be $50,000.',
    "Amendment No. 2": 'Section 2. The "Termination Fee" shall be $75,000.',
}

_QUOTED_CONFLICT = {
    "Side Letter": 'Section 3. The "Holdback" shall be $100,000.',
    "Closing Brief": (
        'The Side Letter recites as follows. The "Holdback" shall be $100,000. '
        'Notwithstanding the foregoing, the "Holdback" shall be $80,000.'
    ),
}


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
        self.assertGreaterEqual(verdicts.count("could_not_verify"), 3)
        for case in self.corpus:
            self.assertGreaterEqual(
                len(case["documents"]), 2, f"{case['id']} must hold >= 2 documents"
            )

    def test_every_case_matches_expectation(self) -> None:
        for case in self.corpus:
            with self.subTest(case=case["id"]):
                findings = detect_cross_document_contradictions(case["documents"])
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
            findings = detect_cross_document_contradictions(case["documents"])
            for finding in findings:
                self.assertIn(
                    finding["verdict"],
                    ALLOWED_VERDICTS,
                    f"{case['id']} emitted a non-allowed verdict {finding['verdict']!r}",
                )

    def test_every_finding_names_its_own_figures_and_documents(self) -> None:
        # Invariant: no content-free message. Every figure surface AND every
        # document identifier a finding disposed over must appear verbatim in
        # its detail text.
        for case in self.corpus:
            findings = detect_cross_document_contradictions(case["documents"])
            for finding in findings:
                for figure in finding["figures"]:
                    self.assertIn(
                        figure["surface"],
                        finding["detail"],
                        f"{case['id']} detail must name figure {figure['surface']!r}",
                    )
                    self.assertIn(
                        figure["document"],
                        finding["detail"],
                        f"{case['id']} detail must name document {figure['document']!r}",
                    )

    def test_consistent_cases_are_silent(self) -> None:
        for case in self.corpus:
            if case["expected"]["verdict"] != "none":
                continue
            self.assertEqual(
                detect_cross_document_contradictions(case["documents"]),
                [],
                f"consistent case {case['id']} must produce zero findings",
            )


class ZeroGreenGuardTest(unittest.TestCase):
    """The zero-green invariant is structural, not merely observed on the corpus."""

    def test_finding_rejects_non_allowed_verdict(self) -> None:
        with self.assertRaises(ValueError):
            CrossDocumentFinding(
                verdict="supported",
                kind="x",
                term="Term",
                dimension="duration_months",
                detail="d",
                figures=(),
            )

    def test_allowed_verdicts_are_exactly_two(self) -> None:
        self.assertEqual(ALLOWED_VERDICTS, frozenset({CONTRADICTED, COULD_NOT_VERIFY}))

    def test_fewer_than_two_documents_is_silent(self) -> None:
        self.assertEqual(detect_cross_document_contradictions({}), [])
        self.assertEqual(
            detect_cross_document_contradictions(
                {"Agreement": 'The "Fee" shall be $50,000. The "Fee" shall be $75,000.'}
            ),
            [],
            "a single document has no cross-document facts; that is the "
            "single-document fact-ledger detector's domain",
        )

    def test_bindingless_documents_are_silent(self) -> None:
        self.assertEqual(
            detect_cross_document_contradictions(
                {"Letter": "Nothing quantified here.", "Memo": "Nor here."}
            ),
            [],
        )


class ConflictNamingTest(unittest.TestCase):
    """A genuine two-document conflict names both documents and both figures."""

    def test_two_document_conflict_names_everything(self) -> None:
        findings = detect_cross_document_contradictions(_CLEAN_CONFLICT)
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f["verdict"], CONTRADICTED)
        self.assertEqual(f["kind"], "cross_document_conflict")
        self.assertEqual(f["term"], "Termination Fee")
        for needle in (
            "Agreement",
            "Amendment No. 2",
            "$50,000",
            "$75,000",
            "USD 50000.00",
            "USD 75000.00",
        ):
            self.assertIn(needle, f["detail"])
        docs = {fig["document"] for fig in f["figures"]}
        self.assertEqual(docs, {"Agreement", "Amendment No. 2"})

    def test_three_documents_name_the_odd_one_out(self) -> None:
        findings = detect_cross_document_contradictions(
            {
                "Agreement": 'The "Initial Term" shall mean twelve (12) months.',
                "Exhibit A": 'The "Initial Term" is 12 months.',
                "Term Sheet": 'The "Initial Term" shall be eighteen (18) months.',
            }
        )
        self.assertEqual([f["verdict"] for f in findings], [CONTRADICTED])
        detail = findings[0]["detail"]
        self.assertIn("odd one out", detail)
        self.assertIn("Term Sheet", detail)
        self.assertIn("eighteen (18) months", detail)
        self.assertIn("Agreement and Exhibit A agree on 12 month", detail)

    def test_defined_in_one_document_used_in_another(self) -> None:
        # The category-expansion case: the contract quote-defines the term,
        # the exhibit merely uses it attributively. The union-term widening
        # makes them meet on one exact-string key.
        findings = detect_cross_document_contradictions(
            {
                "Agreement": 'Section 1.1. The "Term" shall mean a period of '
                "twenty-four (24) months.",
                "Exhibit B": "Rent shall continue to accrue during the 36-month Term.",
            }
        )
        self.assertEqual([f["verdict"] for f in findings], [CONTRADICTED])
        self.assertIn("twenty-four (24) months", findings[0]["detail"])
        self.assertIn("36-month", findings[0]["detail"])


class QuoteGuardTest(unittest.TestCase):
    """A document faithfully quoting another's figure is never accused."""

    def test_verbatim_copied_conflict_is_suppressed(self) -> None:
        findings = detect_cross_document_contradictions(_QUOTED_CONFLICT)
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f["verdict"], COULD_NOT_VERIFY)
        self.assertEqual(f["kind"], "cross_document_verbatim_copy")
        self.assertIn("$100,000", f["detail"])
        self.assertIn("$80,000", f["detail"])
        self.assertTrue(any(fig["copied"] for fig in f["figures"]))

    def test_explicit_verbatim_flag_suppresses_a_clean_conflict(self) -> None:
        findings = detect_cross_document_contradictions(_CLEAN_CONFLICT, verbatim_run_present=True)
        self.assertEqual([f["verdict"] for f in findings], [COULD_NOT_VERIFY])
        self.assertEqual(findings[0]["kind"], "cross_document_verbatim_copy")

    def test_explicit_false_flag_disables_the_scan(self) -> None:
        # With the scan forced off, the quoted sentences count as the brief's
        # own assertions; the result is still a refusal (intra-document
        # inconsistency), NEVER a confident accusation.
        findings = detect_cross_document_contradictions(
            _QUOTED_CONFLICT, verbatim_run_present=False
        )
        self.assertEqual([f["verdict"] for f in findings], [COULD_NOT_VERIFY])
        self.assertEqual(findings[0]["kind"], "cross_document_intra_document_conflict")

    def test_explicit_false_flag_keeps_a_clean_conflict_contradicted(self) -> None:
        findings = detect_cross_document_contradictions(_CLEAN_CONFLICT, verbatim_run_present=False)
        self.assertEqual([f["verdict"] for f in findings], [CONTRADICTED])


class NotProvablyEqualTest(unittest.TestCase):
    """Values the engine cannot prove equal OR unequal refuse; never accuse."""

    def test_days_vs_months_across_documents_refuses(self) -> None:
        findings = detect_cross_document_contradictions(
            {
                "Agreement": 'The "Cure Period" shall be thirty (30) days.',
                "Guaranty": 'The "Cure Period" shall be a period of one (1) month.',
            }
        )
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f["verdict"], COULD_NOT_VERIFY)
        self.assertEqual(f["kind"], "cross_document_incommensurable_units")
        self.assertIn("thirty (30) days", f["detail"])
        self.assertIn("one (1) month", f["detail"])
        self.assertIn("Agreement", f["detail"])
        self.assertIn("Guaranty", f["detail"])

    def test_hedged_difference_refuses_with_figures_named(self) -> None:
        findings = detect_cross_document_contradictions(
            {
                "Letter of Intent": 'The "Earnout" shall be approximately $2,000,000.',
                "Purchase Agreement": 'The "Earnout" shall be $1,900,000.',
            }
        )
        self.assertEqual([f["verdict"] for f in findings], [COULD_NOT_VERIFY])
        self.assertEqual(findings[0]["kind"], "cross_document_hedged_figures")
        self.assertIn("approximately $2,000,000", findings[0]["detail"])
        self.assertIn("$1,900,000", findings[0]["detail"])

    def test_intra_document_conflict_poisons_cross_comparison(self) -> None:
        findings = detect_cross_document_contradictions(
            {
                "Master Agreement": 'Section 1. The "Royalty Rate" shall be 3%. '
                'Section 12. The "Royalty Rate" shall be 4%.',
                "Schedule B": 'The "Royalty Rate" is 3%.',
            }
        )
        self.assertEqual([f["verdict"] for f in findings], [COULD_NOT_VERIFY])
        self.assertEqual(findings[0]["kind"], "cross_document_intra_document_conflict")
        self.assertIn("Master Agreement", findings[0]["detail"])

    def test_unit_normalized_agreement_is_silent_and_disagreement_contradicts(self) -> None:
        self.assertEqual(
            detect_cross_document_contradictions(
                {
                    "Agreement": 'The "Initial Term" shall be two (2) years.',
                    "Renewal Notice": 'The "Initial Term" is 24 months.',
                }
            ),
            [],
        )
        findings = detect_cross_document_contradictions(
            {
                "Agreement": 'The "Support Period" shall be two (2) years.',
                "Statement of Work": 'The "Support Period" is 30 months.',
            }
        )
        self.assertEqual([f["verdict"] for f in findings], [CONTRADICTED])


class ExactKeyingTest(unittest.TestCase):
    """The ledger's exact-string keying survives the cross-document lift."""

    def test_longer_defined_name_never_feeds_shorter_key(self) -> None:
        self.assertEqual(
            detect_cross_document_contradictions(
                {
                    "Agreement": 'The "Term" shall mean twenty-four (24) months.',
                    "Amendment": "Each Renewal Term shall be 12 months. "
                    "The Term Sheet is attached.",
                }
            ),
            [],
        )

    def test_unrelated_dimensions_never_compare(self) -> None:
        self.assertEqual(
            detect_cross_document_contradictions(
                {
                    "Agreement": 'The "Retainer" shall be $9,000.',
                    "Engagement Letter": 'The "Retainer" shall be a period of three (3) months.',
                }
            ),
            [],
        )


class LedgerConsumptionTest(unittest.TestCase):
    """The detector consumes the primitive's real structures, not a reinvention."""

    def test_named_ledgers_hold_fact_ledger_bindings(self) -> None:
        ledgers = build_named_ledgers(_CLEAN_CONFLICT)
        self.assertEqual(set(ledgers), set(_CLEAN_CONFLICT))
        for ledger in ledgers.values():
            for (term, dimension), group in ledger.items():
                self.assertIsInstance(term, str)
                self.assertIsInstance(dimension, str)
                for binding in group:
                    self.assertIsInstance(binding, Binding)

    def test_prebuilt_ledgers_match_the_convenience_entry(self) -> None:
        direct = compare_named_ledgers(build_named_ledgers(_CLEAN_CONFLICT), _CLEAN_CONFLICT)
        convenience = detect_cross_document_contradictions(_CLEAN_CONFLICT)
        self.assertEqual(direct, convenience)

    def test_prebuilt_ledgers_without_texts_still_decide(self) -> None:
        findings = compare_named_ledgers(build_named_ledgers(_CLEAN_CONFLICT))
        self.assertEqual([f["verdict"] for f in findings], [CONTRADICTED])

    def test_extra_terms_widening_is_additive_and_shape_guarded(self) -> None:
        usage = "Rent shall continue to accrue during the 36-month Term."
        self.assertEqual(build_fact_ledger(usage), {}, "default behavior unchanged")
        widened = build_fact_ledger(usage, extra_terms=("Term",))
        self.assertEqual(list(widened), [("Term", "duration_months")])
        self.assertEqual(
            build_fact_ledger(usage, extra_terms=("term", 'x"y', "")),
            {},
            "non-conforming extra terms are ignored, never loosened",
        )


class DeterminismTest(unittest.TestCase):
    """Same input twice: byte-identical findings; hostile inputs raise early."""

    def test_repeated_calls_are_byte_identical(self) -> None:
        docs = {
            "Agreement": 'The "Term" shall mean twenty-four (24) months. '
            'The "Purchase Price" shall be $1,500,000.',
            "Amendment": 'The "Term" is 36 months. The "Purchase Price" shall equal $1,250,000.',
        }
        first = json.dumps(detect_cross_document_contradictions(docs), sort_keys=True)
        second = json.dumps(detect_cross_document_contradictions(docs), sort_keys=True)
        self.assertEqual(first, second)

    def test_input_guards(self) -> None:
        with self.assertRaises(ValueError):
            detect_cross_document_contradictions([("Agreement", "a"), ("Agreement", "b")])
        with self.assertRaises(ValueError):
            detect_cross_document_contradictions([("", "text"), ("Other", "text")])
        with self.assertRaises(TypeError):
            detect_cross_document_contradictions({"Agreement": None, "Other": "text"})
        with self.assertRaises(ValueError):
            detect_cross_document_contradictions([(f"Doc {i}", "text") for i in range(33)])
        with self.assertRaises(TypeError):
            compare_named_ledgers([("Agreement", {})])  # not a mapping


if __name__ == "__main__":
    unittest.main()
