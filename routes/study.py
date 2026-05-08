from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

import db
from ai.providers import get_default_provider
from api_models import (
    BulkDeleteCardsRequest,
    CardAiDraftRequest,
    CardAiDraftResponse,
    CardCreateRequest,
    FlashcardDraftRequest,
    FlashcardDraftResponse,
    QuizGenerateRequest,
    ReviewEventRequestV2,
    ReviewRequest,
)
from services import extraction_pipeline
from services import ingestion as ingestion_service
from services import review_scheduler as review_service
from services import study as study_service
from services import tutor as tutor_service
from services.app_state import fetch_due_queue_v2, log_study_event


router = APIRouter()


def _rating_to_score(rating: str) -> int:
    normalized = (rating or "").strip().lower()
    mapping = {"again": 1, "hard": 2, "good": 3, "easy": 4}
    return mapping.get(normalized, 2)


@router.get("/api/quiz/questions")
def get_quiz_questions() -> Dict[str, List[Dict[str, object]]]:
    with db.get_db() as conn:
        return {"questions": study_service.fetch_questions(conn)}


@router.post("/api/quiz/generate")
def generate_quiz(payload: QuizGenerateRequest) -> Dict[str, List[Dict[str, object]]]:
    with db.get_db() as conn:
        questions = study_service.fetch_questions(conn, limit=max(payload.count, 1))
        if payload.concepts:
            questions = [item for item in questions if item["concept"] in payload.concepts]
        if payload.difficulty:
            questions = [item for item in questions if item["difficulty"].lower() == payload.difficulty.lower()]
        return {"questions": questions[: payload.count]}


@router.post("/api/flashcards/draft", response_model=FlashcardDraftResponse)
def draft_flashcards(payload: FlashcardDraftRequest) -> Dict[str, Any]:
    title = (payload.title or "").strip() or "General"
    content = (payload.content or "").strip()
    chunk_rows: List[Dict[str, Any]] = []
    if payload.source_scope:
        with db.get_db() as conn:
            doc_placeholders = ",".join("?" * len(payload.source_scope))
            docs = conn.execute(
                f"""
                SELECT id, filename, storage_name
                FROM documents
                WHERE id IN ({doc_placeholders})
                ORDER BY rowid ASC
                """,
                tuple(payload.source_scope),
            ).fetchall()
            fresh_chunks: List[Dict[str, Any]] = []
            for doc in docs:
                storage_name = str(doc["storage_name"] or "").strip()
                if not storage_name:
                    continue
                candidate_path = db.UPLOAD_DIR / storage_name
                if not candidate_path.exists():
                    continue
                try:
                    asset = extraction_pipeline.extract_asset(candidate_path)
                except HTTPException:
                    continue
                fresh_chunks.extend(
                    {
                        "id": f"{doc['id']}::{index}",
                        "content": chunk.content,
                        "section": chunk.section,
                        "page_num": chunk.page_num,
                        "chunk_index": chunk.chunk_index,
                        "doc_id": doc["id"],
                    }
                    for index, chunk in enumerate(asset.chunks, start=1)
                    if str(chunk.content or "").strip()
                )
            if fresh_chunks:
                chunk_rows = fresh_chunks[:240]
            else:
                rows = conn.execute(
                    f"""
                    SELECT id, content, section, page_num, chunk_index, doc_id
                    FROM chunks
                    WHERE doc_id IN ({doc_placeholders})
                    ORDER BY doc_id ASC, chunk_index ASC
                    LIMIT 240
                    """,
                    tuple(payload.source_scope),
                ).fetchall()
                chunk_rows = [dict(row) for row in rows]
            if not content:
                content = "\n\n".join(
                    str(chunk.get("content") or "").strip()
                    for chunk in chunk_rows
                    if str(chunk.get("content") or "").strip()
                )
    if not content and not chunk_rows:
        raise HTTPException(status_code=400, detail="Content or source_scope is required.")

    if not chunk_rows:
        chunk_rows = [
            {
                "id": f"manual-{index}",
                "content": chunk,
                "section": title,
                "page_num": None,
                "chunk_index": index,
                "doc_id": None,
            }
            for index, chunk in enumerate(ingestion_service.chunk_text(content), start=1)
            if str(chunk or "").strip()
        ]

    cards = ingestion_service.build_flashcard_deck(chunk_rows, title=title, count=payload.count)
    if not cards and content:
        transformed = tutor_service.transform_note_content(content)
        cards = [
            {
                "q": str(item.get("front") or "").strip(),
                "a": str(item.get("back") or "").strip(),
                "type": "definition",
                "confidence": 0.42,
                "topic": title,
                "supporting_chunk_ids": [],
                "grounding_mode": "internal_only",
                "show_citations": False,
            }
            for item in transformed.get("flashcards", [])
            if item.get("front") and item.get("back")
        ][: max(1, min(payload.count, 16))]
    return {"cards": cards[: max(1, min(payload.count, 16))]}


@router.get("/api/srs/due")
def due_cards(
    subject: Optional[str] = None,
    doc_id: Optional[str] = None,
) -> Dict[str, List[Dict[str, object]]]:
    """Cards due for review, optionally scoped to one subject or doc.

    Both filters AND together. Omit both to get the full due queue.
    Mirrors the filter shape on /api/srs/cards so the Manage view and
    the Review session share a vocabulary.
    """
    with db.get_db() as conn:
        return {
            "cards": study_service.fetch_due_cards(
                conn,
                subject=subject,
                doc_id=doc_id,
            )
        }


@router.get("/api/srs/cards")
def list_cards(
    subject: Optional[str] = None,
    doc_id: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> Dict[str, Any]:
    """List flashcards for the Manage Cards view.

    Filters stack — subject + search + doc_id all AND together. Paged so the
    UI can render 857-card libraries without shipping the whole thing in one
    response.
    """
    with db.get_db() as conn:
        return study_service.list_cards(
            conn,
            subject=subject,
            doc_id=doc_id,
            search=search,
            limit=limit,
            offset=offset,
        )


@router.get("/api/srs/subjects")
def list_subjects() -> Dict[str, List[Dict[str, object]]]:
    """Subjects aggregated with card + due counts for filter chips."""
    with db.get_db() as conn:
        return {"subjects": study_service.list_subjects(conn)}


_AI_DRAFT_CARDS_TOOL: Dict[str, Any] = {
    "name": "submit_flashcard_drafts",
    "description": "Produce a batch of study flashcards on the user's topic.",
    "input_schema": {
        "type": "object",
        "properties": {
            "cards": {
                "type": "array",
                "minItems": 1,
                "maxItems": 20,
                "items": {
                    "type": "object",
                    "properties": {
                        "front": {
                            "type": "string",
                            "description": (
                                "A clear, atomic question or prompt. One idea "
                                "per card. End with a question mark when it is "
                                "a question. Prefer 'How does ... ?' or "
                                "'Why does ... ?' over 'What is ... ?'."
                            ),
                        },
                        "back": {
                            "type": "string",
                            "description": (
                                "The answer. 1 to 3 sentences. Concrete. "
                                "Include a real example or a number when the "
                                "concept has one."
                            ),
                        },
                    },
                    "required": ["front", "back"],
                },
            }
        },
        "required": ["cards"],
    },
}

_AI_DRAFT_CARDS_SYSTEM = (
    "You write rigorous flashcards for a serious learner.\n\n"
    "Non-negotiables:\n"
    "1. Atomic cards. Each card tests ONE idea. If a concept has multiple "
    "parts, split it into multiple cards.\n"
    "2. Test understanding, not definitions. Prefer 'How does X change when "
    "Y shifts?' over 'What is X?'. A pure vocab card is acceptable only "
    "when the term is genuinely worth memorising.\n"
    "3. Back answers are concrete. 1-3 sentences. Use real examples, real "
    "numbers, real names when the concept has them.\n"
    "4. No hedging language: essentially, basically, in essence.\n"
    "5. Do not use: delve, crucial, comprehensive, robust, nuanced, "
    "multifaceted, furthermore, moreover, additionally, pivotal, landscape, "
    "tapestry, underscore, foster, showcase, intricate, vibrant, "
    "fundamental, significant, interplay. Do not use em dashes.\n"
    "6. Fronts and backs stand alone. A card's front cannot reference "
    "'the previous card' or 'the next one'.\n"
    "7. Do not repeat the same concept across two cards in the batch. "
    "Vary angles: definition, mechanism, edge case, comparison, example.\n\n"
    "Output the requested number of cards via the submit_flashcard_drafts "
    "tool. No meta-commentary."
)


def _drafts_from_ai(topic: str, context: Optional[str], count: int) -> Dict[str, Any]:
    """Call the configured provider. Returns the response-shape dict: status,
    cards, optional error. Mirrors the notes.expand contract so the UI can
    handle AI failures with a consistent vocabulary.
    """
    provider = get_default_provider()
    if not provider.ai_enabled():
        return {"status": "ai_disabled", "cards": [], "error": None}

    prompt_parts = [f"Topic: {topic.strip()}"]
    if context:
        prompt_parts.append(f"\nSupporting context from the user:\n{context.strip()}")
    prompt_parts.append(f"\nGenerate exactly {count} flashcards.")
    prompt = "\n".join(prompt_parts)

    result = provider.request_tool_call(
        request_kind="srs.ai_draft",
        system=_AI_DRAFT_CARDS_SYSTEM,
        prompt=prompt,
        tool=_AI_DRAFT_CARDS_TOOL,
        max_tokens=2400,
        task="fast",
    )
    if not result.ok or not isinstance(result.json_payload, dict):
        return {
            "status": "ai_failed",
            "cards": [],
            "error": result.error_code or "unknown",
        }
    raw_cards = result.json_payload.get("cards")
    if not isinstance(raw_cards, list):
        return {"status": "ai_failed", "cards": [], "error": "malformed_payload"}

    cleaned: List[Dict[str, str]] = []
    for item in raw_cards:
        if not isinstance(item, dict):
            continue
        front = str(item.get("front") or "").strip()
        back = str(item.get("back") or "").strip()
        if not front or not back:
            continue
        # Belt-and-braces against truncated fields; sane upper bound that
        # matches the CardCreateRequest server-side validation.
        if len(front) > 4000 or len(back) > 4000:
            continue
        cleaned.append({"front": front, "back": back})
    if not cleaned:
        return {"status": "ai_failed", "cards": [], "error": "no_valid_cards"}
    return {"status": "ok", "cards": cleaned[:count], "error": None}


@router.post("/api/srs/cards/ai-draft", response_model=CardAiDraftResponse)
def ai_draft_cards(payload: CardAiDraftRequest) -> Dict[str, Any]:
    """Generate flashcard drafts for a topic. The New Card dialog's
    "Generate with AI" mode posts here. The user then edits and bulk-saves
    selected drafts via /api/srs/cards, one card per save.
    """
    # Clamp count server-side even though the schema already bounds it;
    # keeps the LLM call bounded if a client ever sends a larger value.
    count = max(1, min(payload.count or 5, 10))
    result = _drafts_from_ai(payload.topic, payload.context, count)
    return result


@router.post("/api/srs/cards")
def create_card(payload: CardCreateRequest) -> Dict[str, Any]:
    """Create a flashcard from the Manage Cards "New card" dialog.

    The dialog posts raw front + back text (required). concept_id is
    optional: orphan cards are allowed and show up in the All-subjects
    filter. We return the new row in the same shape list_cards emits so
    the client can drop it straight into its cached list without a
    round-trip.
    """
    try:
        with db.get_db() as conn:
            card = study_service.create_card(
                conn,
                front=payload.front,
                back=payload.back,
                concept_id=payload.concept_id,
                card_type=payload.card_type,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"card": card}


@router.delete("/api/srs/cards/{card_id}")
def delete_card(card_id: str) -> Dict[str, object]:
    """Delete a single card. 404 when it's already gone so the client can
    distinguish stale UI from a silent noop."""
    with db.get_db() as conn:
        deleted = study_service.delete_card(conn, card_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Card not found")
        conn.commit()
        return {"deleted": 1}


@router.post("/api/srs/cards/bulk-delete")
def bulk_delete_cards(payload: BulkDeleteCardsRequest) -> Dict[str, object]:
    """Delete many cards in one transaction. Returns the actual row count
    deleted, which can be less than len(payload.ids) if some were already
    gone — no error in that case, just an accurate count."""
    with db.get_db() as conn:
        deleted = study_service.bulk_delete_cards(conn, payload.ids)
        conn.commit()
        return {"deleted": deleted}


@router.post("/api/srs/review")
def review_card(payload: ReviewRequest) -> Dict[str, object]:
    rating = _rating_to_score(payload.rating)
    with db.get_db() as conn:
        # LEFT JOIN (not INNER) so orphan cards — the ones users create via
        # the New Card dialog with concept_id=NULL — are found here. Prior
        # INNER JOIN silently returned no rows and this endpoint raised 404
        # on every rating attempt against a user-authored card.
        row = conn.execute(
            """
            SELECT s.id, s.difficulty, s.stability, s.reps, s.lapses, s.concept_id,
                   c.mastery
            FROM srs_cards s
            LEFT JOIN concepts c ON s.concept_id = c.id
            WHERE s.id = ?
            """,
            (payload.card_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Card not found")

        difficulty = float(row["difficulty"] or 0.3)
        stability = float(row["stability"] or 1.0)
        reps = int(row["reps"] or 0) + 1
        lapses = int(row["lapses"] or 0) + (1 if rating < 3 else 0)

        if rating < 3:
            next_interval = 1
            stability = 1.0
        elif stability <= 1.0:
            next_interval = 3
            stability = 2.2
        else:
            multiplier = 1.2 if rating == 3 else 1.45
            next_interval = max(2, round(stability * multiplier))
            stability = round(stability * multiplier, 2)

        mastery_delta = 0.08 if rating >= 3 else -0.06
        # Orphan cards carry no concept, so no mastery value to update.
        # Keep new_mastery set for the response payload below (None means
        # the frontend can ignore it) and skip the concepts UPDATE.
        concept_id = row["concept_id"]
        prior_mastery = row["mastery"]
        new_mastery: float | None = None
        if concept_id is not None and prior_mastery is not None:
            new_mastery = min(
                1.0,
                max(0.05, round(float(prior_mastery) + mastery_delta, 2)),
            )
        next_due = date.today() + timedelta(days=next_interval)

        conn.execute(
            """
            UPDATE srs_cards
            SET state = ?, stability = ?, difficulty = ?, reps = ?, lapses = ?,
                elapsed_days = ?, scheduled_days = ?, due_date = ?, last_review = ?
            WHERE id = ?
            """,
            (
                "review" if rating >= 3 else "relearning",
                stability,
                difficulty,
                reps,
                lapses,
                0,
                next_interval,
                next_due.isoformat(),
                datetime.now(timezone.utc).isoformat(),
                payload.card_id,
            ),
        )
        if concept_id is not None and new_mastery is not None:
            conn.execute(
                "UPDATE concepts SET mastery = ?, last_tested = ? WHERE id = ?",
                (new_mastery, datetime.now(timezone.utc).isoformat(), concept_id),
            )
        conn.commit()
        log_study_event(
            conn,
            "card_reviewed",
            concept_id=concept_id,
            confidence=85.0 if rating >= 3 else 38.0,
            payload={"rating": payload.rating, "interval": next_interval},
        )
        return {"next_due_date": next_due.isoformat(), "interval": next_interval, "ease": stability}


@router.get("/api/review/queue")
def review_queue(
    goal_id: Optional[str] = None,
    source_ids: Optional[List[str]] = Query(default=None),
    session_id: Optional[str] = None,
    include_missed: bool = True,
) -> Dict[str, Any]:
    with db.get_db() as conn:
        queue = fetch_due_queue_v2(
            conn,
            goal_id=goal_id,
            source_ids=source_ids,
            session_id=session_id,
            include_missed=include_missed,
        )
        return {"items": queue}


@router.post("/api/review/events")
def review_event(payload: ReviewEventRequestV2) -> Dict[str, Any]:
    with db.get_db() as conn:
        result = review_service.record_review_event(
            conn,
            item_id=payload.item_id,
            item_kind=payload.item_kind,
            outcome=payload.outcome,
            classification=payload.classification,
            confidence=payload.confidence,
            duration_seconds=payload.duration_seconds,
            goal_id=payload.goal_id,
            session_id=payload.session_id,
        )
        log_study_event(
            conn,
            "review_event_v2",
            concept_id=result["next_action"]["concept_id"],
            confidence=payload.confidence,
            duration_seconds=payload.duration_seconds,
            payload={
                "item_id": payload.item_id,
                "item_kind": payload.item_kind,
                "outcome": payload.outcome,
                "classification": payload.classification,
            },
        )
        conn.commit()
        return result


def register_study_routes(app) -> None:
    app.include_router(router)
