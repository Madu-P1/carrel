from typing import Any, Dict

from fastapi import APIRouter, HTTPException

import db
from api_models import StudioGenerateRequest
from services import artifact_studio as studio_service
from services.app_state import log_study_event


router = APIRouter()


@router.post("/api/studio/generate")
def studio_generate(payload: StudioGenerateRequest) -> Dict[str, Any]:
    with db.get_db() as conn:
        artifact = studio_service.generate_artifact(
            conn,
            artifact_kind=payload.artifact_kind,
            source_ids=payload.source_scope,
            concept_ids=payload.concept_scope,
            goal_id=payload.goal_id,
            session_id=payload.session_id,
            audience=payload.audience,
            difficulty=payload.difficulty,
            depth=payload.depth,
            style=payload.style,
            output_length=payload.output_length,
            evidence_strictness=payload.evidence_strictness,
            custom_prompt=payload.custom_prompt,
            grounding_mode=payload.grounding_mode,
            show_citations=payload.show_citations,
        )
        log_study_event(conn, "artifact_generated", payload={"artifact_kind": payload.artifact_kind})
        return {"artifact": artifact}


@router.get("/api/studio/artifacts")
def studio_list_artifacts(limit: int = 10) -> Dict[str, Any]:
    with db.get_db() as conn:
        return {"artifacts": studio_service.list_artifacts(conn, limit=limit)}


@router.get("/api/studio/artifacts/{artifact_id}")
def studio_get_artifact(artifact_id: str) -> Dict[str, Any]:
    with db.get_db() as conn:
        artifact = studio_service.get_artifact(conn, artifact_id)
        if not artifact:
            raise HTTPException(status_code=404, detail="Artifact not found")
        return artifact


def register_studio_routes(app) -> None:
    app.include_router(router)
