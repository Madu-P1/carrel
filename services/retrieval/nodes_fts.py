"""BM25 search against the `node_fts` index from migration 0016.

Mirrors `services.retrieval.fts.search_keyword` but reads typed-node
columns (heading_path, page, char_start/char_end, verbatim_text,
node_type) so retrieved hits can drive citation chips directly. The
`heading_path` column is indexed alongside `verbatim_text` so a query
like "photosystem II" matches body text AND headings that scope it.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass
from typing import Iterable

from app_logging import get_logger, log_event

LOGGER = get_logger("retrieval.nodes_fts")

_FTS_OPERATOR_CHARS = re.compile(r"[^\w\s]+", re.UNICODE)


@dataclass(frozen=True)
class NodeHit:
    """One BM25 hit against `node_fts`, hydrated from the joined `nodes` row."""

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


def _sanitize_query(query: str) -> str:
    cleaned = _FTS_OPERATOR_CHARS.sub(" ", query)
    tokens = [token for token in cleaned.split() if token]
    return " ".join(tokens)


def search_node_fts(
    conn: sqlite3.Connection,
    query: str,
    *,
    node_types: Iterable[str] | None = None,
    doc_ids: list[str] | None = None,
    subject_name: str | None = None,
    limit: int = 50,
) -> list[NodeHit]:
    """Top-`limit` BM25 candidates from `node_fts` filtered by node_type."""
    sanitized = _sanitize_query(query)
    if not sanitized:
        return []

    sql = [
        "SELECT n.id AS node_id, n.doc_id, n.node_type, n.heading_path,",
        "       n.page, n.char_start, n.char_end, n.verbatim_text,",
        "       snippet(node_fts, 0, '<<', '>>', '…', 12) AS snippet,",
        "       -bm25(node_fts) AS score",
        "FROM node_fts",
        "JOIN nodes n ON n.id = node_fts.id",
    ]
    params: list[object] = [sanitized]
    where = ["node_fts MATCH ?"]

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
            # Empty allowlist means "match nothing" — caller likely
            # meant to skip retrieval entirely.
            return []
        placeholders = ",".join("?" * len(type_list))
        where.append(f"n.node_type IN ({placeholders})")
        params.extend(type_list)

    sql.append("WHERE " + " AND ".join(where))
    sql.append("ORDER BY score DESC LIMIT ?")
    params.append(limit)

    try:
        rows = conn.execute("\n".join(sql), params).fetchall()
    except sqlite3.OperationalError as exc:
        log_event(
            LOGGER,
            logging.WARNING,
            "node_fts_search_failed",
            error_type=exc.__class__.__name__,
            error=str(exc),
            doc_filter_count=len(doc_ids or []),
            subject_filter=bool(subject_name),
        )
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
            snippet=str(row["snippet"] or ""),
            score=float(row["score"]),
        )
        for row in rows
    ]
