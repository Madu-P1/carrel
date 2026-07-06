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
import os
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Literal, Optional, Sequence

from app_logging import get_logger, log_event
from services import tutor as tutor_service
from services.legal.align import align_claims_to_draft, placement_to_dict
from services.legal.quote_check import (
    SourceText,
    check_quote_against_pool,
    extract_draft_quotes,
    prepare_source_pool,
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
    # Cachet PR5a: where this claim was placed in the draft (char_start/char_end/
    # placed/method), or None for cards with no draft placement (unsupported-span
    # cards, the engine-failure card). A placed=False placement means the claim
    # is in the unplaced tray. Deterministic; never mis-pinned (services.legal.align).
    placement: Dict[str, Any] | None = None
    # T1 recall tier (ADR-0012): assessed-tier provenance, defaulted None and set by
    # nothing yet (the selector is wired in a later PR, dark until the calibration gate
    # passes). assessed_confidence stays on the wire for the gate + audit record but is
    # NOT rendered on the card (D3); the frontend reuses the existing `assistive` tier
    # without a number.
    assessed_confidence: float | None = None
    assessed_model: str | None = None
    assessed_label: str | None = None
    # The exact verbatim draft substrings that contradicted the source (e.g. the
    # altered figure "60 billion"). Each is a literal substring of claim_text, so
    # the document view can underline the precise changed token inside the flagged
    # statement rather than only marking the whole sentence. Empty unless this
    # claim is a parametric contradiction carrying a verbatim span.
    flagged_spans: tuple[str, ...] = ()


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
    # Cachet PR5a: claim_index values that could not be placed in the draft
    # (the unplaced tray). Deterministic; a claim is unplaced rather than
    # mis-pinned whenever its locator is ambiguous.
    unplaced: tuple[int, ...] = ()
    # Coverage honesty: how much of the draft the engine actually examined.
    # Set ONLY on the deterministic path, whose claims are sentence-aligned:
    # {"statements": total sentences, "treated": sentences with checkable
    # material (they became cards), "untreated": sentences with no checkable
    # anchor (no card, rendered as plain draft text)}. None on the LLM path,
    # whose claims are model-extracted and not sentence-aligned, so a count
    # would overstate what the engine knows. The UI and the certification
    # render this so "checked" never silently implies "checked everything".
    coverage: Dict[str, int] | None = None
    # Cachet SI-5: document-level structural-integrity findings from the
    # deterministic engine ({kind, disposition, detail, span, start, end, target}).
    # Draft-level, sibling to quote_results; empty on the LLM path and whenever the
    # engine surfaced nothing.
    structural_findings: tuple[Dict[str, Any], ...] = ()
    # Foundry cross_document: conflicts BETWEEN source documents (a defined term
    # bound to irreconcilable values across two or more doc_ids). Its own channel,
    # not structural_findings, because the finding is inherently multi-document
    # ({kind, disposition, term, dimension, detail, figures}). Empty on the LLM
    # path, on single-document verifies, and whenever the sources agree.
    cross_document_findings: tuple[Dict[str, Any], ...] = ()


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


def _verdict_from_case_verdicts(case_verdicts: tuple) -> VerifyVerdict:
    """Litigator: derive the top-line verdict from case-existence results."""
    any_missing = any_failed = any_exists = examined = False
    any_outside_coverage = any_caption_unconfirmed = False
    for cv in case_verdicts:
        if not cv.get("ok", True):
            any_failed = True
        for case in cv.get("verdicts") or []:
            examined = True
            if case.get("caption_mismatch"):
                any_missing = True  # resolves by number, but not the case named
            elif case.get("caption_unconfirmed"):
                # The number resolves, but one side of the draft's caption could
                # not be matched to the resolved case. Refuse, never bless and
                # never accuse: this must not count as an existence confirmation.
                any_caption_unconfirmed = True
            elif case.get("year_mismatch") or case.get("court_mismatch"):
                # The number resolves, but the draft's court-year parenthetical
                # disagrees with the corpus record (a 1990 year on a 1954 case;
                # a 9th Cir. court on a SCOTUS cite). Same refusal as an
                # unconfirmed caption: a wrong parenthetical on a real number
                # is usually a typo, so refuse, never bless and never accuse.
                any_caption_unconfirmed = True
            elif case.get("exists"):
                any_exists = True
            elif case.get("bounded_corpus"):
                # Absent from the BOUNDED offline corpus. That corpus is not the
                # national database, so this reads "outside my coverage" (an honest
                # could-not-check), never the accusatory "does not exist". A 404 with
                # no bounded_corpus flag came from a national lookup and still means
                # the case does not exist (the fabrication catch).
                any_outside_coverage = True
            else:
                any_missing = True
    if any_missing:
        return "unsupported"  # a cited case does not exist -- the catch
    if any_failed:
        return "unknown"  # verification could not run
    if any_caption_unconfirmed:
        return "unknown"  # the caption could not be confirmed -- the honest refusal
    if any_outside_coverage:
        return "unknown"  # outside the offline corpus -- the honest could-not-check
    if any_exists:
        return "verified"
    if examined:
        return "unsupported"  # cases were checked, none resolved
    # An ok batch that yielded zero inner verdicts: CourtListener ran but had
    # nothing to check (e.g. eyecite recognized a cite the live parser did not).
    # That is a could-not-check, never the accusatory "a cited case does not exist."
    return "unknown"


def _verdict_from_contract(contract_verdict: Dict[str, Any]) -> VerifyVerdict:
    """Contract: present -> verified, contradiction -> unsupported, else unknown."""
    disposition = contract_verdict.get("disposition")
    if disposition == "present":
        return "verified"
    if disposition == "parametric_contradiction":
        return "unsupported"
    return "unknown"  # not_found / multi_value_unverifiable -> could-not-check


def _deterministic_reason(
    case_verdicts: tuple, contract_verdict: Dict[str, Any] | None
) -> str | None:
    if contract_verdict:
        return str(contract_verdict.get("detail") or "") or None
    for cv in case_verdicts:
        for case in cv.get("verdicts") or []:
            if case.get("caption_mismatch"):
                return (
                    f"Citation {case.get('citation')} resolves to "
                    f"{case.get('case_name')}, not the case named in your draft."
                )
            if case.get("caption_unconfirmed"):
                return (
                    f"Citation {case.get('citation')} resolves to "
                    f"{case.get('case_name')}, but part of the caption in your draft "
                    "could not be matched to that case. Confirm the case name before "
                    "relying on it."
                )
            if case.get("year_mismatch"):
                return (
                    f"Citation {case.get('citation')} resolves to "
                    f"{case.get('case_name')}, decided in {case.get('resolved_year')}, "
                    f"but your draft dates it {case.get('cited_year')}. Confirm the "
                    "citation's year before relying on it."
                )
            if case.get("court_mismatch"):
                return (
                    f"Citation {case.get('citation')} resolves to "
                    f"{case.get('case_name')} in a different court than your draft's "
                    "parenthetical names. Confirm the citation's court before "
                    "relying on it."
                )
            if not case.get("exists"):
                if case.get("bounded_corpus"):
                    return (
                        f"Citation {case.get('citation')} is outside the offline corpus "
                        f"checked{_corpus_scope_phrase(case)}. This does not establish the "
                        "case does not exist; confirm it against the full national database."
                    )
                as_of = case.get("corpus_as_of")
                if as_of:
                    return (
                        f"Cited case not found: {case.get('citation')}. No such case "
                        f"appears in the citation index checked (complete as of {as_of})."
                    )
                return f"Cited case not found: {case.get('citation')}"
    return None


def _corpus_scope_phrase(case: Dict[str, Any]) -> str:
    """' (a 3-case demo corpus, as of 2026-06-05)' from the verdict's manifest
    fields, or '' when the corpus carried no manifest. Keeps the could-not-check
    copy honest about HOW bounded the check was, so a lawyer reading the card
    knows the denominator, not just that one exists."""
    scope = case.get("corpus_scope")
    count = case.get("corpus_case_count")
    as_of = case.get("corpus_as_of")
    if not scope or not count or not as_of:
        return ""
    return f" (a {count}-case {scope} corpus, as of {as_of})"


def _flagged_spans_from_contract(
    text: str, contract_verdict: Dict[str, Any] | None
) -> tuple[str, ...]:
    """Verbatim draft substrings to underline inside a flagged statement.

    Only a parametric contradiction yields token highlights. The altered-figure
    pre-pass carries the matched draft figure verbatim in ``claim_span`` and in
    ``claim_values``; the per-type parametric path carries CANONICAL values
    (normalized, e.g. ``20`` for "20%"), which usually do not appear verbatim. We
    therefore keep only candidates that are non-empty literal substrings of the
    claim text, deduped in order. A canonical-only contradiction simply yields no
    token span (the renderer still marks the whole sentence), so a highlight is
    never placed on text the engine did not actually flag.
    """
    if not contract_verdict or contract_verdict.get("disposition") != "parametric_contradiction":
        return ()
    candidates: list[str] = []
    span = contract_verdict.get("claim_span")
    if isinstance(span, str):
        candidates.append(span)
    for value in contract_verdict.get("claim_values") or ():
        if isinstance(value, str):
            candidates.append(value)
    seen: set[str] = set()
    out: list[str] = []
    for candidate in candidates:
        cleaned = candidate.strip()
        if cleaned and cleaned in text and cleaned not in seen:
            seen.add(cleaned)
            out.append(cleaned)
    return tuple(out)


def _claim_dict_to_verdict(
    claim_dict: Dict[str, Any],
    index: int,
    *,
    placement: Dict[str, Any] | None = None,
    grounding_error: str | None = None,
) -> VerifyClaimVerdict:
    """Map one engine-returned claim dict to a verifier verdict card.

    The LLM engine's claim carries in-corpus `citations` (>=1 -> verified). The
    deterministic engine instead carries `case_verdicts` (litigator
    case-existence) or a `contract_verdict` (contract claim); when there are no
    in-corpus citations the top-line verdict is derived from those, so a real
    cite reads verified and a fabricated one reads unsupported rather than every
    deterministic claim defaulting to unsupported.
    """
    text = str(claim_dict.get("text") or "").strip()
    citations = tuple(claim_dict.get("citations") or [])
    case_verdicts = tuple(claim_dict.get("case_verdicts") or [])
    contract_verdict = claim_dict.get("contract_verdict")
    section_verdict = claim_dict.get("section_verdict")
    could_not_check_reason = claim_dict.get("could_not_check_reason")
    quote_could_not_check_reason = claim_dict.get("quote_could_not_check_reason")
    section_absent = (
        bool(section_verdict) and section_verdict.get("disposition") == "section_absent"
    )
    # A parametric contradiction outranks the fabricated-section finding for the
    # REASON slot only: both are hard unsupported verdicts, and the
    # contradiction's both-values detail is the more actionable filing-grade
    # record. Every other clause disposition (present/not_found/multi_value)
    # yields to the fabricated section — a matching value must never ride a
    # section the contract does not contain into a green card.
    contract_contradiction = (
        bool(contract_verdict) and contract_verdict.get("disposition") == "parametric_contradiction"
    )
    # The litigator case-existence verdict, computed once. A fabricated caption on a
    # real reporter number ("Smith v. Jones, 347 U.S. 483", which resolves to Brown) or
    # a cited case that does not exist yields "unsupported" -- a HARD fabrication catch,
    # the core litigator beat.
    case_verdict_value = _verdict_from_case_verdicts(case_verdicts) if case_verdicts else None
    if citations:
        verdict: VerifyVerdict = "verified"
    elif section_absent and not contract_contradiction:
        # A draft sentence citing a section the source contract does not contain
        # is unsupported regardless of its predicate, whatever else the sentence
        # carries (computed unconditionally upstream since the percent build).
        verdict = "unsupported"
    elif case_verdict_value == "unsupported":
        # A fabricated caption / non-existent cited case must outrank a could-not-check
        # quote reason on the same sentence, exactly as section_absent does: otherwise a
        # fabricated caption that also carries an unverifiable quote softens from
        # "unsupported" to "unknown", masking the catch (xhigh review finding 8).
        verdict = "unsupported"
    elif quote_could_not_check_reason:
        # The cite may exist, but a quoted phrase could not be verified against the
        # opinion text we hold. Refuse rather than verify-by-existence (a silent pass
        # on the quote) or accuse (a false "altered"). The honest could-not-check.
        verdict = "unknown"
    elif could_not_check_reason:
        # Anchor-free deterministic claim: not independently verifiable. The honest
        # could-not-check, never the accusatory "unsupported".
        verdict = "unknown"
    elif contract_verdict:
        verdict = _verdict_from_contract(contract_verdict)
    elif case_verdict_value is not None:
        verdict = case_verdict_value
    else:
        verdict = "unsupported"
    # C1 silent-pass guard: when the engine reported it declined to ground this run
    # (the LLM passages-only refusal fallback, or a provider/transport error), the
    # fallback may still have attached citations. A citation-only "verified" must
    # never read green on a failed run. Deterministic success sets the envelope
    # error to None, so a real contract-present or case cite keeps its verdict; only
    # a failed-grounding run is demoted, and only to the honest could-not-check,
    # never an accusation (INV-2).
    demoted_for_grounding = grounding_error is not None and verdict == "verified"
    if demoted_for_grounding:
        verdict = "unknown"
        reason = (
            f"Verification could not run (engine error: {grounding_error}). "
            "Load the sources this draft relies on, then verify again."
        )
    elif verdict == "verified":
        # A contract "present" finding stays positive but keeps its hedge detail
        # (the value appears in the named clause; that is presence, not proof of
        # truth), so the card never reads as a bare "this is true." A verified case
        # cite carries no such hedge, so its reason stays None.
        reason = str(contract_verdict.get("detail") or "") or None if contract_verdict else None
    elif section_absent and not contract_contradiction:
        reason = str(section_verdict.get("detail") or "") or None
    elif case_verdict_value == "unsupported":
        # The verdict was hoisted to unsupported for the fabricated caption / absent
        # case; the reason must name THAT, not a co-occurring quote could-not-check, so
        # the filing-grade record reads "resolves to a different case", not "the quote
        # could not be verified" (xhigh review finding 8).
        reason = _deterministic_reason(case_verdicts, contract_verdict)
    elif quote_could_not_check_reason:
        reason = str(quote_could_not_check_reason)
    elif could_not_check_reason:
        reason = str(could_not_check_reason)
    else:
        reason = _deterministic_reason(case_verdicts, contract_verdict)
    # T1 recall tier (ADR-0012): assessed-tier provenance is STRICTLY subordinate to an
    # `unknown` could-not-check verdict. Only an anchor-free claim that stayed unknown via
    # could_not_check can carry an assessment; a T0 verdict (verified / unsupported) never
    # does, so a future Site-A change can't paint a local-model guess over a deterministic
    # fact. The assessment never changes the verdict; it only rides assessed_* for the
    # assistive surface, and stays None (the default) until T1's calibration gate passes.
    assessed_confidence = assessed_model = assessed_label = None
    t1_assessment = claim_dict.get("t1_assessment")
    if isinstance(t1_assessment, dict) and verdict == "unknown" and could_not_check_reason:
        assessed_confidence = t1_assessment.get("confidence")
        assessed_model = t1_assessment.get("model")
        assessed_label = t1_assessment.get("label")
    # Token highlights: only on a confirmed unsupported parametric contradiction,
    # and only the verbatim spans that occur in the claim text (never a canonical
    # value that would mis-highlight). Empty for every other disposition.
    flagged_spans = (
        _flagged_spans_from_contract(text, contract_verdict) if verdict == "unsupported" else ()
    )
    return VerifyClaimVerdict(
        claim_index=index,
        claim_text=text,
        verdict=verdict,
        citations=citations,
        case_verdicts=case_verdicts,
        unsupported_reason=reason,
        placement=placement,
        assessed_confidence=assessed_confidence,
        assessed_model=assessed_model,
        assessed_label=assessed_label,
        flagged_spans=flagged_spans,
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


def _resolve_deterministic(deterministic: bool | None) -> bool:
    """Whether to run the no-LLM deterministic engine for this verify call.

    An explicit ``deterministic`` wins: the Cachet verify route passes its
    surface default (deterministic on) here. When None (direct callers, tests),
    fall back to the legacy opt-in env flag so direct-call behavior is unchanged,
    deterministic only when ``CACHET_DETERMINISTIC_VERIFY`` is explicitly on. The
    surface-level default (on, with an explicit opt-out) lives at the route, not
    here, so importing this orchestrator never silently changes a caller's path.
    """
    if deterministic is not None:
        return deterministic
    return os.getenv("CACHET_DETERMINISTIC_VERIFY", "").lower() in {"1", "true", "yes"}


def verify_draft(
    conn: sqlite3.Connection,
    draft: str,
    *,
    doc_ids: Sequence[str] | None = None,
    subject_name: str | None = None,
    deterministic: bool | None = None,
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

    if _resolve_deterministic(deterministic):
        # No-LLM litigator path (Cachet). Anchor-driven unit selection +
        # offline case-existence; holding-match stays off. Imported lazily so
        # the default (flag-off) path keeps its original import contract and
        # never loads the eyecite chain.
        from services.legal.deterministic_envelope import build_deterministic_envelope

        envelope = build_deterministic_envelope(cleaned, conn=conn, doc_ids=doc_ids)
    else:
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
        "unplaced": list(result.unplaced),
        "coverage": dict(result.coverage) if result.coverage is not None else None,
        "structural_findings": [dict(f) for f in result.structural_findings],
        "cross_document_findings": [dict(f) for f in result.cross_document_findings],
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
    structural_findings = tuple(envelope.get("structural_findings") or [])
    cross_document_findings = tuple(envelope.get("cross_document_findings") or [])

    # Coverage honesty: the deterministic envelope emits exactly one claim per
    # draft sentence, so its claims ARE the denominator. Count them here, before
    # untreated claims are dropped from the card list below, or the information
    # is gone from the wire and every downstream surface can only imply that
    # the whole draft was checked. LLM-path claims are model-extracted, not
    # sentence-aligned: no coverage block there (None), by design.
    coverage: Dict[str, int] | None = None
    if str(envelope.get("provider") or "") == "deterministic":
        dict_claims = [c for c in claims if isinstance(c, dict)]
        untreated_count = sum(1 for c in dict_claims if c.get("untreated"))
        coverage = {
            "statements": len(dict_claims),
            "treated": len(dict_claims) - untreated_count,
            "untreated": untreated_count,
        }

    # Cachet PR4: brief-level draft-quote check. Build the source pool from the
    # envelope's serialized claims (loaded-doc chunk `content` + cited-case
    # `opinion_text`), then check each quoted span the lawyer typed in the draft.
    # Computed here so the non-stream verify_draft and the streamed path produce
    # identical quote_results for the same envelope.
    quote_results: tuple[Dict[str, Any], ...] = ()
    draft_quotes = extract_draft_quotes(cleaned)
    if draft_quotes:
        source_pool = _loaded_doc_sources(claims)
        source_pool.extend(_contract_clause_sources(claims))
        for claim_dict in claims:
            if not isinstance(claim_dict, dict):
                continue
            for cv in claim_dict.get("case_verdicts") or []:
                source_pool.extend(_opinion_sources_from_case_verdict(cv))
        # Normalize + dedupe the shared pool ONCE per request (E1), then check each
        # quote against it: the pool is identical for every span, so re-normalizing
        # it per quote was pure CPU waste at brief scale.
        normalized_pool = prepare_source_pool(source_pool)
        quote_results = tuple(
            _quote_result_to_dict(check_quote_against_pool(q, normalized_pool), i)
            for i, q in enumerate(draft_quotes)
        )

    # Cachet PR5a: deterministically place each claim against the draft so the
    # UI can pin its disposition next to the originating sentence. Computed here
    # (same seam as quote_results) so stream and non-stream agree. Pass the
    # UNFILTERED claims so each placement's claim_index matches the verdict
    # loop's enumerate(claims) index below. Never mis-pins: an ambiguous claim
    # lands in the unplaced tray.
    placements, unplaced_local = align_claims_to_draft(cleaned, claims)
    placement_by_index = {p.claim_index: placement_to_dict(p) for p in placements}

    verdicts: List[VerifyClaimVerdict] = []
    treated_indices: set[int] = set()
    for index, claim_dict in enumerate(claims):
        if not isinstance(claim_dict, dict):
            continue
        if claim_dict.get("untreated"):
            # Anchor-free prose: nothing checkable, so it is not a finding. It never
            # becomes a claim card or a tray entry; it renders as plain draft text
            # (the untreated / could-not-check split). Any placement the aligner
            # computed for it is simply unused.
            continue
        treated_indices.add(index)
        verdicts.append(
            _claim_dict_to_verdict(
                claim_dict,
                index,
                placement=placement_by_index.get(index),
                grounding_error=engine_error,
            )
        )

    # Span cards start after the highest claim_index actually emitted. Deriving the
    # base from the max (not len) keeps a span index from colliding with an emitted
    # claim card when untreated/non-dict claims left gaps in the enumerate sequence.
    base_index = max((v.claim_index for v in verdicts), default=-1) + 1
    for offset, span in enumerate(unsupported_spans):
        if not span:
            continue
        verdicts.append(_unsupported_span_to_verdict(str(span), base_index + offset))

    if not verdicts:
        # Zero cards is a SUCCESSFUL outcome when the engine produced only untreated
        # (anchor-free) claims: a clean prose draft renders as plain text, not a wall
        # of cards and not a lone engine-failure card. Reserve the engine-failure card
        # for a genuine failure: the engine errored, or produced no claims at all
        # (empty retrieval / provider error on the LLM path).
        if engine_error is not None or not claims:
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
        # Only reference claims that actually became cards; an untreated claim has no
        # card, so it must never appear in the unplaced tray.
        unplaced=tuple(i for i in unplaced_local if i in treated_indices),
        coverage=coverage,
        structural_findings=structural_findings,
        cross_document_findings=cross_document_findings,
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
        "placement": verdict.placement,
        "assessed_confidence": verdict.assessed_confidence,
        "assessed_model": verdict.assessed_model,
        "assessed_label": verdict.assessed_label,
        "flagged_spans": list(verdict.flagged_spans),
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


def _contract_clause_sources(claim_cards: list[Dict[str, Any]]) -> list[SourceText]:
    """The matched contract clause for each contract claim, as a draft-quote source.

    D1: the deterministic contract path sets `citations: []`, so without this the
    brief-level quote pool is empty for contract claims and EVERY quoted span reads
    could_not_check, contradicting a claim card that already found the quote verbatim.
    Seeding the pool with the matched clause lets the QuotePanel confirm those quotes,
    so the two surfaces agree. `complete=False`: a single retrieved clause is not the
    whole loaded document, so a quote absent from it degrades to could_not_check, never
    a false `altered` accusation (ADR-0012 invariant 2).
    """
    out: list[SourceText] = []
    for card in claim_cards:
        cv = card.get("contract_verdict")
        if not isinstance(cv, dict):
            continue
        text = str(cv.get("clause_text") or "").strip()
        if text:
            out.append(SourceText(text=text, truncated=False, complete=False))
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
    return {
        "index": index,
        "quote": result.quote,
        "status": status,
        # Autopsy tiling (populated only for an altered quote): the lawyer's own
        # words split into genuine vs fabricated phrases. Carries no source text,
        # so the slim SSE payload and zero-egress posture are unchanged.
        "segments": [{"text": s.text, "kind": s.kind} for s in result.segments],
    }


def verify_draft_stream(
    conn: sqlite3.Connection,
    draft: str,
    *,
    doc_ids: Sequence[str] | None = None,
    subject_name: str | None = None,
    deterministic: bool | None = None,
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

    if _resolve_deterministic(deterministic):
        # The demo UI calls ONLY this stream endpoint (VerifyView -> /api/verify/
        # stream), so the offline engine must run HERE too, not just in the
        # non-stream verify_draft. Without this branch the stream falls through to
        # the LLM path below, which reaches CourtListener with a real client and
        # POSTs the draft off-device -- the "no data leaves this device" guarantee
        # would be false on the live path. The deterministic engine is sub-second
        # and synchronous, so it emits the canonical result in one shot rather than
        # streaming per-cite labor (the result event renders the full surface, the
        # same as the non-stream path).
        from services.legal.deterministic_envelope import build_deterministic_envelope

        envelope = build_deterministic_envelope(cleaned, conn=conn, doc_ids=doc_ids)
        result = _verify_result_from_envelope(cleaned, envelope, started)
        if result.quote_results:
            yield {"type": "quote_batch", "quotes": list(result.quote_results)}
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
                if claim_dict.get("untreated"):
                    # Untreated prose is never a card (the LLM path never emits it, but
                    # the invariant holds uniformly across both card-building loops).
                    continue
                cards.append(_claim_dict_to_verdict(claim_dict, index))
            base_index = max((c.claim_index for c in cards), default=-1) + 1
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
