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
    if anchor_type == "duration":
        return any(_within_tolerance(c, k) for c in claim_values for k in clause_values)
    return bool(set(claim_values) & set(clause_values))


def verify_claim_against_clause(claim: str, clause: str) -> ClauseVerdict:
    """Decide whether ``claim`` is supported, contradicted, or unfound vs ``clause``."""
    claim_anchors = extract_anchors(claim)
    clause_anchors = extract_anchors(clause)

    for anchor_type in _PARAMETRIC_TYPES:
        claim_values = [
            a.canonical_value
            for a in claim_anchors
            if a.type == anchor_type and a.canonical_value is not None
        ]
        if not claim_values:
            continue
        clause_values = [
            a.canonical_value
            for a in clause_anchors
            if a.type == anchor_type and a.canonical_value is not None
        ]
        if not clause_values:
            return ClauseVerdict(
                "not_found",
                f"the claim states a {anchor_type} value the clause does not contain",
                anchor_type,
                tuple(claim_values),
                (),
            )
        if _values_match(anchor_type, claim_values, clause_values):
            return ClauseVerdict(
                "present",
                f"the {anchor_type} value appears in the clause; review the full clause for context",
                anchor_type,
                tuple(claim_values),
                tuple(clause_values),
            )
        return ClauseVerdict(
            "parametric_contradiction",
            f"the claim's {anchor_type} value contradicts the clause",
            anchor_type,
            tuple(claim_values),
            tuple(clause_values),
        )

    for anchor in claim_anchors:
        if anchor.type == "quote" and verbatim_run_present(anchor.text, clause):
            return ClauseVerdict(
                "present",
                "the quoted language appears verbatim in the clause; review the full clause for context",
                "quote",
            )

    return ClauseVerdict("not_found", "the claim's language does not appear in the clause")
