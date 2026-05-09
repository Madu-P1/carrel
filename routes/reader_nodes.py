"""Reader-side typed-node lookup.

PR 4.2 of the Ask-pipeline rebuild. The Free-tier card UI navigates to
`/reader/{doc_id}?node={node_id}` after the user clicks Open on a card.
The reader then fetches THIS endpoint to get everything it needs to
land the highlight on the right passage:

- page (1-indexed)
- char_start / char_end against the canonical normalized text
- verbatim_text (used to text-search inside the rendered chunks)
- heading_path (rendered as a tooltip on the highlight overlay)

The reader uses verbatim_text to locate the passage in the rendered
document via the DOM Range API. Char offsets are returned for future
use — once a canonical-text reader pane lands in PR 4.3+, the reader
can scroll directly to (char_start, char_end) without a text search.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

import db

router = APIRouter()


@router.get("/api/reader/node/{node_id}")
def get_reader_node(node_id: int) -> Dict[str, Any]:
    if node_id <= 0:
        raise HTTPException(status_code=400, detail="node_id must be positive.")

    with db.get_db() as conn:
        # `nodes` table only exists once migration 0016 has applied. If
        # the migration is missing (e.g., a sqlite-vec-less runtime), we
        # surface a 404 — the UI treats this as "node not available"
        # and falls back to page-level navigation only.
        try:
            row = conn.execute(
                """
                SELECT n.id, n.doc_id, n.node_type, n.heading_path,
                       n.page, n.char_start, n.char_end, n.verbatim_text,
                       d.filename, d.subject_name
                FROM nodes n
                LEFT JOIN documents d ON d.id = n.doc_id
                WHERE n.id = ?
                """,
                (node_id,),
            ).fetchone()
        except Exception as exc:
            # Most plausible cause: migration 0016 hasn't run yet on this
            # DB. Surface 404 so the reader UI quietly degrades to
            # page-level navigation.
            raise HTTPException(
                status_code=404,
                detail="Typed-node table not available; re-run migrations.",
            ) from exc

    if row is None:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found.")

    return {
        "node_id": int(row["id"]),
        "doc_id": str(row["doc_id"]),
        "filename": row["filename"],
        "subject_name": row["subject_name"],
        "node_type": str(row["node_type"]),
        "heading_path": str(row["heading_path"] or ""),
        "page": row["page"],
        "char_start": int(row["char_start"]),
        "char_end": int(row["char_end"]),
        "verbatim_text": str(row["verbatim_text"] or ""),
    }


def register_reader_node_routes(app) -> None:
    app.include_router(router)
