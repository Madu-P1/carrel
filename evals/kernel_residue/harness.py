"""Harness for the kernel-residue parity experiment (ADR-0015, trigger #3).

Every case is a (claim, source) pair from a NON-legal domain, shaped like the
AI-fabrication classes the engine already catches in legal work: a near-verbatim
sentence with one drifted figure, a faithful restatement, a quote with invented
words, or an uncheckable semantic claim. Cases run through the two pure kernel
entry points -- ``verify_claim_against_clause`` and
``check_quote_against_sources`` -- with NO legal pack in play (no citations, no
caselaw corpus, no holding checks).

Outcome classes (the honest-verdict algebra, collapsed for scoring):
  - flagged    -- the kernel confidently named an alteration
  - supported  -- the kernel confidently confirmed the claim against the source
  - refused    -- the kernel declined to rule (not_found / multi-value /
                  unplaceable): the honest could-not-check

Invariants the experiment asserts (the honesty floor, non-negotiable):
  - an ALTERED case must never come back "supported"  (no false green)
  - a FAITHFUL case must never come back "flagged"    (no false accusation)

The catch rate on altered cases is the number the council asked for.
"""

from __future__ import annotations

from dataclasses import dataclass

from cachet_verify.adapter import verify_claim


@dataclass(frozen=True)
class Case:
    """One parity case. ``kind`` is "clause" (claim vs source clause) or
    "quote" (quoted span vs source pool). ``truth`` is the ground truth about
    the claim itself: "altered", "faithful", or "uncheckable" (nothing a
    deterministic source-grounded engine could rule on). ``note`` says what the
    case probes."""

    id: str
    domain: str
    kind: str
    truth: str
    claim: str
    source: str
    note: str


@dataclass(frozen=True)
class CaseResult:
    case: Case
    outcome: str  # flagged | supported | refused
    raw: str  # the engine's own disposition/status string
    detail: str


# The kernel's own vocabulary, collapsed for scoring. Since batch A the
# harness runs THE KERNEL (cachet_verify.adapter.verify_claim), not the raw
# legal-engine functions: the parity number now measures exactly the artifact
# ADR-0015 ships.
_STATE_OUTCOME = {
    "altered": "flagged",
    "verified": "supported",
    "could_not_check": "refused",
}


def run_case(case: Case) -> CaseResult:
    attestation = verify_claim(case.claim, [case.source])
    outcome = _STATE_OUTCOME[attestation.state]
    detail = "; ".join(
        c.detail for c in attestation.checks if c.state == attestation.state
    ) or "; ".join(c.detail for c in attestation.checks)
    return CaseResult(case, outcome, attestation.state, detail)


@dataclass(frozen=True)
class ParitySummary:
    results: tuple[CaseResult, ...]
    altered_total: int
    altered_flagged: int
    false_greens: tuple[CaseResult, ...]
    false_accusations: tuple[CaseResult, ...]
    faithful_supported: int
    faithful_total: int
    uncheckable_refused: int
    uncheckable_total: int

    @property
    def catch_rate(self) -> float:
        return self.altered_flagged / self.altered_total if self.altered_total else 0.0


def evaluate(cases: list[Case]) -> ParitySummary:
    results = tuple(run_case(c) for c in cases)
    altered = [r for r in results if r.case.truth == "altered"]
    faithful = [r for r in results if r.case.truth == "faithful"]
    uncheckable = [r for r in results if r.case.truth == "uncheckable"]
    return ParitySummary(
        results=results,
        altered_total=len(altered),
        altered_flagged=sum(1 for r in altered if r.outcome == "flagged"),
        false_greens=tuple(r for r in altered if r.outcome == "supported"),
        false_accusations=tuple(r for r in faithful if r.outcome == "flagged"),
        faithful_supported=sum(1 for r in faithful if r.outcome == "supported"),
        faithful_total=len(faithful),
        uncheckable_refused=sum(1 for r in uncheckable if r.outcome == "refused"),
        uncheckable_total=len(uncheckable),
    )
