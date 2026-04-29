"""Search route.

Hybrid (FTS + vector) search over the user's source library. The
heavy lifting lives in `services.retrieval.search_hybrid`, which fuses
BM25 keyword hits and dense-vector hits via reciprocal rank fusion.
This route is a thin wrapper that:

  1. Validates input (non-empty query, sane limit).
  2. Runs the hybrid search.
  3. Enriches each hit with document-level context (filename, subject,
     page number) so the UI can render hits as "this chunk in this
     document on this page" without a second round trip.

Why hybrid: keyword search excels at proper nouns and exact phrases;
vector search excels at semantic intent. Together they catch both
"the user typed 'mitosis'" and "the user typed 'cell division'" against
a chunk that says "mitosis." Single-source search misses one or the
other ~30% of the time on real corpora; RRF fusion gets us the union
without making us pick.

Limits and rationale:
  * `limit` capped at 50: more results than that don't fit a useful UI
    and the embedding round-trip on the query is the dominant cost; we
    don't want to pay it for results no one scrolls to.
  * `query` capped at 500 chars: search_hybrid sanitizes, but a 100KB
    paste shouldn't get embedded — we'd be running an embedder over
    something the user didn't actually mean to search for.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

import db
from services.retrieval.embeddings import default_embedder
from services.retrieval.hybrid import search_hybrid

router = APIRouter()

# Hard caps. Keep these in lockstep with the frontend's API client validation
# so a bad value gets caught client-side, but the server still defends itself.
MAX_QUERY_CHARS = 500
MAX_LIMIT = 50
DEFAULT_LIMIT = 12


@router.get("/api/search")
def search(
    q: str,
    limit: int = DEFAULT_LIMIT,
    subject_name: Optional[str] = None,
    doc_id: Optional[str] = None,
) -> Dict[str, Any]:
    query = (q or "").strip()
    if not query:
        # 400 not 422: empty query isn't a validation failure of a typed
        # field (q is required as a non-empty string at the protocol level
        # but FastAPI accepts q="" which becomes empty after strip).
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    if len(query) > MAX_QUERY_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Query exceeds {MAX_QUERY_CHARS} characters.",
        )
    if limit < 1 or limit > MAX_LIMIT:
        raise HTTPException(
            status_code=400,
            detail=f"limit must be between 1 and {MAX_LIMIT}.",
        )

    doc_ids = [doc_id] if doc_id else None

    with db.get_db() as conn:
        hits = search_hybrid(
            conn,
            query,
            embedder=default_embedder(),
            doc_ids=doc_ids,
            subject_name=subject_name,
            limit=limit,
        )

        # Enrich with document metadata + page number in one pass so the UI
        # can render "filename · subject · p. 12" without a follow-up fetch
        # per result. The chunk-level JOIN is cheap because we already have
        # the full result set in memory and chunks.id is the PK.
        if not hits:
            return {"query": query, "results": []}

        chunk_ids = [hit.chunk_id for hit in hits]
        placeholders = ",".join("?" * len(chunk_ids))
        meta_rows = conn.execute(
            f"""
            SELECT c.id AS chunk_id,
                   c.page_num,
                   d.filename,
                   d.subject_name
            FROM chunks c
            JOIN documents d ON d.id = c.doc_id
            WHERE c.id IN ({placeholders})
            """,
            chunk_ids,
        ).fetchall()
        meta_by_id = {row["chunk_id"]: row for row in meta_rows}

        results: List[Dict[str, Any]] = []
        for hit in hits:
            meta = meta_by_id.get(hit.chunk_id)
            results.append(
                {
                    "chunk_id": hit.chunk_id,
                    "doc_id": hit.doc_id,
                    "section": hit.section,
                    "snippet": hit.snippet,
                    "score": round(hit.score, 5),
                    # `sources` tells the UI whether this hit came from
                    # keyword (fts), vector (vec), or both. Both-source
                    # hits are typically the strongest matches and the UI
                    # surfaces them with a tighter accent.
                    "sources": list(hit.sources),
                    "filename": meta["filename"] if meta else None,
                    "subject_name": meta["subject_name"] if meta else None,
                    "page_num": meta["page_num"] if meta else None,
                }
            )

        return {"query": query, "results": results}


def register_search_routes(app) -> None:
    app.include_router(router)
