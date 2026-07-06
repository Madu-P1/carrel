"""Tests for services/words_figures.py, the words-vs-figures detector.

Loads the detector's own corpus (evals/words_figures/corpus.jsonl) and asserts
every expected outcome, then locks the campaign invariants directly:

* ZERO-GREEN: no code path can return a supported/green verdict. The finding
  dataclass rejects any verdict outside {contradicted, could_not_verify} at
  construction, and every corpus output is checked against that set.
* FIGURE-NAMING: every contradiction and every refusal names its own figures
  and tokens verbatim, never a content-free message.
* SOURCE-DEFECT: a conflicted pair the source carries verbatim is never
  blamed on the drafter.
* DENOMINATION AMBIGUITY: a structural cross-reference ("Section thirty (40)")
  never fires; only a pair that unambiguously restates the same fact does.
* DETERMINISM: the same input twice gives identical output.

Run directly:

    ./.venv/bin/python -m pytest tests/test_words_figures.py -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.words_figures import (  # noqa: E402
    ALLOWED_VERDICTS,
    CONTRADICTED,
    COULD_NOT_VERIFY,
    WordsFiguresFinding,
    check_words_figures,
    find_pair_sites,
)

_CORPUS_PATH = _REPO_ROOT / "evals" / "words_figures" / "corpus.jsonl"


def _load_corpus() -> list[dict]:
    cases = []
    with _CORPUS_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


_CASES = _load_corpus()


# --- Corpus-driven expectations ---------------------------------------------


def test_corpus_has_required_coverage() -> None:
    assert len(_CASES) >= 12, f"corpus must hold at least 12 cases, has {len(_CASES)}"
    expected_kinds = {case["expected"] for case in _CASES}
    assert expected_kinds == {"contradicted", "could_not_verify", "silent"}
    ids = [case["id"] for case in _CASES]
    assert len(set(ids)) == len(ids), "duplicate corpus ids"
    assert sum(1 for c in _CASES if c["expected"] == "contradicted") >= 4
    assert sum(1 for c in _CASES if c["expected"] == "silent") >= 4
    assert sum(1 for c in _CASES if c["expected"] == "could_not_verify") >= 3


def test_every_corpus_case_matches_its_expected_outcome() -> None:
    for case in _CASES:
        findings = check_words_figures(case["claim"], case["source"])
        if case["expected"] == "silent":
            assert findings == [], (
                f"{case['id']}: expected SILENCE (no verdict at all), got "
                f"{[(f.verdict, f.detail) for f in findings]}"
            )
            continue
        assert findings, f"{case['id']}: expected {case['expected']}, got no findings"
        for finding in findings:
            assert finding.verdict == case["expected"], (
                f"{case['id']}: expected every finding to be {case['expected']}, "
                f"got {finding.verdict}: {finding.detail}"
            )
        details = " | ".join(finding.detail for finding in findings)
        for token in case["must_name"]:
            assert token in details, (
                f"{case['id']}: detail must name {token!r} verbatim; got: {details}"
            )


def test_source_defect_case_never_accuses_the_drafter() -> None:
    (case,) = [c for c in _CASES if c["id"] == "wf-source-verbatim-defect"]
    findings = check_words_figures(case["claim"], case["source"])
    assert findings, "the conflicted pair must still surface"
    for finding in findings:
        assert finding.verdict == COULD_NOT_VERIFY
        assert finding.verdict != CONTRADICTED
        assert "source" in finding.detail, finding.detail
        assert finding.kind == "words_figures_source_defect"


def test_ambiguous_denomination_case_stays_silent() -> None:
    (case,) = [c for c in _CASES if c["id"] == "wf-ambiguous-denomination-section-silent"]
    assert check_words_figures(case["claim"], case["source"]) == []


def test_idiomatic_non_claim_case_stays_silent() -> None:
    (case,) = [c for c in _CASES if c["id"] == "wf-idiomatic-one-of-the-parties-silent"]
    assert check_words_figures(case["claim"], case["source"]) == []


# --- Zero-green invariant ----------------------------------------------------


def test_allowed_verdicts_contain_no_green_state() -> None:
    assert ALLOWED_VERDICTS == frozenset({"contradicted", "could_not_verify"})
    for banned in ("supported", "verified", "present", "ok", "green"):
        assert banned not in ALLOWED_VERDICTS


def test_finding_construction_rejects_any_green_verdict() -> None:
    for banned in ("supported", "verified", "present", ""):
        try:
            WordsFiguresFinding(
                verdict=banned, kind="words_figures_conflict", detail="x", span="x", start=0, end=1
            )
        except ValueError:
            continue
        raise AssertionError(f"finding accepted banned verdict {banned!r}")


def test_no_input_in_corpus_yields_a_verdict_outside_the_allowed_set() -> None:
    for case in _CASES:
        for finding in check_words_figures(case["claim"], case["source"]):
            assert finding.verdict in ALLOWED_VERDICTS, (case["id"], finding.verdict)


def test_consistent_pairs_are_silent_not_green() -> None:
    consistent = [
        "The notice period is thirty (30) days.",
        "The purchase price is One Million Dollars ($1,000,000).",
        "The fee is twenty-five (25) basis points.",
        "The term is one hundred fifty (150) days.",
        "The deposit is five hundred dollars (500).",
    ]
    for claim in consistent:
        assert check_words_figures(claim, claim) == [], claim


# --- Denomination ambiguity (structural cross-references) -------------------


def test_structural_cross_references_never_fire() -> None:
    for text in [
        "The tenant shall pay rent under Section thirty (40) of the Lease.",
        "See Exhibit thirty (40) attached hereto.",
        "Article five (40) governs termination rights.",
        "Pursuant to Schedule five (40) attached hereto, Buyer shall pay the amounts listed.",
        "As set forth in Paragraph twelve (5) above, the terms apply.",
    ]:
        assert check_words_figures(text) == [], text


def test_idiomatic_non_claims_never_fire() -> None:
    for text in [
        'One of the parties (the "Buyer") shall bear all recording costs.',
        "The parties agree that one of the parties shall notify the other in writing.",
    ]:
        assert check_words_figures(text) == [], text


# --- Figure-naming on every emission -----------------------------------------


def test_every_emitted_finding_names_its_own_figures() -> None:
    for case in _CASES:
        for finding in check_words_figures(case["claim"], case["source"]):
            sites = {s.span: s for s in find_pair_sites(case["claim"])}
            site = sites[finding.span]
            assert f"'{site.word_text}'" in finding.detail, (case["id"], finding.detail)
            assert f"'{site.paren_text}'" in finding.detail, (case["id"], finding.detail)
            assert any(ch.isdigit() for ch in finding.detail), (case["id"], finding.detail)


def test_refusals_name_the_specific_unparsed_token() -> None:
    findings = check_words_figures("The amount is one and a half million dollars ($1,500,000).")
    assert [f.verdict for f in findings] == [COULD_NOT_VERIFY]
    assert "'one and a half million dollars'" in findings[0].detail
    assert "$1,500,000" in findings[0].detail

    findings = check_words_figures("The cure period is thirty (3,0) days.")
    assert [f.verdict for f in findings] == [COULD_NOT_VERIFY]
    assert "'3,0'" in findings[0].detail
    assert "'thirty'" in findings[0].detail


# --- Determinism --------------------------------------------------------------


def test_same_input_twice_gives_identical_output() -> None:
    for case in _CASES:
        first = check_words_figures(case["claim"], case["source"])
        second = check_words_figures(case["claim"], case["source"])
        assert first == second, case["id"]
    sites_a = find_pair_sites("thirty (40) days and Five Thousand Dollars ($5,000)")
    sites_b = find_pair_sites("thirty (40) days and Five Thousand Dollars ($5,000)")
    assert sites_a == sites_b


# --- verbatim_run_present handling --------------------------------------------


def test_explicit_verbatim_flag_true_routes_conflict_to_source_defect() -> None:
    findings = check_words_figures(
        "The cure period is thirty (40) days.", verbatim_run_present=True
    )
    assert [f.verdict for f in findings] == [COULD_NOT_VERIFY]
    assert findings[0].kind == "words_figures_source_defect"
    assert "source" in findings[0].detail


def test_explicit_verbatim_flag_false_overrides_the_source_text() -> None:
    source = "If Tenant fails to cure within thirty (40) days, Landlord may terminate."
    findings = check_words_figures(
        "The cure period is thirty (40) days.", source, verbatim_run_present=False
    )
    assert [f.verdict for f in findings] == [CONTRADICTED]


def test_default_computes_verbatim_presence_from_source() -> None:
    claim = "The cure period is thirty (40) days."
    in_source = "If Tenant fails to cure within thirty (40) days, Landlord may terminate."
    not_in_source = "If Tenant fails to cure within thirty (30) days, Landlord may terminate."
    assert [f.verdict for f in check_words_figures(claim, in_source)] == [COULD_NOT_VERIFY]
    assert [f.verdict for f in check_words_figures(claim, not_in_source)] == [CONTRADICTED]


# --- Site location unit checks -------------------------------------------------


def test_find_pair_sites_parses_values_and_positions() -> None:
    text = "Deliver within thirty (40) days; pay Five Thousand Dollars ($5,000)."
    sites = find_pair_sites(text)
    assert len(sites) == 2
    first, second = sites
    assert (first.word_value, first.figure_value) == (30, 40)
    assert text[first.start : first.end] == first.span == "thirty (40)"
    assert (second.word_value, second.figure_value) == (5000, 5000)
    assert second.word_is_dollars and second.figure_is_dollars


def test_non_sites_stay_silent() -> None:
    for text in [
        "The Deposit (as defined in Section 3) shall be returned.",
        "Payment is due on the thirtieth (30th) day of each month.",
        "See page two (2 of 14) for the schedule.",
        "The fee is thirty ($30) per day.",
        "There is no parenthetical here, just thirty days.",
    ]:
        assert check_words_figures(text) == [], text


def test_invalid_input_types_raise() -> None:
    for bad in (None, 30, ["thirty (30) days"]):
        try:
            check_words_figures(bad)  # type: ignore[arg-type]
        except TypeError:
            continue
        raise AssertionError(f"claim {bad!r} should have raised TypeError")
    try:
        check_words_figures("thirty (30) days", None)  # type: ignore[arg-type]
    except TypeError:
        pass
    else:
        raise AssertionError("non-str source should have raised TypeError")
