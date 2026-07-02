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

import re
from collections.abc import Sequence
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

# The clause + residue legs each compare the claim against every source
# SENTENCE, so a single verify_claim costs O(source_sentences); attest_draft
# multiplies that by the draft's sentence count. The relevance prefilter blunts
# this on unrelated prose but NOT on a near-copy document (every sentence shares
# vocabulary), so a large record wedges the synchronous worker (mythos
# final-sweep, high: ~150s at 100x100 sentences). This is a hard ceiling on the
# work a single attestation may attempt: past it the engine REFUSES
# (could_not_check) rather than block, because a silent multi-minute stall on a
# trust surface is worse than an honest "too large, split it". A per-request
# sentence cache would raise this ceiling; that is recorded debt, not done here.
_MAX_SENTENCE_PAIRS = 20_000


def _too_large(claim_sentence_count: int, source_sentence_count: int) -> bool:
    return claim_sentence_count * source_sentence_count > _MAX_SENTENCE_PAIRS


def _oversize_refusal(claim: str) -> CheckResult:
    return CheckResult(
        state="could_not_check",
        provenance="deterministic",
        detail=(
            "the draft and sources are too large to attest deterministically in "
            "bounded time; split them into smaller sections and attest each"
        ),
        subject=claim,
    )


def _normalize(text: str) -> str:
    return " ".join(text.split()).strip().lower()


def _coerce_sources(sources: Sequence[SourceInput]) -> list[SourceText]:
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


def _sentence_relevant(claim_tokens: frozenset[str], sentence: str) -> bool:
    """Cheap prefilter for the per-sentence engine fan-out (the O(N*M) cost).

    A sentence with NO shared fact vocabulary AND NO digit can contribute
    nothing the pipeline keeps: it cannot carry the claim's value (values are
    digit-bearing), and any contradiction it produced would be zero-overlap
    cross-fact noise the filter discards anyway. Digit-bearing sentences are
    ALWAYS kept, whatever their vocabulary, so a value carrier with different
    surface wording ("$5,000,000" for "$5 million") still reaches the
    adjudicator's rule-1 conservatism (mythos batchE-20260702, perf).
    """
    if any(ch.isdigit() for ch in sentence):
        return True
    return bool(claim_tokens & _content_tokens(sentence))


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
    claim_tokens = _content_tokens(claim)
    for source in source_texts:
        for sentence in split_sentences(source):
            if not _sentence_relevant(claim_tokens, sentence):
                continue
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
    # Cross-fact noise gate (mythos batchD, floor): a parametric_contradiction
    # from a sentence sharing ZERO fact vocabulary with the claim is a
    # different fact that happens to carry a different figure ("break fee
    # $3M" vs "marketing budget $7M"). Left in, it either falsely accuses
    # (when it is the only candidate) or supplies a wrong-clause detail on a
    # true accusation. Presents / multi-value / not_found candidates all stay:
    # the carrier logic (rule 1) must keep seeing every sentence.
    filtered = [
        cand
        for cand in candidates
        if not (
            cand.verdict.disposition == "parametric_contradiction"
            and claim_tokens
            and not (claim_tokens & _content_tokens(cand.clause_text or ""))
        )
    ]
    verdict, _section, _clause = adjudicate_clause_candidates(filtered or candidates)
    if not filtered:
        # Every candidate was cross-fact contradiction noise: nothing on this
        # fact exists in the sources, so the honest verdict is a refusal, and
        # the adjudicator never sees a candidate set that can accuse.
        return (
            "could_not_check",
            "the sources carry different figures, but none concern this claim's "
            "subject; nothing on this fact could be checked",
            "not_found",
        )
    return (
        _CLAUSE_STATE.get(verdict.disposition, "could_not_check"),
        verdict.detail,
        verdict.disposition,
    )


# Function words + verbs of stating that carry no fact identity: shared
# occurrences of these must not make two sentences "the same fact".
_TOPIC_STOPWORDS = frozenset(
    """a an and are as at be been by for from in is it its no not notwithstanding
    of on or per shall should that the this to under was were will with within
    would foregoing applicable total totals totaled totalling amount amounts
    pay payable paid states stated stating
    million billion trillion thousand hundred mln bln mn bn mld
    dollar dollars euro euros usd eur gbp pound percent percentage
    day days week weeks month months year years annual annually""".split()
)


def _content_tokens(text: str) -> frozenset[str]:
    """Fact-identity tokens: lowercase alphabetic words minus function words,
    minus digits (figures are compared by the anchor machinery, not here)."""
    words = re.findall(r"[a-z]+", text.lower())
    return frozenset(w for w in words if len(w) >= 3 and w not in _TOPIC_STOPWORDS)


def _topical_conflict(claim: str, norm_claim: str, source_texts: list[str]) -> bool:
    """True when some source sentence CONTRADICTS the claim (a same-type value
    mismatch, per the engine) AND shares fact-identity vocabulary with it.

    This decides whether the adjudicator's ``conflicting_clauses`` refusal
    vetoes the confirmation legs. Direction of error is chosen deliberately:
    ANY shared content token keeps the veto (over-refusal, the safe side); only
    a contradiction with ZERO topical overlap -- an unrelated figure elsewhere
    in the document -- is treated as cross-fact noise. A reworded amendment
    ("the applicable termination fee shall be...") shares its subject nouns
    with the claim, so it always keeps the veto (mythos batchB-20260702,
    critical: the earlier skeleton-equality narrowing let a reworded amendment
    slip past the veto and a verbatim restatement green a contradicted value).
    """
    claim_tokens = _content_tokens(claim)
    if not claim_tokens:
        return True  # nothing to compare on: keep the veto (refuse)
    for source in source_texts:
        for sentence in split_sentences(source):
            if _normalize(sentence) == norm_claim:
                continue
            if not _sentence_relevant(claim_tokens, sentence):
                continue
            verdict = verify_claim_against_clause(claim, sentence)
            if verdict.disposition != "parametric_contradiction":
                continue
            if claim_tokens & _content_tokens(sentence):
                return True
    return False


def verify_claim(claim: str, sources: Sequence[SourceInput]) -> Attestation:
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

    # Bound the per-claim work: one claim vs every source sentence.
    source_sentence_count = sum(len(split_sentences(s)) for s in source_texts)
    if _too_large(1, source_sentence_count):
        checks.append(_oversize_refusal(claim))
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
    # every sentence of every source is a candidate, so an unrelated figure
    # elsewhere in the document manufactures "conflict" noise. The veto is
    # kept for every TOPICAL contradiction (any shared fact vocabulary; the
    # amended-value shape always qualifies, however reworded) and dropped only
    # for zero-overlap cross-fact noise, so the residual error is over-refusal,
    # never a green over a contradicted value.
    clause_conflict = (
        clause_outcome is not None
        and clause_outcome[2] == "conflicting_clauses"
        and _topical_conflict(claim, norm_claim, source_texts)
    )
    altered_residue = next((o for o in residue_outcomes if o.state == "altered"), None)
    verified_residue = next((o for o in residue_outcomes if o.state == "verified"), None)

    any_altered = altered_clause or altered_residue is not None

    # Genuine same-fact disagreement -- the ONLY confirmation that may veto a
    # caught alteration (mythos final-sweep, high: a matching co-located
    # DIFFERENT anchor used to mask a real catch). Two shapes qualify:
    #   - a source states the WHOLE claim verbatim while another contradicts it
    #     (restated + altered): the same fact, confirmed here and denied there;
    #   - the residue leg fires BOTH altered and verified across sentences: the
    #     SAME quantity confirmed in one source sentence and contradicted in
    #     another.
    # A verified signal from a DIFFERENT leg/anchor than the altered one (the
    # $900->$500 money drift beside a matching "1,234 units") is NOT
    # disagreement about the altered fact, so it must never downgrade the catch.
    same_fact_disagreement = (restated and any_altered) or (
        altered_residue is not None and verified_residue is not None
    )
    any_verified = restated or verified_clause or verified_residue is not None

    if clause_conflict or same_fact_disagreement:
        # The sources disagree about THIS fact (a same-skeleton sentence carries
        # different figures, or the whole claim is both stated and contradicted).
        # That refusal outranks every confirmation: a source that both states
        # and contradicts a claim proves nothing either way.
        detail = (
            clause_outcome[1]
            if clause_conflict and clause_outcome is not None
            else (
                "the sources disagree about this claim (one statement matches, "
                "another contradicts); refusing to pick a winner"
            )
        )
        checks.append(
            CheckResult(
                state="could_not_check",
                provenance="deterministic",
                detail=detail,
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


def attest_draft(draft: str, sources: Sequence[SourceInput]) -> DraftAttestation:
    """Attest every statement in a draft (sentence-split exactly like the
    app's verify surface). An empty draft is honestly uncheckable."""
    sentences = split_sentences(draft)
    if not sentences:
        return DraftAttestation(state="could_not_check")
    # Bound the whole-draft work: draft sentences x source sentences. Past the
    # ceiling the draft refuses as one honest could_not_check rather than
    # wedging the caller (mythos final-sweep, high). Guarding here AND in
    # verify_claim means the daemon /attest and /verify surfaces share the
    # bound -- no wire divergence.
    source_sentence_count = sum(len(split_sentences(s.text)) for s in _coerce_sources(sources))
    if _too_large(len(sentences), source_sentence_count):
        return DraftAttestation(
            state="could_not_check",
            claims=(ClaimAttestation(claim=draft, attestation=attest([_oversize_refusal(draft)])),),
        )
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
