from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, Optional


def resolve_evidence(
    conn: sqlite3.Connection,
    *,
    document_id: str,
    chunk_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if chunk_id:
        row = conn.execute(
            """
            SELECT c.id AS chunk_id, c.doc_id AS document_id, c.section, c.page_num,
                   c.content, c.provenance_json, d.filename AS document_name
            FROM chunks c
            JOIN documents d ON d.id = c.doc_id
            WHERE c.doc_id = ? AND c.id = ?
            """,
            (document_id, chunk_id),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT NULL AS chunk_id, d.id AS document_id, NULL AS section,
                   NULL AS page_num, '' AS content, NULL AS provenance_json,
                   d.filename AS document_name
            FROM documents d
            WHERE d.id = ?
            """,
            (document_id,),
        ).fetchone()
    if row is None:
        return None

    provenance: dict[str, Any] = {}
    try:
        provenance = json.loads(row["provenance_json"] or "{}")
        if not isinstance(provenance, dict):
            provenance = {}
    except json.JSONDecodeError:
        provenance = {}

    bbox = provenance.get("bbox")
    if not (isinstance(bbox, list) and len(bbox) == 4):
        bbox = None
    text_offset_start = provenance.get("text_offset_start")
    text_offset_end = provenance.get("text_offset_end")
    if bbox:
        location_kind = "bbox"
    elif isinstance(text_offset_start, int) and isinstance(text_offset_end, int):
        location_kind = "text_offset"
    elif row["chunk_id"]:
        location_kind = "chunk"
    else:
        location_kind = "page"

    quote_text = str(row["content"] or "").strip()
    if len(quote_text) > 420:
        quote_text = f"{quote_text[:420].rstrip()}..."

    return {
        "document_id": row["document_id"],
        "chunk_id": row["chunk_id"],
        "document_name": row["document_name"] or "Source",
        "section": row["section"],
        "page_num": row["page_num"],
        "quote_text": quote_text,
        "confidence": 0.92
        if location_kind in {"bbox", "text_offset"}
        else 0.72
        if row["chunk_id"]
        else 0.5,
        "location_kind": location_kind,
        "bbox": bbox,
        "text_offset_start": text_offset_start if isinstance(text_offset_start, int) else None,
        "text_offset_end": text_offset_end if isinstance(text_offset_end, int) else None,
    }
