import json
import re
from typing import Any, Dict, Iterator, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import db
from ai.streaming import stream_claude_text
from api_models import (
    DialogueMessageRequest,
    DialogueStartRequest,
    NoteExpandRequest,
    NoteFolderCreateRequest,
    NoteFolderUpdateRequest,
    NoteMoveRequest,
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
from services import mastery_engine
from services import note_folders as note_folders_service
from services import provenance_service
from services import tutor as tutor_service
from services.app_state import fetch_recent_events, fetch_workspace_state, log_study_event
from services.notes import expand as notes_expand_service


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


class TutorStreamRequest(BaseModel):
    """Pattern endpoint payload: raw prompt streaming, no RAG or citations.

    Carrel's primary tutor endpoint (``/api/tutor/query``) returns a
    citation-validated envelope. This streaming variant is for
    chat-style follow-ups where the user has already accepted the
    grounded answer and wants to expand, rephrase, or chat. Token-by-
    token streaming keeps the UI responsive on long completions.
    """

    prompt: str = Field(..., min_length=1, max_length=4000)
    system: str = Field(
        "You are a helpful study companion. Be concise and concrete.",
        max_length=2000,
    )
    max_tokens: int = Field(1600, ge=64, le=4096)


@router.post("/api/tutor/query/stream")
def tutor_query_stream(payload: TutorStreamRequest) -> StreamingResponse:
    """Stream raw Claude tokens as Server-Sent Events.

    Each event: ``data: {"text": "<delta>"}\\n\\n``. On failure, one
    event of the shape ``data: {"error": "<message>"}\\n\\n`` is
    emitted before the stream closes. The stream is terminated by
    ``data: [DONE]\\n\\n``. Errors are surfaced, not swallowed, per
    Carrel's "no silent AI fallbacks" rule.

    The client at ``frontend/src/services/api/streaming.ts`` parses
    this shape via ``streamTextDeltas``.
    """

    def event_stream() -> Iterator[str]:
        try:
            for delta in stream_claude_text(
                system=payload.system,
                prompt=payload.prompt,
                max_tokens=payload.max_tokens,
            ):
                yield f"data: {json.dumps({'text': delta})}\n\n"
        except Exception as exc:  # noqa: BLE001 - surface, don't swallow
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
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
def evaluate_tutor_exchange(
    exchange_id: str, payload: TutorExchangeEvaluateRequest
) -> Dict[str, Any]:
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
    folder_id: Optional[str] = None,
    subject_name: Optional[str] = None,
    limit: int = 8,
) -> Dict[str, List[Dict[str, Any]]]:
    """List notes for the Reader's Notes tab AND the global Notes page.

    The global Notes page passes `subject_name` (one of the resolved
    subjects from `/api/notes/organization`) or `folder_id` (a
    concrete folder id, or the literal string "none" for unfoldered
    notes). The Reader keeps using `doc_id`. All three filters compose.
    """

    with db.get_db() as conn:
        return {
            "notes": tutor_service.fetch_notes(
                conn,
                doc_id=doc_id,
                concept_id=concept_id,
                folder_id=folder_id,
                subject_name=subject_name,
                limit=limit,
            )
        }


@router.get("/api/notes/organization")
def get_notes_organization() -> Dict[str, Any]:
    """Composite rail payload for the global Notes page.

    Returns subjects (auto-derived from notes' folders/documents) plus
    each subject's folders with note counts. One round-trip on page
    open beats N parallel fetches.
    """

    with db.get_db() as conn:
        return note_folders_service.fetch_organization(conn)


@router.get("/api/notes/folders")
def list_note_folders(subject_name: Optional[str] = None) -> Dict[str, Any]:
    with db.get_db() as conn:
        return {"folders": note_folders_service.list_folders(conn, subject_name=subject_name)}


@router.post("/api/notes/folders")
def create_note_folder(payload: NoteFolderCreateRequest) -> Dict[str, Any]:
    with db.get_db() as conn:
        folder = note_folders_service.create_folder(
            conn, name=payload.name, subject_name=payload.subject_name
        )
        return {"folder": folder}


@router.patch("/api/notes/folders/{folder_id}")
def update_note_folder(folder_id: str, payload: NoteFolderUpdateRequest) -> Dict[str, Any]:
    with db.get_db() as conn:
        folder = note_folders_service.update_folder(
            conn,
            folder_id,
            name=payload.name,
            subject_name=payload.subject_name,
        )
        return {"folder": folder}


@router.delete("/api/notes/folders/{folder_id}")
def delete_note_folder(folder_id: str) -> Dict[str, Any]:
    with db.get_db() as conn:
        ok = note_folders_service.delete_folder(conn, folder_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Folder not found.")
        return {"deleted": True, "folder_id": folder_id}


@router.patch("/api/notes/{note_id}/folder")
def move_note(note_id: str, payload: NoteMoveRequest) -> Dict[str, Any]:
    """Move a note into a folder (or remove it from its folder).

    Lighter than the full upsert because the client doesn't need to
    re-send title/content/etc. just to refile. The response carries
    the same shape `GET /api/notes` returns so the client can swap the
    row in place.
    """

    with db.get_db() as conn:
        note = tutor_service.move_note_to_folder(conn, note_id, payload.folder_id)
        return {"note": note}


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
            folder_id=payload.folder_id,
        )
        if payload.evidence_reference_ids:
            provenance_service.attach_evidence_to_note(
                conn, note["id"], payload.evidence_reference_ids
            )
        mastery_state = None
        concept_id = payload.concept_id or note.get("concept_id")
        if concept_id:
            content_words = len(re.findall(r"[A-Za-z0-9]+", payload.content or ""))
            evidence_count = len(payload.evidence_reference_ids or [])
            if content_words >= 8:
                mastery_state = mastery_engine.update_mastery_state(
                    conn,
                    concept_id,
                    goal_id=payload.goal_id,
                    session_id=payload.session_id,
                    classification="shallow_but_correct",
                    learner_confidence=min(95, max(45, content_words + evidence_count * 8)),
                    evidence_quality=0.85 if evidence_count else 0.58,
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
        return {
            "note": note,
            "workspace": fetch_workspace_state(conn),
            "mastery_state": mastery_state,
        }


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


def register_tutor_routes(app) -> None:
    app.include_router(router)
