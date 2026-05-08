"""Vector kNN against the `node_embeddings` index from migration 0016.

Mirrors `services.retrieval.vector.search_vector` but reads from
`node_embeddings` (vec0 float[384], same dim as chunks_vec so the same
`BAAI/bge-small-en-v1.5` embedder serves both indexes). Returns
`NodeHit` rows hydrated from `nodes` so callers can fuse with BM25
candidates from `nodes_fts.py` without a second round-trip.
"""
from __future__ import annotations

import sqlite3
import struct
from typing import Iterable

from services.retrieval.embeddings import Embedder, default_embedder
from services.retrieval.nodes_fts import NodeHit


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def node_vector_table_exists(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'node_embeddings'"
    ).fetchone()
    return bool(row)


def search_node_vectors(
    conn: sqlite3.Connection,
    query: str,
    *,
    embedder: Embedder | None = None,
    node_types: Iterable[str] | None = None,
    doc_ids: list[str] | None = None,
    subject_name: str | None = None,
    limit: int = 50,
) -> list[NodeHit]:
    """Top-`limit` cosine-distance hits from `node_embeddings`.

    Filters narrow the candidate pool: when `subject_name`, `doc_ids`,
    or `node_types` are passed, vec0 is asked for `limit * 4` raw
    candidates and the SQL filter trims to `limit` after the join.
    """
    if not query.strip() or not node_vector_table_exists(conn):
        return []

    embedder = embedder or default_embedder()
    qvec = _pack(embedder.embed_query(query))
    has_filters = bool(subject_name or doc_ids or node_types is not None)
    candidate_k = limit * 4 if has_filters else limit

    sql = [
        "SELECT n.id AS node_id, n.doc_id, n.node_type, n.heading_path,",
        "       n.page, n.char_start, n.char_end, n.verbatim_text,",
        "       v.distance AS distance",
        "FROM node_embeddings v",
        "JOIN nodes n ON n.id = v.node_id",
    ]
    params: list[object] = [qvec, candidate_k]
    where = ["v.embedding MATCH ?", "k = ?"]

    if subject_name:
        sql.append("JOIN documents d ON d.id = n.doc_id")
        where.append("d.subject_name = ?")
        params.append(subject_name)

    if doc_ids:
        placeholders = ",".join("?" * len(doc_ids))
        where.append(f"n.doc_id IN ({placeholders})")
        params.extend(doc_ids)

    if node_types is not None:
        type_list = list(node_types)
        if not type_list:
            return []
        placeholders = ",".join("?" * len(type_list))
        where.append(f"n.node_type IN ({placeholders})")
        params.extend(type_list)

    sql.append("WHERE " + " AND ".join(where))
    sql.append("ORDER BY v.distance ASC LIMIT ?")
    params.append(limit)

    try:
        rows = conn.execute("\n".join(sql), params).fetchall()
    except sqlite3.OperationalError:
        return []

    return [
        NodeHit(
            node_id=int(row["node_id"]),
            doc_id=str(row["doc_id"]),
            node_type=str(row["node_type"]),
            heading_path=str(row["heading_path"] or ""),
            page=row["page"],
            char_start=int(row["char_start"]),
            char_end=int(row["char_end"]),
            verbatim_text=str(row["verbatim_text"] or ""),
            snippet=str(row["verbatim_text"] or "")[:240],
            score=-float(row["distance"]),
        )
        for row in rows
    ]
