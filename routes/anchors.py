from __future__ import annotations

import re
from typing import Any, Dict, List

from fastapi import APIRouter, FastAPI, HTTPException, Query

import db
from api_models import (
    AnchorCardDraftRequest,
    AnchorCreateRequest,
    AnchorPromotionRequest,
    AnchorTransitionRequest,
)
from services import anchors as anchor_service
from services import ingestion as ingestion_service
from services import study as study_service


router = APIRouter()


def _anchor_to_dict(anchor: anchor_service.Anchor) -> Dict[str, Any]:
    return {
        "id": anchor.id,
        "document_id": anchor.document_id,
        "chunk_id": anchor.chunk_id,
        "page_num": anchor.page_num,
        "bbox": anchor.bbox,
        "text_offset_start": anchor.text_offset_start,
        "text_offset_end": anchor.text_offset_end,
        "quote_text": anchor.quote_text,
        "user_question": anchor.user_question,
        "claim_text": anchor.claim_text,
        "origin": anchor.origin,
        "promotion_state": anchor.promotion_state,
        "srs_card_id": anchor.srs_card_id,
        "thread_id": anchor.thread_id,
        "confidence": anchor.confidence,
        "citations_out": anchor.citations_out,
        "created_at": anchor.created_at,
        "updated_at": anchor.updated_at,
    }


def _normalize_for_duplicate(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", value.lower())).strip()


@router.post("/api/anchors")
def create_anchor(payload: AnchorCreateRequest) -> Dict[str, Any]:
    try:
        with db.get_db() as conn:
            anchor = anchor_service.create_anchor(
                conn,
                document_id=payload.document_id,
                quote_text=payload.quote_text,
                origin=payload.origin,  # type: ignore[arg-type]
                promotion_state=payload.promotion_state,  # type: ignore[arg-type]
                chunk_id=payload.chunk_id,
                page_num=payload.page_num,
                bbox=payload.bbox,
                text_offset_start=payload.text_offset_start,
                text_offset_end=payload.text_offset_end,
                user_question=payload.user_question,
                claim_text=payload.claim_text,
                thread_id=payload.thread_id,
                confidence=payload.confidence,
            )
            conn.commit()
            return {"anchor": _anchor_to_dict(anchor)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/anchors/document/{document_id}")
def list_document_anchors(
    document_id: str,
    page_num: int | None = Query(default=None),
) -> Dict[str, List[Dict[str, Any]]]:
    with db.get_db() as conn:
        anchors = anchor_service.list_anchors_for_document(
            conn,
            document_id,
            page_num=page_num,
        )
        return {"anchors": [_anchor_to_dict(anchor) for anchor in anchors]}


@router.post("/api/anchors/{anchor_id}/transition")
def transition_anchor(anchor_id: str, payload: AnchorTransitionRequest) -> Dict[str, Any]:
    try:
        with db.get_db() as conn:
            anchor = anchor_service.transition_state(
                conn,
                anchor_id,
                payload.promotion_state,  # type: ignore[arg-type]
                srs_card_id=payload.srs_card_id,
            )
            conn.commit()
            return {"anchor": _anchor_to_dict(anchor)}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Anchor not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/anchors/{anchor_id}/draft-cards")
def draft_anchor_cards(anchor_id: str, payload: AnchorCardDraftRequest) -> Dict[str, Any]:
    with db.get_db() as conn:
        anchor = anchor_service.get_anchor(conn, anchor_id)
        if anchor is None:
            raise HTTPException(status_code=404, detail="Anchor not found")
        chunk = None
        if anchor.chunk_id:
            chunk = conn.execute(
                """
                SELECT id, content, section, page_num, chunk_index, doc_id
                FROM chunks
                WHERE id = ?
                """,
                (anchor.chunk_id,),
            ).fetchone()
        chunk_rows = [
            dict(chunk)
            if chunk
            else {
                "id": anchor.id,
                "content": anchor.quote_text,
                "section": "Anchor",
                "page_num": anchor.page_num,
                "chunk_index": 0,
                "doc_id": anchor.document_id,
            }
        ]
        drafts = ingestion_service.build_flashcard_deck(
            chunk_rows,
            title=anchor.claim_text or anchor.quote_text[:80] or "Anchor",
            count=payload.count,
        )
        if not drafts:
            drafts = [
                {
                    "q": f"What does this source passage establish: {anchor.quote_text[:120]}?",
                    "a": anchor.claim_text or anchor.quote_text,
                    "type": "anchor",
                    "confidence": anchor.confidence or 0.6,
                    "topic": "Anchor",
                    "supporting_chunk_ids": [anchor.chunk_id] if anchor.chunk_id else [],
                }
            ]
        cards = study_service.list_cards(conn, doc_id=anchor.document_id, limit=500)
        card_rows = cards.get("cards", [])
        if not isinstance(card_rows, list):
            card_rows = []
        existing_norms = {
            _normalize_for_duplicate(str(card.get("front") or ""))
            for card in card_rows
            if isinstance(card, dict)
        } | {
            _normalize_for_duplicate(str(card.get("back") or ""))
            for card in card_rows
            if isinstance(card, dict)
        }
        out = []
        for draft in drafts[: payload.count]:
            front = str(draft.get("q") or draft.get("front") or "").strip()
            back = str(draft.get("a") or draft.get("back") or "").strip()
            norm = _normalize_for_duplicate(front)
            out.append(
                {
                    "front": front,
                    "back": back,
                    "duplicate_warning": bool(norm and norm in existing_norms),
                    "source_anchor_id": anchor.id,
                    "supporting_chunk_ids": draft.get("supporting_chunk_ids") or [],
                }
            )
        return {"cards": out}


@router.post("/api/anchors/{anchor_id}/promote-card")
def promote_anchor_card(anchor_id: str, payload: AnchorPromotionRequest) -> Dict[str, Any]:
    try:
        with db.get_db() as conn:
            anchor = anchor_service.get_anchor(conn, anchor_id)
            if anchor is None:
                raise LookupError("Anchor not found")
            if anchor.promotion_state == "weak":
                anchor_service.transition_state(conn, anchor_id, "saved")
            card = study_service.create_card(
                conn,
                front=payload.front,
                back=payload.back,
                concept_id=payload.concept_id,
                card_type=payload.card_type,
            )
            updated = anchor_service.transition_state(
                conn,
                anchor_id,
                "carded",
                srs_card_id=str(card["id"]),
            )
            conn.commit()
            return {"anchor": _anchor_to_dict(updated), "card": card}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Anchor not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def register_anchor_routes(app: FastAPI) -> None:
    app.include_router(router)
