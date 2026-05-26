"""Carrel V2 Stage 1 — Verify-mode route.

POST /api/verify takes a draft (brief, memo, paragraph) and returns a
per-claim verdict surface. Thin wrapper over
`services.verify.verify_draft`; the engine work happens there.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

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


def register_verify_routes(app) -> None:
    app.include_router(router)
