import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from services import mastery_engine
from services.documents import clean_concept_label


def _dump_scope(values: Optional[List[str]]) -> Optional[str]:
    if not values:
        return None
    return json.dumps(values)


def _load_scope(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


def list_sessions(conn: sqlite3.Connection, limit: int = 8) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, goal_id, objective, source_scope, concept_scope, difficulty_target, duration_minutes,
               mode, status, interruptions, mastery_delta, unresolved_items, suggested_next_session,
               started_at, completed_at, created_at
        FROM sessions
        ORDER BY COALESCE(started_at, created_at) DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    sessions: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["source_scope"] = _load_scope(item["source_scope"])
        item["concept_scope"] = _load_scope(item["concept_scope"])
        item["unresolved_items"] = _load_scope(item["unresolved_items"])
        sessions.append(item)
    return sessions


def start_session(
    conn: sqlite3.Connection,
    *,
    goal_id: Optional[str],
    source_scope: Optional[List[str]],
    concept_scope: Optional[List[str]],
    difficulty_target: str,
    duration_minutes: int,
    mode: str,
    objective: str,
) -> Dict[str, Any]:
    session_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO sessions (
            id, goal_id, objective, source_scope, concept_scope, difficulty_target,
            duration_minutes, mode, status, started_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
        """,
        (
            session_id,
            goal_id,
            objective,
            _dump_scope(source_scope),
            _dump_scope(concept_scope),
            difficulty_target,
            duration_minutes,
            mode,
            started_at,
        ),
    )
    row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    item = dict(row)
    item["source_scope"] = _load_scope(item["source_scope"])
    item["concept_scope"] = _load_scope(item["concept_scope"])
    item["unresolved_items"] = _load_scope(item["unresolved_items"])
    return item


def complete_session(
    conn: sqlite3.Connection,
    session_id: str,
    *,
    fetch_due_queue,
    build_momentum_engine,
) -> Dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Session not found.")

    session = dict(row)
    concept_scope = _load_scope(session.get("concept_scope"))
    unresolved_rows = conn.execute(
        """
        SELECT classification, question
        FROM tutor_exchanges
        WHERE session_id = ? AND classification IN ('misconception', 'wrong_relation', 'wrong_example', 'omission')
        ORDER BY created_at DESC
        LIMIT 4
        """,
        (session_id,),
    ).fetchall()
    unresolved_items = [f"{item['classification']}: {item['question']}" for item in unresolved_rows]
    mastery_delta = mastery_engine.compute_session_mastery_delta(conn, session_id)

    weak_rows = []
    if concept_scope:
        placeholders = ",".join("?" * len(concept_scope))
        weak_rows = conn.execute(
            f"""
            SELECT name, mastery
            FROM concepts
            WHERE id IN ({placeholders})
            ORDER BY mastery ASC, rowid ASC
            LIMIT 3
            """,
            concept_scope,
        ).fetchall()
    else:
        weak_rows = conn.execute(
            """
            SELECT name, mastery
            FROM concepts
            ORDER BY mastery ASC, rowid ASC
            LIMIT 3
            """
        ).fetchall()

    weak_concepts = [
        f"{clean_concept_label(item['name'])} ({round(float(item['mastery'] or 0) * 100)}%)"
        for item in weak_rows
    ]
    review_queue = fetch_due_queue(conn, session_id=session_id, include_missed=True, limit=5)
    suggested_next_action = build_momentum_engine(conn)
    weakest_name = clean_concept_label(weak_rows[0]["name"]) if weak_rows else None
    stretch_question = (
        f"Apply {weakest_name} to a novel example and explain which evidence would support your answer."
        if weak_rows
        else "Pick one weak area and explain it from source evidence without notes."
    )
    revision_recommendation = (
        f"Revisit {weakest_name} with source-grounded comparison before your next sprint."
        if weak_rows
        else "Run a short review sprint on the next due items."
    )

    conn.execute(
        """
        UPDATE sessions
        SET status = 'completed', mastery_delta = ?, unresolved_items = ?, suggested_next_session = ?,
            completed_at = ?
        WHERE id = ?
        """,
        (
            mastery_delta,
            json.dumps(unresolved_items),
            suggested_next_action["headline"],
            datetime.now(timezone.utc).isoformat(),
            session_id,
        ),
    )
    return {
        "session_id": session_id,
        "mastery_delta": mastery_delta,
        "weak_concepts": weak_concepts,
        "generated_cards": [],
        "unresolved_items": unresolved_items,
        "stretch_question": stretch_question,
        "revision_recommendation": revision_recommendation,
        "suggested_next_session": suggested_next_action["headline"],
        "recommended_next_action": suggested_next_action,
        "due_queue_count": len(review_queue),
    }
