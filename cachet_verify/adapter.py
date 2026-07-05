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

The post-campaign upgrade (mythos final-sweep follow-through): everything
derivable from the sources alone -- the quote pool, sentence splits, per-
sentence tokens, digit flags, and anchor extractions -- lives in a
``SourceIndex`` built ONCE per request. ``attest_draft`` used to rebuild all
of it per claim (N pool builds, N x M sentence extractions) and the topical-
conflict check re-ran the engine over the same sentences a second time; both
redundancies are gone, and the work ceiling is calibrated from measured
per-pair cost rather than a guess.
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
    quote_adverse_framed,
)
from services.legal.sentences import split_sentences

from .contract import SCHEMA_VERSION, Attestation, CheckResult, attest, combine
from .nearcopy import verify_near_copy_flip
from .residue import ResidueAnchor, ResidueComparison, compare_residue, extract_residue_anchors

_CLAUSE_STATE = {
    "parametric_contradiction": "altered",
    "present": "verified",
    "not_found": "could_not_check",
    "multi_value_unverifiable": "could_not_check",
    "conflicting_clauses": "could_not_check",
}

SourceInput = str | dict | SourceText

# The clause + residue legs compare the claim against every source SENTENCE, so
# a single verify_claim costs O(source_sentences) engine calls and attest_draft
# multiplies that by the draft's sentence count. The relevance prefilter blunts
# this on unrelated prose but NOT on a near-copy document (every sentence shares
# vocabulary), and the dominant per-pair cost is INSIDE
# verify_claim_against_clause (it re-extracts anchors per call), which this seam
# cannot cache without touching the sealed engine; the SourceIndex removes the
# source-prep redundancy but not that engine cost. Measured on an M-series
# machine post-index: ~0.7 ms per relevant pair on a small near-copy doc, rising
# to ~2 ms at ~3600 pairs (the cross-clause adjudicator is superlinear in
# candidate count). At the ceiling that is a worst-case near-copy wedge on the
# order of ~10 s -- bounded, not minutes. Past the ceiling the engine REFUSES
# (could_not_check) rather than block, because a silent stall on a trust surface
# is worse than an honest "too large, split it". A wall-clock budget is
# deliberately NOT used: it would make a verdict machine-speed-dependent and
# break the determinism the sealed certificate relies on, so the bound is a
# deterministic pair COUNT. Removing the per-pair engine cost (so the ceiling
# can rise) is ADR-0014 step-2 work.
_MAX_SENTENCE_PAIRS = 4_000

# Whole-draft aggregate work ceiling (attest_draft): the summed per-claim
# candidate upper bound. Sized from measurement -- ~10us per candidate
# comparison, so ~500k keeps a worst-case attest under ~5s on an M-series
# machine, well inside the anti-wedge budget -- while a long PROSE draft against
# a sparse source stays far below it. This is a deliberately conservative
# ceiling; L3 (profiling + a pre-registered budget) refines it.
_MAX_DRAFT_CANDIDATE_WORK = 500_000


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


def _value_keys_from_anchors(serv_anchors, res_anchors) -> frozenset[str]:
    """The VALUE-identity keys of a sentence (or claim): the canonical value of
    every parametric anchor (money/date/duration/percent/...) and residue
    anchor (quantity/count/...) it carries. Used by the value-anchor candidate
    index: a claim retrieves only the source sentences that carry ONE OF ITS
    OWN values -- the sentences that can carry or contradict it -- instead of
    every digit-bearing sentence. A serv anchor with no canonical value falls
    back to its lowercased text so a non-numeric anchor (a defined term, a
    governing-law name) still keys deterministically."""
    keys: set[str] = set()
    for a in serv_anchors:
        cv = getattr(a, "canonical_value", None)
        keys.add(f"s:{cv}" if cv is not None else f"t:{a.text.strip().lower()}")
    for a in res_anchors:
        c = getattr(a, "canonical", None)
        if c is not None:
            keys.add(f"r:{c}")
    return frozenset(keys)


def _claim_value_keys(claim: str) -> frozenset[str]:
    serv = extract_anchors(claim)
    res = extract_residue_anchors(claim, claimed_spans=[(a.start, a.end) for a in serv])
    return _value_keys_from_anchors(serv, res)


@dataclass(frozen=True)
class _SentenceEntry:
    """One source sentence with everything the legs need, computed once."""

    text: str
    normalized: str
    tokens: frozenset[str]
    has_digit: bool
    serv_spans: tuple[tuple[int, int], ...]
    res_anchors: tuple[ResidueAnchor, ...]
    all_spans: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class SourceIndex:
    """Everything derivable from the sources alone, built once per request.

    ``attest_draft`` shares one index across every claim; a bare
    ``verify_claim`` call builds its own (same behavior, same cost as before
    for the single-claim path). The index is pure data -- no I/O, no network --
    so sharing it cannot change any verdict, only skip recomputation. The
    equivalence suite pins that.

    Inverted maps (value-anchor index, 2026-07-05) let a single claim retrieve
    only the source sentences that could possibly affect its verdict, instead of
    scanning every one. They are a candidate FILTER, never a ranker: no scores,
    no top-K, so a candidate can never be silently dropped.

    - ``token_ids``: content token -> the sentence ids containing it. Retrieves
      every source sentence sharing fact vocabulary with the claim (so a
      same-topic contradiction, whatever its figure, is a candidate).
    - ``value_ids``: canonical anchor VALUE -> the sentence ids carrying it. A
      claim retrieves only the source sentences that carry ONE OF ITS OWN values
      -- the sentences that can CONFIRM it (same value) -- instead of every
      digit-bearing sentence. This is what lets a figure-DENSE long document
      (a real contract, thousands of amounts/dates) be verified: the old
      all-digit candidate set blew the per-claim ceiling on such a document.
    - ``norm_ids``: normalized sentence text -> ids. Guarantees a normalized-
      exact restatement of the claim is always a candidate, even when it carries
      no content token (e.g. a polarity-only sentence).

    EQUIVALENCE (weaker than the old all-digit index, deliberately): the
    candidate set is value|token|norm, NOT a superset of the old token|digit
    filter -- a digit sentence carrying neither a shared token nor one of the
    claim's values is now dropped. That change preserves the VERDICT STATE and
    the honesty floor (0 false greens, 0 false accusations over the parity
    corpus, the adversarial rotation, the long-doc family, and 2,500 random
    corpora), and never weakens a REAL alteration catch (the whole cachet_verify
    suite is the oracle). Its only measured cost: a handful of DEGENERATE
    multi-value word-salad claims flip altered->could_not_check -- a refusal,
    which is honest (Cachet's stance is honesty over coverage), never a false
    green. This is a truth-surface trade and is REVIEW-gated.
    """

    records: tuple[SourceText, ...]
    pool: object  # NormalizedSourcePool (opaque here; owned by quote_check)
    sentences: tuple[_SentenceEntry, ...]
    token_ids: dict[str, frozenset[int]]
    value_ids: dict[str, frozenset[int]]
    norm_ids: dict[str, frozenset[int]]

    @property
    def sentence_count(self) -> int:
        return len(self.sentences)

    def candidate_ids(
        self, claim_tokens: frozenset[str], norm_claim: str, value_keys: frozenset[str]
    ) -> frozenset[int]:
        """The sentence ids a claim must be compared against: those sharing a
        content token (same-topic contradictions), those carrying one of the
        claim's own anchor VALUES (confirmations/carriers), and any normalized-
        exact restatement. Independent of source size when the claim's values
        and vocabulary are sparse in the document -- which is what lets a long
        figure-dense document be verified. Sorted at the call sites for a stable
        candidate order."""
        ids: set[int] = set()
        for token in claim_tokens:
            hit = self.token_ids.get(token)
            if hit:
                ids |= hit
        for key in value_keys:
            hit = self.value_ids.get(key)
            if hit:
                ids |= hit
        if norm_claim:
            norm_hit = self.norm_ids.get(norm_claim)
            if norm_hit:
                ids |= norm_hit
        return frozenset(ids)


def build_source_index(sources: Sequence[SourceInput]) -> SourceIndex:
    records = tuple(_coerce_sources(sources))
    entries: list[_SentenceEntry] = []
    token_ids: dict[str, set[int]] = {}
    value_ids: dict[str, set[int]] = {}
    norm_ids: dict[str, set[int]] = {}
    for record in records:
        for sentence in split_sentences(record.text):
            serv_anchors = extract_anchors(sentence)
            serv_spans = tuple((a.start, a.end) for a in serv_anchors)
            res_anchors = tuple(extract_residue_anchors(sentence, claimed_spans=list(serv_spans)))
            idx = len(entries)
            tokens = _content_tokens(sentence)
            has_digit = any(ch.isdigit() for ch in sentence)
            normalized = _normalize(sentence)
            entries.append(
                _SentenceEntry(
                    text=sentence,
                    normalized=normalized,
                    tokens=tokens,
                    has_digit=has_digit,
                    serv_spans=serv_spans,
                    res_anchors=res_anchors,
                    all_spans=serv_spans + tuple((a.start, a.end) for a in res_anchors),
                )
            )
            for token in tokens:
                token_ids.setdefault(token, set()).add(idx)
            for key in _value_keys_from_anchors(serv_anchors, res_anchors):
                value_ids.setdefault(key, set()).add(idx)
            if normalized:
                norm_ids.setdefault(normalized, set()).add(idx)
    return SourceIndex(
        records=records,
        pool=prepare_source_pool(list(records)),
        sentences=tuple(entries),
        token_ids={k: frozenset(v) for k, v in token_ids.items()},
        value_ids={k: frozenset(v) for k, v in value_ids.items()},
        norm_ids={k: frozenset(v) for k, v in norm_ids.items()},
    )


def _quote_checks(claim: str, pool) -> list[CheckResult]:
    checks: list[CheckResult] = []
    for quote in extract_draft_quotes(claim):
        result = check_quote_against_pool(quote, pool)
        if result.altered:
            state, detail = "altered", "quoted words absent from every source"
        elif result.unplaceable:
            state, detail = "could_not_check", "no source could be fully seen for this quote"
        elif quote_adverse_framed(quote, pool):
            # Verbatim presence is not faithful quotation: the quoted words
            # appear in the source only inside a frame that rejects or merely
            # attributes the proposition. Demote to could_not_check (never a new
            # green); the honest reading is that the source does not support the
            # quote as stated (Q1).
            state, detail = (
                "could_not_check",
                (
                    "the quoted words appear in the source only inside a rejected or "
                    "attributed argument; verbatim presence there does not confirm the "
                    "quoted proposition"
                ),
            )
        else:
            state, detail = "verified", "quote is verbatim in a source"
        checks.append(
            CheckResult(state=state, provenance="deterministic", detail=detail, subject=quote)
        )
    return checks


def _sentence_relevant(claim_tokens: frozenset[str], entry: _SentenceEntry) -> bool:
    """Cheap prefilter for the per-sentence engine fan-out (the O(N*M) cost).

    A sentence with NO shared fact vocabulary AND NO digit can contribute
    nothing the pipeline keeps: it cannot carry the claim's value (values are
    digit-bearing), and any contradiction it produced would be zero-overlap
    cross-fact noise the filter discards anyway. Digit-bearing sentences are
    ALWAYS kept, whatever their vocabulary, so a value carrier with different
    surface wording ("$5,000,000" for "$5 million") still reaches the
    adjudicator's rule-1 conservatism (mythos batchE-20260702, perf).
    """
    return entry.has_digit or bool(claim_tokens & entry.tokens)


def _clause_leg(claim: str, index: SourceIndex) -> tuple[str, str, str, bool] | None:
    """Run the app's cross-clause adjudicator over every indexed sentence.

    Returns (state, detail, disposition, topical_conflict) or None when there
    is nothing to adjudicate. The raw disposition rides along because
    ``conflicting_clauses`` is not a plain abstention: it is the adjudicator
    KNOWING the sources disagree, and that knowledge must veto every
    confirmation path (including the exact-restatement rule -- a source that
    both states and contradicts a claim proves nothing either way).

    ``topical_conflict`` is computed HERE, from the same engine verdicts the
    candidates are built from (it used to be a second full engine pass over
    the same sentences): True when any contradiction shares fact vocabulary
    with the claim. Direction of error unchanged (mythos batchB-20260702,
    critical): ANY shared content token keeps the veto (over-refusal, the
    safe side); an empty claim-token set keeps it too; only a contradiction
    with ZERO topical overlap -- an unrelated figure elsewhere in the document
    -- is cross-fact noise.
    """
    candidates: list[ClauseCandidate] = []
    claim_tokens = _content_tokens(claim)
    topical_conflict = not claim_tokens  # nothing to compare on: keep the veto
    # Retrieve only the candidate sentences instead of scanning every one; the
    # ``_sentence_relevant`` guard below still runs. Value-anchor candidates are
    # the sentences sharing a content token (topical contradictions) or one of
    # the claim's own anchor VALUES (presents / carriers); a same-topic
    # contradiction reaches the adjudicator via its shared token, a confirmation
    # via its shared value. Sorted for a stable candidate order.
    value_keys = _claim_value_keys(claim)
    for cid in sorted(index.candidate_ids(claim_tokens, _normalize(claim), value_keys)):
        entry = index.sentences[cid]
        if not _sentence_relevant(claim_tokens, entry):
            continue
        verdict = verify_claim_against_clause(claim, entry.text)
        if (
            verdict.disposition == "parametric_contradiction"
            and claim_tokens
            and (claim_tokens & entry.tokens)
        ):
            topical_conflict = True
        candidates.append(
            ClauseCandidate(
                verdict=verdict,
                section=None,
                clause_text=entry.text,
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
            topical_conflict,
        )
    return (
        _CLAUSE_STATE.get(verdict.disposition, "could_not_check"),
        verdict.detail,
        verdict.disposition,
        topical_conflict,
    )


def verify_claim(
    claim: str,
    sources: Sequence[SourceInput],
    *,
    index: SourceIndex | None = None,
) -> Attestation:
    """Attest one claim against sources. Pure, no I/O, no network.

    Legs (each participating only when the claim carries its content):
    quotes (verbatim against the pool, truncation-honest), clause (the legal
    engine's parametrics under the app's own adjudicator), residue
    (kernel-owned quantities/counts under the near-copy gate), and the
    exact-restatement confirmation.

    ``index`` shares one prebuilt SourceIndex across many claims
    (attest_draft's path); None builds one for this call.
    """
    if index is None:
        index = build_source_index(sources)

    checks: list[CheckResult] = list(_quote_checks(claim, index.pool))

    claim_serv = extract_anchors(claim)
    serv_spans = [(a.start, a.end) for a in claim_serv]
    claim_res = extract_residue_anchors(claim, claimed_spans=serv_spans)
    res_spans = [(a.start, a.end) for a in claim_res]
    claim_all_spans = serv_spans + res_spans
    norm_claim = _normalize(claim)
    claim_tokens = _content_tokens(claim)

    if not claim_serv and not claim_res:
        # Anchor-free near-copy flip leg (live-smoke gap, 2026-07-02): a claim
        # with no parametric/residue anchor can still deterministically
        # contradict a source when a source sentence is token-identical except
        # for a negation flip or a proper-noun swap — and a verbatim
        # restatement of an anchor-free claim is confirmable by presence. The
        # detector carries its own honesty guards (single-run gate,
        # rhetorical-"not" and abbreviation refusals, the elsewhere demotion,
        # the stated+contradicted veto) — see nearcopy.py, byte-identical with
        # the companion's copy. Behind the same oversize bound as every other
        # per-sentence leg; when the detector abstains, behavior is
        # byte-identical to before.
        if index.records and not _too_large(1, index.sentence_count):
            near = verify_near_copy_flip(claim, "\n".join(record.text for record in index.records))
            if near is not None:
                checks.append(
                    CheckResult(
                        state=near.state,
                        provenance="deterministic",
                        detail=near.detail,
                        subject=near.subject,
                    )
                )
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

    if not index.records:
        checks.append(
            CheckResult(
                state="could_not_check",
                provenance="deterministic",
                detail="no sources were provided to check this claim against",
                subject=claim,
            )
        )
        return attest(checks)

    # Bound the per-claim work by the CANDIDATE count, not the total source
    # size (L1/value-anchor, 2026-07-05). The old bound refused any source past
    # ~4,000 sentences outright, so a long document could not be checked at all.
    # The value-anchor candidate set is the sentences that could actually affect
    # this claim's verdict -- those sharing one of its content tokens or one of
    # its own anchor VALUES -- so a long document (even a figure-DENSE one, a
    # real contract with thousands of amounts) verifies as long as THIS claim's
    # values and vocabulary are sparse in it, while a genuinely degenerate claim
    # (its value repeated across a huge fraction of the source) still refuses
    # honestly at the same bound.
    claim_value_keys = _value_keys_from_anchors(claim_serv, claim_res)
    claim_candidates = index.candidate_ids(claim_tokens, norm_claim, claim_value_keys)
    if _too_large(1, len(claim_candidates)):
        checks.append(_oversize_refusal(claim))
        return attest(checks)

    clause_outcome = _clause_leg(claim, index) if claim_serv else None

    residue_outcomes: list[ResidueComparison] = []
    restated = False
    # The value-anchor candidate set: a residue confirmation carries one of the
    # claim's residue values (-> in value_ids), a residue contradiction shares
    # the claim's subject vocabulary (-> in token_ids), and a restatement is a
    # normalized match (-> in norm_ids). Sorted for a stable outcome order.
    for cid in sorted(claim_candidates):
        entry = index.sentences[cid]
        if norm_claim and entry.normalized == norm_claim:
            restated = True
        if claim_res:
            outcome = compare_residue(
                claim,
                claim_res,
                claim_all_spans,
                entry.text,
                list(entry.res_anchors),
                list(entry.all_spans),
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
        and clause_outcome[3]
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
    app's verify surface). An empty draft is honestly uncheckable.

    The SourceIndex is built ONCE and shared across every claim: the pool,
    sentence splits, and per-sentence extractions no longer scale with the
    draft's claim count (the post-campaign upgrade)."""
    sentences = split_sentences(draft)
    if not sentences:
        return DraftAttestation(state="could_not_check")
    index = build_source_index(sources)
    # AGGREGATE anti-wedge bound (L1 fix, mythos D-track+L1 c4). The old
    # whole-draft product bound (draft_sentences x source_sentences > 4,000)
    # refused a long prose draft outright, so the candidate index removed it and
    # relied on the per-claim candidate bound. But a per-claim bound does NOT
    # bound the SUM: a crafted in-caps draft (~2,500 sentences) x a source of
    # ~3,999 candidate-bearing sentences (each claim just under the per-claim
    # refusal) drives ~10M sentence-pair comparisons and wedges the sync worker
    # (measured: ~15.5s at 400 claims, ~97s at 2,500). This pre-pass restores the
    # anti-wedge guarantee WITHOUT the old over-conservatism: it sums a CHEAP
    # per-claim candidate UPPER bound (precomputed inverted-index list lengths,
    # no set materialized) and refuses the whole draft once the total exceeds the
    # work budget. It over-counts overlaps, so it only ever refuses MORE
    # conservatively (never a false verify), and a long PROSE draft against a
    # sparse source stays far under the budget. The per-claim upper bound sums
    # the SAME inverted-index lists candidate_ids unions (value-key + token +
    # norm postings), so it tracks the value-anchor candidate count -- a
    # figure-dense source no longer inflates every claim's bound by its whole
    # digit population (which the old digit_n term did), only by the sentences
    # carrying THIS claim's actual values.
    total_upper = 0
    for sentence in sentences:
        upper = len(index.norm_ids.get(_normalize(sentence), ()))
        for token in _content_tokens(sentence):
            upper += len(index.token_ids.get(token, ()))
        for key in _claim_value_keys(sentence):
            upper += len(index.value_ids.get(key, ()))
        total_upper += upper
        if total_upper > _MAX_DRAFT_CANDIDATE_WORK:
            return DraftAttestation(
                state="could_not_check",
                claims=(
                    ClaimAttestation(claim=draft, attestation=attest([_oversize_refusal(draft)])),
                ),
            )
    # Each verify_claim additionally self-bounds by its OWN candidate count, so a
    # single degenerate claim under the aggregate budget still refuses
    # individually; the daemon /attest and /verify surfaces share that identical
    # per-claim bound, so there is no wire divergence.
    claims = tuple(
        ClaimAttestation(claim=s, attestation=verify_claim(s, sources, index=index))
        for s in sentences
    )
    # Draft-level state: reuse the combine algebra over one synthetic check
    # per claim so the precedence rules stay in ONE place.
    synthetic = [
        CheckResult(state=c.attestation.state, provenance="deterministic", subject=c.claim)
        for c in claims
    ]
    return DraftAttestation(state=combine(synthetic), claims=claims)
