"""Carrel V2 Stage 1 — Verify-mode orchestrator.

Repositions the existing grounded-tutor engine as a per-claim
verifier. Input is a drafted text (a brief, a memo, a paragraph);
output is a per-claim verdict surface — VERIFIED when the engine
returns a grounded claim, UNSUPPORTED when it lands in the
unsupported_spans bucket, UNKNOWN when the engine itself failed
(empty retrieval, scope-fallback weak coverage, provider error).

This module is a thin coordinator on top of
`services.tutor.grounded_tutor_response`. The engine already does
the hard work — quote validation, structural-citation drops,
CourtListener case-existence verification (PR c6d5ec08). The
verifier just changes the framing (question -> draft) and re-shapes
the output (claims + unsupported_spans -> per-claim verdict cards).

V1 scope cut (this PR):
  - One LLM call per Verify request, not per draft sentence. The
    engine returns multiple claims; the verifier maps each returned
    claim to one verdict card.
  - The mapping is fuzzy: model-extracted claim text vs. literal
    draft sentence. Litigator-facing UX surfaces both so the
    operator can audit. Honest by design.

V2 follow-ups (out of scope):
  - Sentence-level claim alignment via embeddings or fuzzy matching.
  - Custom verifier prompt (currently passes the draft through the
    existing tutor system prompt with a verify-framed prefix).
  - Streaming verdicts so a 30-claim brief renders incrementally.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Literal, Optional, Sequence

from app_logging import get_logger, log_event
from services import tutor as tutor_service
from services.legal.quote_check import (
    SourceText,
    check_quote_against_sources,
    extract_draft_quotes,
)

LOGGER = get_logger("einstein.verify")

VerifyVerdict = Literal["verified", "unsupported", "unknown"]


@dataclass(frozen=True)
class VerifyClaimVerdict:
    """One per-claim verdict surfaced to the verifier UX."""

    claim_index: int
    claim_text: str
    verdict: VerifyVerdict
    citations: tuple[Dict[str, Any], ...]
    case_verdicts: tuple[Dict[str, Any], ...]
    unsupported_reason: str | None


@dataclass(frozen=True)
class VerifySummary:
    total: int
    verified: int
    unsupported: int
    unknown: int


@dataclass(frozen=True)
class VerifyResult:
    draft_text: str
    claim_verdicts: tuple[VerifyClaimVerdict, ...]
    summary: VerifySummary
    latency_ms: float
    model: str
    ok: bool
    error: str | None
    # T64 Phase 2 (answer-quality provenance): which provider produced
    # this verification result. Mirrors GroundedAnswer.provider; threaded
    # through grounded_tutor_envelope so the API surface can render a
    # provenance badge or fail-loud banner.
    provider: str = ""
    # Cachet PR4: brief-level draft-quote-verbatim results. One entry per quoted
    # span found in the draft, each {index, quote, status} where status is
    # "altered" | "could_not_check" | "verbatim". Brief-level (not per-claim):
    # per-claim placement is PR5's claim-span-alignment job. Empty when the
    # draft contains no quoted spans.
    quote_results: tuple[Dict[str, Any], ...] = ()


def _verify_framed_question(draft: str) -> str:
    """Wrap the draft in a verify-framed prompt the existing engine
    accepts as a 'question'. The engine prompt instructs the model
    to ground every claim in the chunks; here we extend that to mean
    'every factual statement in the draft below'.

    Kept minimal in V1 — the existing system prompt does most of the
    work. A future PR can swap to a dedicated verifier system prompt
    if claim extraction quality plateaus.
    """
    return (
        "Verify each factual statement in the following draft against "
        "the source chunks. Treat each statement as a separate claim "
        "to be grounded; if a statement is not supported by the "
        "chunks, move it to unsupported_spans rather than guessing.\n\n"
        "<draft>\n"
        f"{draft.strip()}\n"
        "</draft>"
    )


def _claim_dict_to_verdict(
    claim_dict: Dict[str, Any],
    index: int,
) -> VerifyClaimVerdict:
    """Map one engine-returned claim dict to a verifier verdict card.

    The engine's serialized claim shape (see
    `services.tutor._serialize_claims`) carries `text`, `citations`,
    and `case_verdicts`. A claim with at least one citation is
    VERIFIED; otherwise UNSUPPORTED (the engine moves orphaned
    claims to unsupported_spans, but if a claim somehow reaches us
    with empty citations it is still unsupported).
    """
    text = str(claim_dict.get("text") or "").strip()
    citations = tuple(claim_dict.get("citations") or [])
    case_verdicts = tuple(claim_dict.get("case_verdicts") or [])
    verdict: VerifyVerdict = "verified" if citations else "unsupported"
    return VerifyClaimVerdict(
        claim_index=index,
        claim_text=text,
        verdict=verdict,
        citations=citations,
        case_verdicts=case_verdicts,
        unsupported_reason=None,
    )


def _unsupported_span_to_verdict(span: str, index: int) -> VerifyClaimVerdict:
    """Wrap an engine `unsupported_spans` entry as a verdict card."""
    return VerifyClaimVerdict(
        claim_index=index,
        claim_text=str(span).strip(),
        verdict="unsupported",
        citations=(),
        case_verdicts=(),
        unsupported_reason=("The engine could not ground this claim in any retrieved chunk."),
    )


def _engine_failure_verdict(
    draft: str,
    error: str | None,
) -> VerifyClaimVerdict:
    """Single-card verdict when the engine itself failed (no claims,
    no unsupported_spans — typically empty_retrieval / weak_coverage
    / provider error). Surfaces the engine's error_code so the
    operator can act."""
    return VerifyClaimVerdict(
        claim_index=0,
        claim_text=draft.strip()[:280] or "<empty draft>",
        verdict="unknown",
        citations=(),
        case_verdicts=(),
        unsupported_reason=(f"Engine could not produce verdicts (error: {error or 'unknown'})."),
    )


def _payload_for_envelope(
    draft: str,
    doc_ids: Sequence[str] | None,
    subject_name: str | None,
) -> Any:
    """Build the duck-typed payload `grounded_tutor_envelope` expects.

    The envelope reads attributes via `getattr` (concept_id,
    doc_ids, confidence, learner_confidence, etc.); a tiny dataclass
    matches that contract without dragging the full TutorQueryRequest
    pydantic model in.
    """

    @dataclass
    class _VerifyPayload:
        question: str
        doc_ids: List[str] | None
        subject_name: str | None
        concept_id: None = None
        concept_scope: None = None
        confidence: None = None
        learner_confidence: None = None
        show_citations: bool = True
        top_k: int = 8
        mode: str = "standard"
        response_mode: str = "standard"

    return _VerifyPayload(
        question=_verify_framed_question(draft),
        doc_ids=list(doc_ids) if doc_ids else None,
        subject_name=subject_name,
    )


def verify_draft(
    conn: sqlite3.Connection,
    draft: str,
    *,
    doc_ids: Sequence[str] | None = None,
    subject_name: str | None = None,
    log_study_event,
    fetch_recent_events,
) -> VerifyResult:
    """Run the verifier on `draft` and return a per-claim verdict result.

    Returns `ok=False` only when the engine itself failed end-to-end
    (no envelope produced). A successful run with zero claims is
    still ok=True with verdict cards drawn from unsupported_spans
    or a single 'unknown' card surfacing the engine's error.
    """
    cleaned = (draft or "").strip()
    started = time.perf_counter()
    if not cleaned:
        return VerifyResult(
            draft_text="",
            claim_verdicts=(),
            summary=VerifySummary(total=0, verified=0, unsupported=0, unknown=0),
            latency_ms=0.0,
            model="",
            ok=False,
            error="empty_draft",
            provider="",
        )

    payload = _payload_for_envelope(cleaned, doc_ids, subject_name)
    envelope = tutor_service.grounded_tutor_envelope(
        conn,
        payload,
        log_study_event=log_study_event,
        fetch_recent_events=fetch_recent_events,
    )

    return _verify_result_from_envelope(cleaned, envelope, started)


def verify_result_to_payload(result: VerifyResult) -> Dict[str, Any]:
    """Serialize a VerifyResult into the API response shape."""
    return {
        "draft_text": result.draft_text,
        "claim_verdicts": [_verdict_card_to_dict(v) for v in result.claim_verdicts],
        "summary": {
            "total": result.summary.total,
            "verified": result.summary.verified,
            "unsupported": result.summary.unsupported,
            "unknown": result.summary.unknown,
        },
        "latency_ms": result.latency_ms,
        "model": result.model,
        "ok": result.ok,
        "error": result.error,
        "provider": result.provider,
        "quote_results": list(result.quote_results),
    }


def _verify_result_from_envelope(
    cleaned: str,
    envelope: Dict[str, Any],
    started: float,
) -> VerifyResult:
    """Map a grounded-tutor envelope into the per-claim VerifyResult.

    Shared by `verify_draft` (non-stream) and `verify_draft_stream` so both
    produce an identical result for the same envelope.
    """
    claims = envelope.get("claims") or []
    unsupported_spans = envelope.get("unsupported_spans") or []
    model_name = str(envelope.get("model") or envelope.get("answer_model") or "")
    engine_error = envelope.get("error")

    # Cachet PR4: brief-level draft-quote check. Build the source pool from the
    # envelope's serialized claims (loaded-doc chunk `content` + cited-case
    # `opinion_text`), then check each quoted span the lawyer typed in the draft.
    # Computed here so the non-stream verify_draft and the streamed path produce
    # identical quote_results for the same envelope.
    quote_results: tuple[Dict[str, Any], ...] = ()
    draft_quotes = extract_draft_quotes(cleaned)
    if draft_quotes:
        source_pool = _loaded_doc_sources(claims)
        for claim_dict in claims:
            if not isinstance(claim_dict, dict):
                continue
            for cv in claim_dict.get("case_verdicts") or []:
                source_pool.extend(_opinion_sources_from_case_verdict(cv))
        quote_results = tuple(
            _quote_result_to_dict(check_quote_against_sources(q, source_pool), i)
            for i, q in enumerate(draft_quotes)
        )

    verdicts: List[VerifyClaimVerdict] = []
    for index, claim_dict in enumerate(claims):
        if not isinstance(claim_dict, dict):
            continue
        verdicts.append(_claim_dict_to_verdict(claim_dict, index))

    base_index = len(verdicts)
    for offset, span in enumerate(unsupported_spans):
        if not span:
            continue
        verdicts.append(_unsupported_span_to_verdict(str(span), base_index + offset))

    if not verdicts:
        verdicts.append(_engine_failure_verdict(cleaned, engine_error))

    verified = sum(1 for v in verdicts if v.verdict == "verified")
    unsupported = sum(1 for v in verdicts if v.verdict == "unsupported")
    unknown = sum(1 for v in verdicts if v.verdict == "unknown")
    summary = VerifySummary(
        total=len(verdicts),
        verified=verified,
        unsupported=unsupported,
        unknown=unknown,
    )
    latency_ms = (time.perf_counter() - started) * 1000.0

    log_event(
        LOGGER,
        logging.INFO,
        "verify_draft",
        request_kind="verify.draft",
        total=summary.total,
        verified=summary.verified,
        unsupported=summary.unsupported,
        unknown=summary.unknown,
        latency_ms=round(latency_ms, 2),
        model=model_name,
        engine_error=engine_error,
    )

    return VerifyResult(
        draft_text=cleaned,
        claim_verdicts=tuple(verdicts),
        summary=summary,
        latency_ms=latency_ms,
        model=model_name,
        ok=engine_error is None,
        error=engine_error,
        provider=str(envelope.get("provider") or ""),
        quote_results=quote_results,
    )


def _verdict_card_to_dict(verdict: VerifyClaimVerdict) -> Dict[str, Any]:
    """Serialize one VerifyClaimVerdict card to the API / stream shape.

    Strips the server-internal `opinion_text` (PR4) from every case-verdict
    batch here, at the single serialization boundary that BOTH the streamed
    skeleton cards and the final result payload flow through, so the bulky
    opinion text can never cross the SSE wire by any path.
    """
    return {
        "claim_index": verdict.claim_index,
        "claim_text": verdict.claim_text,
        "verdict": verdict.verdict,
        "citations": list(verdict.citations),
        "case_verdicts": [_strip_opinion_text(cv) for cv in verdict.case_verdicts],
        "unsupported_reason": verdict.unsupported_reason,
    }


def _citation_position(citation: Dict[str, Any]) -> tuple[int | None, int | None, int | None]:
    """(char_start, char_end, chunk_index) for a serialized citation, any None."""

    def _int(v: Any) -> int | None:
        return v if isinstance(v, int) else None

    return (
        _int(citation.get("char_start")),
        _int(citation.get("char_end")),
        _int(citation.get("chunk_index")),
    )


def _join_adjacent(citations: list[Dict[str, Any]]) -> list[SourceText]:
    """Join PROVABLY-ADJACENT citations of one document into contiguous sources.

    Cachet PR4 finding [3]: a quoted run straddling two retrieved pieces appears
    verbatim in neither, so checking pieces independently false-flags. We merge
    only pieces we can PROVE are contiguous in the source, so the join never
    fabricates adjacency (which would be a new cry-wolf bug):

      - nodes path: char offsets present. Adjacent iff next.char_start <=
        prev.char_end + _ADJACENCY_GAP (small gap absorbs inter-node whitespace
        the extractor dropped). Joined text is complete=True.
      - chunks path: no char offsets, only chunk_index. Adjacent iff
        next.chunk_index == prev.chunk_index + 1. Joined complete=True.

    A piece with no position info, or a gap between pieces, starts a new source.
    A source built from a single un-joinable piece stays complete=False (it may
    straddle into a neighbor we did not retrieve), so it can ground could_not_
    check but never an `altered` verdict. A multi-piece contiguous join is
    complete=True: we have proven the run space between those pieces.
    """

    # Order by best available position key: char_start, else chunk_index.
    def sort_key(c: Dict[str, Any]) -> tuple[int, int]:
        cs, _ce, ci = _citation_position(c)
        if cs is not None:
            return (0, cs)
        if ci is not None:
            return (1, ci)
        return (2, 0)

    ordered = sorted(citations, key=sort_key)
    out: list[SourceText] = []
    run_texts: list[str] = []
    run_len = 0  # number of pieces merged into the current run
    run_node_based = False  # any piece in this run had real char offsets
    prev: tuple[int | None, int | None, int | None] | None = None

    def flush() -> None:
        nonlocal run_texts, run_len, run_node_based
        if run_texts:
            # A run is a COMPLETE source when it is either a multi-piece
            # contiguous join (we have proven the space between the pieces) OR a
            # node-based piece (a node is a whole structural unit, e.g. a
            # paragraph, so a lone node does not straddle the way an arbitrary
            # chunk split can). A lone chunk (chunk_index only) stays incomplete.
            complete = run_len > 1 or run_node_based
            out.append(SourceText(text="\n".join(run_texts), complete=complete))
        run_texts = []
        run_len = 0
        run_node_based = False

    for cit in ordered:
        text = str((cit or {}).get("content") or "").strip()
        if not text:
            continue
        cs, ce, ci = _citation_position(cit)
        adjacent = False
        if prev is not None:
            pcs, pce, pci = prev
            if pce is not None and cs is not None:
                adjacent = cs <= pce + _ADJACENCY_GAP and cs >= (pcs or 0)
            elif pci is not None and ci is not None:
                adjacent = ci == pci + 1
        if prev is not None and not adjacent:
            flush()
        run_texts.append(text)
        run_len += 1
        if cs is not None or ce is not None:
            run_node_based = True
        prev = (cs, ce, ci)
    flush()
    return out


# Whitespace the extractor may have dropped between adjacent nodes; a gap up to
# this many chars between prev.char_end and next.char_start still counts as
# contiguous. Small + conservative: a real omission is far larger.
_ADJACENCY_GAP = 5


def _loaded_doc_sources(claim_cards: list[Dict[str, Any]]) -> list[SourceText]:
    """Build the loaded-doc half of the draft-quote source pool.

    Each serialized citation carries its node/chunk text under `content` plus
    its source position (char_start/char_end for nodes, chunk_index for chunks).
    We group citations by document and join PROVABLY-ADJACENT pieces into
    contiguous, complete sources (so a quote straddling two retrieved pieces is
    found verbatim and not false-flagged), while a lone un-joinable piece stays
    complete=False (it can only ground could_not_check, never `altered`).
    """
    by_doc: dict[str, list[Dict[str, Any]]] = {}
    for card in claim_cards:
        for citation in card.get("citations") or []:
            if not isinstance(citation, dict):
                continue
            if not str(citation.get("content") or "").strip():
                continue
            doc_id = str(citation.get("document_id") or citation.get("doc_id") or "")
            by_doc.setdefault(doc_id, []).append(citation)
    out: list[SourceText] = []
    for cits in by_doc.values():
        out.extend(_join_adjacent(cits))
    return out


def _opinion_sources_from_case_verdict(case_verdict: Dict[str, Any]) -> list[SourceText]:
    """Pull retained opinion text out of a serialized case-verdict batch.

    The cited-case half of the source pool. A full opinion is a complete
    contiguous passage (`complete=True`), but may be truncated by the fetch cap;
    `fetch_opinion_text` appends a " …" sentinel when it cut the text, which we
    read into `truncated` so a run absent from the visible head degrades to
    could_not_check rather than flagging (finding [4]). Server-internal: the
    caller strips `opinion_text` from the event before the SSE boundary.
    """
    out: list[SourceText] = []
    for case in case_verdict.get("verdicts") or []:
        text = str((case or {}).get("opinion_text") or "").strip()
        if text:
            truncated = text.endswith("…")
            out.append(SourceText(text=text, truncated=truncated, complete=True))
    return out


def _strip_opinion_text(case_verdict: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of a case-verdict batch with the bulky server-internal
    `opinion_text` removed from each case, so the SSE payload stays lean."""
    cleaned_cases = []
    for case in case_verdict.get("verdicts") or []:
        cleaned_cases.append({k: v for k, v in case.items() if k != "opinion_text"})
    return {**case_verdict, "verdicts": cleaned_cases}


def _quote_result_to_dict(result, index: int) -> Dict[str, Any]:
    """Serialize one QuoteCheckResult into the wire shape for the quote panel.

    `status` is the plain-word disposition the UI renders: "altered" (a run is
    not verbatim in any source), "could_not_check" (no usable source / truncated
    past the cut), or "verbatim" (every run found). No confidence numbers.
    """
    if result.unplaceable:
        status = "could_not_check"
    elif result.altered:
        status = "altered"
    else:
        status = "verbatim"
    return {"index": index, "quote": result.quote, "status": status}


def verify_draft_stream(
    conn: sqlite3.Connection,
    draft: str,
    *,
    doc_ids: Sequence[str] | None = None,
    subject_name: str | None = None,
    log_study_event,
    fetch_recent_events,
) -> Iterator[Dict[str, Any]]:
    """Streaming variant of `verify_draft`.

    Yields verifier-shaped events so the UI shows the per-cite labor as it
    happens, then a final canonical result:

      - ``{"type": "progress", "phase": "extracting"}``
      - ``{"type": "claims", "claim_verdicts": [...skeleton cards...]}`` once the
        grounded answer resolves (case verdicts NOT yet attached)
      - ``{"type": "cite_verdict", "claim_index": i, "case_verdict": {...}}`` per
        claim as the CourtListener + holding-match labor completes
      - ``{"type": "result", "verify": {...}}`` identical to POST /api/verify

    Invariant #6 (an unfinished verification must never read as a pass): this
    generator never pre-emits a resolved case verdict. Skeleton cards carry an
    empty ``case_verdicts`` list, so the client must default each claim's
    cite-axis to ``could_not_check`` and resolve it only on an explicit
    cite_verdict (or the final result). A dropped stream therefore leaves the
    not-yet-yielded claims as could_not_check, never supported. Exactly one
    cite_verdict is emitted per claim card (non-legal claims included, as an
    ok=True empty batch), so the client knows the expected count.
    """
    cleaned = (draft or "").strip()
    started = time.perf_counter()
    if not cleaned:
        result = VerifyResult(
            draft_text="",
            claim_verdicts=(),
            summary=VerifySummary(total=0, verified=0, unsupported=0, unknown=0),
            latency_ms=0.0,
            model="",
            ok=False,
            error="empty_draft",
            provider="",
        )
        yield {"type": "result", "verify": verify_result_to_payload(result)}
        return

    payload = _payload_for_envelope(cleaned, doc_ids, subject_name)
    envelope: Dict[str, Any] = {}
    for event in tutor_service.grounded_tutor_envelope_steps(
        conn,
        payload,
        log_study_event=log_study_event,
        fetch_recent_events=fetch_recent_events,
    ):
        etype = event.get("type")
        if etype == "progress":
            yield event
        elif etype == "claims":
            engine_claims = event.get("claims") or []
            spans = event.get("unsupported_spans") or []
            cards: List[VerifyClaimVerdict] = []
            for index, claim_dict in enumerate(engine_claims):
                if not isinstance(claim_dict, dict):
                    continue
                cards.append(_claim_dict_to_verdict(claim_dict, index))
            base_index = len(cards)
            for offset, span in enumerate(spans):
                if not span:
                    continue
                cards.append(_unsupported_span_to_verdict(str(span), base_index + offset))
            yield {
                "type": "claims",
                "claim_verdicts": [_verdict_card_to_dict(v) for v in cards],
            }
        elif etype == "cite_verdict":
            # Strip the server-internal opinion_text before the SSE boundary so
            # the wire stays lean; the quote check reads it from the envelope.
            case_verdict = event.get("case_verdict") or {}
            yield {**event, "case_verdict": _strip_opinion_text(case_verdict)}
        elif etype == "result":
            envelope = event["envelope"]

    # Build the canonical result (which computes the brief-level quote_results
    # from the same envelope the non-stream path uses, so stream and non-stream
    # agree exactly). Emit the quote panel as its own event before the result
    # for the watch-the-labor reveal; the result payload also carries it so a
    # reload / non-stream caller is identical. Cachet PR4 quote verdicts are
    # BRIEF-LEVEL; per-claim placement is deferred to PR5 claim-span alignment.
    result = _verify_result_from_envelope(cleaned, envelope, started)
    if result.quote_results:
        yield {"type": "quote_batch", "quotes": list(result.quote_results)}
    yield {"type": "result", "verify": verify_result_to_payload(result)}
