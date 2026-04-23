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
from ai.providers import get_default_provider
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


_SUBMIT_EXPANDED_NOTE_TOOL: Dict[str, Any] = {
    "name": "submit_expanded_note",
    "description": "Produce a structured study-notes expansion of a terse user input.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": (
                    "2 to 4 sentences that EXPLAIN the concept. Must add real "
                    "information beyond the user's input. Never a restatement."
                ),
            },
            "key_ideas": {
                "type": "array",
                "minItems": 3,
                "maxItems": 6,
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "1 to 3 word noun phrase, no punctuation.",
                        },
                        "description": {
                            "type": "string",
                            "description": (
                                "1 or 2 sentences that explain the sub-concept "
                                "concretely. Never a reword of the name."
                            ),
                        },
                    },
                    "required": ["name", "description"],
                },
            },
            "organized_notes": {
                "type": "array",
                "minItems": 4,
                "maxItems": 8,
                "items": {"type": "string"},
                "description": (
                    "Study-ready factual bullets in logical order: definition, "
                    "mechanism, examples, edge cases. Each a single sentence."
                ),
            },
            "review_prompts": {
                "type": "array",
                "minItems": 3,
                "maxItems": 5,
                "items": {"type": "string"},
                "description": (
                    "Questions that test comprehension, not name recall. "
                    "Prefer how, why, when, and compare questions."
                ),
            },
        },
        "required": ["summary", "key_ideas", "organized_notes", "review_prompts"],
    },
}

_EXPAND_NOTE_SYSTEM = (
    "You expand rough study notes into rigorous, concrete study material for a "
    "serious learner.\n\n"
    "Non-negotiables:\n"
    "1. Never restate the user's input. If they write \"Bonds are issued by "
    "government bodies,\" your summary is NOT that sentence. It explains what "
    "a bond IS (a debt security, fixed-income instrument), how it works (face "
    "value, coupon, maturity, yield), who else issues them (corporations, "
    "agencies, municipalities), and why it matters.\n"
    "2. Add substance. If the note leaves out an obvious mechanism, add it. "
    "If it implies a partial truth, expand to the fuller picture. If a term "
    "has a standard definition, give that definition.\n"
    "3. Be concrete. Use real examples, real organizations, real numbers, "
    "real timeframes.\n"
    "4. Short sentences. One idea per sentence.\n"
    "5. Do not use: delve, crucial, comprehensive, robust, nuanced, "
    "multifaceted, furthermore, moreover, additionally, pivotal, landscape, "
    "tapestry, underscore, foster, showcase, intricate, vibrant, fundamental, "
    "significant, interplay. Do not use em dashes. Do not hedge with "
    "essentially, basically, in essence.\n"
    "6. Review prompts must be COMPLETE QUESTIONS ending with a question mark. "
    "Four words minimum. Test understanding, not name recall. Prefer \"How "
    "does X change when Y increases?\" over \"What is X?\". NEVER emit a "
    "plain heading like \"Bond Yields\" or a field identifier like "
    "\"yield_and_bond_prices\" as a review prompt. Every prompt is a "
    "grammatical question.\n"
    "7. Organized notes are COMPLETE SENTENCES ending with a period. Not "
    "headings. Not labels. Not outline points. \"Bonds pay fixed coupon "
    "interest until maturity.\" is right. \"Bond Valuation\" is wrong.\n\n"
    "Fill every field of the submit_expanded_note tool."
)


_IDENTIFIER_LOOKALIKE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)+$")
# Matches headings like "Bond Schedules" or "Real-World Examples" that small
# models emit when they slip into outline mode. Each word starts with a
# capital (allowing for hyphenated words), no terminal punctuation, no verbs.
_TITLE_CASE_HEADING = re.compile(
    r"^(?:[A-Z][A-Za-z0-9-]*)(?:[ :][A-Z][A-Za-z0-9-]*){0,5}[A-Za-z0-9]$"
)


def _looks_like_schema_leak(text: str) -> bool:
    """Small models sometimes emit field-name tokens instead of actual content
    (e.g., "concepts_related_to_bonds" as a review prompt). Filter those.
    """
    if not text:
        return True
    return bool(_IDENTIFIER_LOOKALIKE.match(text))


def _is_real_sentence(text: str) -> bool:
    """A proper factual note should be a sentence: multi-word, end in a
    period or question mark. Rejects title-case headings like
    "Government Bonds" or "Real-World Examples" that some small models
    emit when they slip into outline mode.
    """
    if not text or len(text) < 12:
        return False
    if " " not in text:
        return False
    if _TITLE_CASE_HEADING.match(text):
        return False
    return text.endswith((".", "!", "?"))


def _is_real_question(text: str) -> bool:
    """A review prompt must be an actual question. Requires a question mark
    at the end and at least a few words. Catches "Bond Schedules" and
    similar headings that sometimes leak into the prompt list.
    """
    if not text:
        return False
    if not text.endswith("?"):
        return False
    words = text.split()
    return len(words) >= 4


def _format_expansion_markdown(title: str, payload: Dict[str, Any]) -> str:
    """Render the tool payload back into the feature's expected markdown shape.

    Aggressively filters malformed items (empty, identifier-looking tokens)
    rather than letting a model artifact reach the user. If filtering leaves
    a section empty, that section is omitted entirely.
    """
    summary = str(payload.get("summary") or "").strip()
    lines: List[str] = [f"# {title}", "", "## Summary", summary or "No summary produced."]

    key_ideas = payload.get("key_ideas") or []
    if isinstance(key_ideas, list) and key_ideas:
        body: List[str] = []
        for item in key_ideas:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            description = str(item.get("description") or "").strip()
            if not name or not description:
                continue
            if _looks_like_schema_leak(name) or _looks_like_schema_leak(description):
                continue
            body.append(f"- **{name}**: {description}")
        if body:
            lines.extend(["", "## Key Ideas", *body])

    notes = payload.get("organized_notes") or []
    if isinstance(notes, list) and notes:
        body = []
        for note in notes:
            text = str(note).strip()
            if not text or _looks_like_schema_leak(text):
                continue
            # Small models sometimes produce a topic outline ("Government
            # Bonds", "Bond Valuation") instead of factual sentences. Require
            # a real sentence shape before rendering.
            if not _is_real_sentence(text):
                continue
            body.append(text)
        if body:
            lines.extend(["", "## Organized Notes"])
            lines.extend(f"{i}. {note}" for i, note in enumerate(body, start=1))

    prompts = payload.get("review_prompts") or []
    if isinstance(prompts, list) and prompts:
        body = []
        for prompt in prompts:
            text = str(prompt).strip()
            if not text or _looks_like_schema_leak(text):
                continue
            if not _is_real_question(text):
                continue
            body.append(f"- {text}")
        if body:
            lines.extend(["", "## Review Prompts", *body])

    return "\n".join(lines).strip()


def _try_ai_expansion(title: str, content: str) -> Optional[Dict[str, Any]]:
    """Call the configured provider. Returns the tool payload dict on success,
    None on any failure so the caller can fall back to the deterministic path.
    """
    provider = get_default_provider()
    if not provider.ai_enabled():
        return None
    # task="fast" — notes expansion is a structured-output task, not a
    # reasoning task. On Ollama the 8B "balanced" model takes 3-4 minutes
    # on this tool schema (measured in prod logs) and routinely times out.
    # The 3B "fast" model finishes in ~20s with comparable quality for this
    # shape of problem. Callers who want max quality should switch to
    # EINSTEIN_AI_PROVIDER=claude in .env.
    result = provider.request_tool_call(
        request_kind="notes.expand",
        system=_EXPAND_NOTE_SYSTEM,
        prompt=f"Title: {title}\n\nUser's note:\n{content}",
        tool=_SUBMIT_EXPANDED_NOTE_TOOL,
        max_tokens=1600,
        task="fast",
    )
    if not result.ok or not isinstance(result.json_payload, dict):
        return None
    payload = result.json_payload
    # Defensive shape check. The tool schema enforces this, but a model that
    # ignores the schema shouldn't 500 the endpoint.
    required_lists = ("key_ideas", "organized_notes", "review_prompts")
    if not isinstance(payload.get("summary"), str):
        return None
    if any(not isinstance(payload.get(key), list) for key in required_lists):
        return None
    return payload


def _build_deterministic_expansion(title: str, content: str) -> str:
    """Fallback path when AI is disabled or the call fails.

    This is the original Phase 1 logic: extractive summary, heuristic concept
    extraction, sentence split. It does not expand the note with new content,
    it just re-organizes whatever the user typed. Kept so /api/notes/expand
    still returns something usable offline.
    """
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
    return "\n".join(lines).strip()


@router.post("/api/notes/expand")
def expand_note(payload: NoteExpandRequest) -> Dict[str, str]:
    content = (payload.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Content is required.")

    title = (payload.title or "").strip() or "Expanded Notes"

    # Try the LLM path first. The deterministic fallback exists so a disabled
    # provider, rate limit, or schema mismatch never 500s the endpoint; the
    # user still gets something, just less rich.
    ai_payload = _try_ai_expansion(title, content)
    if ai_payload is not None:
        return {"expanded_markdown": _format_expansion_markdown(title, ai_payload)}

    return {"expanded_markdown": _build_deterministic_expansion(title, content)}


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
