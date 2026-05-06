import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

import db
from services.ingestion.persistence import delete_chunk_vectors
from services.ingestion import summarize_document

# Duplicate detection moved to services/document_duplicates.py.
# Subject grouping moved to services/library_subjects.py.
# Re-exported here so existing callers (routes/documents.py,
# routes/workspace.py, services/jobs.py, services/app_state.py,
# tests) keep working unchanged.
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


def load_messages(raw):
    if not raw:
        return []
    try:
        import json

        return json.loads(raw)
    except Exception:
        return []


SELECTOR_CACHE_PREFIX = "concept_selector:"
SELECTOR_LIMIT = 8
SELECTOR_NOISE_PATTERNS = [
    r"all rights reserved",
    r"all right reserved",
    r"copyright",
    r"pearson education",
    r"\bltd\b",
    r"\breserved\b",
]


def _get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row and row["value"] is not None else default



def _set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO app_settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )
    conn.commit()


def _selector_cache_key(doc_id: str) -> str:
    return f"{SELECTOR_CACHE_PREFIX}{doc_id}"


def clean_concept_label(value: str) -> str:
    cleaned = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(value or ""))
    cleaned = re.sub(r"[_/\\-]+", " ", cleaned)
    cleaned = re.sub(r"([A-Za-z])(\d)", r"\1 \2", cleaned)
    cleaned = re.sub(r"(\d)([A-Za-z])", r"\1 \2", cleaned)
    for pattern in SELECTOR_NOISE_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,:;-_")
    deduped_words: List[str] = []
    for word in cleaned.split():
        if not deduped_words or deduped_words[-1].lower() != word.lower():
            deduped_words.append(word)
    cleaned = " ".join(deduped_words)
    return cleaned or "Study concept"


def _concept_name_replacements(concepts: List[Dict[str, Any]]) -> List[tuple[str, str]]:
    pairs: List[tuple[str, str]] = []
    seen = set()
    for concept in concepts:
        raw_name = str(concept.get("name") or "").strip()
        if not raw_name or raw_name in seen:
            continue
        seen.add(raw_name)
        cleaned = clean_concept_label(raw_name)
        if cleaned and cleaned != raw_name:
            pairs.append((raw_name, cleaned))
    return pairs


def _normalize_concept_text(text: str, replacements: List[tuple[str, str]]) -> str:
    value = str(text or "")
    for raw_name, cleaned in replacements:
        value = value.replace(raw_name, cleaned)
    return value


def _selector_reason(concept: Dict[str, Any], goal: str) -> str:
    reason_parts = []
    if goal:
        goal_tokens = {token for token in re.findall(r"[a-z0-9]+", goal.lower()) if len(token) > 3}
        concept_text = f"{concept.get('name', '')} {concept.get('description', '')}".lower()
        if goal_tokens and any(token in concept_text for token in goal_tokens):
            reason_parts.append("Aligned with the current learning goal")
    if concept.get("description"):
        reason_parts.append("Grounded in the document's extracted explanation")
    if concept.get("source_chunk_ids"):
        reason_parts.append("Backed by source chunks")
    return ". ".join(reason_parts[:2]) or "Selected as a high-signal study concept."


def _selector_score(concept: Dict[str, Any], goal: str) -> float:
    raw_name = str(concept.get("name") or "")
    clean_name = clean_concept_label(raw_name)
    description = str(concept.get("description") or "")
    score = 50.0
    if clean_name != raw_name.strip():
        score += 8
    if 2 <= len(clean_name.split()) <= 6:
        score += 10
    if description:
        score += min(len(description) / 24, 12)
    if concept.get("source_chunk_ids"):
        score += 8
    try:
        score += float(concept.get("mastery") or 0) * 5
    except (TypeError, ValueError):
        pass
    if goal:
        goal_tokens = {token for token in re.findall(r"[a-z0-9]+", goal.lower()) if len(token) > 3}
        concept_text = f"{raw_name} {description}".lower()
        score += sum(6 for token in goal_tokens if token in concept_text)
    if len(clean_name) < 4:
        score -= 25
    if any(re.search(pattern, raw_name, flags=re.IGNORECASE) for pattern in SELECTOR_NOISE_PATTERNS):
        score -= 20
    return score


def _build_selector_context(
    concepts: List[Dict[str, Any]],
    chunk_items: List[Dict[str, Any]],
) -> str:
    chunk_lookup = {item["id"]: item.get("content", "") for item in chunk_items}
    blocks = []
    for concept in concepts:
        chunk_preview = ""
        for chunk_id in concept.get("source_chunk_ids", [])[:2]:
            content = chunk_lookup.get(chunk_id, "").strip()
            if content:
                chunk_preview = " ".join(content.split())[:280]
                break
        blocks.append(
            "\n".join(
                [
                    f"Concept id: {concept['id']}",
                    f"Raw name: {concept.get('name', '')}",
                    f"Description: {concept.get('description', '')}",
                    f"Preview: {chunk_preview}",
                ]
            )
        )
    return "\n\n".join(blocks)


def _fallback_concept_options(
    concepts: List[Dict[str, Any]],
    goal: str,
) -> List[Dict[str, Any]]:
    ordered = sorted(concepts, key=lambda item: (-_selector_score(item, goal), str(item.get("name") or "").lower()))
    if len(ordered) > SELECTOR_LIMIT:
        ordered = ordered[:SELECTOR_LIMIT]
    curated: List[Dict[str, Any]] = []
    seen_labels = set()
    for concept in ordered:
        label = clean_concept_label(str(concept.get("name") or ""))
        key = label.lower()
        if key in seen_labels:
            continue
        seen_labels.add(key)
        curated.append(
            {
                "concept_id": concept["id"],
                "display_name": label,
                "reason": _selector_reason(concept, goal),
            }
        )
    return curated or [
        {
            "concept_id": concept["id"],
            "display_name": clean_concept_label(str(concept.get("name") or "Study concept")),
            "reason": "Fallback selector option.",
        }
        for concept in concepts[:1]
    ]


def _concept_selector_signature(
    document_row: Dict[str, Any],
    concepts: List[Dict[str, Any]],
    goal: str,
) -> str:
    payload = {
        "doc_id": document_row["id"],
        "filename": document_row["filename"],
        "goal": goal,
        "concepts": [
            {
                "id": item["id"],
                "name": item.get("name"),
                "description": item.get("description"),
                "mastery": item.get("mastery"),
            }
            for item in concepts
        ],
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def build_concept_options(
    conn: sqlite3.Connection,
    *,
    document_row: Dict[str, Any],
    concepts: List[Dict[str, Any]],
    chunk_items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not concepts:
        return []

    goal = _get_setting(conn, "learning_goal", "")
    signature = _concept_selector_signature(document_row, concepts, goal)
    cache_key = _selector_cache_key(document_row["id"])
    cached = load_messages(_get_setting(conn, cache_key, ""))
    if isinstance(cached, dict) and cached.get("signature") == signature and isinstance(cached.get("options"), list):
        cached_options = cached["options"]
    else:
        cached_options = _fallback_concept_options(concepts, goal)
        _set_setting(conn, cache_key, json.dumps({"signature": signature, "options": cached_options}))

    by_id = {concept["id"]: concept for concept in concepts}
    selected: List[Dict[str, Any]] = []
    seen = set()
    for rank, item in enumerate(cached_options):
        concept = by_id.get(item.get("concept_id"))
        if not concept or concept["id"] in seen:
            continue
        seen.add(concept["id"])
        selected.append(
            {
                **concept,
                "raw_name": concept.get("name"),
                "name": item.get("display_name") or clean_concept_label(str(concept.get("name") or "")),
                "selector_reason": item.get("reason") or _selector_reason(concept, goal),
                "selector_rank": rank,
            }
        )

    if not selected:
        return [
            {
                **concept,
                "raw_name": concept.get("name"),
                "name": clean_concept_label(str(concept.get("name") or "")),
                "selector_reason": _selector_reason(concept, goal),
                "selector_rank": index,
            }
            for index, concept in enumerate(concepts[:SELECTOR_LIMIT])
        ]
    return selected


def collect_document_concepts(conn: sqlite3.Connection, doc_id: str) -> List[Dict[str, object]]:
    if not doc_id:
        return []
    rows = conn.execute(
        """
        SELECT c.id, c.doc_id, c.name, c.description, c.mastery, c.source_chunks, d.filename AS document_name,
               d.subject_name
        FROM concepts c
        JOIN documents d ON d.id = c.doc_id
        WHERE c.doc_id = ?
        ORDER BY c.rowid ASC
        """,
        (doc_id,),
    ).fetchall()
    concepts: List[Dict[str, object]] = []
    for row in rows:
        item = dict(row)
        item["source_chunk_ids"] = load_messages(item["source_chunks"])
        item.pop("source_chunks", None)
        item["display_name"] = clean_concept_label(item.get("name"))
        concepts.append(item)
    return concepts


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
