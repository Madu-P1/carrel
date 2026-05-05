"""Notes CRUD — fetch + upsert.

Lifted from services/tutor.py (which had grown to 1133 LoC mixing
LLM-tutor logic with note storage). Notes have nothing to do with
the tutor pipeline; they're addressed by doc / concept / goal /
session and joined to documents + concepts for display.

`services/tutor.py` re-exports the public names from this module so
existing callers (routes/workspace.py, services/workspace.py,
evals/run_evals.py, all of test_tutor_grounded.py) don't need to
change.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from services.documents import clean_concept_label


_NOTE_SELECT = """
    SELECT n.id, n.doc_id, n.concept_id, n.title, n.content, n.source_snippet,
           n.note_type, n.goal_id, n.session_id, n.created_at, n.updated_at,
           d.filename AS document_name, c.name AS concept_name
    FROM notes n
    LEFT JOIN documents d ON n.doc_id = d.id
    LEFT JOIN concepts c ON n.concept_id = c.id
"""


def _row_to_note(row: sqlite3.Row) -> Dict[str, Any]:
    item = dict(row)
    if item.get("concept_name"):
        item["concept_name"] = clean_concept_label(item["concept_name"])
    return item


def fetch_notes(
    conn: sqlite3.Connection,
    doc_id: Optional[str] = None,
    concept_id: Optional[str] = None,
    limit: int = 8,
) -> List[Dict[str, Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    if doc_id:
        conditions.append("n.doc_id = ?")
        params.append(doc_id)
    if concept_id:
        conditions.append("n.concept_id = ?")
        params.append(concept_id)
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = conn.execute(
        f"{_NOTE_SELECT} {where_clause} ORDER BY n.updated_at DESC LIMIT ?",
        (*params, limit),
    ).fetchall()
    return [_row_to_note(row) for row in rows]


def upsert_note_record(
    conn: sqlite3.Connection,
    note_id: Optional[str],
    doc_id: Optional[str],
    concept_id: Optional[str],
    title: Optional[str],
    content: str,
    source_snippet: Optional[str],
    note_type: str = "saved_insight",
    goal_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    clean_title = (title or "").strip() or "Study note"
    if note_id:
        conn.execute(
            """
            UPDATE notes
            SET doc_id = ?, concept_id = ?, title = ?, content = ?, source_snippet = ?,
                note_type = ?, goal_id = ?, session_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                doc_id,
                concept_id,
                clean_title,
                content,
                source_snippet,
                note_type,
                goal_id,
                session_id,
                datetime.now(timezone.utc).isoformat(),
                note_id,
            ),
        )
    else:
        note_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO notes (id, doc_id, concept_id, title, content, source_snippet,
                               note_type, goal_id, session_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                note_id, doc_id, concept_id, clean_title, content, source_snippet,
                note_type, goal_id, session_id,
            ),
        )
    conn.commit()
    row = conn.execute(f"{_NOTE_SELECT} WHERE n.id = ?", (note_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Saved note could not be loaded.")
    return _row_to_note(row)
