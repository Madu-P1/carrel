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

import re

from services.legal.anchors import (
    GRANT_NOUN_WORDS,
    POLARITY_VOCAB,
    extract_anchors,
    grant_noun_pattern,
    related_jurisdictions,
)
from services.retrieval.validators import verbatim_run_present

# percent compares by exact basis-point equality through the default
# set-intersection branch of _values_match (Decimal hashes by numeric value, so
# "0.5%" and "50 bps" intersect); governing_law compares normalized jurisdiction
# keys through the same branch (lexicon normalization makes "English law" and
# "laws of England and Wales" one key); duration alone keeps a tolerance.
# polarity is adjudicated PER STEM (a dedicated pass), because its values are
# heterogeneous across stems and a whole-type comparison would let a matching
# qualifier mask a flipped sibling.
_PARAMETRIC_TYPES = ("money", "percent", "date", "duration", "governing_law", "polarity")
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


# Function words, contract boilerplate, party roles, and cosmetic adjectives
# excluded when comparing the subject matter around a qualified grant noun
# ("license to use the SOFTWARE", "the TRADEMARK license"). Grant-noun and
# polarity vocabulary are excluded separately below.
_OBJECT_STOPWORDS = frozenset(
    {
        "this",
        "that",
        "these",
        "those",
        "with",
        "shall",
        "will",
        "under",
        "during",
        "herein",
        "hereunder",
        "hereto",
        "thereof",
        "thereto",
        "hereby",
        "pursuant",
        "term",
        "terms",
        "party",
        "parties",
        "granted",
        "grants",
        "receives",
        "section",
        "licensor",
        "licensee",
        "grantor",
        "grantee",
        "lessor",
        "lessee",
        "buyer",
        "seller",
        "vendor",
        "supplier",
        "customer",
        "client",
        "recipient",
        "worldwide",
        "perpetual",
        "limited",
        "personal",
        "sole",
        "global",
        "royalty",
        "free",
        "fully",
        "paid",
    }
)


def _noun_objects(text: str, noun_class: str) -> frozenset[str]:
    """Content words naming the subject matter around a grant noun.

    Bounded T0: for every surface form of the noun class, take the window up
    to the next [.;:,] after it AND back to the previous [.;:,] before it
    (max 60 chars each — "the TRADEMARK license" puts the subject matter
    pre-noun) and keep 4+ letter words minus boilerplate, qualifier
    vocabulary, and the grant nouns themselves. Empty means the side states
    no subject matter for this noun.
    """
    words: set[str] = set()
    for m in re.finditer(rf"\b(?:{grant_noun_pattern(noun_class)})\b", text, re.IGNORECASE):
        after = re.split(r"[.;:,]", text[m.end() : m.end() + 60], maxsplit=1)[0]
        before = re.split(r"[.;:,]", text[max(0, m.start() - 60) : m.start()])[-1]
        # The backward window stops at a granting verb so it reads the noun's
        # modifiers ("the TRADEMARK license"), never the sentence subject —
        # "The Company hereby grants an exclusive license" names a grantor,
        # not subject matter, and reading it suppressed real flips (round-3
        # note 2).
        before = re.split(
            r"\b(?:grants?|granted|granting|conveys?|issues?|provides?|"
            r"receives?|retains?|holds?|delivers?)\b",
            before,
            flags=re.IGNORECASE,
        )[-1]
        for window in (before, after):
            words.update(
                w
                for w in re.findall(r"[a-z]{4,}", window.lower())
                if w not in _OBJECT_STOPWORDS
                and w not in POLARITY_VOCAB
                and w not in GRANT_NOUN_WORDS
            )
    return frozenset(words)


def _polarity_pass(
    claim_hits: list, clause_hits: list, where: str, claim: str, clause: str
) -> tuple[ClauseVerdict | None, ClauseVerdict | None, ClauseVerdict | None, ClauseVerdict | None]:
    """Per-(stem, noun-class) polarity adjudication:
    (contradiction, multi, present, not_found).

    Each key ("exclusive:license", "binding:arbitration", ...) is its own
    comparison, and the verdict's anchor_type is key-qualified
    ("polarity:exclusive:license") so the cross-clause adjudicator's same-type
    rules also operate per key — an exclusive REMEDY can never confirm or veto
    a claim about an exclusive LICENSE. A flip on any key is a contradiction
    even when a sibling key matches; one key carrying both signs on a side
    refuses; a key the clause never qualifies is an honest not_found.

    Subject-matter gate (round-2 hardening): the two qualifiers may describe
    different grants that are simultaneously true (an exclusive Software
    license beside a non-exclusive Documentation license), and comparing them
    in either direction would manufacture certainty. The pair refuses when
    the sides' stated subject matter cannot be matched:

    - ASYMMETRY: one side names subject matter and the other is bare. "The
      license is exclusive" cannot be aligned to "a non-exclusive license to
      the source code" — which license is unknowable deterministically.
    - MUTUAL DIFFERENCE: each side carries a content word the other lacks
      ("Product source code" vs "Product user manual" — a shared generic
      word does not make them the same grant).

    Both bare, equal, or one-a-subset-of-the-other still compares: verbose
    restatement of the same subject matter keeps the catch.
    """

    def by_key(hits: list) -> dict[str, list]:
        grouped: dict[str, list] = {}
        for a in hits:
            grouped.setdefault(str(a.canonical_value)[:-1], []).append(a)
        return grouped

    claim_keys = by_key(claim_hits)
    clause_keys = by_key(clause_hits)
    contradiction = multi = present = not_found = None
    for key, c_hits in claim_keys.items():
        k_hits = clause_keys.get(key, [])
        qualified = f"polarity:{key}"
        stem, noun = key.split(":", 1)
        c_vals = tuple(dict.fromkeys(a.canonical_value for a in c_hits))
        k_vals = tuple(dict.fromkeys(a.canonical_value for a in k_hits))
        if not k_hits:
            if not_found is None:
                not_found = ClauseVerdict(
                    "not_found",
                    f"The summary states {c_hits[0].text}, which the deterministic check "
                    "could not locate in your loaded sources.",
                    qualified,
                    c_vals,
                    (),
                )
            continue
        if len(c_vals) > 1 or len(k_vals) > 1:
            if multi is None:
                multi = ClauseVerdict(
                    "multi_value_unverifiable",
                    (
                        f"The summary and {where} carry {stem} qualifiers that cannot be "
                        "aligned one-to-one deterministically, so this sentence was not "
                        "independently checked."
                    ),
                    qualified,
                    c_vals,
                    k_vals,
                )
            continue
        claim_objects = _noun_objects(claim, noun)
        clause_objects = _noun_objects(clause, noun)
        asymmetric = bool(claim_objects) != bool(clause_objects)
        mutually_different = bool(claim_objects - clause_objects) and bool(
            clause_objects - claim_objects
        )
        if asymmetric or mutually_different:
            if multi is None:
                multi = ClauseVerdict(
                    "multi_value_unverifiable",
                    (
                        f"The summary and {where} qualify a {noun} whose subject matter "
                        f"cannot be matched deterministically, so the {stem} qualifiers "
                        "were not independently checked."
                    ),
                    qualified,
                    c_vals,
                    k_vals,
                )
            continue
        if c_vals[0] == k_vals[0]:
            if present is None:
                present = ClauseVerdict(
                    "present",
                    f"{c_hits[0].text} appears in {where}; review the full passage for context.",
                    qualified,
                    c_vals,
                    k_vals,
                    claim_span=c_hits[0].text,
                    clause_span=k_hits[0].text,
                    where=where,
                )
            continue
        contradiction = ClauseVerdict(
            "parametric_contradiction",
            f"The summary states {c_hits[0].text}; {where} states {k_hits[0].text}.",
            qualified,
            c_vals,
            k_vals,
            claim_span=c_hits[0].text,
            clause_span=k_hits[0].text,
            where=where,
        )
        break
    return contradiction, multi, present, not_found


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
        if anchor_type == "polarity":
            contradiction, p_multi, p_present, p_not_found = _polarity_pass(
                claim_hits, clause_hits, where, claim, clause
            )
            if contradiction is not None:
                return contradiction
            multi_value_verdict = multi_value_verdict or p_multi
            present_verdict = present_verdict or p_present
            not_found_verdict = not_found_verdict or p_not_found
            continue
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
