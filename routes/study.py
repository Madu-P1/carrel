from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

import db
from api_models import (
    BulkDeleteCardsRequest,
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
def due_cards() -> Dict[str, List[Dict[str, object]]]:
    with db.get_db() as conn:
        return {"cards": study_service.fetch_due_cards(conn)}


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
        row = conn.execute(
            """
            SELECT s.id, s.difficulty, s.stability, s.reps, s.lapses, s.concept_id, c.mastery
            FROM srs_cards s
            JOIN concepts c ON s.concept_id = c.id
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
        new_mastery = min(1.0, max(0.05, round(float(row["mastery"]) + mastery_delta, 2)))
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
        conn.execute(
            "UPDATE concepts SET mastery = ?, last_tested = ? WHERE id = ?",
            (new_mastery, datetime.now(timezone.utc).isoformat(), row["concept_id"]),
        )
        conn.commit()
        log_study_event(
            conn,
            "card_reviewed",
            concept_id=row["concept_id"],
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
