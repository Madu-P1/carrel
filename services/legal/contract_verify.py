"""Contract-claim verification (Cachet contract path, Phase 6).

Given one claim (a sentence from an AI-drafted summary of a contract) and a
candidate clause from the executed contract, decide deterministically (T0):

  - ``parametric_contradiction``: the claim's number / date / duration differs
    from the clause's same-type value. Pure arithmetic after regex extraction,
    no model. This is the gold case the litigator path cannot match.
  - ``present``: the claim's value or quoted language appears in the clause.
    This attests that the language appears, NEVER that the surrounding
    proposition is legally correct (a carve-out can change the meaning), so the
    detail tells the reader to review the full passage for context.
  - ``multi_value_unverifiable``: the claim and the clause each carry more than
    one value of the same type, so a deterministic check cannot align them
    one-to-one. Routed to the could-not-check tray instead of guessing: a guessed
    match would MASK a contradiction and a guessed miss would be a false
    accusation (ADR-0012 invariant 2). Role-aligned multi-value checking is T1.
  - ``not_found``: the claim asserts a value or language the clause does not
    contain. The honest scope exit, never dressed as a clean pass.

No LLM, no network. Money and date compare exactly; duration compares within a
small tolerance so equivalent terms ("12 months" vs "1 year") are not flagged
as a contradiction by the day-count approximation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from services.legal.anchors import Anchor, extract_anchors
from services.retrieval.validators import verbatim_run_present

_PARAMETRIC_TYPES = ("money", "date", "duration")
_DURATION_REL_TOLERANCE = 0.05
_DURATION_UNIT = re.compile(r"\b(year|month|week|day)s?\b", re.IGNORECASE)


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


def _duration_unit(text: str) -> str | None:
    m = _DURATION_UNIT.search(text)
    return m.group(1).lower() if m else None


def _durations_match(claim_anchor: Anchor, clause_anchor: Anchor) -> bool:
    """Whether two single duration anchors agree.

    The 5% tolerance exists ONLY to bridge the day-count approximation across
    units (12 months canonicalizes to 360 days, 1 year to 365; the terms are
    the same). Within one unit there is no approximation to bridge, so the
    compare is exact: 23 months vs 24 months is a different term, not a
    rounding artifact, and a 360 vs 365 days basis is a real financial
    difference. An anchor whose unit cannot be re-derived (should not happen;
    the detector requires the unit word) falls back to the tolerant compare,
    the lenient pre-existing behavior.
    """
    claim_unit = _duration_unit(claim_anchor.text)
    clause_unit = _duration_unit(clause_anchor.text)
    if claim_unit is not None and claim_unit == clause_unit:
        return claim_anchor.canonical_value == clause_anchor.canonical_value
    return _within_tolerance(
        float(claim_anchor.canonical_value), float(clause_anchor.canonical_value)
    )


def _values_match(claim_values: list, clause_values: list) -> bool:
    # Invoked only on SINGLE-value pairs (one value per side): the caller routes any
    # multi-value type to multi_value_unverifiable, because "any matches any" cannot
    # align multiple values and would mask a contradiction (a claim's $1M cap spuriously
    # matching a clause's unrelated $1M line item). On a single pair the intersection
    # test is exact equality. Durations are compared by the caller via
    # `_durations_match` (unit-aware); this helper covers money and date.
    return bool(set(claim_values) & set(clause_values))


def _normalized_anchor_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _present_detail(claim_anchor: Anchor, clause_anchor: Anchor, where: str) -> str:
    """A literally-true detail line for a parametric present.

    Three forms, because the certification record stands on its own and must
    never assert text the clause does not contain:
      - identical written forms: "X appears in Section 8"
      - same value, different written form: "the summary's X matches Y in ..."
      - tolerant cross-unit duration: "the summary's X is consistent with Y in ..."
    """
    if _normalized_anchor_text(claim_anchor.text) == _normalized_anchor_text(clause_anchor.text):
        return f"{claim_anchor.text} appears in {where}; review the full passage for context."
    if claim_anchor.canonical_value == clause_anchor.canonical_value:
        return (
            f"The summary's {claim_anchor.text} matches {clause_anchor.text} in {where}; "
            "review the full passage for context."
        )
    return (
        f"The summary's {claim_anchor.text} is consistent with {clause_anchor.text} in {where}; "
        "review the full passage for context."
    )


def verify_claim_against_clause(claim: str, clause: str) -> ClauseVerdict:
    """Decide whether ``claim`` is supported, contradicted, or unfound vs ``clause``.

    The detail is filing-grade: it names the contract section and quotes the
    actual values ("The summary states $1,000,000; Section 8 states $500,000"),
    so the certification record stands on its own.
    """
    claim_anchors = extract_anchors(claim)
    clause_anchors = extract_anchors(clause)
    section = next((a.text for a in clause_anchors if a.type == "section"), None)
    where = section or "your loaded sources"

    # Evaluate EVERY parametric type the claim carries, not just the first. A
    # contradiction in ANY type wins outright: a sentence with a matching amount but a
    # falsified date must read contradiction, not "present" (returning on the first
    # type that matched would mask the wrong date). Among non-contradictions, a
    # present finding beats a not_found.
    present_verdict: ClauseVerdict | None = None
    not_found_verdict: ClauseVerdict | None = None
    multi_value_verdict: ClauseVerdict | None = None
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
                    f"The summary states {claim_hits[0].text}, which does not appear in your loaded sources.",
                    anchor_type,
                    claim_values,
                    (),
                )
            continue
        if len(claim_values) > 1 or len(clause_values) > 1:
            # Multiple values of this type on a side: a deterministic clause-level check
            # cannot say WHICH claim value maps to WHICH clause value. The old
            # "any matches any" test could MASK a real contradiction (a claim's $1M cap
            # spuriously matching a clause's unrelated $1M line) or, on a clean miss, name
            # a guessed first-value contradiction (a false accusation). Neither is honest,
            # so route to the could-not-check tray (ADR-0012 invariant 2: below-confidence
            # is never a guessed verdict). Role-aligned multi-value checking is T1 work.
            if multi_value_verdict is None:
                multi_value_verdict = ClauseVerdict(
                    "multi_value_unverifiable",
                    (
                        f"The {anchor_type} values in the summary and {where} cannot be aligned "
                        "one-to-one deterministically, so this sentence was not independently checked."
                    ),
                    anchor_type,
                    claim_values,
                    clause_values,
                )
            continue
        if anchor_type == "duration":
            matched = _durations_match(claim_hits[0], clause_hits[0])
        else:
            matched = _values_match(list(claim_values), list(clause_values))
        if matched:
            if present_verdict is None:
                present_verdict = ClauseVerdict(
                    "present",
                    _present_detail(claim_hits[0], clause_hits[0], where),
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
    # Precedence: a single-value contradiction already returned outright above. Among the
    # rest, an honest could-not-check (a type carried multiple values we could not align)
    # outranks a present, because a sentence is not "present" if any checkable part of it
    # went unaligned; a present in turn outranks a bare not_found.
    if multi_value_verdict is not None:
        return multi_value_verdict
    if present_verdict is not None:
        return present_verdict
    if not_found_verdict is not None:
        return not_found_verdict

    for anchor in claim_anchors:
        if anchor.type == "quote" and verbatim_run_present(anchor.text, clause):
            return ClauseVerdict(
                "present",
                f'The quoted language "{anchor.text}" appears verbatim in {where}; '
                "review the full passage for context.",
                "quote",
            )

    return ClauseVerdict(
        "not_found", "The summary's language does not appear in your loaded sources."
    )
