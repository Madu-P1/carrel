from __future__ import annotations

import sqlite3
import struct
from typing import Iterable

from services.retrieval.embeddings import Embedder, default_embedder
from services.retrieval.fts import Hit


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def vector_table_exists(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'chunks_vec'"
    ).fetchone()
    return bool(row)


def index_chunk(conn: sqlite3.Connection, rowid: int, vec: list[float]) -> None:
    if not vector_table_exists(conn):
        return
    conn.execute(
        "INSERT OR REPLACE INTO chunks_vec(chunk_id, embedding) VALUES (?, ?)",
        (rowid, _pack(vec)),
    )


def index_chunks_batch(conn: sqlite3.Connection, rows: Iterable[tuple[int, list[float]]]) -> None:
    if not vector_table_exists(conn):
        return
    conn.executemany(
        "INSERT OR REPLACE INTO chunks_vec(chunk_id, embedding) VALUES (?, ?)",
        ((rowid, _pack(vec)) for rowid, vec in rows),
    )


def search_vector(
    conn: sqlite3.Connection,
    query: str,
    *,
    embedder: Embedder | None = None,
    doc_ids: list[str] | None = None,
    subject_name: str | None = None,
    limit: int = 20,
) -> list[Hit]:
    if not query.strip() or not vector_table_exists(conn):
        return []

    embedder = embedder or default_embedder()
    qvec = _pack(embedder.embed_query(query))
    candidate_k = limit * 4 if (doc_ids or subject_name) else limit

    sql = [
        "SELECT c.id AS chunk_id, c.doc_id, c.section, c.content,",
        "       v.distance AS score",
        "FROM chunks_vec v",
        "JOIN chunks c ON c.rowid = v.chunk_id",
    ]
    params: list[object] = [qvec, candidate_k]
    where = ["v.embedding MATCH ?", "k = ?"]

    if subject_name:
        sql.append("JOIN documents d ON d.id = c.doc_id")
        where.append("d.subject_name = ?")
        params.append(subject_name)

    if doc_ids:
        placeholders = ",".join("?" * len(doc_ids))
        where.append(f"c.doc_id IN ({placeholders})")
        params.extend(doc_ids)

    sql.append("WHERE " + " AND ".join(where))
    sql.append("ORDER BY v.distance ASC LIMIT ?")
    params.append(limit)

    try:
        rows = conn.execute("\n".join(sql), params).fetchall()
    except sqlite3.OperationalError:
        return []

    return [
        Hit(
            chunk_id=str(row["chunk_id"]),
            doc_id=str(row["doc_id"]),
            section=row["section"],
            snippet=str(row["content"] or "")[:240],
            score=-float(row["score"]),
        )
        for row in rows
    ]
