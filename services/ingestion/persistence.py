from __future__ import annotations

import os
import sqlite3
import struct
from typing import Iterable, Sequence

from services.retrieval.embeddings import Embedder, default_embedder
from services.retrieval.vector import index_chunks_batch, vector_table_exists

from .typed_walker import TypedNode


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


# --- Typed-node persistence (PR 1, behind INGEST_USE_DOCLING) -----------
#
# Mirrors the chunk helpers above but writes into the `nodes`,
# `node_embeddings`, and `node_fts` tables added by migration 0016.
# The `nodes` table has FK to `documents(id) ON DELETE CASCADE` and
# triggers keep `node_fts` in sync. `node_embeddings` is a vec0 virtual
# table — vec0 doesn't honor FK cascades, so we clear orphans explicitly.

# Retrievable subset of the nine node types. `header` and `footer` are
# excluded — they're page chrome (page numbers, running titles) that
# would pollute BM25 + vector hits with low-signal text.
_RETRIEVABLE_NODE_TYPES = frozenset(
    {"heading", "body", "list_item", "caption", "table_cell", "footnote", "equation"}
)


def _pack_vector(vec: Sequence[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def node_embeddings_table_exists(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'node_embeddings'"
    ).fetchone()
    return bool(row)


def insert_typed_nodes(
    conn: sqlite3.Connection,
    doc_id: str,
    nodes: Sequence[TypedNode],
) -> list[int]:
    """Insert typed nodes for `doc_id`, return their assigned rowids in order."""
    ids: list[int] = []
    for node in nodes:
        cursor = conn.execute(
            """
            INSERT INTO nodes (
                doc_id, node_type, heading_path, page,
                char_start, char_end, verbatim_text,
                parent_block_id, reading_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc_id,
                node.node_type,
                node.heading_path,
                node.page,
                node.char_start,
                node.char_end,
                node.verbatim_text,
                node.parent_block_id,
                node.reading_order,
            ),
        )
        if cursor.lastrowid is not None:
            ids.append(int(cursor.lastrowid))
    return ids


def delete_typed_nodes(conn: sqlite3.Connection, doc_id: str) -> None:
    conn.execute("DELETE FROM nodes WHERE doc_id = ?", (doc_id,))
    if node_embeddings_table_exists(conn):
        conn.execute(
            "DELETE FROM node_embeddings WHERE node_id NOT IN (SELECT id FROM nodes)"
        )


def embed_and_index_nodes(
    conn: sqlite3.Connection,
    nodes: Sequence[TypedNode],
    node_ids: Sequence[int],
    *,
    embedder: Embedder | None = None,
) -> int:
    """Embed retrievable nodes, write into `node_embeddings`, return count.

    Skips silently when `node_embeddings` doesn't exist (sqlite-vec not
    loaded at runtime — same fallback the chunks_vec path uses).
    """
    if not nodes or not node_embeddings_table_exists(conn):
        return 0
    payload: list[tuple[int, str]] = [
        (int(nid), node.verbatim_text)
        for nid, node in zip(node_ids, nodes)
        if node.node_type in _RETRIEVABLE_NODE_TYPES
    ]
    if not payload:
        return 0
    embedder = embedder or default_embedder()
    vectors = embedder.embed_passages([text for _, text in payload])
    conn.executemany(
        "INSERT OR REPLACE INTO node_embeddings(node_id, embedding) VALUES (?, ?)",
        [(nid, _pack_vector(vec)) for (nid, _), vec in zip(payload, vectors)],
    )
    return len(payload)
