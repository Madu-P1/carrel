"""Strangler-fig adapter: the hardened engine behind the frozen contract.

This is ADR-0014's extraction seam. It maps ``services.legal``'s dispositions
into the kernel's three-state contract and layers the kernel's OWN residue
detectors (dosages, physical-unit quantities, grouped counts) on top; when the
extraction completes, the engine's internals move INSIDE this package and this
module dissolves. Surfaces and the daemon depend only on ``verify_claim`` --
never on ``services.legal`` directly -- so the migration never breaks an
embedder.

Adjudication discipline: where evidence disagrees (across sources, or between
a verbatim restatement and a contradicting sentence), this seam refuses and
names the conflict; it never averages and never picks a winner. Abstention
handling: a leg only participates when the claim actually carries content that
leg can check, so a pure-quote claim is decided by its quote checks alone and
a claim with no checkable content gets one honest refusal.
"""

from __future__ import annotations

from services.legal.anchors import extract_anchors
from services.legal.contract_verify import verify_claim_against_clause
from services.legal.quote_check import check_quote_against_sources, extract_draft_quotes
from services.legal.sentences import split_sentences

from .contract import Attestation, CheckResult, attest
from .residue import ResidueComparison, compare_residue, extract_residue_anchors

_CLAUSE_STATE = {
    "parametric_contradiction": "altered",
    "present": "verified",
    "not_found": "could_not_check",
    "multi_value_unverifiable": "could_not_check",
    "conflicting_clauses": "could_not_check",
}


def _normalize(text: str) -> str:
    return " ".join(text.split()).strip().lower()


def _quote_checks(claim: str, sources: list[str]) -> list[CheckResult]:
    checks: list[CheckResult] = []
    for quote in extract_draft_quotes(claim):
        result = check_quote_against_sources(quote, list(sources))
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


def verify_claim(claim: str, sources: list[str]) -> Attestation:
    """Attest one claim against raw source texts. Pure, no I/O, no network.

    Three legs, each participating only when the claim carries its content:

    - quotes: every quoted span checked verbatim against the whole pool;
    - clause (legal engine): the claim's parametric anchors (money, percent,
      duration, magnitude, date) against each source;
    - residue (kernel-owned): dosage / physical-unit / count anchors compared
      per source SENTENCE under the near-copy accusation gate, plus the
      exact-restatement confirmation (a source sentence identical to the
      claim confirms it outright).
    """
    checks: list[CheckResult] = list(_quote_checks(claim, sources))

    claim_serv = extract_anchors(claim)
    serv_spans = [(a.start, a.end) for a in claim_serv]
    claim_res = extract_residue_anchors(claim, claimed_spans=serv_spans)
    res_spans = [(a.start, a.end) for a in claim_res]
    claim_all_spans = serv_spans + res_spans
    norm_claim = _normalize(claim)

    has_content = bool(claim_serv) or bool(claim_res)

    if not has_content:
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

    if not sources:
        checks.append(
            CheckResult(
                state="could_not_check",
                provenance="deterministic",
                detail="no sources were provided to check this claim against",
                subject=claim,
            )
        )
        return attest(checks)

    clause_states: list[str] = []
    clause_details: list[str] = []
    residue_outcomes: list[ResidueComparison] = []
    restated = False

    for source in sources:
        if claim_serv:
            verdict = verify_claim_against_clause(claim, source)
            clause_states.append(_CLAUSE_STATE.get(verdict.disposition, "could_not_check"))
            clause_details.append(verdict.detail)
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

    altered_clause = "altered" in clause_states
    verified_clause = "verified" in clause_states
    altered_residue = next((o for o in residue_outcomes if o.state == "altered"), None)
    verified_residue = next((o for o in residue_outcomes if o.state == "verified"), None)

    any_altered = altered_clause or altered_residue is not None
    any_verified = restated or verified_clause or verified_residue is not None

    if any_altered and any_verified:
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
            detail = clause_details[clause_states.index("altered")]
            subject = claim
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
            detail = clause_details[clause_states.index("verified")]
        else:
            assert verified_residue is not None
            detail = verified_residue.detail
        checks.append(
            CheckResult(state="verified", provenance="deterministic", detail=detail, subject=claim)
        )
    else:
        if clause_details:
            detail = clause_details[0]
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
