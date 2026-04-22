import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from services import mastery_engine
from services.documents import clean_concept_label


def _name_replacements(conn: sqlite3.Connection) -> List[tuple[str, str]]:
    rows = conn.execute("SELECT name FROM concepts ORDER BY LENGTH(name) DESC, rowid ASC").fetchall()
    pairs: List[tuple[str, str]] = []
    seen = set()
    for row in rows:
        raw_name = str(row["name"] or "").strip()
        if not raw_name or raw_name in seen:
            continue
        seen.add(raw_name)
        cleaned = clean_concept_label(raw_name)
        if cleaned and cleaned != raw_name:
            pairs.append((raw_name, cleaned))
    return pairs


def _normalize_card_text(text: str, replacements: List[tuple[str, str]]) -> str:
    value = str(text or "")
    for raw_name, cleaned in replacements:
        value = value.replace(raw_name, cleaned)
    return value


def _next_due_days(outcome: str, classification: Optional[str]) -> int:
    if outcome == "missed":
        if classification == "misconception":
            return 0
        if classification == "wrong_relation":
            return 0
        return 1
    if classification == "robust_and_transferable":
        return 10
    if classification == "shallow_but_correct":
        return 3
    return 5


def fetch_due_queue(
    conn: sqlite3.Connection,
    *,
    goal_id: Optional[str] = None,
    source_ids: Optional[List[str]] = None,
    session_id: Optional[str] = None,
    include_missed: bool = True,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    conditions = ["(s.due_date IS NULL OR s.due_date <= date('now'))"]
    params: List[Any] = []
    if source_ids:
        placeholders = ",".join("?" * len(source_ids))
        conditions.append(f"c.doc_id IN ({placeholders})")
        params.extend(source_ids)
    where_clause = " AND ".join(conditions)
    rows = conn.execute(
        f"""
        SELECT s.id, s.concept_id, s.front, s.back, s.state, s.due_date, s.last_review, s.reps, s.lapses,
               c.name AS concept_name, c.doc_id AS source_id, d.filename AS source_name
        FROM srs_cards s
        JOIN concepts c ON c.id = s.concept_id
        JOIN documents d ON d.id = c.doc_id
        WHERE {where_clause}
        ORDER BY COALESCE(s.due_date, date('now')) ASC, s.rowid ASC
        LIMIT ?
        """,
        (*params, limit),
    ).fetchall()
    queue: List[Dict[str, Any]] = []
    replacements = _name_replacements(conn)
    for row in rows:
        item = dict(row)
        item["raw_concept_name"] = item["concept_name"]
        item["concept_name"] = clean_concept_label(item["concept_name"])
        item["front"] = _normalize_card_text(item["front"], replacements)
        item["back"] = _normalize_card_text(item["back"], replacements)
        review_row = conn.execute(
            """
            SELECT outcome, classification, confidence, created_at
            FROM review_events
            WHERE card_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (row["id"],),
        ).fetchone()
        recent_outcome = dict(review_row) if review_row else None
        if recent_outcome and recent_outcome["outcome"] == "missed" and not include_missed:
            continue
        mastery_state = mastery_engine.ensure_mastery_state(conn, row["concept_id"], goal_id=goal_id, session_id=session_id)
        item["mastery_state"] = mastery_state
        item["recent_review"] = recent_outcome
        item["missed_recently"] = bool(recent_outcome and recent_outcome["outcome"] == "missed")
        queue.append(item)
    return queue


def record_review_event(
    conn: sqlite3.Connection,
    *,
    item_id: str,
    item_kind: str,
    outcome: str,
    classification: Optional[str] = None,
    confidence: Optional[float] = None,
    duration_seconds: Optional[int] = None,
    goal_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    if item_kind not in {"flashcard", "quiz"}:
        raise HTTPException(status_code=400, detail="Review currently supports flashcard and quiz items.")

    if item_kind == "flashcard":
        item_row = conn.execute(
            """
            SELECT s.id, s.concept_id, s.reps, s.lapses, s.state, c.doc_id AS source_id
            FROM srs_cards s
            JOIN concepts c ON c.id = s.concept_id
            WHERE s.id = ?
            """,
            (item_id,),
        ).fetchone()
    else:
        item_row = conn.execute(
            """
            SELECT q.id, q.concept_id, q.times_shown AS reps, (q.times_shown - q.times_correct) AS lapses,
                   'quiz' AS state, c.doc_id AS source_id
            FROM questions q
            JOIN concepts c ON c.id = q.concept_id
            WHERE q.id = ?
            """,
            (item_id,),
        ).fetchone()

    if not item_row:
        raise HTTPException(status_code=404, detail="Review item not found.")

    review_id = str(uuid.uuid4())
    mastery_state = mastery_engine.update_mastery_state(
        conn,
        item_row["concept_id"],
        goal_id=goal_id,
        session_id=session_id,
        classification=classification,
        learner_confidence=confidence,
        evidence_quality=0.72 if outcome == "got_it" else 0.45,
    )
    conn.execute(
        """
        INSERT INTO review_events (
            id, mastery_state_id, card_id, question_id, outcome, classification, confidence, duration_seconds
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            review_id,
            mastery_state["id"],
            item_id if item_kind == "flashcard" else None,
            item_id if item_kind == "quiz" else None,
            outcome,
            classification,
            confidence,
            duration_seconds,
        ),
    )

    next_due_days = _next_due_days(outcome, classification)
    next_due_at = (
        datetime.now(timezone.utc) + timedelta(days=next_due_days)
        if next_due_days
        else datetime.now(timezone.utc) + timedelta(minutes=20)
    )

    if item_kind == "flashcard":
        conn.execute(
            """
            UPDATE srs_cards
            SET state = ?, reps = COALESCE(reps, 0) + 1, lapses = COALESCE(lapses, 0) + ?,
                due_date = ?, last_review = ?
            WHERE id = ?
            """,
            (
                "review" if outcome == "got_it" else "relearning",
                0 if outcome == "got_it" else 1,
                next_due_at.date().isoformat(),
                datetime.now(timezone.utc).isoformat(),
                item_id,
            ),
        )
    else:
        conn.execute(
            """
            UPDATE questions
            SET times_shown = COALESCE(times_shown, 0) + 1,
                times_correct = COALESCE(times_correct, 0) + ?
            WHERE id = ?
            """,
            (1 if outcome == "got_it" else 0, item_id),
        )

    next_action = {
        "type": "tutor" if outcome == "missed" else "review",
        "label": "Run repair step" if outcome == "missed" else "Promote interval",
        "concept_id": item_row["concept_id"],
        "source_id": item_row["source_id"],
    }
    return {
        "review_event_id": review_id,
        "next_due_at": next_due_at.isoformat(),
        "mastery_state": mastery_state,
        "next_action": next_action,
    }
