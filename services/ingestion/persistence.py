from __future__ import annotations

import os
import sqlite3
from typing import Iterable, Sequence

from services.retrieval.embeddings import Embedder, default_embedder
from services.retrieval.vector import index_chunks_batch, vector_table_exists


def _embed_on_ingest_enabled() -> bool:
    return os.getenv("EMBED_ON_INGEST", "true").lower() in ("1", "true", "yes")


def mark_vector_backfill_pending(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO app_settings (key, value)
        VALUES ('chunks_vec_backfill_pending', '1')
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """
    )


def index_chunk_rowids_on_ingest(
    conn: sqlite3.Connection,
    chunk_rowids: Sequence[int],
    *,
    embedder: Embedder | None = None,
) -> int:
    if not chunk_rowids or not vector_table_exists(conn):
        return 0
    if not _embed_on_ingest_enabled():
        mark_vector_backfill_pending(conn)
        return 0

    placeholders = ",".join("?" * len(chunk_rowids))
    rows = conn.execute(
        f"SELECT rowid, content FROM chunks WHERE rowid IN ({placeholders}) ORDER BY rowid ASC",
        tuple(chunk_rowids),
    ).fetchall()
    if not rows:
        return 0

    embedder = embedder or default_embedder()
    contents = [str(row["content"] or "") for row in rows]
    vectors = embedder.embed_passages(contents)
    indexed_rows = [(int(row["rowid"]), vector) for row, vector in zip(rows, vectors)]
    index_chunks_batch(conn, indexed_rows)
    conn.execute(
        f"UPDATE chunks SET embedding_status = 'indexed' WHERE rowid IN ({placeholders})",
        tuple(chunk_rowids),
    )
    return len(indexed_rows)


def delete_chunk_vectors(conn: sqlite3.Connection, rowids: Iterable[int]) -> None:
    if not vector_table_exists(conn):
        return
    rowid_list = [int(rowid) for rowid in rowids]
    if not rowid_list:
        return
    placeholders = ",".join("?" * len(rowid_list))
    conn.execute(
        f"DELETE FROM chunks_vec WHERE chunk_id IN ({placeholders})",
        tuple(rowid_list),
    )
