from typing import Any, Dict, List, Optional

from fastapi import APIRouter, FastAPI, HTTPException

import db
from api_models import (
    DialogueMessageRequest,
    DialogueStartRequest,
    NoteExpandRequest,
    NoteTransformRequest,
    NoteUpsertRequest,
    TutorExchangeCreateRequest,
    TutorExchangeEvaluateRequest,
    TutorQueryRequest,
    TutorQueryResponse,
)
from ai.providers import get_default_provider
from services import adaptive_tutor as adaptive_tutor_service
from services import dialogue as dialogue_service
from services import provenance_service
from services import tutor as tutor_service
from services.app_state import fetch_recent_events, fetch_workspace_state, log_study_event
from services.notes import expand as notes_expand_service
from services.notes.mastery import maybe_update_note_mastery


router = APIRouter()


@router.post("/api/tutor/query", response_model=TutorQueryResponse)
def tutor_query(payload: TutorQueryRequest) -> Dict[str, Any]:
    with db.get_db() as conn:
        return tutor_service.grounded_tutor_envelope(
            conn,
            payload,
            log_study_event=log_study_event,
            fetch_recent_events=fetch_recent_events,
        )


@router.post("/api/tutor/exchanges")
def tutor_exchange(payload: TutorExchangeCreateRequest) -> Dict[str, Any]:
    with db.get_db() as conn:
        response = adaptive_tutor_service.run_exchange(
            conn,
            payload,
            log_study_event=log_study_event,
            fetch_recent_events=fetch_recent_events,
        )
        conn.commit()
        return response


@router.post("/api/tutor/exchanges/{exchange_id}/evaluate")
def evaluate_tutor_exchange(exchange_id: str, payload: TutorExchangeEvaluateRequest) -> Dict[str, Any]:
    with db.get_db() as conn:
        response = adaptive_tutor_service.evaluate_exchange(
            conn,
            exchange_id,
            learner_response=payload.learner_response,
            mode=payload.mode,
        )
        conn.commit()
        return response


@router.get("/api/notes")
def get_notes(
    doc_id: Optional[str] = None,
    concept_id: Optional[str] = None,
    limit: int = 8,
) -> Dict[str, List[Dict[str, Any]]]:
    with db.get_db() as conn:
        return {"notes": tutor_service.fetch_notes(conn, doc_id=doc_id, concept_id=concept_id, limit=limit)}


@router.post("/api/notes")
def save_note(payload: NoteUpsertRequest) -> Dict[str, Any]:
    with db.get_db() as conn:
        note = tutor_service.upsert_note_record(
            conn,
            payload.note_id,
            payload.doc_id,
            payload.concept_id,
            payload.title,
            payload.content,
            payload.source_snippet,
            payload.note_type,
            payload.goal_id,
            payload.session_id,
        )
        if payload.evidence_reference_ids:
            provenance_service.attach_evidence_to_note(conn, note["id"], payload.evidence_reference_ids)
        mastery_state = None
        concept_id = payload.concept_id or note.get("concept_id")
        if concept_id:
            mastery_state = maybe_update_note_mastery(
                conn,
                concept_id=concept_id,
                content=payload.content,
                evidence_reference_ids=payload.evidence_reference_ids,
                goal_id=payload.goal_id,
                session_id=payload.session_id,
            )
        log_study_event(
            conn,
            "note_saved",
            doc_id=payload.doc_id,
            concept_id=concept_id,
            payload={
                "note_id": note["id"],
                "title": note["title"],
                "note_type": payload.note_type,
                "evidence_count": len(payload.evidence_reference_ids or []),
            },
        )
        return {"note": note, "workspace": fetch_workspace_state(conn), "mastery_state": mastery_state}


@router.post("/api/notes/transform")
def transform_note(payload: NoteTransformRequest) -> Dict[str, Any]:
    with db.get_db() as conn:
        transformed = tutor_service.transform_note_content(payload.content)
        log_study_event(
            conn,
            "note_transformed",
            doc_id=payload.doc_id,
            concept_id=payload.concept_id,
            payload={
                "flashcard_count": len(transformed["flashcards"]),
                "quiz_count": len(transformed["quiz"]),
            },
        )
        return transformed


@router.post("/api/notes/expand")
def expand_note(payload: NoteExpandRequest) -> Dict[str, Optional[str]]:
    content = (payload.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Content is required.")

    title = (payload.title or "").strip() or "Expanded Notes"

    return notes_expand_service.expand_note_content(
        title=title,
        content=content,
        provider_factory=get_default_provider,
    )


@router.post("/api/dialogue/start")
def dialogue_start(payload: DialogueStartRequest) -> Dict[str, object]:
    with db.get_db() as conn:
        try:
            return dialogue_service.start_dialogue(conn, concept_id=payload.concept_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/dialogue/message")
def dialogue_message(payload: DialogueMessageRequest) -> Dict[str, object]:
    with db.get_db() as conn:
        try:
            return dialogue_service.post_message(
                conn,
                session_id=payload.session_id,
                message=payload.message,
                concept_id=payload.concept_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


def register_tutor_routes(app: FastAPI) -> None:
    app.include_router(router)
