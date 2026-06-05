"""Contract-claim verification (Cachet contract path, Phase 6).

Given one claim (a sentence from an AI-drafted summary of a contract) and a
candidate clause from the executed contract, decide deterministically (T0):

  - ``parametric_contradiction``: the claim's number / date / duration differs
    from the clause's same-type value. Pure arithmetic after regex extraction,
    no model. This is the gold case the litigator path cannot match.
  - ``present``: the claim's value or quoted language appears in the clause.
    This attests that the language appears, NEVER that the surrounding
    proposition is legally correct (a carve-out can change the meaning), so the
    detail tells the reader to review the full clause for context.
  - ``not_found``: the claim asserts a value or language the clause does not
    contain. The honest scope exit, never dressed as a clean pass.

No LLM, no network. Money and date compare exactly; duration compares within a
small tolerance so equivalent terms ("12 months" vs "1 year") are not flagged
as a contradiction by the day-count approximation.
"""

from __future__ import annotations

from dataclasses import dataclass

from services.legal.anchors import extract_anchors
from services.retrieval.validators import verbatim_run_present

_PARAMETRIC_TYPES = ("money", "date", "duration")
_DURATION_REL_TOLERANCE = 0.05


@dataclass(frozen=True)
class ClauseVerdict:
    disposition: str  # present | parametric_contradiction | not_found
    detail: str
    anchor_type: str | None = None
    claim_values: tuple = ()
    clause_values: tuple = ()


def _within_tolerance(a: float, b: float, rel: float = _DURATION_REL_TOLERANCE) -> bool:
    if a == b:
        return True
    hi = max(abs(a), abs(b)) or 1
    return abs(a - b) / hi <= rel


def _values_match(anchor_type: str, claim_values: list, clause_values: list) -> bool:
    # Known limitation: with multiple values of one type on either side, this
    # "any matches any" test can MASK a contradiction (a claim's $1M cap spuriously
    # matching a clause's unrelated $1M line item). Resolving it needs role
    # alignment (which claim value maps to which clause value), which is out of
    # scope; the demo uses single-value clauses where this is exact. Surfaced as a
    # coverage caveat (see demo/README honest scope), never a silent claim of full
    # coverage: a multi-value contract sentence is not fully checked.
    if anchor_type == "duration":
        return any(_within_tolerance(c, k) for c in claim_values for k in clause_values)
    return bool(set(claim_values) & set(clause_values))


def verify_claim_against_clause(claim: str, clause: str) -> ClauseVerdict:
    """Decide whether ``claim`` is supported, contradicted, or unfound vs ``clause``.

    The detail is filing-grade: it names the contract section and quotes the
    actual values ("The summary states $1,000,000; Section 8 states $500,000"),
    so the certification record stands on its own.
    """
    claim_anchors = extract_anchors(claim)
    clause_anchors = extract_anchors(clause)
    section = next((a.text for a in clause_anchors if a.type == "section"), None)
    where = section or "the contract"

    # Evaluate EVERY parametric type the claim carries, not just the first. A
    # contradiction in ANY type wins outright: a sentence with a matching amount but a
    # falsified date must read contradiction, not "present" (returning on the first
    # type that matched would mask the wrong date). Among non-contradictions, a
    # present finding beats a not_found.
    present_verdict: ClauseVerdict | None = None
    not_found_verdict: ClauseVerdict | None = None
    for anchor_type in _PARAMETRIC_TYPES:
        claim_hits = [
            a for a in claim_anchors if a.type == anchor_type and a.canonical_value is not None
        ]
        if not claim_hits:
            continue
        clause_hits = [
            a for a in clause_anchors if a.type == anchor_type and a.canonical_value is not None
        ]
        claim_values = tuple(a.canonical_value for a in claim_hits)
        clause_values = tuple(a.canonical_value for a in clause_hits)
        if not clause_hits:
            if not_found_verdict is None:
                not_found_verdict = ClauseVerdict(
                    "not_found",
                    f"The summary states {claim_hits[0].text}, which does not appear in the contract.",
                    anchor_type,
                    claim_values,
                    (),
                )
            continue
        if _values_match(anchor_type, list(claim_values), list(clause_values)):
            if present_verdict is None:
                present_verdict = ClauseVerdict(
                    "present",
                    f"{claim_hits[0].text} appears in {where}; review the full clause for context.",
                    anchor_type,
                    claim_values,
                    clause_values,
                )
            continue
        return ClauseVerdict(
            "parametric_contradiction",
            f"The summary states {claim_hits[0].text}; {where} states {clause_hits[0].text}.",
            anchor_type,
            claim_values,
            clause_values,
        )
    if present_verdict is not None:
        return present_verdict
    if not_found_verdict is not None:
        return not_found_verdict

    for anchor in claim_anchors:
        if anchor.type == "quote" and verbatim_run_present(anchor.text, clause):
            return ClauseVerdict(
                "present",
                f'The quoted language "{anchor.text}" appears verbatim in {where}; '
                "review the full clause for context.",
                "quote",
            )

    return ClauseVerdict("not_found", "The summary's language does not appear in the contract.")
