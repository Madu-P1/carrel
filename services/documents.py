import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

import db
from services.ingestion.persistence import delete_chunk_vectors
from services.ingestion import summarize_document

# Three concerns moved out of this file:
#   * Duplicate detection -> services/document_duplicates.py
#   * Subject grouping    -> services/library_subjects.py
#   * Concept labels +
#     selector ranking    -> services/concept_labels.py
#
# All public names are re-exported here so existing callers
# (11 modules importing `clean_concept_label`, plus routes and
# services/app_state.py) keep working unchanged.
from services.document_duplicates import (  # noqa: E402, F401
    cleanup_duplicate_documents,
    compute_document_source_hash,
    find_canonical_duplicate,
    find_duplicate_groups,
)
from services.library_subjects import (  # noqa: E402, F401
    fetch_subject_groups,
    list_subject_summaries,
    set_document_subject,
)
from services.concept_labels import (  # noqa: E402, F401
    SELECTOR_CACHE_PREFIX,
    SELECTOR_LIMIT,
    SELECTOR_NOISE_PATTERNS,
    _build_selector_context,
    _concept_name_replacements,
    _concept_selector_signature,
    _fallback_concept_options,
    _get_setting,
    _normalize_concept_text,
    _selector_cache_key,
    _selector_reason,
    _selector_score,
    _set_setting,
    build_concept_options,
    clean_concept_label,
    collect_document_concepts,
)


def load_messages(raw):
    if not raw:
        return []
    try:
        import json

        return json.loads(raw)
    except Exception:
        return []


def fetch_documents(conn: sqlite3.Connection) -> List[Dict[str, object]]:
    rows = conn.execute(
        """
        SELECT id, filename, storage_name, subject_name, file_type, upload_date, page_count, status,
               source_kind, source_hash, parser_status, parser_diagnostics, duplicate_of, updated_at, extracted_at
        FROM documents
        ORDER BY subject_name ASC, upload_date DESC
        """
    ).fetchall()
    documents: List[Dict[str, object]] = []
    for row in rows:
        item = dict(row)
        try:
            item["parser_diagnostics"] = json.loads(item.get("parser_diagnostics") or "{}")
        except Exception:
            item["parser_diagnostics"] = {}
        item["confidence"] = _document_confidence(item["parser_diagnostics"])
        detail = fetch_document_detail(conn, item["id"], include_chunks=False, include_selector_options=False)
        item["summary"] = detail["summary"]
        item["concept_count"] = detail["counts"]["concepts"]
        item["question_count"] = detail["counts"]["questions"]
        documents.append(item)
    return documents


def fetch_document_detail(
    conn: sqlite3.Connection,
    doc_id: str,
    include_chunks: bool = True,
    include_selector_options: bool = True,
) -> Dict[str, object]:
    document_row = conn.execute(
        """
        SELECT id, filename, storage_name, subject_name, file_type, upload_date, page_count, status,
               source_kind, source_hash, parser_status, parser_diagnostics, duplicate_of, updated_at, extracted_at
        FROM documents
        WHERE id = ?
        """,
        (doc_id,),
    ).fetchone()
    if not document_row:
        raise HTTPException(status_code=404, detail="Document not found")

    chunk_rows = conn.execute(
        """
        SELECT id, section, page_num, chunk_index, token_count, content, chunk_hash, provenance_json, embedding_status
        FROM chunks
        WHERE doc_id = ?
        ORDER BY chunk_index ASC
        """,
        (doc_id,),
    ).fetchall()
    chunk_items = []
    for row in chunk_rows:
        item = dict(row)
        try:
            item["provenance_json"] = json.loads(item.get("provenance_json") or "{}")
        except Exception:
            item["provenance_json"] = {}
        chunk_items.append(item)
    combined_text = "\n\n".join(item["content"] for item in chunk_items)
    summary = summarize_document(combined_text) if combined_text else "No extracted content yet."
    document_item = dict(document_row)
    try:
        document_item["parser_diagnostics"] = json.loads(document_item.get("parser_diagnostics") or "{}")
    except Exception:
        document_item["parser_diagnostics"] = {}
    document_item["confidence"] = _document_confidence(document_item["parser_diagnostics"])

    concepts = collect_document_concepts(conn, doc_id)
    replacements = _concept_name_replacements(concepts)
    concept_ids = [item["id"] for item in concepts]
    questions: List[Dict[str, object]] = []
    if concept_ids:
        placeholders = ",".join("?" * len(concept_ids))
        question_rows = conn.execute(
            f"""
            SELECT q.id, q.question, q.answer, q.explanation, q.difficulty, c.name AS concept
            FROM questions q
            JOIN concepts c ON q.concept_id = c.id
            WHERE q.concept_id IN ({placeholders})
            ORDER BY q.rowid ASC
            """,
            concept_ids,
        ).fetchall()
        for row in question_rows:
            item = dict(row)
            item["difficulty"] = (
                "Hard" if item["difficulty"] >= 0.7 else "Medium" if item["difficulty"] >= 0.45 else "Easy"
            )
            item["raw_concept"] = item["concept"]
            item["concept"] = clean_concept_label(item["concept"])
            item["question"] = _normalize_concept_text(item["question"], replacements)
            item["answer"] = _normalize_concept_text(item["answer"], replacements)
            item["explanation"] = _normalize_concept_text(item["explanation"], replacements)
            questions.append(item)

    cards_count = 0
    if concept_ids:
        placeholders = ",".join("?" * len(concept_ids))
        cards_count = conn.execute(
            f"SELECT COUNT(*) AS total FROM srs_cards WHERE concept_id IN ({placeholders})",
            concept_ids,
        ).fetchone()["total"]

    detail = {
        "document": document_item,
        "summary": summary,
        "concepts": concepts,
        "questions": questions,
        "counts": {
            "chunks": len(chunk_items),
            "concepts": len(concepts),
            "questions": len(questions),
            "cards": cards_count,
        },
    }
    if include_selector_options:
        detail["concept_options"] = build_concept_options(
            conn,
            document_row=dict(document_row),
            concepts=concepts,
            chunk_items=chunk_items,
        )
    if include_chunks:
        detail["chunks"] = chunk_items
    return detail


def delete_document_record(conn: sqlite3.Connection, doc_id: str) -> bool:
    document_row = conn.execute(
        "SELECT storage_name FROM documents WHERE id = ?",
        (doc_id,),
    ).fetchone()
    if not document_row:
        return False
    concept_ids = [concept["id"] for concept in collect_document_concepts(conn, doc_id)]
    if concept_ids:
        placeholders = ",".join("?" * len(concept_ids))
        conn.execute(f"DELETE FROM questions WHERE concept_id IN ({placeholders})", concept_ids)
        conn.execute(f"DELETE FROM srs_cards WHERE concept_id IN ({placeholders})", concept_ids)
        conn.execute(f"DELETE FROM notes WHERE concept_id IN ({placeholders})", concept_ids)
        conn.execute(f"DELETE FROM study_events WHERE concept_id IN ({placeholders})", concept_ids)
        conn.execute(
            f"DELETE FROM concept_edges WHERE source_id IN ({placeholders}) OR target_id IN ({placeholders})",
            concept_ids * 2,
        )
        conn.execute(f"DELETE FROM concepts WHERE id IN ({placeholders})", concept_ids)
    conn.execute("DELETE FROM notes WHERE doc_id = ?", (doc_id,))
    conn.execute("DELETE FROM study_events WHERE doc_id = ?", (doc_id,))
    chunk_rowids = [
        int(row["rowid"])
        for row in conn.execute(
            "SELECT rowid FROM chunks WHERE doc_id = ?",
            (doc_id,),
        ).fetchall()
    ]
    delete_chunk_vectors(conn, chunk_rowids)
    conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
    conn.execute("DELETE FROM app_settings WHERE key = ?", (_selector_cache_key(doc_id),))
    deleted = conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,)).rowcount
    conn.commit()
    storage_name = document_row["storage_name"]
    if deleted and storage_name:
        stored_path = db.UPLOAD_DIR / storage_name
        if stored_path.exists():
            stored_path.unlink()
    return bool(deleted)


def _document_confidence(parser_diagnostics: Dict[str, Any]) -> Optional[float]:
    quality = parser_diagnostics.get("quality")
    if not isinstance(quality, dict):
        return None

    confidence = quality.get("confidence")
    if isinstance(confidence, (int, float)):
        return float(confidence)
    return None
