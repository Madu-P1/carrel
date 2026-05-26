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
from typing import Any, Dict, List, Literal, Optional, Sequence

from app_logging import get_logger, log_event
from services import tutor as tutor_service

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

    claims = envelope.get("claims") or []
    unsupported_spans = envelope.get("unsupported_spans") or []
    model_name = str(envelope.get("model") or envelope.get("answer_model") or "")
    engine_error = envelope.get("error")

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
    )


def verify_result_to_payload(result: VerifyResult) -> Dict[str, Any]:
    """Serialize a VerifyResult into the API response shape."""
    return {
        "draft_text": result.draft_text,
        "claim_verdicts": [
            {
                "claim_index": v.claim_index,
                "claim_text": v.claim_text,
                "verdict": v.verdict,
                "citations": list(v.citations),
                "case_verdicts": list(v.case_verdicts),
                "unsupported_reason": v.unsupported_reason,
            }
            for v in result.claim_verdicts
        ],
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
    }
