"""Grounding & retrieval — pull chunks + concepts for an artifact's scope.

Three responsibilities:
  * Loading source chunks (`_chunk_text_for_scope`, `_fresh_chunks_for_sources`)
  * Loading concepts (`_concepts_for_scope`)
  * Building the final ranked grounding bundle (`retrieve_grounding_chunks`,
    `render_grounding_text`)

The orchestrator at `_orchestrator.generate_artifact` is the only intended
caller (along with `benchmarks/phase0.py` which exercises
`retrieve_grounding_chunks` directly).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from services import extraction_pipeline
from services.documents import clean_concept_label
from services.helpers import split_sentences, tokenize


# Project root → data/uploads. The grounding loader resolves stored
# filenames against this directory when a chunk's text needs re-loading
# from disk (rare, but keeps the pre-extraction-pipeline cold path alive).
UPLOAD_DIR = Path(__file__).resolve().parents[2] / "data" / "uploads"


def _chunk_text_for_scope(
    conn: sqlite3.Connection,
    source_ids: Optional[List[str]],
    concept_ids: Optional[List[str]],
    limit: int = 12,
) -> List[Dict[str, Any]]:
    if concept_ids:
        placeholders = ",".join("?" * len(concept_ids))
        rows = conn.execute(
            f"""
            SELECT ch.id, ch.content, ch.section, ch.page_num, d.filename, d.id AS doc_id
            FROM concepts c
            JOIN chunks ch ON ch.doc_id = c.doc_id
            JOIN documents d ON d.id = ch.doc_id
            WHERE c.id IN ({placeholders})
            ORDER BY ch.chunk_index ASC
            LIMIT ?
            """,
            (*concept_ids, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    if source_ids:
        placeholders = ",".join("?" * len(source_ids))
        rows = conn.execute(
            f"""
            SELECT ch.id, ch.content, ch.section, ch.page_num, d.filename, d.id AS doc_id
            FROM chunks ch
            JOIN documents d ON d.id = ch.doc_id
            WHERE ch.doc_id IN ({placeholders})
            ORDER BY ch.chunk_index ASC
            LIMIT ?
            """,
            (*source_ids, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    rows = conn.execute(
        """
        SELECT ch.id, ch.content, ch.section, ch.page_num, d.filename, d.id AS doc_id
        FROM chunks ch
        JOIN documents d ON d.id = ch.doc_id
        ORDER BY ch.rowid DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def _fresh_chunks_for_sources(conn: sqlite3.Connection, source_ids: Optional[List[str]]) -> List[Dict[str, Any]]:
    if not source_ids:
        return []
    placeholders = ",".join("?" * len(source_ids))
    rows = conn.execute(
        f"""
        SELECT id, filename, storage_name
        FROM documents
        WHERE id IN ({placeholders})
        ORDER BY rowid ASC
        """,
        source_ids,
    ).fetchall()
    fresh_chunks: List[Dict[str, Any]] = []
    for row in rows:
        storage_name = str(row["storage_name"] or "").strip()
        if not storage_name:
            continue
        candidate_path = UPLOAD_DIR / storage_name
        if not candidate_path.exists():
            continue
        try:
            asset = extraction_pipeline.extract_asset(candidate_path)
        except Exception:
            continue
        fresh_chunks.extend(
            {
                "id": f"{row['id']}::{index}",
                "content": chunk.content,
                "section": chunk.section,
                "page_num": chunk.page_num,
                "filename": row["filename"],
                "doc_id": row["id"],
                "chunk_index": chunk.chunk_index,
            }
            for index, chunk in enumerate(asset.chunks, start=1)
            if str(chunk.content or "").strip()
        )
    return fresh_chunks


def _concepts_for_scope(
    conn: sqlite3.Connection,
    source_ids: Optional[List[str]],
    concept_ids: Optional[List[str]],
    limit: int = 10,
) -> List[Dict[str, Any]]:
    if concept_ids:
        placeholders = ",".join("?" * len(concept_ids))
        rows = conn.execute(
            f"""
            SELECT c.id, c.name, c.description, c.mastery, c.source_chunks, d.filename AS document_name
            FROM concepts c
            JOIN documents d ON d.id = c.doc_id
            WHERE c.id IN ({placeholders})
            LIMIT ?
            """,
            (*concept_ids, limit),
        ).fetchall()
        concepts = [dict(r) for r in rows]
        for concept in concepts:
            concept["raw_name"] = concept["name"]
            concept["name"] = clean_concept_label(concept["name"])
            try:
                concept["source_chunk_ids"] = json.loads(concept.get("source_chunks") or "[]")
            except Exception:
                concept["source_chunk_ids"] = []
        return concepts
    if source_ids:
        placeholders = ",".join("?" * len(source_ids))
        rows = conn.execute(
            f"""
            SELECT c.id, c.name, c.description, c.mastery, c.source_chunks, d.filename AS document_name
            FROM concepts c
            JOIN documents d ON d.id = c.doc_id
            WHERE c.doc_id IN ({placeholders})
            ORDER BY c.mastery ASC
            LIMIT ?
            """,
            (*source_ids, limit),
        ).fetchall()
        concepts = [dict(r) for r in rows]
        for concept in concepts:
            concept["raw_name"] = concept["name"]
            concept["name"] = clean_concept_label(concept["name"])
            try:
                concept["source_chunk_ids"] = json.loads(concept.get("source_chunks") or "[]")
            except Exception:
                concept["source_chunk_ids"] = []
        return concepts
    rows = conn.execute(
        """
        SELECT c.id, c.name, c.description, c.mastery, c.source_chunks, d.filename AS document_name
        FROM concepts c
        JOIN documents d ON d.id = c.doc_id
        ORDER BY c.mastery ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    concepts = [dict(r) for r in rows]
    for concept in concepts:
        concept["raw_name"] = concept["name"]
        concept["name"] = clean_concept_label(concept["name"])
        try:
            concept["source_chunk_ids"] = json.loads(concept.get("source_chunks") or "[]")
        except Exception:
            concept["source_chunk_ids"] = []
    return concepts


def _support_snippet(concept: Dict[str, Any], chunks: List[Dict[str, Any]]) -> str:
    name_tokens = set(tokenize(str(concept.get("name") or "")))
    best_sentence = ""
    best_score = 0
    for chunk in chunks:
        for sentence in split_sentences(chunk.get("content") or "")[:3]:
            score = len(name_tokens & set(tokenize(sentence)))
            if concept.get("name", "").lower() in sentence.lower():
                score += 2
            if score > best_score:
                best_score = score
                best_sentence = sentence
    return best_sentence


def retrieve_grounding_chunks(
    conn: sqlite3.Connection,
    *,
    source_ids: Optional[List[str]],
    concept_ids: Optional[List[str]],
    query: str,
    limit: int = 12,
) -> List[Dict[str, Any]]:
    candidate_limit = max(limit * 4, 24)
    candidates = _chunk_text_for_scope(conn, source_ids, concept_ids, limit=candidate_limit)
    if not candidates:
        return []

    query_tokens = set(tokenize(query or ""))
    if not query_tokens:
        return candidates[:limit]

    ranked: List[Dict[str, Any]] = []
    for chunk in candidates:
        content = str(chunk.get("content") or "")
        if not content:
            continue
        content_tokens = tokenize(content)
        overlap = sum(1 for token in content_tokens if token in query_tokens)
        if overlap <= 0:
            continue
        section = str(chunk.get("section") or "")
        filename = str(chunk.get("filename") or "")
        score = overlap * 5
        score += sum(3 for token in query_tokens if token in section.lower())
        score += sum(2 for token in query_tokens if token in filename.lower())
        if chunk.get("page_num") is not None:
            score += 0.5
        ranked.append({**chunk, "_score": score})

    ordered = sorted(
        ranked or [{**chunk, "_score": 0} for chunk in candidates],
        key=lambda item: (-float(item.get("_score", 0)), item.get("filename", ""), item.get("chunk_index", 0)),
    )
    return [{key: value for key, value in chunk.items() if key != "_score"} for chunk in ordered[:limit]]


def render_grounding_text(chunks: List[Dict[str, Any]]) -> str:
    blocks = []
    for chunk in chunks:
        content = str(chunk.get("content") or "").strip()
        if not content:
            continue
        label = " · ".join(
            piece
            for piece in [
                str(chunk.get("filename") or "").strip(),
                str(chunk.get("section") or "").strip(),
                f"p.{chunk['page_num']}" if chunk.get("page_num") is not None else "",
            ]
            if piece
        )
        blocks.append(f"[{label or 'Source'}]\n{content}")
    return "\n\n".join(blocks)
