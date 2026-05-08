"""Hybrid BM25 + vector retrieval over the typed-node tables.

Reciprocal Rank Fusion (k=60) over `nodes_fts` and `node_embeddings`,
filtered by query-keyword-driven node_type expansion. Mirrors the
existing `services.retrieval.hybrid::search_hybrid` shape but reads
from migration 0016 and emits a richer `RetrievedNode` row that
includes everything the citation chip needs (doc_id, page,
heading_path, verbatim_text, char_start/char_end).

PR 2 landed BM25 + vector + RRF; PR 3 adds optional cross-encoder
rerank (gated by `RETRIEVAL_USE_RERANKER`) and a blended final score
of `0.7 * rerank_normalized + 0.3 * rrf_normalized`. Both paths are
exercised by the same entry point — callers pass `use_reranker=True`
to opt in.
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
from services.retrieval.rerank import Reranker, default_reranker, normalize_scores


@dataclass(frozen=True)
class RetrievedNode:
    """Citation-ready retrieval result.

    `score` is the RRF sum from BM25 + vector when rerank is off,
    or the blended `0.7 * rerank_normalized + 0.3 * rrf_normalized`
    when rerank is on. `rerank_score` carries the raw [0, 1]
    cross-encoder score for inspection / logging; it's None when
    rerank wasn't applied.
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
    rerank_score: float | None = None


def retrieval_use_nodes_enabled() -> bool:
    """Top-level flag — callers above retrieval gate which path to use.

    Defaults off so deploying PR 2 alone never changes user-facing
    behavior. PR 4 (Free-tier card UI) flips it on for new sessions.
    """
    return os.getenv("RETRIEVAL_USE_NODES", "false").lower() in ("1", "true", "yes")


def retrieval_use_reranker_enabled() -> bool:
    """Cross-encoder rerank flag — independent of `RETRIEVAL_USE_NODES`.

    Defaults off so first-run users don't pay the ~1 GB cross-encoder
    model download until rerank is actually wanted. The flag is read by
    callers above retrieval, not by `search_typed_hybrid` itself —
    keeping retrieval pure makes it testable without env-var fiddling.
    """
    return os.getenv("RETRIEVAL_USE_RERANKER", "false").lower() in ("1", "true", "yes")


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


def _apply_rerank(
    candidates: list[RetrievedNode],
    query: str,
    reranker: Reranker,
    blend: float,
) -> list[RetrievedNode]:
    """Re-score `candidates` via cross-encoder + blend with normalized RRF.

    Returns a new list (RetrievedNode is frozen) sorted by the blended
    final score. The blend formula is `blend * rerank + (1 - blend) * rrf`
    after both sides are min-max normalised to [0, 1] across the result
    set, which is what the parent algorithm spec asks for.
    """
    if not candidates:
        return []
    rerank_scores = reranker.rerank_pairs(query, [n.verbatim_text for n in candidates])
    if len(rerank_scores) != len(candidates):
        # Defensive: a misbehaving reranker that doesn't return one
        # score per document should not silently mislabel hits.
        raise ValueError(
            f"reranker returned {len(rerank_scores)} scores for {len(candidates)} candidates"
        )
    rrf_norm = normalize_scores(c.score for c in candidates)
    rerank_norm = normalize_scores(rerank_scores)
    rescored: list[RetrievedNode] = []
    for cand, rrf_n, rer_n, raw_rer in zip(candidates, rrf_norm, rerank_norm, rerank_scores):
        rescored.append(
            RetrievedNode(
                node_id=cand.node_id,
                doc_id=cand.doc_id,
                node_type=cand.node_type,
                heading_path=cand.heading_path,
                page=cand.page,
                char_start=cand.char_start,
                char_end=cand.char_end,
                verbatim_text=cand.verbatim_text,
                snippet=cand.snippet,
                score=blend * rer_n + (1.0 - blend) * rrf_n,
                components=cand.components,
                sources=cand.sources,
                rerank_score=float(raw_rer),
            )
        )
    rescored.sort(key=lambda hit: hit.score, reverse=True)
    return rescored


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
    use_reranker: bool = False,
    reranker: Reranker | None = None,
    rerank_top: int = 50,
    rerank_blend: float = 0.7,
) -> list[RetrievedNode]:
    """Top-`limit` typed-node hits, fused via RRF over BM25 + vector.

    `node_types`, when omitted, is derived from the query via
    `node_types_for_query` — base prose types plus any extras
    triggered by query keywords (table, figure, formula, footnote).
    Pass an explicit set to override.

    When `use_reranker=True`, the top `rerank_top` RRF candidates are
    re-scored by a cross-encoder (defaults to `default_reranker()`,
    which lazy-loads `BAAI/bge-reranker-base` on first call). Final
    score becomes `rerank_blend * rerank + (1 - rerank_blend) * rrf`,
    both min-max normalised across the result set.
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

    if use_reranker:
        top = fused[:rerank_top]
        active_reranker = reranker if reranker is not None else default_reranker()
        fused = _apply_rerank(top, query, active_reranker, rerank_blend)

    return fused[:limit]
