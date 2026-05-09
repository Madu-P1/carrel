"""Free-tier Ask cards endpoint — typed-node retrieval as JSON.

PR 4 of 6 from the Ask-pipeline rebuild. The Free-tier UI replaces
today's synthesised-answer view with a vertical list of citation
cards: heading_path eyebrow, verbatim quote, doc + page footer, Open
button. Every field the card needs comes back from this endpoint.

Why a separate endpoint instead of extending /api/tutor/query
- /api/tutor/query is the Pro-tier flow: it synthesises prose with
  Claude via tool-use validators (PR 5). The Free-tier card view
  doesn't synthesise — the cards ARE the answer. Splitting routes
  keeps the validator surface small and lets us deprecate the
  legacy chunks path at the route level once typed-node retrieval
  is the default.
- The endpoint never touches the legacy `chunks` tables. Calling it
  on a library that hasn't run the typed-node ingest will simply
  return zero cards, never an error — the UI shows an empty state.

Behaviour gates
- The endpoint exists unconditionally; the FRONTEND chooses whether
  to call it based on `RETRIEVAL_USE_NODES`. The flag isn't read
  here so a developer can hit the route with curl and inspect raw
  data even when the flag is off in their session.
- `use_reranker` query param: explicit True/False overrides the
  `RETRIEVAL_USE_RERANKER` env flag. Omitted -> follow the flag.

Limits mirror /api/search so a misbehaving client can't run the
embedder on a 100 KB paste or pull a 10 K result set.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

import db
from services.retrieval.embeddings import default_embedder
from services.retrieval.typed_hybrid import (
    retrieval_use_reranker_enabled,
    search_typed_hybrid,
)

router = APIRouter()

# Hard caps. Keep these in lockstep with the frontend client validation
# so a bad value gets caught client-side; the server defends itself too.
MAX_QUERY_CHARS = 500
MAX_LIMIT = 20
DEFAULT_LIMIT = 5


@router.get("/api/ask/cards")
def ask_cards(
    q: str,
    limit: int = DEFAULT_LIMIT,
    subject_name: Optional[str] = None,
    doc_id: Optional[str] = None,
    use_reranker: Optional[bool] = None,
) -> Dict[str, Any]:
    query = (q or "").strip()
    if not query:
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

    rerank_effective = (
        use_reranker if use_reranker is not None else retrieval_use_reranker_enabled()
    )

    doc_ids = [doc_id] if doc_id else None

    with db.get_db() as conn:
        # Snapshot library size so the UI can render an honest empty
        # state ("no typed nodes indexed yet — run docling ingest first")
        # instead of a generic "no results."
        total_nodes = conn.execute("SELECT COUNT(*) AS n FROM nodes").fetchone()["n"]

        hits = search_typed_hybrid(
            conn,
            query,
            embedder=default_embedder(),
            doc_ids=doc_ids,
            subject_name=subject_name,
            limit=limit,
            use_reranker=rerank_effective,
        )

        if not hits:
            return {
                "query": query,
                "cards": [],
                "library": {"total_nodes": total_nodes},
                "rerank_used": rerank_effective,
            }

        # Hydrate doc filename + subject in one round-trip so the card
        # footer ("Lehninger, p. 472") doesn't need an extra fetch.
        unique_doc_ids = list({hit.doc_id for hit in hits})
        placeholders = ",".join("?" * len(unique_doc_ids))
        meta_rows = conn.execute(
            f"""
            SELECT id AS doc_id, filename, subject_name
            FROM documents
            WHERE id IN ({placeholders})
            """,
            unique_doc_ids,
        ).fetchall()
        meta_by_id = {row["doc_id"]: row for row in meta_rows}

        cards: List[Dict[str, Any]] = []
        for hit in hits:
            meta = meta_by_id.get(hit.doc_id)
            cards.append(
                {
                    "node_id": hit.node_id,
                    "doc_id": hit.doc_id,
                    "filename": meta["filename"] if meta else None,
                    "subject_name": meta["subject_name"] if meta else None,
                    "node_type": hit.node_type,
                    "heading_path": hit.heading_path,
                    "page": hit.page,
                    "char_start": hit.char_start,
                    "char_end": hit.char_end,
                    "verbatim_text": hit.verbatim_text,
                    "snippet": hit.snippet,
                    "score": round(hit.score, 5),
                    # rerank_score is None when the rerank path didn't
                    # fire — UI uses presence to decide whether to show
                    # a confidence badge.
                    "rerank_score": (
                        round(hit.rerank_score, 5) if hit.rerank_score is not None else None
                    ),
                    # `sources` lets the UI surface "matched on both
                    # keyword and meaning" with a tighter accent.
                    "sources": list(hit.sources),
                }
            )

        return {
            "query": query,
            "cards": cards,
            "library": {"total_nodes": total_nodes},
            "rerank_used": rerank_effective,
        }


def register_ask_cards_routes(app) -> None:
    app.include_router(router)
