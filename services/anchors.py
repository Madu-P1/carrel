"""Anchor service.

The Anchor is Carrel's atomic unit of learning: evidence tied to a source
with an optional question, an optional claim, and a lifecycle state that can
mature into an SRS card.

This module owns the lifecycle. No feature should INSERT into `anchors`
directly; call `create_anchor()` so every anchor carries a stable shape and
timestamp. Reads go through `get_anchor` / `list_anchors_for_document` so
future optimizations (FTS, caching) don't require refactoring callers.

v1 scope (this file):
  - CRUD on anchors
  - Promotion state transitions: weak -> saved -> carded -> mastered / archived
  - Link to / unlink from an srs_cards row when a card is created/deleted
  - Optional bbox / text-offset location payloads stored as columns, not JSON,
    so the Evidence Inspector fallback hierarchy can SELECT them cheaply.

NOT in v1 (explicitly deferred):
  - Full-text search over quote_text (chunks FTS already covers retrieval;
    anchor search is scoped to a document until the volume demands FTS).
  - citations_out graph traversal helpers. The column exists; no traversal
    UI calls for it yet.
  - Merge / dedupe. Card-draft drawer will handle dedupe at promotion time.

Thread safety: each call takes an existing sqlite3.Connection the caller
opened. Callers that want auto-commit should set conn.isolation_level
appropriately; this module does NOT commit on the caller's behalf (except
where documented) to keep transactional composition clean.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, List, Literal, Optional

AnchorOrigin = Literal["highlight", "ai_answer_citation", "manual", "imported"]
AnchorPromotionState = Literal["weak", "saved", "carded", "mastered", "archived"]

_ALLOWED_ORIGINS: frozenset[str] = frozenset(
    ("highlight", "ai_answer_citation", "manual", "imported")
)
_ALLOWED_STATES: frozenset[str] = frozenset(
    ("weak", "saved", "carded", "mastered", "archived")
)

# Forward transitions we explicitly allow. Backward transitions (e.g. mastered
# -> saved when a user wants to re-promote) go through archive + re-create.
# Keeping the machine one-way simplifies reasoning about analytics.
_VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "weak": frozenset(("saved", "archived")),
    "saved": frozenset(("carded", "archived")),
    "carded": frozenset(("mastered", "archived")),
    "mastered": frozenset(("archived",)),
    "archived": frozenset(),  # terminal
}


@dataclass(frozen=True)
class Anchor:
    """Read-only view of an anchors row. Callers mutate via service calls,
    not by rewriting this dataclass."""

    id: str
    document_id: str
    chunk_id: Optional[str]
    page_num: Optional[int]
    bbox: Optional[List[float]]
    text_offset_start: Optional[int]
    text_offset_end: Optional[int]
    quote_text: str
    user_question: Optional[str]
    claim_text: Optional[str]
    origin: AnchorOrigin
    promotion_state: AnchorPromotionState
    srs_card_id: Optional[str]
    thread_id: Optional[str]
    confidence: Optional[float]
    citations_out: List[str]
    created_at: str
    updated_at: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_anchor(row: sqlite3.Row) -> Anchor:
    bbox_raw = row["bbox"]
    citations_raw = row["citations_out"] or "[]"
    try:
        bbox_parsed: Optional[List[float]] = json.loads(bbox_raw) if bbox_raw else None
    except json.JSONDecodeError:
        bbox_parsed = None
    try:
        citations_parsed = json.loads(citations_raw)
        if not isinstance(citations_parsed, list):
            citations_parsed = []
    except json.JSONDecodeError:
        citations_parsed = []
    return Anchor(
        id=str(row["id"]),
        document_id=str(row["document_id"]),
        chunk_id=str(row["chunk_id"]) if row["chunk_id"] is not None else None,
        page_num=int(row["page_num"]) if row["page_num"] is not None else None,
        bbox=bbox_parsed,
        text_offset_start=(
            int(row["text_offset_start"])
            if row["text_offset_start"] is not None
            else None
        ),
        text_offset_end=(
            int(row["text_offset_end"])
            if row["text_offset_end"] is not None
            else None
        ),
        quote_text=str(row["quote_text"]),
        user_question=row["user_question"],
        claim_text=row["claim_text"],
        origin=str(row["origin"]),  # type: ignore[return-value]
        promotion_state=str(row["promotion_state"]),  # type: ignore[return-value]
        srs_card_id=(
            str(row["srs_card_id"]) if row["srs_card_id"] is not None else None
        ),
        thread_id=(
            str(row["thread_id"]) if row["thread_id"] is not None else None
        ),
        confidence=(
            float(row["confidence"]) if row["confidence"] is not None else None
        ),
        citations_out=[str(x) for x in citations_parsed],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def create_anchor(
    conn: sqlite3.Connection,
    *,
    document_id: str,
    quote_text: str,
    origin: AnchorOrigin,
    promotion_state: AnchorPromotionState = "weak",
    chunk_id: Optional[str] = None,
    page_num: Optional[int] = None,
    bbox: Optional[Iterable[float]] = None,
    text_offset_start: Optional[int] = None,
    text_offset_end: Optional[int] = None,
    user_question: Optional[str] = None,
    claim_text: Optional[str] = None,
    srs_card_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    confidence: Optional[float] = None,
    citations_out: Optional[Iterable[str]] = None,
    anchor_id: Optional[str] = None,
) -> Anchor:
    """Insert a single anchor. Returns the row shape for immediate use.

    Validation:
      - quote_text must be non-empty after trimming.
      - origin must be in the allowed set (CHECK constraint enforces this
        at the DB level; we raise early for a cleaner error message).
      - promotion_state must be in the allowed set.
      - If bbox is provided it must have exactly 4 numeric elements.

    The service does NOT verify document_id / chunk_id / srs_card_id exist;
    those are FKs with ON DELETE SET NULL (or CASCADE for document_id), and
    we rely on SQLite's foreign_keys pragma being set at connection open
    time. If foreign_keys is off, bad FKs silently insert; the CI + prod
    config enable foreign_keys.
    """
    cleaned_quote = (quote_text or "").strip()
    if not cleaned_quote:
        raise ValueError("quote_text must be non-empty after trimming")
    if origin not in _ALLOWED_ORIGINS:
        raise ValueError(f"origin {origin!r} not in {sorted(_ALLOWED_ORIGINS)!r}")
    if promotion_state not in _ALLOWED_STATES:
        raise ValueError(
            f"promotion_state {promotion_state!r} not in {sorted(_ALLOWED_STATES)!r}"
        )
    bbox_json: Optional[str] = None
    if bbox is not None:
        bbox_list = [float(x) for x in bbox]
        if len(bbox_list) != 4:
            raise ValueError("bbox must have exactly 4 numeric elements [x,y,w,h]")
        bbox_json = json.dumps(bbox_list)

    citations_json = json.dumps(
        list(str(x) for x in (citations_out or ()))
    )
    now = _now_iso()
    new_id = anchor_id or str(uuid.uuid4())

    conn.execute(
        """
        INSERT INTO anchors (
            id, document_id, chunk_id, page_num,
            bbox, text_offset_start, text_offset_end,
            quote_text, user_question, claim_text,
            origin, promotion_state,
            srs_card_id, thread_id, confidence,
            citations_out, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_id,
            document_id,
            chunk_id,
            page_num,
            bbox_json,
            text_offset_start,
            text_offset_end,
            cleaned_quote,
            user_question,
            claim_text,
            origin,
            promotion_state,
            srs_card_id,
            thread_id,
            confidence,
            citations_json,
            now,
            now,
        ),
    )
    return _row_to_anchor(_fetch_row(conn, new_id))


def get_anchor(conn: sqlite3.Connection, anchor_id: str) -> Optional[Anchor]:
    row = conn.execute(
        "SELECT * FROM anchors WHERE id = ?",
        (anchor_id,),
    ).fetchone()
    return _row_to_anchor(row) if row else None


def list_anchors_for_document(
    conn: sqlite3.Connection,
    document_id: str,
    *,
    page_num: Optional[int] = None,
    promotion_states: Optional[Iterable[AnchorPromotionState]] = None,
    limit: int = 500,
    offset: int = 0,
) -> List[Anchor]:
    """Primary read path for the Anchor Column UI.

    page_num filter is the hot case (the Anchor Column shows only anchors on
    the page the user is reading). promotion_states lets the UI filter to
    "show me only carded + mastered" without a second pass in Python.
    """
    where = ["document_id = ?"]
    params: list[Any] = [document_id]
    if page_num is not None:
        where.append("page_num = ?")
        params.append(page_num)
    states = list(promotion_states) if promotion_states else []
    if states:
        placeholders = ",".join("?" * len(states))
        where.append(f"promotion_state IN ({placeholders})")
        params.extend(states)
    params.append(int(limit))
    params.append(int(offset))
    rows = conn.execute(
        f"""
        SELECT * FROM anchors
        WHERE {' AND '.join(where)}
        ORDER BY COALESCE(page_num, 0) ASC, created_at ASC
        LIMIT ? OFFSET ?
        """,
        params,
    ).fetchall()
    return [_row_to_anchor(row) for row in rows]


def transition_state(
    conn: sqlite3.Connection,
    anchor_id: str,
    new_state: AnchorPromotionState,
    *,
    srs_card_id: Optional[str] = None,
) -> Anchor:
    """Advance the promotion machine. Raises if the transition is illegal.

    `carded` transitions MUST supply the card id so the back-reference is
    set atomically with the state change. Other transitions ignore it.
    """
    if new_state not in _ALLOWED_STATES:
        raise ValueError(f"new_state {new_state!r} not in {sorted(_ALLOWED_STATES)!r}")
    current = get_anchor(conn, anchor_id)
    if current is None:
        raise LookupError(f"anchor {anchor_id!r} not found")
    if new_state not in _VALID_TRANSITIONS[current.promotion_state]:
        raise ValueError(
            f"illegal transition {current.promotion_state!r} -> {new_state!r} "
            f"for anchor {anchor_id!r}"
        )
    if new_state == "carded" and not srs_card_id:
        raise ValueError("transition to 'carded' requires srs_card_id")

    conn.execute(
        """
        UPDATE anchors
        SET promotion_state = ?,
            srs_card_id = COALESCE(?, srs_card_id),
            updated_at = ?
        WHERE id = ?
        """,
        (new_state, srs_card_id, _now_iso(), anchor_id),
    )
    updated = get_anchor(conn, anchor_id)
    assert updated is not None
    return updated


def delete_anchor(conn: sqlite3.Connection, anchor_id: str) -> bool:
    """Hard delete. Rare — the promotion machine has `archived` for the soft
    case. We expose delete only for tests, migration backout, and explicit
    user intent ("forget this ever existed").
    """
    cursor = conn.execute("DELETE FROM anchors WHERE id = ?", (anchor_id,))
    return (cursor.rowcount or 0) > 0


def count_by_state(
    conn: sqlite3.Connection,
    document_id: Optional[str] = None,
) -> dict[str, int]:
    """Returns {state: count} covering all five states. Missing states are
    reported as 0 so UI code can render the same table shape regardless of
    data."""
    where = ""
    params: list[Any] = []
    if document_id is not None:
        where = "WHERE document_id = ?"
        params.append(document_id)
    rows = conn.execute(
        f"""
        SELECT promotion_state AS state, COUNT(*) AS n
        FROM anchors
        {where}
        GROUP BY promotion_state
        """,
        params,
    ).fetchall()
    out = {state: 0 for state in _ALLOWED_STATES}
    for row in rows:
        out[str(row["state"])] = int(row["n"] or 0)
    return out


def _fetch_row(conn: sqlite3.Connection, anchor_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM anchors WHERE id = ?", (anchor_id,)).fetchone()
    if row is None:
        raise LookupError(f"anchor {anchor_id!r} not found after insert")
    return row
