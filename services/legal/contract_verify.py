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

from dataclasses import dataclass

from services.legal.anchors import extract_anchors, related_jurisdictions
from services.retrieval.validators import verbatim_run_present

# percent compares by exact basis-point equality through the default
# set-intersection branch of _values_match (Decimal hashes by numeric value, so
# "0.5%" and "50 bps" intersect); governing_law compares normalized jurisdiction
# keys through the same branch (lexicon normalization makes "English law" and
# "laws of England and Wales" one key); duration alone keeps a tolerance.
_PARAMETRIC_TYPES = ("money", "percent", "date", "duration", "governing_law")
_DURATION_REL_TOLERANCE = 0.05


@dataclass(frozen=True)
class ClauseVerdict:
    # present | parametric_contradiction | multi_value_unverifiable |
    # conflicting_clauses | not_found
    disposition: str
    detail: str
    anchor_type: str | None = None
    claim_values: tuple = ()
    clause_values: tuple = ()
    # The matched anchor spans (claim side / clause side) and the clause's own
    # "where" phrase, carried so the cross-clause adjudicator can compose a
    # filing-grade conflict detail naming both clauses without string surgery.
    # Server-internal (the contract_verdict never serializes to the wire).
    claim_span: str | None = None
    clause_span: str | None = None
    where: str | None = None


@dataclass(frozen=True)
class ClauseCandidate:
    """One retrieved clause's verdict, in retrieval-rank order, for the
    cross-clause adjudicator. ``on_topic`` is the C3 relevance gate's answer
    for present-shaped candidates (True for everything else)."""

    verdict: ClauseVerdict
    section: str | None
    clause_text: str | None
    on_topic: bool


def _within_tolerance(a: float, b: float, rel: float = _DURATION_REL_TOLERANCE) -> bool:
    if a == b:
        return True
    hi = max(abs(a), abs(b)) or 1
    return abs(a - b) / hi <= rel


def _values_match(anchor_type: str, claim_values: list, clause_values: list) -> bool:
    # Invoked only on SINGLE-value pairs (one value per side): the caller routes any
    # multi-value type to multi_value_unverifiable, because "any matches any" cannot
    # align multiple values and would mask a contradiction (a claim's $1M cap spuriously
    # matching a clause's unrelated $1M line item). On a single pair the intersection
    # test below is exact equality; duration keeps a small tolerance so equivalent terms
    # ("12 months" vs "1 year") are not flagged as a contradiction.
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
    # Singular on purpose: the fallback feeds "{where} states {value}" below.
    where = section or "the loaded source"

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
        # Equal canonicals collapse to one fact: "0.5% (50 bps)" is a single
        # rate written twice, not two values needing alignment. Only genuinely
        # different values trigger the multi-value refusal below.
        claim_values = tuple(dict.fromkeys(a.canonical_value for a in claim_hits))
        clause_values = tuple(dict.fromkeys(a.canonical_value for a in clause_hits))
        if not clause_hits:
            if not_found_verdict is None:
                not_found_verdict = ClauseVerdict(
                    "not_found",
                    f"The summary states {claim_hits[0].text}, which the deterministic check "
                    "could not locate in your loaded sources.",
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
        if anchor_type == "governing_law" and related_jurisdictions(
            claim_values[0], clause_values[0]
        ):
            # A container/member pair (UAE vs DIFC, United States vs Delaware):
            # the values differ but one jurisdiction sits inside the other, so a
            # flat comparison can neither confirm nor accuse. Routed to the
            # honest could-not-check as an alignment refusal (ADR-0012
            # invariant 2); sibling mismatches still contradict below.
            if multi_value_verdict is None:
                multi_value_verdict = ClauseVerdict(
                    "multi_value_unverifiable",
                    (
                        f"The summary states {claim_hits[0].text} and {where} states "
                        f"{clause_hits[0].text}: one jurisdiction contains the other, "
                        "which a flat deterministic comparison cannot adjudicate, so "
                        "this sentence was not independently checked."
                    ),
                    anchor_type,
                    claim_values,
                    clause_values,
                )
            continue
        if _values_match(anchor_type, list(claim_values), list(clause_values)):
            if present_verdict is None:
                present_verdict = ClauseVerdict(
                    "present",
                    f"{claim_hits[0].text} appears in {where}; review the full passage for context.",
                    anchor_type,
                    claim_values,
                    clause_values,
                    claim_span=claim_hits[0].text,
                    clause_span=clause_hits[0].text,
                    where=where,
                )
            continue
        return ClauseVerdict(
            "parametric_contradiction",
            f"The summary states {claim_hits[0].text}; {where} states {clause_hits[0].text}.",
            anchor_type,
            claim_values,
            clause_values,
            claim_span=claim_hits[0].text,
            clause_span=clause_hits[0].text,
            where=where,
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


def adjudicate_clause_candidates(
    candidates: list[ClauseCandidate],
) -> tuple[ClauseVerdict, str | None, str | None]:
    """Adjudicate one claim across ALL retrieved clauses (topicality decision,
    docs/notes/2026-06-10-cachet-contradiction-topicality.md).

    Returns ``(verdict, section, clause_text)`` for the claim card. The rules,
    in precedence order:

    1. A contradiction stands only when NO retrieved clause carries the claim's
       value for that anchor type. A same-type present anywhere — on-topic or
       not — means the value is verbatim in the contract, so accusing from a
       different clause would be a guess: the engine REFUSES with both clauses
       named (``conflicting_clauses``, mapped to the could-not-check card).
       Certainty is manufactured in neither direction (ADR-0012 invariant 2);
       present-wins was rejected because a value coincidence would paint a
       green over an amended-contract conflict, the worst failure class.
    2. An uncontested contradiction wins, first by retrieval rank. Topicality
       never gates it: a falsified value LOWERS overlap with its true clause,
       so a relevance gate would suppress exactly the true catches.
    3. Otherwise the first ON-topic present wins (C3 unchanged: an off-topic
       value coincidence never earns a green).
    4. Otherwise the first multi-value refusal, then not_found.
    """
    presents_by_type: dict[str | None, ClauseCandidate] = {}
    on_topic_presents: list[ClauseCandidate] = []
    contradictions: list[ClauseCandidate] = []
    multi_value: ClauseCandidate | None = None
    for cand in candidates:
        disposition = cand.verdict.disposition
        if disposition == "present":
            presents_by_type.setdefault(cand.verdict.anchor_type, cand)
            if cand.on_topic or cand.verdict.anchor_type == "quote":
                on_topic_presents.append(cand)
        elif disposition == "parametric_contradiction":
            contradictions.append(cand)
        elif disposition == "multi_value_unverifiable" and multi_value is None:
            multi_value = cand

    first_conflict: tuple[ClauseCandidate, ClauseCandidate] | None = None
    for contra in contradictions:
        present = presents_by_type.get(contra.verdict.anchor_type)
        if present is None:
            return contra.verdict, contra.section, contra.clause_text
        if first_conflict is None:
            first_conflict = (contra, present)
    if first_conflict is not None:
        contra, present = first_conflict
        where_p = present.verdict.where or "one retrieved clause"
        where_c = contra.verdict.where or "another retrieved clause"
        if where_p == where_c:
            where_p, where_c = "one retrieved clause", "another retrieved clause"
        claim_span = contra.verdict.claim_span or "this value"
        clause_span = contra.verdict.clause_span or "a different value"
        conflict = ClauseVerdict(
            "conflicting_clauses",
            (
                f"The summary states {claim_span}; {where_p} carries that value, but "
                f"{where_c} states {clause_span}. The retrieved clauses conflict, so this "
                "statement was not independently checked. Review both clauses."
            ),
            contra.verdict.anchor_type,
            contra.verdict.claim_values,
            tuple(present.verdict.clause_values) + tuple(contra.verdict.clause_values),
            claim_span=contra.verdict.claim_span,
            clause_span=contra.verdict.clause_span,
        )
        # Carry the PRESENT clause's location: it is where the claim's value
        # verifiably lives, so the quote pool and the card's section point at
        # real matching text rather than the accusing clause.
        return conflict, present.section, present.clause_text
    if on_topic_presents:
        chosen = on_topic_presents[0]
        return chosen.verdict, chosen.section, chosen.clause_text
    if multi_value is not None:
        return multi_value.verdict, multi_value.section, multi_value.clause_text
    return (
        ClauseVerdict("not_found", "no matching passage found in your loaded sources"),
        None,
        None,
    )
