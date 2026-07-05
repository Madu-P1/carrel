"""Carrel V2 Stage 1 — Verify-mode route.

POST /api/verify takes a draft (brief, memo, paragraph) and returns a
per-claim verdict surface. Thin wrapper over
`services.verify.verify_draft`; the engine work happens there.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterator

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

import db
from api_models import DraftExtractionResponse, VerifyRequest, VerifyResponse
from app_logging import get_logger, log_event
from services import extraction_pipeline
from services import verify as verify_service
from services.app_state import fetch_recent_events, log_study_event
from services.extraction.utils import text_sha
from services.legal.sentences import split_sentences
from services.uploads import save_upload_bounded, validate_upload_suffix

LOGGER = get_logger("verify_api")

router = APIRouter()


def _deterministic_surface_default() -> bool:
    """The /api/verify surface IS Cachet (no egress, no LLM), so the deterministic
    engine is the default and the LLM grounding path is an explicit opt-out
    (``CACHET_DETERMINISTIC_VERIFY=0/false/no``). Unset -> deterministic. The
    decision lives here, at the surface, not in the verify orchestrator: a direct
    caller of ``verify_draft`` keeps the conservative legacy default, while the
    production route defaults safe for the privacy product.
    """
    return os.getenv("CACHET_DETERMINISTIC_VERIFY", "").strip().lower() not in {"0", "false", "no"}


@router.post("/api/verify", response_model=VerifyResponse)
def verify_endpoint(payload: VerifyRequest) -> Dict[str, Any]:
    with db.get_db() as conn:
        result = verify_service.verify_draft(
            conn,
            payload.draft,
            doc_ids=payload.doc_ids,
            subject_name=payload.subject_name,
            deterministic=_deterministic_surface_default(),
            log_study_event=log_study_event,
            fetch_recent_events=fetch_recent_events,
        )
        return verify_service.verify_result_to_payload(result)


@router.post("/api/verify/stream")
def verify_stream_endpoint(payload: VerifyRequest) -> StreamingResponse:
    """Stream verification verdicts as Server-Sent Events.

    Mirrors POST /api/verify but emits the per-cite labor incrementally so
    the UI can show it happening: a ``progress`` event, a ``claims``
    skeleton, one ``cite_verdict`` per claim, then a final ``result``
    carrying the same payload as POST /api/verify. Each event is
    ``data: {json}\\n\\n``; the stream ends with ``data: [DONE]\\n\\n``. On
    failure, one ``{"type": "error", "error": "..."}`` event is emitted
    before close (errors surfaced, not swallowed, per "no silent fallbacks").
    The client parses this via ``frontend/src/services/api/streaming.ts``.
    """

    def event_stream() -> Iterator[str]:
        try:
            with db.get_db() as conn:
                for event in verify_service.verify_draft_stream(
                    conn,
                    payload.draft,
                    doc_ids=payload.doc_ids,
                    subject_name=payload.subject_name,
                    deterministic=_deterministic_surface_default(),
                    log_study_event=log_study_event,
                    fetch_recent_events=fetch_recent_events,
                ):
                    yield f"data: {json.dumps(event)}\n\n"
        except Exception:  # noqa: BLE001 - surface, don't swallow
            LOGGER.exception("verify stream failed")
            yield f"data: {json.dumps({'type': 'error', 'error': 'Verification failed.'})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


def _extractor_label(asset: Any) -> str:
    """Name the extraction identity honestly. OCR fidelity is a materially
    different trust statement than embedded text, so the mode is included
    (e.g. "pdf:native_text" vs "pdf:docling-rapidocr")."""
    modes = list(getattr(asset.quality, "extraction_modes", None) or [])
    detected = str(getattr(asset, "detected_type", "") or "file")
    return f"{detected}:{'+'.join(modes)}" if modes else detected


@router.post("/api/verify/extract-draft", response_model=DraftExtractionResponse)
async def extract_draft_endpoint(file: UploadFile = File(...)) -> Dict[str, Any]:
    """Extract the text of an uploaded DOCUMENT so it can be verified as a draft.

    This is NOT an upload: nothing is persisted. It reuses the same extraction
    path as sources but stores no document row and no file, because a draft
    that entered the retrieval corpus could verify against itself (a structural
    false green). The response carries the extracted text (the read-back and
    the verify input), both artifact hashes (raw bytes + extracted text), and
    the named extractor. An unreadable or empty document refuses explicitly;
    it never returns a silent empty draft.

    Zero-egress holds: extraction is local (PDFKit/Vision/docling), no network,
    no LLM.
    """
    suffix = validate_upload_suffix(file.filename)
    # A private temp file, NOT db.UPLOAD_DIR (the persistent source store). It
    # is deleted in `finally` no matter what, so nothing survives the request.
    tmp_dir = tempfile.mkdtemp(prefix="cachet-draft-")
    path = Path(tmp_dir) / f"draft{suffix}"
    try:
        await save_upload_bounded(file, path)
        try:
            asset = extraction_pipeline.extract_asset(path)
        except HTTPException as exc:
            # extract_asset raises 400 when no grounded text could be read. The
            # honesty law: refuse explicitly with a concrete reason, never a
            # silent empty draft.
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "extraction_failed",
                    "message": str(exc.detail),
                },
            ) from exc
        except Exception as exc:  # noqa: BLE001 - surface, don't swallow
            log_event(
                LOGGER,
                30,
                "extract_draft_failed",
                filename=file.filename or "",
                error=str(exc),
            )
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "extraction_failed",
                    "message": "Could not read this document as text.",
                },
            ) from exc

        draft_text = str(asset.cleaned_text or asset.raw_text or "").strip()
        sentences = split_sentences(draft_text)
        if not draft_text or not sentences:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "no_checkable_text",
                    "message": "This document has no checkable text to verify.",
                },
            )
        return {
            "draft_text": draft_text,
            # asset.content_hash is file_sha(path): sha256 over the raw bytes.
            "draft_file_sha256": str(asset.content_hash),
            "draft_sha256": text_sha(draft_text),
            "extractor": _extractor_label(asset),
            "chars": len(draft_text),
            "sentences": len(sentences),
        }
    finally:
        # Persist nothing: the draft never becomes a source and never touches
        # the retrieval corpus.
        path.unlink(missing_ok=True)
        try:
            Path(tmp_dir).rmdir()
        except OSError:
            pass


def register_verify_routes(app) -> None:
    app.include_router(router)
