import json
import sqlite3
import uuid
from typing import Any, Dict, List, Optional

from services import review_scheduler as review_service
from services import study as study_service
from services import workspace as workspace_service
from services.documents import clean_concept_label, fetch_documents, fetch_subject_groups


def get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row and row["value"] is not None else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO app_settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )
    conn.commit()


def load_messages(raw: Optional[str]) -> List[Dict[str, Any]]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    return data if isinstance(data, list) else []


def log_study_event(
    conn: sqlite3.Connection,
    event_type: str,
    doc_id: Optional[str] = None,
    concept_id: Optional[str] = None,
    confidence: Optional[float] = None,
    duration_seconds: Optional[int] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO study_events (id, event_type, doc_id, concept_id, confidence, duration_seconds, payload)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            event_type,
            doc_id,
            concept_id,
            confidence,
            duration_seconds,
            json.dumps(payload or {}),
        ),
    )
    conn.commit()


def fetch_recent_events(conn: sqlite3.Connection, limit: int = 12) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT e.id, e.event_type, e.doc_id, e.concept_id, e.confidence, e.duration_seconds, e.payload, e.created_at,
               d.filename AS document_name, c.name AS concept_name
        FROM study_events e
        LEFT JOIN documents d ON e.doc_id = d.id
        LEFT JOIN concepts c ON e.concept_id = c.id
        ORDER BY e.created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    events: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        payload = item.get("payload")
        item["payload"] = load_messages(payload) if isinstance(payload, str) else payload
        if item.get("concept_name"):
            item["concept_name"] = clean_concept_label(item["concept_name"])
        events.append(item)
    return events


def fetch_due_queue_v2(
    conn: sqlite3.Connection,
    *,
    goal_id: Optional[str] = None,
    source_ids: Optional[List[str]] = None,
    session_id: Optional[str] = None,
    include_missed: bool = True,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    return review_service.fetch_due_queue(
        conn,
        goal_id=goal_id,
        source_ids=source_ids,
        session_id=session_id,
        include_missed=include_missed,
        limit=limit,
    )


def build_stats(conn: sqlite3.Connection) -> Dict[str, object]:
    concepts = conn.execute(
        "SELECT c.name, c.mastery, d.subject_name FROM concepts c JOIN documents d ON d.id = c.doc_id"
    ).fetchall()
    cards = conn.execute("SELECT difficulty, reps, lapses FROM srs_cards").fetchall()
    due_cards = study_service.fetch_due_cards(conn)
    if cards:
        correct_estimate = sum(max(row["reps"] - row["lapses"], 0) for row in cards)
        attempts = sum(max(row["reps"], 1) for row in cards)
        retention = round((correct_estimate / attempts) * 100, 1)
    else:
        retention = 0.0
    weakest = min(concepts, key=lambda row: row["mastery"])["name"] if concepts else "-"
    mastered = sum(1 for row in concepts if row["mastery"] >= 0.75)
    return {
        "documents": len(fetch_documents(conn)),
        "subjects": len(fetch_subject_groups(conn)),
        "questions": len(study_service.fetch_questions(conn, limit=1000)),
        "due": len(due_cards),
        "retention": retention,
        "mastered": mastered,
        "weakestConcept": weakest,
    }


def fetch_workspace_state(conn: sqlite3.Connection) -> Dict[str, Any]:
    return workspace_service.fetch_workspace_state(
        conn,
        get_setting=get_setting,
        fetch_recent_events=fetch_recent_events,
        fetch_subject_groups=fetch_subject_groups,
    )
