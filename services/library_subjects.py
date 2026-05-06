"""Subject grouping + per-subject summaries for the Library home grid.

Lifted from `services.documents` (which had grown to mix duplicate
detection, concept-label cleanup, subject grouping, and document
CRUD into one file). Subject is the primary organizing axis the
Library UI uses, so a focused module makes the queries here easier
to find and test.

The public surface — `fetch_subject_groups`, `list_subject_summaries`,
`set_document_subject` — is re-exported from `services/documents.py`
so callers (`routes/documents.py`, `routes/workspace.py`,
`services/app_state.py`) don't change.

`set_document_subject` calls `fetch_document_detail`, which stays in
`services.documents`. We import it lazily inside the function to
avoid a circular import at module load time.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from services.ingestion import normalize_subject_name
from services.subjects import ensure_subject, list_subject_names


def fetch_subject_groups(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """List every subject — declared (`library_subjects`) or implicit
    (rows on the `documents` table) — with a count.

    Empty / NULL `subject_name` rolls up to the bucket `'General'`,
    which is also the default for new uploads. The UNION + COALESCE
    pattern means the user sees a subject card even when no documents
    yet exist (declared subjects) AND when documents exist without a
    formal subject row (newly imported library)."""
    rows = conn.execute(
        """
        WITH subjects AS (
            SELECT name AS subject_name FROM library_subjects
            UNION
            SELECT DISTINCT COALESCE(NULLIF(TRIM(subject_name), ''), 'General') AS subject_name
            FROM documents
        )
        SELECT
            subjects.subject_name,
            COUNT(documents.id) AS document_count
        FROM subjects
        LEFT JOIN documents
          ON COALESCE(NULLIF(TRIM(documents.subject_name), ''), 'General') = subjects.subject_name
        GROUP BY subjects.subject_name
        ORDER BY subjects.subject_name ASC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def list_subject_summaries(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Per-subject dashboard payload for the Library home grid.

    Each row returns the stats a subject card needs to render:
      subject_name       — the group label
      source_count       — total documents in this subject
      failed_count       — documents whose parser_status is not 'ready'
      flashcard_count    — SRS cards bound to concepts in this subject
      last_studied_at    — max(study_events.created_at) across docs in this
                           subject; null when the user has never studied any
                           source here
      first_failed_doc   — {id, filename, error} for the first failed doc so
                           the card can render an inline error with a direct
                           "Retry" action. Null when nothing failed.

    This is a pure read. One query per metric, joined in Python — the
    workspace has <100 subjects in any realistic deployment, so the extra
    round-trip beats a four-way JOIN that SQLite would plan badly.
    """
    subject_names = list_subject_names(conn)

    summaries: List[Dict[str, Any]] = []
    for subject in subject_names:
        source_row = conn.execute(
            """
            SELECT
                COUNT(*) AS source_count,
                SUM(CASE WHEN COALESCE(parser_status, 'ready') != 'ready' THEN 1 ELSE 0 END) AS failed_count
            FROM documents
            WHERE COALESCE(NULLIF(TRIM(subject_name), ''), 'General') = ?
            """,
            (subject,),
        ).fetchone()
        cards_row = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM srs_cards s
            JOIN concepts c ON s.concept_id = c.id
            JOIN documents d ON c.doc_id = d.id
            WHERE COALESCE(NULLIF(TRIM(d.subject_name), ''), 'General') = ?
            """,
            (subject,),
        ).fetchone()
        last_studied_row = conn.execute(
            """
            SELECT MAX(e.created_at) AS ts
            FROM study_events e
            JOIN documents d ON e.doc_id = d.id
            WHERE COALESCE(NULLIF(TRIM(d.subject_name), ''), 'General') = ?
            """,
            (subject,),
        ).fetchone()
        failed_doc_row = conn.execute(
            """
            SELECT id, filename, parser_status, parser_diagnostics
            FROM documents
            WHERE COALESCE(NULLIF(TRIM(subject_name), ''), 'General') = ?
              AND COALESCE(parser_status, 'ready') != 'ready'
            ORDER BY upload_date ASC
            LIMIT 1
            """,
            (subject,),
        ).fetchone()
        first_failed: Optional[Dict[str, Any]] = None
        if failed_doc_row:
            diagnostics = failed_doc_row["parser_diagnostics"] or "{}"
            try:
                diag_dict = json.loads(diagnostics) if isinstance(diagnostics, str) else diagnostics
            except Exception:
                diag_dict = {}
            warnings = []
            if isinstance(diag_dict, dict):
                quality = diag_dict.get("quality") or {}
                if isinstance(quality, dict):
                    warnings = [str(w) for w in (quality.get("warnings") or [])]
            first_failed = {
                "id": failed_doc_row["id"],
                "filename": failed_doc_row["filename"],
                "status": failed_doc_row["parser_status"],
                "error": warnings[0] if warnings else "Parser reported a problem with this source.",
            }
        summaries.append(
            {
                "subject_name": subject,
                "source_count": int(source_row["source_count"] if source_row else 0),
                "failed_count": int(source_row["failed_count"] if source_row and source_row["failed_count"] else 0),
                "flashcard_count": int(cards_row["n"] if cards_row else 0),
                "last_studied_at": last_studied_row["ts"] if last_studied_row else None,
                "first_failed_doc": first_failed,
            }
        )
    summaries.sort(key=lambda item: (-int(item["source_count"]), str(item["subject_name"])))
    return summaries


def set_document_subject(
    conn: sqlite3.Connection, doc_id: str, subject_name: str
) -> Dict[str, Any]:
    """Re-tag a document with a (possibly new) subject and return the
    refreshed detail payload. Raises 404 if the doc id doesn't exist."""
    # Late binding to avoid a circular import — documents.py re-exports
    # this function, and we call back into it here.
    from services.documents import _document_confidence, fetch_document_detail  # noqa: PLC0415

    normalized_subject = normalize_subject_name(subject_name)
    ensure_subject(conn, normalized_subject)
    updated = conn.execute(
        "UPDATE documents SET subject_name = ? WHERE id = ?",
        (normalized_subject, doc_id),
    ).rowcount
    if not updated:
        raise HTTPException(status_code=404, detail="Document not found")
    conn.commit()
    row = conn.execute(
        """
        SELECT id, filename, storage_name, subject_name, file_type, upload_date, page_count, status,
               source_kind, source_hash, parser_status, parser_diagnostics, duplicate_of, updated_at, extracted_at
        FROM documents
        WHERE id = ?
        """,
        (doc_id,),
    ).fetchone()
    item = dict(row)
    try:
        item["parser_diagnostics"] = json.loads(item.get("parser_diagnostics") or "{}")
    except Exception:
        item["parser_diagnostics"] = {}
    item["confidence"] = _document_confidence(item["parser_diagnostics"])
    detail = fetch_document_detail(conn, doc_id, include_chunks=False, include_selector_options=False)
    item["summary"] = detail["summary"]
    item["concept_count"] = detail["counts"]["concepts"]
    item["question_count"] = detail["counts"]["questions"]
    return item
