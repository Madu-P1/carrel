"""Strangler-fig adapter: the hardened engine behind the frozen contract.

This is ADR-0014's extraction seam. Today it maps ``services.legal``'s
dispositions into the kernel's three-state contract; when the extraction
completes, the engine's internals move INSIDE this package and this module
dissolves. Surfaces and the daemon depend only on ``verify_claim`` -- never on
``services.legal`` directly -- so the migration never breaks an embedder.

Adjudication here is deliberately CONSERVATIVE relative to the app's richer
cross-clause adjudicator (which carries topicality, subject binding, and
conflict rules). Where evidence across sources disagrees, this seam refuses;
it never averages. The richer adjudicator is swallowed at extraction step 2.
"""

from __future__ import annotations

from services.legal.contract_verify import verify_claim_against_clause
from services.legal.quote_check import check_quote_against_sources, extract_draft_quotes

from .contract import Attestation, CheckResult, attest

_CLAUSE_STATE = {
    "parametric_contradiction": "altered",
    "present": "verified",
    "not_found": "could_not_check",
    "multi_value_unverifiable": "could_not_check",
    "conflicting_clauses": "could_not_check",
}


def verify_claim(claim: str, sources: list[str]) -> Attestation:
    """Attest one claim against raw source texts. Pure, no I/O, no network.

    Every quoted span in the claim is checked verbatim against the whole
    source pool; the claim's parametric anchors (money, percent, duration,
    magnitude, date) are checked clause-by-clause. Cross-source disagreement
    on the clause path (one source contradicts, another confirms) refuses
    rather than picking a winner -- the engine surfaces disagreements, never
    adjudicates them silently.
    """
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

    clause_states: list[str] = []
    clause_details: list[str] = []
    for source in sources:
        verdict = verify_claim_against_clause(claim, source)
        clause_states.append(_CLAUSE_STATE.get(verdict.disposition, "could_not_check"))
        clause_details.append(verdict.detail)
    if clause_states:
        if "altered" in clause_states and "verified" in clause_states:
            # Conflicting evidence across sources: refuse, name the conflict.
            checks.append(
                CheckResult(
                    state="could_not_check",
                    provenance="deterministic",
                    detail="sources disagree about this claim; refusing to pick a winner",
                    subject=claim,
                )
            )
        elif "altered" in clause_states:
            i = clause_states.index("altered")
            checks.append(
                CheckResult(
                    state="altered",
                    provenance="deterministic",
                    detail=clause_details[i],
                    subject=claim,
                )
            )
        elif "verified" in clause_states:
            i = clause_states.index("verified")
            checks.append(
                CheckResult(
                    state="verified",
                    provenance="deterministic",
                    detail=clause_details[i],
                    subject=claim,
                )
            )
        else:
            checks.append(
                CheckResult(
                    state="could_not_check",
                    provenance="deterministic",
                    detail=clause_details[0] if clause_details else "no checkable anchor",
                    subject=claim,
                )
            )

    return attest(checks)
