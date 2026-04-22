from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query

import db
from api_models import SynthesisRunRequest
from services import documents as document_service
from services import synthesis as synthesis_service
from services.app_state import log_study_event


router = APIRouter()


@router.post("/api/synthesis/run")
def synthesis_run(payload: SynthesisRunRequest) -> Dict[str, Any]:
    with db.get_db() as conn:
        result = synthesis_service.run_synthesis(
            conn,
            source_ids=payload.source_ids,
            synthesis_type=payload.synthesis_type,
        )
        log_study_event(conn, "synthesis_run", payload={"synthesis_type": payload.synthesis_type})
        return result


@router.get("/api/synthesis/contradictions")
def synthesis_contradictions(
    source_ids: Optional[List[str]] = Query(default=None),
) -> Dict[str, Any]:
    with db.get_db() as conn:
        docs = document_service.fetch_documents(conn)
        ids = source_ids or [d["id"] for d in docs]
        contradictions = synthesis_service.detect_contradictions(conn, ids)
        return {"contradictions": contradictions}


def register_synthesis_routes(app) -> None:
    app.include_router(router)
