from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from services.retrieval.embeddings import Embedder
from services.retrieval.fts import Hit, search_keyword
from services.retrieval.vector import search_vector


@dataclass(frozen=True)
class ScoredHit:
    chunk_id: str
    doc_id: str
    section: str | None
    snippet: str
    score: float
    components: dict[str, float] = field(default_factory=dict)
    sources: tuple[str, ...] = ()


def _rrf_score(rank: int, k: int = 60) -> float:
    return 1.0 / (k + rank)


def _upsert_hit(
    buckets: dict[str, dict[str, object]],
    hit: Hit,
    *,
    source: str,
    rank: int,
    rrf_k: int,
) -> None:
    bucket = buckets.setdefault(
        hit.chunk_id,
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
    assert isinstance(existing_hit, Hit)
    if source == "fts" and ("<<" in hit.snippet or ">>" in hit.snippet or not existing_hit.snippet):
        bucket["hit"] = hit


def search_hybrid(
    conn: sqlite3.Connection,
    query: str,
    *,
    embedder: Embedder | None = None,
    doc_ids: list[str] | None = None,
    subject_name: str | None = None,
    limit: int = 10,
    candidate_k: int = 30,
    rrf_k: int = 60,
) -> list[ScoredHit]:
    if not query.strip():
        return []

    fts_hits = search_keyword(
        conn,
        query,
        doc_ids=doc_ids,
        subject_name=subject_name,
        limit=candidate_k,
    )
    vec_hits = search_vector(
        conn,
        query,
        embedder=embedder,
        doc_ids=doc_ids,
        subject_name=subject_name,
        limit=candidate_k,
    )

    by_id: dict[str, dict[str, object]] = {}
    for rank, hit in enumerate(fts_hits, start=1):
        _upsert_hit(by_id, hit, source="fts", rank=rank, rrf_k=rrf_k)
    for rank, hit in enumerate(vec_hits, start=1):
        _upsert_hit(by_id, hit, source="vec", rank=rank, rrf_k=rrf_k)

    fused: list[ScoredHit] = []
    for chunk_id, bucket in by_id.items():
        hit = bucket["hit"]
        components = bucket["components"]
        sources = bucket["sources"]
        assert isinstance(hit, Hit)
        assert isinstance(components, dict)
        assert isinstance(sources, list)
        fused.append(
            ScoredHit(
                chunk_id=chunk_id,
                doc_id=hit.doc_id,
                section=hit.section,
                snippet=hit.snippet,
                score=sum(float(value) for value in components.values()),
                components={str(key): float(value) for key, value in components.items()},
                sources=tuple(str(source) for source in sources),
            )
        )

    fused.sort(key=lambda hit: hit.score, reverse=True)
    return fused[:limit]
