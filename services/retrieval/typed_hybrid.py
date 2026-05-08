"""Hybrid BM25 + vector retrieval over the typed-node tables.

Reciprocal Rank Fusion (k=60) over `nodes_fts` and `node_embeddings`,
filtered by query-keyword-driven node_type expansion. Mirrors the
existing `services.retrieval.hybrid::search_hybrid` shape but reads
from migration 0016 and emits a richer `RetrievedNode` row that
includes everything the citation chip needs (doc_id, page,
heading_path, verbatim_text, char_start/char_end).

PR 2 of 6 from the Ask-pipeline rebuild. Cross-encoder rerank ships in
PR 3 — until then `score` is the RRF sum only.
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from typing import Iterable

from services.retrieval.embeddings import Embedder
from services.retrieval.node_type_router import node_types_for_query
from services.retrieval.nodes_fts import NodeHit, search_node_fts
from services.retrieval.nodes_vector import search_node_vectors


@dataclass(frozen=True)
class RetrievedNode:
    """Citation-ready retrieval result.

    `score` is the RRF sum across the BM25 + vector lists in PR 2.
    PR 3 will add a `rerank_score` field and recompute `score` as
    `0.7 * rerank + 0.3 * rrf_normalized`.
    """

    node_id: int
    doc_id: str
    node_type: str
    heading_path: str
    page: int | None
    char_start: int
    char_end: int
    verbatim_text: str
    snippet: str
    score: float
    components: dict[str, float] = field(default_factory=dict)
    sources: tuple[str, ...] = ()


def retrieval_use_nodes_enabled() -> bool:
    """Top-level flag — callers above retrieval gate which path to use.

    Defaults off so deploying PR 2 alone never changes user-facing
    behavior. PR 4 (Free-tier card UI) flips it on for new sessions.
    """
    return os.getenv("RETRIEVAL_USE_NODES", "false").lower() in ("1", "true", "yes")


def _rrf_score(rank: int, k: int = 60) -> float:
    return 1.0 / (k + rank)


def _upsert_hit(
    buckets: dict[int, dict[str, object]],
    hit: NodeHit,
    *,
    source: str,
    rank: int,
    rrf_k: int,
) -> None:
    bucket = buckets.setdefault(
        hit.node_id,
        {
            "hit": hit,
            "components": {},
            "sources": [],
        },
    )
    components = bucket["components"]
    sources = bucket["sources"]
    assert isinstance(components, dict)
    assert isinstance(sources, list)
    components[source] = _rrf_score(rank, rrf_k)
    if source not in sources:
        sources.append(source)

    existing_hit = bucket["hit"]
    assert isinstance(existing_hit, NodeHit)
    # FTS hits carry the highlighted snippet; prefer them when available.
    if source == "fts" and ("<<" in hit.snippet or ">>" in hit.snippet):
        bucket["hit"] = hit


def search_typed_hybrid(
    conn: sqlite3.Connection,
    query: str,
    *,
    embedder: Embedder | None = None,
    node_types: Iterable[str] | None = None,
    doc_ids: list[str] | None = None,
    subject_name: str | None = None,
    limit: int = 10,
    candidate_k: int = 50,
    rrf_k: int = 60,
) -> list[RetrievedNode]:
    """Top-`limit` typed-node hits, fused via RRF over BM25 + vector.

    `node_types`, when omitted, is derived from the query via
    `node_types_for_query` — base prose types plus any extras
    triggered by query keywords (table, figure, formula, footnote).
    Pass an explicit set to override.
    """
    if not query.strip():
        return []

    types = frozenset(node_types) if node_types is not None else node_types_for_query(query)

    fts_hits = search_node_fts(
        conn,
        query,
        node_types=types,
        doc_ids=doc_ids,
        subject_name=subject_name,
        limit=candidate_k,
    )
    vec_hits = search_node_vectors(
        conn,
        query,
        embedder=embedder,
        node_types=types,
        doc_ids=doc_ids,
        subject_name=subject_name,
        limit=candidate_k,
    )

    by_id: dict[int, dict[str, object]] = {}
    for rank, hit in enumerate(fts_hits, start=1):
        _upsert_hit(by_id, hit, source="fts", rank=rank, rrf_k=rrf_k)
    for rank, hit in enumerate(vec_hits, start=1):
        _upsert_hit(by_id, hit, source="vec", rank=rank, rrf_k=rrf_k)

    fused: list[RetrievedNode] = []
    for node_id, bucket in by_id.items():
        hit = bucket["hit"]
        components = bucket["components"]
        sources = bucket["sources"]
        assert isinstance(hit, NodeHit)
        assert isinstance(components, dict)
        assert isinstance(sources, list)
        fused.append(
            RetrievedNode(
                node_id=node_id,
                doc_id=hit.doc_id,
                node_type=hit.node_type,
                heading_path=hit.heading_path,
                page=hit.page,
                char_start=hit.char_start,
                char_end=hit.char_end,
                verbatim_text=hit.verbatim_text,
                snippet=hit.snippet,
                score=sum(float(value) for value in components.values()),
                components={str(key): float(value) for key, value in components.items()},
                sources=tuple(str(source) for source in sources),
            )
        )

    fused.sort(key=lambda hit: hit.score, reverse=True)
    return fused[:limit]
