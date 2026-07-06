"""Tests for services/crossdoc_ledger.py, the cross-document labeled-fact ledger.

Loads the detector's own corpus (evals/crossdoc/corpus.jsonl) and asserts
every expected verdict plus every must_name substring, then locks the campaign
invariants directly:

* ZERO-GREEN / SILENT-BY-DEFAULT: no code path returns a supported/green
  verdict. The finding dataclass rejects any verdict outside {contradicted,
  could_not_verify} at construction; a consistent document set, a label
  present in only one document, a bindingless document set, and a
  fewer-than-two-documents input all produce zero findings.
* EXACT-LABEL-ONLY: labels match only when identical after case/whitespace
  normalization. "Termination Fee" never meets "Early Termination Fee";
  "TERMINATION  FEE" meets "Termination Fee".
* DOCUMENT-AND-FIGURE NAMING: every contradiction and every refusal names, in
  its own detail text, every document identifier, the shared label, and every
  conflicting figure surface verbatim. Content-free findings fail review.
* VERBATIM GUARD: ``verbatim_run_present=True`` (or a per-document
  ``"verbatim": true`` mark) attributes a conflict to the sources with a
  refusal; it never accuses the drafter with ``contradicted``.
* NOT-PROVABLY-EQUAL: days vs months and USD vs EUR across documents refuse
  naming both figures, hedged differences refuse, and an intra-document
  conflict poisons the cross-document comparison into a refusal; none of
  these ever contradicts. Within-family unit conversion (years -> months)
  happens before comparison.
* DETERMINISM: same input twice produces byte-identical findings.

Written for pytest:

    ./.venv/bin/python -m pytest tests/test_crossdoc_ledger.py -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.crossdoc_ledger import (  # noqa: E402
    ALLOWED_VERDICTS,
    CONTRADICTED,
    COULD_NOT_VERIFY,
    CrossDocLedgerFinding,
    detect_crossdoc_contradictions,
    extract_labeled_facts,
)

_CORPUS = _REPO_ROOT / "evals" / "crossdoc" / "corpus.jsonl"

_CLEAN_CONFLICT = [
    {"doc_id": "Agreement", "text": 'Section 8.2. The "Termination Fee" shall be $50,000.'},
    {"doc_id": "Amendment No. 2", "text": 'Section 2. The "Termination Fee" shall be $75,000.'},
]


def _load_corpus() -> list[dict]:
    return [json.loads(line) for line in _CORPUS.read_text().splitlines() if line.strip()]


def _run_case(case: dict) -> list[dict]:
    kwargs = {}
    if "verbatim_run_present" in case:
        kwargs["verbatim_run_present"] = case["verbatim_run_present"]
    return detect_crossdoc_contradictions(case["documents"], **kwargs)


def _haystack(findings: list[dict]) -> str:
    return " ".join(" ".join(str(v) for v in f.values()) for f in findings)


CORPUS = _load_corpus()


class TestCorpus:
    """Every corpus case: exact verdict, every must_name substring present."""

    def test_corpus_has_required_mix(self) -> None:
        assert len(CORPUS) >= 12, "corpus must hold >= 12 cases"
        verdicts = [c["expected"]["verdict"] for c in CORPUS]
        assert CONTRADICTED in verdicts
        assert COULD_NOT_VERIFY in verdicts
        assert "silent" in verdicts

    @pytest.mark.parametrize("case", CORPUS, ids=[c["id"] for c in CORPUS])
    def test_case(self, case: dict) -> None:
        findings = _run_case(case)
        expected = case["expected"]
        if expected["verdict"] == "silent":
            assert findings == [], f"{case['id']}: expected zero findings, got {findings}"
            return
        assert findings, f"{case['id']}: expected a finding, got none"
        matching = [f for f in findings if f["verdict"] == expected["verdict"]]
        assert matching, f"{case['id']}: no finding with verdict {expected['verdict']}"
        if "kind" in expected:
            assert any(f["kind"] == expected["kind"] for f in matching), (
                f"{case['id']}: no {expected['verdict']} finding of kind {expected['kind']}"
            )
        hay = _haystack(findings)
        for needle in expected["must_name"]:
            assert needle in hay, f"{case['id']}: finding does not name {needle!r}"


class TestNeverEmitsSupported:
    """The zero-green invariant, locked structurally and behaviorally."""

    @pytest.mark.parametrize("verdict", ["supported", "verified", "green", "ok", ""])
    def test_finding_dataclass_rejects_green_verdicts(self, verdict: str) -> None:
        with pytest.raises(ValueError):
            CrossDocLedgerFinding(
                verdict=verdict, kind="k", label="L", dimension="d", detail="x", figures=()
            )

    def test_allowed_verdicts_is_exactly_the_two_non_green_states(self) -> None:
        assert ALLOWED_VERDICTS == frozenset({CONTRADICTED, COULD_NOT_VERIFY})

    @pytest.mark.parametrize("case", CORPUS, ids=[c["id"] for c in CORPUS])
    def test_every_corpus_output_verdict_is_non_green(self, case: dict) -> None:
        for f in _run_case(case):
            assert f["verdict"] in ALLOWED_VERDICTS

    def test_consistent_documents_are_silent_not_supported(self) -> None:
        docs = [
            {"doc_id": "A", "text": 'The "Notice Period" shall be thirty (30) days.'},
            {"doc_id": "B", "text": 'The "Notice Period" is 30 days.'},
        ]
        assert detect_crossdoc_contradictions(docs) == []

    def test_bindingless_documents_are_silent(self) -> None:
        docs = [
            {"doc_id": "A", "text": "The parties shall cooperate in good faith."},
            {"doc_id": "B", "text": "Each party bears its own costs."},
        ]
        assert detect_crossdoc_contradictions(docs) == []

    def test_fewer_than_two_documents_is_silent(self) -> None:
        assert detect_crossdoc_contradictions([]) == []
        assert (
            detect_crossdoc_contradictions([{"doc_id": "A", "text": 'The "Fee" shall be $50,000.'}])
            == []
        )


class TestExactLabelOnly:
    """Case/whitespace normalization is the ENTIRE matching relation."""

    def test_near_miss_labels_never_contradict(self) -> None:
        docs = [
            {"doc_id": "A", "text": 'The "Termination Fee" shall be $50,000.'},
            {"doc_id": "B", "text": 'The "Early Termination Fee" shall be $75,000.'},
        ]
        assert detect_crossdoc_contradictions(docs) == []

    def test_case_and_whitespace_normalize_before_matching(self) -> None:
        docs = [
            {"doc_id": "A", "text": "TERMINATION  FEE: $50,000"},
            {"doc_id": "B", "text": "Termination Fee: $75,000"},
        ]
        findings = detect_crossdoc_contradictions(docs)
        assert len(findings) == 1
        assert findings[0]["verdict"] == CONTRADICTED

    def test_substring_labels_never_match(self) -> None:
        docs = [
            {"doc_id": "A", "text": "Break Fee: $200,000"},
            {"doc_id": "B", "text": "Reverse Break Fee: $300,000"},
        ]
        assert detect_crossdoc_contradictions(docs) == []

    def test_label_reused_across_unrelated_dimensions_is_silent(self) -> None:
        docs = [
            {"doc_id": "A", "text": 'The "Term" shall be 24 months.'},
            {"doc_id": "B", "text": 'The "Term" shall be $50,000.'},
        ]
        assert detect_crossdoc_contradictions(docs) == []


class TestNamingDiscipline:
    """Every finding names both doc_ids, the shared label, and both figures."""

    @pytest.mark.parametrize(
        "case",
        [c for c in CORPUS if c["expected"]["verdict"] != "silent"],
        ids=[c["id"] for c in CORPUS if c["expected"]["verdict"] != "silent"],
    )
    def test_detail_names_documents_and_figures(self, case: dict) -> None:
        for f in _run_case(case):
            for doc in case["documents"]:
                assert doc["doc_id"] in f["detail"], (
                    f"{case['id']}: detail does not name document {doc['doc_id']!r}"
                )
            assert f["label"] and f["label"].lower() in f["detail"].lower()
            assert len(f["figures"]) >= 2
            for fig in f["figures"]:
                assert fig["surface"] in f["detail"], (
                    f"{case['id']}: detail does not carry figure surface {fig['surface']!r}"
                )
                assert fig["doc_id"] in f["detail"]

    def test_figures_payload_carries_doc_and_values(self) -> None:
        (finding,) = detect_crossdoc_contradictions(_CLEAN_CONFLICT)
        docs = {fig["doc_id"] for fig in finding["figures"]}
        assert docs == {"Agreement", "Amendment No. 2"}
        normalized = {fig["normalized"] for fig in finding["figures"]}
        assert normalized == {"USD 50000.00", "USD 75000.00"}


class TestVerbatimGuard:
    """A caller-marked faithful copy is never accused."""

    def test_global_flag_attributes_to_sources(self) -> None:
        findings = detect_crossdoc_contradictions(_CLEAN_CONFLICT, verbatim_run_present=True)
        assert len(findings) == 1
        f = findings[0]
        assert f["verdict"] == COULD_NOT_VERIFY
        assert f["kind"] == "crossdoc_verbatim_source_conflict"
        assert "sources" in f["detail"]
        assert "does not accuse the drafter" in f["detail"]
        assert "$50,000" in f["detail"] and "$75,000" in f["detail"]

    def test_per_document_mark_attributes_to_sources(self) -> None:
        docs = [
            {"doc_id": "A", "text": 'The "Holdback" shall be $100,000.', "verbatim": True},
            {"doc_id": "B", "text": 'The "Holdback" shall be $80,000.'},
        ]
        (f,) = detect_crossdoc_contradictions(docs)
        assert f["verdict"] == COULD_NOT_VERIFY
        assert f["kind"] == "crossdoc_verbatim_source_conflict"

    def test_false_flag_overrides_per_document_marks(self) -> None:
        docs = [
            {"doc_id": "A", "text": 'The "Holdback" shall be $100,000.', "verbatim": True},
            {"doc_id": "B", "text": 'The "Holdback" shall be $80,000.'},
        ]
        (f,) = detect_crossdoc_contradictions(docs, verbatim_run_present=False)
        assert f["verdict"] == CONTRADICTED

    def test_verbatim_never_produces_contradicted(self) -> None:
        for case in CORPUS:
            findings = detect_crossdoc_contradictions(case["documents"], verbatim_run_present=True)
            assert all(f["verdict"] == COULD_NOT_VERIFY for f in findings)


class TestNotProvablyEqualRefusals:
    """Uncertain normalization refuses with both figures named, never guesses."""

    def test_days_vs_months_refuses_naming_both(self) -> None:
        docs = [
            {"doc_id": "Agreement", "text": 'The "Cure Period" shall be 90 days.'},
            {"doc_id": "Guaranty", "text": 'The "Cure Period" shall be three months.'},
        ]
        (f,) = detect_crossdoc_contradictions(docs)
        assert f["verdict"] == COULD_NOT_VERIFY
        assert f["kind"] == "crossdoc_incomparable_units"
        assert "90 days" in f["detail"] and "three months" in f["detail"]

    def test_days_vs_months_never_contradicts_even_when_convertible_by_30(self) -> None:
        docs = [
            {"doc_id": "A", "text": 'The "Cure Period" shall be 30 days.'},
            {"doc_id": "B", "text": 'The "Cure Period" shall be one (1) month.'},
        ]
        findings = detect_crossdoc_contradictions(docs)
        assert findings and all(f["verdict"] == COULD_NOT_VERIFY for f in findings)

    def test_certain_unit_conversion_happens_before_comparing(self) -> None:
        docs = [
            {"doc_id": "A", "text": 'The "Initial Term" shall be two (2) years.'},
            {"doc_id": "B", "text": 'The "Initial Term" shall be twenty-four (24) months.'},
        ]
        assert detect_crossdoc_contradictions(docs) == []  # 2 years == 24 months

    def test_cross_currency_refuses_naming_both(self) -> None:
        docs = [
            {"doc_id": "A", "text": 'The "Purchase Price" shall be $1,000,000.'},
            {"doc_id": "B", "text": "Purchase Price: EUR 900,000"},
        ]
        (f,) = detect_crossdoc_contradictions(docs)
        assert f["verdict"] == COULD_NOT_VERIFY
        assert f["kind"] == "crossdoc_incomparable_units"
        assert "$1,000,000" in f["detail"] and "EUR 900,000" in f["detail"]

    def test_hedged_difference_refuses(self) -> None:
        docs = [
            {"doc_id": "A", "text": 'The "Deposit" shall be approximately $10,000.'},
            {"doc_id": "B", "text": 'The "Deposit" shall be $12,000.'},
        ]
        (f,) = detect_crossdoc_contradictions(docs)
        assert f["verdict"] == COULD_NOT_VERIFY
        assert f["kind"] == "crossdoc_hedged_figures"

    def test_intra_document_conflict_poisons_comparison(self) -> None:
        docs = [
            {
                "doc_id": "A",
                "text": 'The "Fee" shall be $50,000. Notwithstanding, the "Fee" shall be $60,000.',
            },
            {"doc_id": "B", "text": 'The "Fee" shall be $50,000.'},
        ]
        (f,) = detect_crossdoc_contradictions(docs)
        assert f["verdict"] == COULD_NOT_VERIFY
        assert f["kind"] == "crossdoc_intra_document_conflict"

    def test_ambiguous_numeric_dates_are_never_bound(self) -> None:
        docs = [
            {"doc_id": "A", "text": "Closing Date: 03/04/2026"},
            {"doc_id": "B", "text": "Closing Date: 04/03/2026"},
        ]
        assert detect_crossdoc_contradictions(docs) == []

    def test_impossible_calendar_date_is_never_bound(self) -> None:
        facts = extract_labeled_facts("A", "Closing Date: 2027-02-31")
        assert facts == []


class TestInputContract:
    def test_duplicate_doc_ids_raise(self) -> None:
        docs = [{"doc_id": "A", "text": "x"}, {"doc_id": "A", "text": "y"}]
        with pytest.raises(ValueError):
            detect_crossdoc_contradictions(docs)

    def test_blank_doc_id_raises(self) -> None:
        with pytest.raises(ValueError):
            detect_crossdoc_contradictions(
                [{"doc_id": " ", "text": "x"}, {"doc_id": "B", "text": "y"}]
            )

    def test_non_string_text_raises(self) -> None:
        with pytest.raises(TypeError):
            detect_crossdoc_contradictions(
                [{"doc_id": "A", "text": 1}, {"doc_id": "B", "text": "y"}]
            )

    def test_mapping_input_is_accepted(self) -> None:
        docs = {
            "Agreement": 'The "Termination Fee" shall be $50,000.',
            "Amendment": 'The "Termination Fee" shall be $75,000.',
        }
        (f,) = detect_crossdoc_contradictions(docs)
        assert f["verdict"] == CONTRADICTED

    def test_too_many_documents_raise(self) -> None:
        docs = [{"doc_id": f"D{i}", "text": ""} for i in range(33)]
        with pytest.raises(ValueError):
            detect_crossdoc_contradictions(docs)


class TestDeterminism:
    @pytest.mark.parametrize("case", CORPUS, ids=[c["id"] for c in CORPUS])
    def test_same_input_same_output(self, case: dict) -> None:
        first = json.dumps(_run_case(case), sort_keys=True)
        second = json.dumps(_run_case(case), sort_keys=True)
        assert first == second


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
