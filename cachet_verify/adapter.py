"""Strangler-fig adapter: the hardened engine behind the frozen contract.

This is ADR-0014's extraction seam. It maps ``services.legal``'s dispositions
into the kernel's three-state contract and layers the kernel's OWN residue
detectors (dosages, physical-unit quantities, grouped counts) on top; when the
extraction completes, the engine's internals move INSIDE this package and this
module dissolves. Surfaces and the daemon depend only on ``verify_claim`` /
``attest_draft`` -- never on ``services.legal`` directly -- so the migration
never breaks an embedder.

Batch B swallowed the richer cross-clause adjudicator: every source SENTENCE
becomes a ClauseCandidate and ``adjudicate_clause_candidates`` applies the
app's own precedence rules (a contradiction stands only when no clause carries
the value; conflicting clauses refuse with both named; certainty is
manufactured in neither direction). Candidates carry ``on_topic=False`` on
purpose: the seam has no retrieval-relevance signal, and without one a bare
value coincidence must never earn a green (C3) -- confirmations come only from
the strictly stronger conditions (exact restatement, equal-values near-copy,
verbatim quotes).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from services.legal.anchors import extract_anchors
from services.legal.contract_verify import (
    ClauseCandidate,
    adjudicate_clause_candidates,
    verify_claim_against_clause,
)
from services.legal.quote_check import (
    SourceText,
    check_quote_against_pool,
    extract_draft_quotes,
    prepare_source_pool,
)
from services.legal.sentences import split_sentences

from .contract import SCHEMA_VERSION, Attestation, CheckResult, attest, combine
from .residue import ResidueComparison, compare_residue, extract_residue_anchors

_CLAUSE_STATE = {
    "parametric_contradiction": "altered",
    "present": "verified",
    "not_found": "could_not_check",
    "multi_value_unverifiable": "could_not_check",
    "conflicting_clauses": "could_not_check",
}

SourceInput = str | dict | SourceText


def _normalize(text: str) -> str:
    return " ".join(text.split()).strip().lower()


def _coerce_sources(sources: list[SourceInput]) -> list[SourceText]:
    """Accept raw strings (complete by assumption), dicts ({text, truncated?,
    complete?}), or SourceText records. Truncation/completeness ride into the
    quote pool so a run absent from a partial source degrades to
    could_not_check instead of flagging (the quote engine's own rule)."""
    out: list[SourceText] = []
    for s in sources:
        if isinstance(s, SourceText):
            out.append(s)
        elif isinstance(s, dict):
            text = s.get("text")
            if not isinstance(text, str):
                continue
            out.append(
                SourceText(
                    text=text,
                    truncated=bool(s.get("truncated", False)),
                    complete=bool(s.get("complete", True)),
                )
            )
        elif isinstance(s, str):
            out.append(SourceText(text=s))
    return out


def _quote_checks(claim: str, pool) -> list[CheckResult]:
    checks: list[CheckResult] = []
    for quote in extract_draft_quotes(claim):
        result = check_quote_against_pool(quote, pool)
        if result.altered:
            state, detail = "altered", "quoted words absent from every source"
        elif result.unplaceable:
            state, detail = "could_not_check", "no source could be fully seen for this quote"
        else:
            state, detail = "verified", "quote is verbatim in a source"
        checks.append(
            CheckResult(state=state, provenance="deterministic", detail=detail, subject=quote)
        )
    return checks


def _clause_leg(claim: str, source_texts: list[str]) -> tuple[str, str, str] | None:
    """Run the app's cross-clause adjudicator over every source sentence.

    Returns (state, detail, disposition) or None when there is nothing to
    adjudicate. The raw disposition rides along because ``conflicting_clauses``
    is not a plain abstention: it is the adjudicator KNOWING the sources
    disagree, and that knowledge must veto every confirmation path (including
    the exact-restatement rule -- a source that both states and contradicts a
    claim proves nothing either way).
    """
    candidates: list[ClauseCandidate] = []
    for source in source_texts:
        for sentence in split_sentences(source):
            verdict = verify_claim_against_clause(claim, sentence)
            candidates.append(
                ClauseCandidate(
                    verdict=verdict,
                    section=None,
                    clause_text=sentence,
                    # No retrieval-relevance signal exists at this seam; a bare
                    # value coincidence must never earn a green (C3), so no
                    # candidate is marked on-topic. Quote presents are exempt
                    # inside the adjudicator itself.
                    on_topic=False,
                )
            )
    if not candidates:
        return None
    verdict, _section, _clause = adjudicate_clause_candidates(candidates)
    return (
        _CLAUSE_STATE.get(verdict.disposition, "could_not_check"),
        verdict.detail,
        verdict.disposition,
    )


def _skeleton(text: str) -> str:
    """The text with every anchor span (legal + residue) masked: the
    same-fact test. Two sentences with equal skeletons state the same fact,
    possibly with different figures."""
    serv_spans = [(a.start, a.end) for a in extract_anchors(text)]
    res = extract_residue_anchors(text, claimed_spans=serv_spans)
    spans = sorted(serv_spans + [(a.start, a.end) for a in res])
    out: list[str] = []
    last = 0
    for start, end in spans:
        out.append(text[last:start])
        out.append("#")
        last = end
    out.append(text[last:])
    return _normalize(" ".join(out))


def _same_fact_conflict(claim: str, norm_claim: str, source_texts: list[str]) -> bool:
    """True when some source sentence states the SAME fact as the claim (equal
    skeleton) with DIFFERENT figures (unequal normalized text). This is the
    amended-value shape, the one conflict that must veto every confirmation.
    A different-fact sentence that merely shares a value is retrieval noise at
    this seam, not a conflict."""
    claim_skeleton = _skeleton(claim)
    for source in source_texts:
        for sentence in split_sentences(source):
            if _normalize(sentence) == norm_claim:
                continue
            if _skeleton(sentence) == claim_skeleton:
                return True
    return False


def verify_claim(claim: str, sources: list[SourceInput]) -> Attestation:
    """Attest one claim against sources. Pure, no I/O, no network.

    Legs (each participating only when the claim carries its content):
    quotes (verbatim against the pool, truncation-honest), clause (the legal
    engine's parametrics under the app's own adjudicator), residue
    (kernel-owned quantities/counts under the near-copy gate), and the
    exact-restatement confirmation.
    """
    source_records = _coerce_sources(sources)
    source_texts = [s.text for s in source_records]
    pool = prepare_source_pool(source_records)

    checks: list[CheckResult] = list(_quote_checks(claim, pool))

    claim_serv = extract_anchors(claim)
    serv_spans = [(a.start, a.end) for a in claim_serv]
    claim_res = extract_residue_anchors(claim, claimed_spans=serv_spans)
    res_spans = [(a.start, a.end) for a in claim_res]
    claim_all_spans = serv_spans + res_spans
    norm_claim = _normalize(claim)

    if not claim_serv and not claim_res:
        if not checks:
            checks.append(
                CheckResult(
                    state="could_not_check",
                    provenance="deterministic",
                    detail="no deterministically checkable content in this claim",
                    subject=claim,
                )
            )
        return attest(checks)

    if not source_records:
        checks.append(
            CheckResult(
                state="could_not_check",
                provenance="deterministic",
                detail="no sources were provided to check this claim against",
                subject=claim,
            )
        )
        return attest(checks)

    clause_outcome = _clause_leg(claim, source_texts) if claim_serv else None

    residue_outcomes: list[ResidueComparison] = []
    restated = False
    for source in source_texts:
        for sentence in split_sentences(source):
            if norm_claim and _normalize(sentence) == norm_claim:
                restated = True
            if claim_res:
                s_serv_spans = [(a.start, a.end) for a in extract_anchors(sentence)]
                s_res = extract_residue_anchors(sentence, claimed_spans=s_serv_spans)
                s_all_spans = s_serv_spans + [(a.start, a.end) for a in s_res]
                outcome = compare_residue(
                    claim, claim_res, claim_all_spans, sentence, s_res, s_all_spans
                )
                if outcome is not None:
                    residue_outcomes.append(outcome)

    altered_clause = clause_outcome is not None and clause_outcome[0] == "altered"
    verified_clause = clause_outcome is not None and clause_outcome[0] == "verified"
    # The adjudicator's conflicting_clauses fires whenever ANY candidate
    # carries the claim's value while another contradicts it -- at this seam
    # every sentence of every source is a candidate, so an unrelated sentence
    # sharing a money figure manufactures "conflict" noise. The veto is
    # therefore narrowed to the REAL amended-value shape: a sentence stating
    # the same fact (equal skeleton) with different figures. Cross-fact noise
    # abstains instead (the confirmation legs may still speak).
    clause_conflict = (
        clause_outcome is not None
        and clause_outcome[2] == "conflicting_clauses"
        and _same_fact_conflict(claim, norm_claim, source_texts)
    )
    altered_residue = next((o for o in residue_outcomes if o.state == "altered"), None)
    verified_residue = next((o for o in residue_outcomes if o.state == "verified"), None)

    any_altered = altered_clause or altered_residue is not None
    any_verified = restated or verified_clause or verified_residue is not None

    if clause_conflict:
        # The adjudicator KNOWS the sources disagree about THIS fact (a
        # same-skeleton sentence carries different figures). That refusal
        # outranks every confirmation, including an exact restatement: a
        # source that both states and contradicts a claim proves nothing
        # either way.
        assert clause_outcome is not None
        checks.append(
            CheckResult(
                state="could_not_check",
                provenance="deterministic",
                detail=clause_outcome[1],
                subject=claim,
            )
        )
    elif any_altered and any_verified:
        checks.append(
            CheckResult(
                state="could_not_check",
                provenance="deterministic",
                detail=(
                    "the sources disagree about this claim (one statement matches, "
                    "another contradicts); refusing to pick a winner"
                ),
                subject=claim,
            )
        )
    elif any_altered:
        if altered_clause:
            assert clause_outcome is not None
            detail, subject = clause_outcome[1], claim
        else:
            assert altered_residue is not None
            detail, subject = altered_residue.detail, altered_residue.subject
        checks.append(
            CheckResult(state="altered", provenance="deterministic", detail=detail, subject=subject)
        )
    elif any_verified:
        if restated:
            detail = "a source states this claim verbatim"
        elif verified_clause:
            assert clause_outcome is not None
            detail = clause_outcome[1]
        else:
            assert verified_residue is not None
            detail = verified_residue.detail
        checks.append(
            CheckResult(state="verified", provenance="deterministic", detail=detail, subject=claim)
        )
    else:
        if clause_outcome is not None:
            detail = clause_outcome[1]
        elif claim_res:
            detail = (
                "the claim's quantities have no near-verbatim source statement to "
                "compare against; not confirmed and not accused"
            )
        else:
            detail = "no checkable anchor"
        checks.append(
            CheckResult(
                state="could_not_check", provenance="deterministic", detail=detail, subject=claim
            )
        )

    return attest(checks)


@dataclass(frozen=True)
class ClaimAttestation:
    claim: str
    attestation: Attestation


@dataclass(frozen=True)
class DraftAttestation:
    """A whole draft's attestation: one claim per sentence (the same unit the
    app's verify surface reasons about), plus the combined draft state under
    the kernel algebra: any altered claim marks the draft altered; a draft is
    verified only when EVERY claim verified; anything else is could_not_check."""

    state: str
    claims: tuple[ClaimAttestation, ...] = field(default_factory=tuple)
    schema_version: int = SCHEMA_VERSION


def attest_draft(draft: str, sources: list[SourceInput]) -> DraftAttestation:
    """Attest every statement in a draft (sentence-split exactly like the
    app's verify surface). An empty draft is honestly uncheckable."""
    sentences = split_sentences(draft)
    if not sentences:
        return DraftAttestation(state="could_not_check")
    claims = tuple(
        ClaimAttestation(claim=s, attestation=verify_claim(s, sources)) for s in sentences
    )
    # Draft-level state: reuse the combine algebra over one synthetic check
    # per claim so the precedence rules stay in ONE place.
    synthetic = [
        CheckResult(state=c.attestation.state, provenance="deterministic", subject=c.claim)
        for c in claims
    ]
    return DraftAttestation(state=combine(synthetic), claims=claims)
