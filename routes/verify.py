"""Carrel V2 Stage 1 — Verify-mode route.

POST /api/verify takes a draft (brief, memo, paragraph) and returns a
per-claim verdict surface. Thin wrapper over
`services.verify.verify_draft`; the engine work happens there.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

import db
from api_models import VerifyRequest, VerifyResponse
from services import verify as verify_service
from services.app_state import fetch_recent_events, log_study_event

router = APIRouter()


@router.post("/api/verify", response_model=VerifyResponse)
def verify_endpoint(payload: VerifyRequest) -> Dict[str, Any]:
    with db.get_db() as conn:
        result = verify_service.verify_draft(
            conn,
            payload.draft,
            doc_ids=payload.doc_ids,
            subject_name=payload.subject_name,
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
                    log_study_event=log_study_event,
                    fetch_recent_events=fetch_recent_events,
                ):
                    yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:  # noqa: BLE001 - surface, don't swallow
            yield f"data: {json.dumps({'type': 'error', 'error': str(exc)})}\n\n"
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


def register_verify_routes(app) -> None:
    app.include_router(router)
