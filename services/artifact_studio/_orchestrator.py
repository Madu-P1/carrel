"""Artifact-studio orchestrator — the public entry points.

`generate_artifact` is the workhorse: scope → grounding → topic map →
generator dispatch → persistence → provenance linking. `list_artifacts`
and `get_artifact` are reads.

Imports private helpers from sibling submodules (grounding, topic_map,
generators). Names with leading underscores stay private *within the
package* — they are not part of the package's public surface.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app_logging import get_logger, log_event
from services import artifact_prompts
from services import provenance_service
from services.ingestion import build_flashcard_deck

from .grounding import (
    _chunk_text_for_scope,
    _concepts_for_scope,
    _fresh_chunks_for_sources,
    retrieve_grounding_chunks,
)
from .topic_map import _build_topic_map, _select_focus_concepts
from .generators import _hidden_artifact_payload, _KIND_TO_GENERATOR


LOGGER = get_logger("artifact_studio")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_artifact(
    conn: sqlite3.Connection,
    *,
    artifact_kind: str,
    source_ids: Optional[List[str]] = None,
    concept_ids: Optional[List[str]] = None,
    goal_id: Optional[str] = None,
    session_id: Optional[str] = None,
    audience: str = "student",
    difficulty: str = "standard",
    depth: str = "standard",
    style: str = "prose",
    output_length: str = "medium",
    evidence_strictness: str = "normal",
    custom_prompt: Optional[str] = None,
    show_citations: bool = False,
    grounding_mode: str = "internal_only",
) -> Dict[str, Any]:
    requested_kind = artifact_kind
    if artifact_kind not in _KIND_TO_GENERATOR:
        # Silent fallback was P0 in the autoplan eng review — at least
        # leave an audit trail so a typo'd kind from the route layer
        # shows up in logs and the response telegraphs that it was
        # rewritten (callers can branch on `requested_kind != artifact_kind`).
        log_event(
            LOGGER,
            logging.WARNING,
            "artifact_kind_rewritten",
            requested=requested_kind,
            fallback="study_guide",
        )
        artifact_kind = "study_guide"

    concepts = _concepts_for_scope(conn, source_ids, concept_ids, limit=16)

    goal_text = ""
    if goal_id:
        row = conn.execute("SELECT title FROM goals WHERE id = ?", (goal_id,)).fetchone()
        if row:
            goal_text = row["title"]

    retrieval_query = " ".join(
        part
        for part in [
            artifact_kind.replace("_", " "),
            custom_prompt or "",
            goal_text,
            " ".join(concept.get("name", "") for concept in concepts[:6]),
        ]
        if part
    ).strip()
    if artifact_kind == "flashcards" and source_ids and not concept_ids:
        chunks = _fresh_chunks_for_sources(conn, source_ids) or _chunk_text_for_scope(conn, source_ids, concept_ids, limit=96)
    else:
        chunks = retrieve_grounding_chunks(
            conn,
            source_ids=source_ids,
            concept_ids=concept_ids,
            query=retrieval_query,
            limit=12,
        )
    focus_concepts = _select_focus_concepts(concepts, chunks, limit=10)
    topic_map = _build_topic_map(focus_concepts)
    deck_items = None
    if artifact_kind == "flashcards":
        deck_title = str(custom_prompt or goal_text or (chunks[0].get("filename") if chunks else "") or artifact_kind).strip()
        deck_items = build_flashcard_deck(chunks, title=deck_title, count=12)
    markdown = _KIND_TO_GENERATOR[artifact_kind](
        focus_concepts,
        chunks,
        depth=depth,
        goal=goal_text,
        topic_map=topic_map,
        deck_items=deck_items,
    )
    hidden_payload = _hidden_artifact_payload(
        artifact_kind,
        focus_concepts,
        chunks,
        topic_map,
        custom_prompt=custom_prompt,
        deck_items=deck_items,
    )
    prompt_text = artifact_prompts.build_artifact_prompt(
        artifact_kind=artifact_kind,
        topic_map=topic_map,
        concepts=[
            {
                "id": concept["id"],
                "name": concept["name"],
                "description": concept.get("study_description") or concept.get("description"),
                "topic": concept.get("topic"),
            }
            for concept in focus_concepts
        ],
        grounding_chunks=[
            {
                "id": chunk.get("id"),
                "section": chunk.get("section"),
                "page_num": chunk.get("page_num"),
                "content": chunk.get("content"),
            }
            for chunk in chunks
        ],
        custom_prompt=custom_prompt,
    )

    source_scope_json = json.dumps(source_ids or [])
    concept_scope_json = json.dumps(concept_ids or [])

    # Build snapshot hash from all participating sources
    source_hashes = []
    if source_ids:
        rows = conn.execute(
            f"SELECT COALESCE(source_hash, id) AS h FROM documents WHERE id IN ({','.join('?' * len(source_ids))})",
            source_ids,
        ).fetchall()
        source_hashes = [r["h"] for r in rows]
    snapshot_hash = ":".join(sorted(source_hashes)) if source_hashes else None

    artifact_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO artifacts (
            id, artifact_kind, goal_id, session_id, source_scope, concept_scope,
            audience, difficulty, depth, style, output_length, evidence_strictness,
            prompt_text, output_markdown, output_json, source_snapshot_hash, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready')
        """,
        (
            artifact_id, artifact_kind, goal_id, session_id,
            source_scope_json, concept_scope_json,
            audience, difficulty, depth, style, output_length, evidence_strictness,
            prompt_text, markdown, json.dumps(hidden_payload, ensure_ascii=False), snapshot_hash,
        ),
    )
    # --- Link evidence references to artifact (Phase 1c) ---
    evidence_ids: List[str] = []
    for ch in chunks[:6]:
        snippet = (ch.get("content") or "")[:200].strip()
        doc_id = ch.get("doc_id")
        chunk_id = ch.get("id")
        if not snippet or not doc_id or not chunk_id:
            continue
        try:
            ev = provenance_service.build_evidence_reference(
                conn,
                {"document_id": doc_id, "chunk_id": chunk_id, "snippet": snippet,
                 "page_num": ch.get("page_num"), "section": ch.get("section")},
                confidence=0.65,
            )
            evidence_ids.append(ev["id"])
        except Exception:
            pass
    if evidence_ids:
        provenance_service.link_evidence_to_artifact(conn, artifact_id, evidence_ids)

    # --- Link to session if provided (Phase 1d) ---
    if session_id:
        provenance_service.link_session_artifact(conn, session_id, artifact_id)

    conn.commit()

    return {
        "id": artifact_id,
        "artifact_kind": artifact_kind,
        "requested_kind": requested_kind,
        "output_markdown": markdown,
        "audience": audience,
        "depth": depth,
        "output_length": output_length,
        "status": "ready",
        "stale": False,
        "concept_count": len(concepts),
        "source_count": len(set(ch.get("doc_id", "") for ch in chunks)),
        "evidence_count": len(evidence_ids),
        "grounding_mode": grounding_mode,
        "show_citations": show_citations,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def list_artifacts(conn: sqlite3.Connection, limit: int = 10) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, artifact_kind, audience, depth, output_length, status, stale,
               output_markdown, created_at, updated_at
        FROM artifacts
        ORDER BY updated_at DESC, created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        md = item.get("output_markdown") or ""
        item["preview"] = md[:200] + "…" if len(md) > 200 else md
        item.pop("output_markdown", None)
        items.append(item)
    return items


def get_artifact(conn: sqlite3.Connection, artifact_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        """
        SELECT id, artifact_kind, goal_id, session_id, source_scope, concept_scope,
               audience, difficulty, depth, style, output_length, evidence_strictness,
               prompt_text, output_markdown, output_json, source_snapshot_hash, version, status, stale,
               created_at, updated_at
        FROM artifacts
        WHERE id = ?
        """,
        (artifact_id,),
    ).fetchone()
    if not row:
        return None
    item = dict(row)
    for field in ("source_scope", "concept_scope"):
        try:
            item[field] = json.loads(item[field] or "[]")
        except Exception:
            item[field] = []
    try:
        item["output_json"] = json.loads(item.get("output_json") or "{}")
    except Exception:
        item["output_json"] = {}
    return item
