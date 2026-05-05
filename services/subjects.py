from __future__ import annotations

import sqlite3
from typing import Any, Dict, List


def normalize_subject_name(subject_name: str | None) -> str:
    cleaned = (subject_name or "").strip()
    return cleaned or "General"


def ensure_subject(conn: sqlite3.Connection, subject_name: str | None) -> Dict[str, Any]:
    normalized = normalize_subject_name(subject_name)
    conn.execute(
        """
        INSERT INTO library_subjects (name)
        VALUES (?)
        ON CONFLICT(name) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
        """,
        (normalized,),
    )
    row = conn.execute(
        "SELECT name AS subject_name, created_at, updated_at FROM library_subjects WHERE name = ?",
        (normalized,),
    ).fetchone()
    return dict(row) if row else {"subject_name": normalized}


def list_subject_names(conn: sqlite3.Connection) -> List[str]:
    rows = conn.execute(
        """
        SELECT name AS subject_name
        FROM library_subjects
        UNION
        SELECT DISTINCT COALESCE(NULLIF(TRIM(subject_name), ''), 'General') AS subject_name
        FROM documents
        ORDER BY subject_name ASC
        """
    ).fetchall()
    return [str(row["subject_name"]) for row in rows]
