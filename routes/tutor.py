import json
import re
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

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
from services import adaptive_tutor as adaptive_tutor_service
from services import mastery_engine
from services import provenance_service
from services import tutor as tutor_service
from services.app_state import fetch_recent_events, fetch_workspace_state, load_messages, log_study_event
from services.helpers import concept_takeaway, split_sentences
from services.ingestion import build_concept_payloads, summarize_document


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
def expand_note(payload: NoteExpandRequest) -> Dict[str, str]:
    content = (payload.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Content is required.")

    title = (payload.title or "").strip() or "Expanded Notes"
    summary = summarize_document(content, max_sentences=3)
    concepts = build_concept_payloads(content, title, limit=5)
    sentences = split_sentences(content)

    lines = [
        f"# {title}",
        "",
        "## Summary",
        summary or "Review the note once, then restate the main idea in your own words.",
    ]

    if concepts:
        lines.extend(["", "## Key Ideas"])
        for concept in concepts[:5]:
            description = str(concept.get("description") or concept.get("summary") or concept["name"])
            lines.append(f"- **{concept['name']}**: {concept_takeaway(description)}")

    if sentences:
        lines.extend(["", "## Organized Notes"])
        for index, sentence in enumerate(sentences[:6], start=1):
            lines.append(f"{index}. {sentence}")

    review_prompts = [
        f"How would you explain **{concept['name']}** without looking?" for concept in concepts[:3]
    ]
    if not review_prompts:
        review_prompts = [
            "What is the single most important idea in this note?",
            "Which part would you want to practice from memory next?",
        ]
    lines.extend(["", "## Review Prompts", *[f"- {prompt}" for prompt in review_prompts]])
    return {"expanded_markdown": "\n".join(lines).strip()}


@router.post("/api/dialogue/start")
def dialogue_start(payload: DialogueStartRequest) -> Dict[str, object]:
    with db.get_db() as conn:
        concept = None
        if payload.concept_id:
            concept = conn.execute(
                "SELECT id, name FROM concepts WHERE id = ?",
                (payload.concept_id,),
            ).fetchone()
        if not concept:
            concept = conn.execute(
                "SELECT id, name FROM concepts ORDER BY mastery ASC LIMIT 1"
            ).fetchone()
        session_id = str(uuid.uuid4())
        opening = f"What do you already know about {concept['name']}?"
        conn.execute(
            """
            INSERT INTO dialogue_sessions (id, concept_id, messages, misconceptions, final_understanding)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session_id,
                concept["id"],
                json.dumps([{"role": "assistant", "content": opening}]),
                json.dumps([]),
                None,
            ),
        )
        conn.commit()
        log_study_event(conn, "dialogue_started", concept_id=concept["id"], payload={"opening": opening})
        return {"session_id": session_id, "opening_prompt": opening}


@router.post("/api/dialogue/message")
def dialogue_message(payload: DialogueMessageRequest) -> Dict[str, object]:
    with db.get_db() as conn:
        session = None
        if payload.session_id:
            session = conn.execute(
                "SELECT id, concept_id, messages FROM dialogue_sessions WHERE id = ?",
                (payload.session_id,),
            ).fetchone()

        if not session:
            concept = None
            if payload.concept_id:
                concept = conn.execute("SELECT id FROM concepts WHERE id = ?", (payload.concept_id,)).fetchone()
            if not concept:
                concept = conn.execute("SELECT id FROM concepts ORDER BY mastery ASC LIMIT 1").fetchone()
            session_id = str(uuid.uuid4())
            session = {"id": session_id, "concept_id": concept["id"], "messages": "[]"}
            conn.execute(
                """
                INSERT INTO dialogue_sessions (id, concept_id, messages, misconceptions, final_understanding)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, concept["id"], "[]", json.dumps([]), None),
            )

        concept = conn.execute(
            "SELECT id, name, description, mastery FROM concepts WHERE id = ?",
            (session["concept_id"],),
        ).fetchone()
        reply = (
            f"Before we jump to the answer, what is one clue from your document that points to {concept['name']}? "
            "If you're unsure, compare it to a related idea and tell me what changes."
        )
        messages = load_messages(session["messages"])
        messages.extend(
            [
                {"role": "user", "content": payload.message},
                {"role": "assistant", "content": reply},
            ]
        )
        understanding = 4 if len(payload.message.split()) > 20 else 2
        conn.execute(
            """
            UPDATE dialogue_sessions
            SET messages = ?, final_understanding = ?
            WHERE id = ?
            """,
            (json.dumps(messages), understanding, session["id"]),
        )
        conn.commit()
        log_study_event(
            conn,
            "dialogue_message",
            concept_id=session["concept_id"],
            confidence=70.0 if understanding >= 4 else 45.0,
            payload={"understanding": understanding},
        )
        return {"reply": reply, "understanding": understanding, "session_id": session["id"]}


def register_tutor_routes(app) -> None:
    app.include_router(router)
