"""Tests for services/crossref_integrity.py, the document-structure detector.

Loads the detector's corpora (evals/crossref/corpus.jsonl and the gate corpus
evals/crossref_corpus.jsonl) and asserts every expected verdict, kind, and
must_name substring, then locks the campaign invariants directly:

* ZERO-GREEN / SILENT-BY-DEFAULT: no code path returns a supported/green
  verdict. The finding dataclass rejects any verdict outside {contradicted,
  could_not_verify} at construction; every clean document -- and every
  near-miss trap -- produces zero findings.
* VERBATIM EVIDENCE: a dangling reference names the exact citation string and
  quotes its sentence; an undefined term quotes its usage spans; a conflicting
  duplicate definition quotes BOTH definition spans.
* FALSE-ACCUSATION GUARDS: a reference never fires unless its numbering family
  demonstrably parses in the document; a reference into an EXTERNAL document
  ("Section 4.2 of the Prior Agreement", "Exhibit B to the Original
  Agreement", "Section 9 thereof") never fires; an undefined term never fires
  without a provable definitions convention, and never for a term imported
  "(as defined in ...)".
* QUOTE GUARD: a defect carried verbatim from the source refuses as a source
  defect; verbatim_run_present forces either disposition.
* ZERO FALSE ACCUSATION: over every silent corpus case, no verdict of any kind
  is emitted.
* DETERMINISM: same input twice produces byte-identical findings.

Run directly:

    ./.venv/bin/python -m pytest tests/test_crossref_integrity.py -q
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.crossref_integrity import (  # noqa: E402
    ALLOWED_VERDICTS,
    CONTRADICTED,
    COULD_NOT_VERIFY,
    CrossrefFinding,
    check_crossref_integrity,
    detect,
    detect_crossref_defects,
)

_CORPUS = _REPO_ROOT / "evals" / "crossref" / "corpus.jsonl"
_GATE_CORPUS = _REPO_ROOT / "evals" / "crossref_corpus.jsonl"


def _load_file(path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _load_corpus() -> list[dict]:
    return _load_file(_CORPUS) + _load_file(_GATE_CORPUS)


def _run(case: dict) -> list[dict]:
    kwargs = {}
    if "verbatim_run_present" in case:
        kwargs["verbatim_run_present"] = case["verbatim_run_present"]
    return detect(case["text"], case.get("source", ""), **kwargs)


def _haystack(finding: dict) -> str:
    return " ".join(str(v) for v in finding.values())


class CorpusTests(unittest.TestCase):
    """Every case in the frozen corpus disposes exactly as recorded."""

    def test_gate_corpus_exists_with_twelve_plus_cases(self) -> None:
        self.assertTrue(_GATE_CORPUS.is_file(), "evals/crossref_corpus.jsonl is the gate path")
        self.assertGreaterEqual(len(_load_file(_GATE_CORPUS)), 12)

    def test_corpus_dispositions(self) -> None:
        cases = _load_corpus()
        self.assertGreaterEqual(len(cases), 15, "corpus must carry at least 15 cases")
        for case in cases:
            with self.subTest(case=case["id"]):
                findings = _run(case)
                exp = case["expected"]
                if exp["verdict"] == "silent":
                    self.assertEqual(findings, [], f"{case['id']} must be silent (clean)")
                    continue
                match = [f for f in findings if f["kind"] == exp["kind"]]
                self.assertTrue(
                    match,
                    f"{case['id']} expected a {exp['kind']} finding; got "
                    f"{[f['kind'] for f in findings]}",
                )
                found = match[0]
                self.assertEqual(found["verdict"], exp["verdict"], case["id"])
                hay = _haystack(found)
                for needle in exp["must_name"]:
                    self.assertIn(needle, hay, f"{case['id']} must name {needle!r}")

    def test_zero_false_accusation_over_silent_cases(self) -> None:
        for case in _load_corpus():
            if case["expected"]["verdict"] != "silent":
                continue
            with self.subTest(case=case["id"]):
                self.assertEqual(_run(case), [])

    def test_no_green_verdict_anywhere_in_corpus(self) -> None:
        for case in _load_corpus():
            for f in _run(case):
                self.assertIn(f["verdict"], ALLOWED_VERDICTS)

    def test_check_crossref_integrity_matches_detect_over_corpus(self) -> None:
        for case in _load_corpus():
            context = {"source": case.get("source", "")}
            if "verbatim_run_present" in case:
                context["verbatim_run_present"] = case["verbatim_run_present"]
            with self.subTest(case=case["id"]):
                self.assertEqual(check_crossref_integrity(case["text"], context), _run(case))


class DanglingReferenceTests(unittest.TestCase):
    """Defect class (a): dangling references, with the family-in-play guard."""

    def test_dangling_section_names_verbatim_evidence(self) -> None:
        text = (
            "Section 1. Purpose. The scope is set out below.\n"
            "Section 2. Term. The term is one year. "
            "The audit rights in Section 6.3 survive termination."
        )
        findings = detect(text)
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f["verdict"], CONTRADICTED)
        self.assertEqual(f["kind"], "crossref_dangling_reference")
        self.assertEqual(f["subject"], "Section 6.3")
        self.assertIn("Section 6.3", f["detail"])
        self.assertIn("The audit rights in Section 6.3 survive termination", f["detail"])
        self.assertIn("Section 1", f["detail"])  # names the real headings
        self.assertTrue(f["evidence"])
        self.assertEqual(f["evidence"][0]["role"], "reference")

    def test_family_not_in_play_stays_silent(self) -> None:
        text = (
            "Section 1. Scope. Services are described below.\n"
            "Section 2. Deliverables. The items in Exhibit Q shall be delivered."
        )
        self.assertEqual(detect(text), [])

    def test_no_headings_at_all_stays_silent(self) -> None:
        self.assertEqual(detect("The procedures in Section 12.4 govern all claims."), [])

    def test_external_document_reference_never_fires(self) -> None:
        for tail in (
            "Section 4.2 of the Prior Agreement",
            "Section 4.2 of that Purchase Agreement",
            "Exhibit C to the Original Agreement",
            "Section 4.2 thereof",
            "Section 4.2 of Exhibit A",
        ):
            with self.subTest(tail=tail):
                text = (
                    "Section 1. Scope. Services are described below.\n"
                    "EXHIBIT A\nStatement of Work\n"
                    f"Section 2. Incorporation. The terms in {tail} are incorporated."
                )
                self.assertEqual(detect(text), [])

    def test_internal_of_this_agreement_fires(self) -> None:
        text = (
            "Section 1. Scope. Services are described below.\n"
            "Section 2. Disputes. Section 9 of this Agreement governs disputes."
        )
        findings = detect(text)
        self.assertEqual([f["kind"] for f in findings], ["crossref_dangling_reference"])
        self.assertEqual(findings[0]["subject"], "Section 9")

    def test_parent_heading_resolves_subsection_reference(self) -> None:
        text = (
            "Section 1. General. Effective on signature.\n"
            "Section 4. Indemnity. The procedures in Section 4.3 govern claims."
        )
        self.assertEqual(detect(text), [])

    def test_child_heading_resolves_parent_reference(self) -> None:
        text = (
            "Section 3.1. Fees. Fees are due monthly.\n"
            "Section 3.2. Expenses. Expenses per Section 3 are reimbursable."
        )
        self.assertEqual(detect(text), [])

    def test_article_roman_and_arabic_unify(self) -> None:
        text = "ARTICLE IV\nTermination. Either party may act under Article 4 at will."
        self.assertEqual(detect(text), [])

    def test_repeated_dangling_reference_emits_one_finding(self) -> None:
        text = (
            "Section 1. Scope. Services are described below.\n"
            "Section 2. Fees. Per Section 8, fees vest. Section 8 also governs refunds."
        )
        findings = detect(text)
        self.assertEqual(len(findings), 1)
        self.assertEqual(len(findings[0]["evidence"]), 2)


class DefinedTermTests(unittest.TestCase):
    """Defect class (b): undefined defined-terms, always a refusal."""

    _DEF = (
        'Section 1. Definitions. "Disclosing Party" means the party disclosing data. '
        "The Disclosing Party shall mark data.\n"
    )

    def test_undefined_term_refuses_with_usage_quoted(self) -> None:
        text = self._DEF + (
            "Section 2. Duties. The Receiving Party shall guard the data. "
            "The Receiving Party shall return the data."
        )
        findings = detect(text)
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f["verdict"], COULD_NOT_VERIFY)
        self.assertEqual(f["kind"], "crossref_undefined_term")
        self.assertEqual(f["subject"], "Receiving Party")
        self.assertIn("The Receiving Party shall guard the data", f["detail"])
        self.assertIn("no definition", f["detail"])

    def test_no_definitions_convention_stays_silent(self) -> None:
        text = (
            "The Receiving Party shall guard the data. The Receiving Party shall return the data."
        )
        self.assertEqual(detect(text), [])

    def test_single_unquoted_use_stays_silent(self) -> None:
        text = self._DEF + "Section 2. Duties. The Receiving Party shall guard the data."
        self.assertEqual(detect(text), [])

    def test_quoted_use_fires_on_first_occurrence(self) -> None:
        text = self._DEF + 'Section 2. Work. The "Statement of Work" deliverables are due.'
        findings = detect(text)
        self.assertEqual([f["kind"] for f in findings], ["crossref_undefined_term"])
        self.assertEqual(findings[0]["subject"], "Statement of Work")

    def test_as_defined_in_external_document_suppresses(self) -> None:
        text = self._DEF + (
            "Section 2. Duties. The Receiving Party (as defined in the Prior Agreement) "
            "shall guard the data. The Receiving Party shall return the data."
        )
        self.assertEqual(detect(text), [])

    def test_parenthetical_definition_resolves_term(self) -> None:
        text = (
            'Each supplier of record (the "Approved Vendor") is listed below. '
            "The Approved Vendor shall invoice monthly. "
            "The Approved Vendor shall report defects."
        )
        self.assertEqual(detect(text), [])

    def test_meaning_pointer_definition_resolves_term(self) -> None:
        text = self._DEF + (
            '"Receiving Party" has the meaning given in the recitals. '
            "The Receiving Party shall guard the data. "
            "The Receiving Party shall return the data."
        )
        self.assertEqual(detect(text), [])


class ConflictingDefinitionTests(unittest.TestCase):
    """Defect class (c): duplicate definitions with different bodies."""

    def test_conflict_quotes_both_definition_spans(self) -> None:
        text = (
            'Section 1. Definitions. "Net Revenue" means gross receipts less returns.\n'
            'Section 7. Royalties. "Net Revenue" means gross receipts less all taxes.'
        )
        findings = detect(text)
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f["verdict"], CONTRADICTED)
        self.assertEqual(f["kind"], "crossref_conflicting_definition")
        self.assertEqual(f["subject"], "Net Revenue")
        self.assertIn('"Net Revenue" means gross receipts less returns', f["detail"])
        self.assertIn('"Net Revenue" means gross receipts less all taxes', f["detail"])
        self.assertEqual(len(f["evidence"]), 2)
        self.assertEqual({e["role"] for e in f["evidence"]}, {"definition"})

    def test_identical_restatement_stays_silent(self) -> None:
        text = (
            'Section 1. "Business Day" means any day other than a Sunday.\n'
            'Section 9. For clarity, "Business Day" means any day other than a Sunday. '
            "Notices are effective on the next Business Day."
        )
        self.assertEqual(detect(text), [])

    def test_different_terms_never_conflict(self) -> None:
        text = (
            'Section 1. "Gross Revenue" means all receipts.\n'
            'Section 2. "Net Revenue" means all receipts less returns. '
            "The royalty is computed from Gross Revenue and from Net Revenue quarterly."
        )
        self.assertEqual(detect(text), [])


class QuoteGuardTests(unittest.TestCase):
    """A defect carried verbatim from the source never accuses the drafter."""

    _TEXT = (
        "Section 1. Purpose. This Amendment restates the assignment clause.\n"
        "Section 2. Assignment. The transfer restrictions in Section 7.1 apply here."
    )
    _SOURCE = "Original: the transfer restrictions in Section 7.1 apply here."

    def test_auto_source_match_refuses_as_source_defect(self) -> None:
        findings = detect(self._TEXT, self._SOURCE)
        self.assertEqual([f["kind"] for f in findings], ["crossref_source_defect"])
        f = findings[0]
        self.assertEqual(f["verdict"], COULD_NOT_VERIFY)
        self.assertIn("Section 7.1", f["detail"])
        self.assertIn("source", f["detail"])

    def test_verbatim_run_present_true_forces_source_defect(self) -> None:
        findings = detect(self._TEXT, verbatim_run_present=True)
        self.assertEqual([f["kind"] for f in findings], ["crossref_source_defect"])
        self.assertEqual(findings[0]["verdict"], COULD_NOT_VERIFY)

    def test_verbatim_run_present_false_forces_accusation(self) -> None:
        findings = detect(self._TEXT, self._SOURCE, verbatim_run_present=False)
        self.assertEqual([f["kind"] for f in findings], ["crossref_dangling_reference"])
        self.assertEqual(findings[0]["verdict"], CONTRADICTED)

    def test_unrelated_source_still_accuses(self) -> None:
        findings = detect(self._TEXT, "A source about something else entirely.")
        self.assertEqual([f["kind"] for f in findings], ["crossref_dangling_reference"])

    def test_conflicting_definitions_in_source_refuse(self) -> None:
        text = (
            'Section 1. "Net Revenue" means gross receipts less returns.\n'
            'Section 7. "Net Revenue" means gross receipts less all taxes.'
        )
        source = (
            'Legacy: "Net Revenue" means gross receipts less returns. Later: '
            '"Net Revenue" means gross receipts less all taxes.'
        )
        findings = detect(text, source)
        self.assertEqual([f["kind"] for f in findings], ["crossref_source_defect"])
        self.assertEqual(findings[0]["verdict"], COULD_NOT_VERIFY)


class InvariantTests(unittest.TestCase):
    """Structural honesty invariants."""

    def test_finding_rejects_green_verdicts(self) -> None:
        for verdict in ("supported", "verified", "green", ""):
            with self.subTest(verdict=verdict):
                with self.assertRaises(ValueError):
                    CrossrefFinding(
                        verdict=verdict,
                        kind="crossref_dangling_reference",
                        subject="Section 1",
                        detail="",
                        evidence=(),
                        span="",
                        start=0,
                        end=0,
                    )

    def test_determinism_byte_identical(self) -> None:
        for case in _load_corpus():
            a = _run(case)
            b = _run(case)
            self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))

    def test_empty_and_trivial_inputs_are_silent(self) -> None:
        self.assertEqual(detect(""), [])
        self.assertEqual(detect("Hello world."), [])

    def test_type_and_size_guards(self) -> None:
        with self.assertRaises(TypeError):
            detect(None)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            detect("x", source=7)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            detect("x" * 2_000_001)

    def test_alias_is_the_same_callable(self) -> None:
        self.assertIs(detect, detect_crossref_defects)


class UnusedTermTests(unittest.TestCase):
    """Defect class (d): defined-but-never-used, always informational."""

    _UNUSED = (
        'Section 1. Definitions. "Permitted Purpose" means evaluation of the '
        "Software for internal testing.\n"
        "Section 2. License. A non-exclusive license is granted under Section 1."
    )

    def test_unused_means_definition_fires_informational(self) -> None:
        findings = detect(self._UNUSED)
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f["verdict"], COULD_NOT_VERIFY)
        self.assertEqual(f["kind"], "crossref_unused_term")
        self.assertEqual(f["subject"], "Permitted Purpose")
        self.assertIn(
            '"Permitted Purpose" means evaluation of the Software for internal testing',
            f["detail"],
        )
        self.assertIn("Informational", f["detail"])
        self.assertEqual([e["role"] for e in f["evidence"]], ["definition"])

    def test_any_reuse_silences_even_lowercase(self) -> None:
        text = (
            'Section 1. Definitions. "Term" means the twelve-month period '
            "beginning on signature.\n"
            "Section 2. Restrictions. During the term, neither party may solicit."
        )
        self.assertEqual(detect(text), [])

    def test_use_inside_another_definition_body_counts_as_use(self) -> None:
        text = (
            '"Net Revenue" means Gross Revenue less returns and refunds. '
            '"Gross Revenue" means all amounts invoiced to customers. '
            "Net Revenue determines the royalty each quarter."
        )
        self.assertEqual(detect(text), [])

    def test_pointer_definition_unused_fires(self) -> None:
        text = (
            'Section 1. Definitions. "Holdback Amount" has the meaning given in '
            "the escrow instructions. The parties shall follow Section 1."
        )
        findings = detect(text)
        self.assertEqual([f["kind"] for f in findings], ["crossref_unused_term"])
        self.assertEqual(findings[0]["subject"], "Holdback Amount")

    def test_conflicted_term_is_not_double_reported_as_unused(self) -> None:
        text = (
            'Section 1. "Net Revenue" means gross receipts less returns.\n'
            'Section 7. "Net Revenue" means gross receipts less all taxes.'
        )
        findings = detect(text)
        self.assertEqual([f["kind"] for f in findings], ["crossref_conflicting_definition"])


class BareNumberAnchorTests(unittest.TestCase):
    """A keyword-less '4.2.' heading resolves references, never accuses."""

    def test_bare_dotted_heading_resolves_section_reference(self) -> None:
        text = (
            "Section 1. General. This Agreement is effective on signature.\n"
            "Section 2. Liability. Liability is capped as stated in Section 4.2.\n"
            "4.2. Indemnity and Liability Cap. The cap equals the fees paid."
        )
        self.assertEqual(detect(text), [])

    def test_bare_heading_without_trailing_prose_resolves(self) -> None:
        text = (
            "Section 1. Scope. Services are described below. See Section 3.1 for fees.\n3.1\n"
            "Fees are due monthly."
        )
        self.assertEqual(detect(text), [])

    def test_bare_headings_alone_never_put_a_family_in_play(self) -> None:
        text = "4.2. Indemnity Procedures. All claims follow the procedures in Section 4.2."
        self.assertEqual(detect(text), [])
        text2 = "1. Scope of Work.\n2. Payment.\nThe warranty in Section 5 is exclusive."
        self.assertEqual(detect(text2), [])

    def test_bare_anchor_does_not_mask_a_truly_absent_number(self) -> None:
        text = (
            "Section 1. Scope. Services are described below.\n"
            "4.2. Indemnity Cap. The remedies in Section 9.9 are exclusive."
        )
        findings = detect(text)
        self.assertEqual([f["kind"] for f in findings], ["crossref_dangling_reference"])
        self.assertEqual(findings[0]["subject"], "Section 9.9")


class CheckCrossrefIntegrityTests(unittest.TestCase):
    """The mandated surface: check_crossref_integrity(text, context)."""

    _TEXT = QuoteGuardTests._TEXT
    _SOURCE = QuoteGuardTests._SOURCE

    def test_no_context_matches_detect(self) -> None:
        self.assertEqual(check_crossref_integrity(self._TEXT), detect(self._TEXT))
        self.assertEqual(check_crossref_integrity(self._TEXT, None), detect(self._TEXT))

    def test_context_source_maps_to_quote_guard(self) -> None:
        findings = check_crossref_integrity(self._TEXT, {"source": self._SOURCE})
        self.assertEqual(findings, detect(self._TEXT, self._SOURCE))
        self.assertEqual([f["kind"] for f in findings], ["crossref_source_defect"])

    def test_context_verbatim_flag_forces_disposition(self) -> None:
        forced = check_crossref_integrity(self._TEXT, {"verbatim_run_present": True})
        self.assertEqual([f["kind"] for f in forced], ["crossref_source_defect"])
        accused = check_crossref_integrity(
            self._TEXT, {"source": self._SOURCE, "verbatim_run_present": False}
        )
        self.assertEqual([f["kind"] for f in accused], ["crossref_dangling_reference"])

    def test_context_type_guard(self) -> None:
        with self.assertRaises(TypeError):
            check_crossref_integrity(self._TEXT, context=["source"])  # type: ignore[arg-type]

    def test_silent_on_clean_input(self) -> None:
        self.assertEqual(check_crossref_integrity("Hello world."), [])


if __name__ == "__main__":
    unittest.main()
