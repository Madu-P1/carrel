"""Folder organization for notes.

The global Notes page groups by subject (auto-derived from each note's
document) and lets the student create folders *within* a subject so a
single class doesn't become an undifferentiated dump of paragraphs.

Subject rule (mirrored in `services/tutor.fetch_notes`):

    note.subject = COALESCE(folder.subject_name,
                            document.subject_name,
                            'Unfiled')

A note's folder wins over its document's subject. Moving a note into a
folder under a different subject reclassifies it. Notes with no folder
fall back to their document; notes with no folder and no document
surface under "Unfiled" in the UI.

Folders themselves are intentionally lightweight: id, name, the subject
they live under, a sort_order column we don't sort by yet (drag-drop is
a follow-up), and timestamps. No nesting, no colors, no icons. Add
those when a user actually asks.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException


# We never want a UI element labelled with an empty string — every code
# path that surfaces a subject coerces null/empty to "General" the way
# `documents.subject_name` defaults do. A separate "Unfiled" bucket is
# reserved for notes that have no document at all.
UNFILED_SUBJECT = "Unfiled"
DEFAULT_SUBJECT = "General"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_folder(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "subject_name": row["subject_name"],
        "sort_order": int(row["sort_order"] or 0),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_folders(
    conn: sqlite3.Connection,
    subject_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return every folder, optionally filtered to a single subject.

    Order: subject_name, then sort_order, then name. The composite index
    on (subject_name, sort_order, name) services this without a sort.
    """

    if subject_name is not None:
        rows = conn.execute(
            """
            SELECT id, name, subject_name, sort_order, created_at, updated_at
            FROM note_folders
            WHERE subject_name = ?
            ORDER BY sort_order, name
            """,
            (subject_name,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, name, subject_name, sort_order, created_at, updated_at
            FROM note_folders
            ORDER BY subject_name, sort_order, name
            """
        ).fetchall()
    return [_row_to_folder(row) for row in rows]


def get_folder(conn: sqlite3.Connection, folder_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        """
        SELECT id, name, subject_name, sort_order, created_at, updated_at
        FROM note_folders
        WHERE id = ?
        """,
        (folder_id,),
    ).fetchone()
    return _row_to_folder(row) if row else None


def create_folder(
    conn: sqlite3.Connection,
    name: str,
    subject_name: str,
) -> Dict[str, Any]:
    clean_name = (name or "").strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Folder name is required.")
    clean_subject = (subject_name or "").strip() or DEFAULT_SUBJECT

    folder_id = str(uuid.uuid4())
    now = _now_iso()
    conn.execute(
        """
        INSERT INTO note_folders (id, name, subject_name, sort_order, created_at, updated_at)
        VALUES (?, ?, ?, 0, ?, ?)
        """,
        (folder_id, clean_name, clean_subject, now, now),
    )
    conn.commit()
    folder = get_folder(conn, folder_id)
    if folder is None:
        # Defensive: SELECT-after-INSERT should always succeed because
        # we just committed. If it doesn't, something is very wrong and
        # a 500 is the right shape.
        raise HTTPException(status_code=500, detail="Folder created but could not be read back.")
    return folder


def update_folder(
    conn: sqlite3.Connection,
    folder_id: str,
    *,
    name: Optional[str] = None,
    subject_name: Optional[str] = None,
) -> Dict[str, Any]:
    existing = get_folder(conn, folder_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Folder not found.")

    next_name = existing["name"]
    if name is not None:
        clean = name.strip()
        if not clean:
            raise HTTPException(status_code=400, detail="Folder name cannot be empty.")
        next_name = clean

    next_subject = existing["subject_name"]
    if subject_name is not None:
        clean_subject = subject_name.strip() or DEFAULT_SUBJECT
        next_subject = clean_subject

    conn.execute(
        """
        UPDATE note_folders
        SET name = ?, subject_name = ?, updated_at = ?
        WHERE id = ?
        """,
        (next_name, next_subject, _now_iso(), folder_id),
    )
    conn.commit()
    folder = get_folder(conn, folder_id)
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder vanished mid-update.")
    return folder


def delete_folder(conn: sqlite3.Connection, folder_id: str) -> bool:
    """Delete a folder. Notes inside revert to folder_id NULL so they
    keep their doc-derived subject and stay visible under "All in subject".

    Returns True if a row was deleted. 404 is the caller's job to map
    from False.
    """

    cur = conn.execute("SELECT id FROM note_folders WHERE id = ?", (folder_id,))
    if cur.fetchone() is None:
        return False
    conn.execute("UPDATE notes SET folder_id = NULL WHERE folder_id = ?", (folder_id,))
    conn.execute("DELETE FROM note_folders WHERE id = ?", (folder_id,))
    conn.commit()
    return True


def fetch_organization(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Composite payload powering the global Notes page's left rail.

    Returns one row per subject, each carrying:
      - name
      - note_count: total notes whose resolved subject is this one
      - folders: list of {id, name, sort_order, note_count}

    "Resolved subject" matches the COALESCE rule on fetch_notes so the
    rail counts and the main pane never disagree.
    """

    # First: per-folder note counts. Notes assigned to a folder belong
    # to the folder's subject regardless of their document.
    folder_counts = conn.execute(
        """
        SELECT f.id        AS folder_id,
               f.name      AS folder_name,
               f.subject_name AS subject_name,
               f.sort_order AS sort_order,
               COUNT(n.id) AS note_count
        FROM note_folders f
        LEFT JOIN notes n ON n.folder_id = f.id
        GROUP BY f.id, f.name, f.subject_name, f.sort_order
        ORDER BY f.subject_name, f.sort_order, f.name
        """
    ).fetchall()

    # Second: per-subject note counts for unfoldered notes (notes whose
    # subject derives from documents.subject_name or "Unfiled"). We
    # union these into the per-subject totals below so a subject that
    # only has unfoldered notes still appears in the rail.
    unfoldered = conn.execute(
        """
        SELECT COALESCE(d.subject_name, ?) AS subject_name,
               COUNT(n.id) AS note_count
        FROM notes n
        LEFT JOIN documents d ON n.doc_id = d.id
        WHERE n.folder_id IS NULL
        GROUP BY COALESCE(d.subject_name, ?)
        """,
        (UNFILED_SUBJECT, UNFILED_SUBJECT),
    ).fetchall()

    # Build the subject -> { note_count, folders } map. Subject is keyed
    # by its display name; we accumulate counts and folder lists in one
    # pass.
    by_subject: Dict[str, Dict[str, Any]] = {}

    def _ensure(subject: str) -> Dict[str, Any]:
        if subject not in by_subject:
            by_subject[subject] = {"name": subject, "note_count": 0, "folders": []}
        return by_subject[subject]

    for row in folder_counts:
        subject = row["subject_name"] or DEFAULT_SUBJECT
        bucket = _ensure(subject)
        bucket["note_count"] += int(row["note_count"] or 0)
        bucket["folders"].append(
            {
                "id": row["folder_id"],
                "name": row["folder_name"],
                "sort_order": int(row["sort_order"] or 0),
                "note_count": int(row["note_count"] or 0),
            }
        )

    for row in unfoldered:
        subject = row["subject_name"] or DEFAULT_SUBJECT
        bucket = _ensure(subject)
        bucket["note_count"] += int(row["note_count"] or 0)

    # Stable ordering: Unfiled last, otherwise alphabetical. Real subject
    # names ("Math", "Physics") read better grouped together; Unfiled is
    # a leftover bucket so it belongs at the bottom.
    subjects = sorted(
        by_subject.values(),
        key=lambda s: (s["name"] == UNFILED_SUBJECT, s["name"].lower()),
    )

    return {"subjects": subjects}
