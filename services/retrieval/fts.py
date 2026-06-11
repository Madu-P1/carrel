import re
import sqlite3
from dataclasses import dataclass

_FTS_OPERATOR_CHARS = re.compile(r"[^\w\s]+", re.UNICODE)


@dataclass(frozen=True)
class Hit:
    chunk_id: str
    doc_id: str
    section: str | None
    snippet: str
    score: float


def _sanitize_query(query: str) -> str:
    # OR-joined quoted tokens, mirroring services.retrieval.nodes_fts: bare
    # space-separated terms are implicit AND in FTS5, which zeroes out any
    # sentence-shaped query with one non-shared word. Ranked BM25 over the
    # query vocabulary is what the hybrid fusion expects from this arm.
    cleaned = _FTS_OPERATOR_CHARS.sub(" ", query)
    tokens = dict.fromkeys(token for token in cleaned.split() if token)
    return " OR ".join(f'"{token}"' for token in tokens)


def search_keyword(
    conn: sqlite3.Connection,
    query: str,
    *,
    doc_ids: list[str] | None = None,
    subject_name: str | None = None,
    limit: int = 20,
) -> list[Hit]:
    sanitized = _sanitize_query(query)
    if not sanitized:
        return []

    sql = [
        "SELECT f.id AS chunk_id, f.doc_id, f.section,",
        "       snippet(chunks_fts, 0, '<<', '>>', '…', 12) AS snippet,",
        "       -bm25(chunks_fts) AS score",
        "FROM chunks_fts f",
    ]
    params: list[object] = [sanitized]
    where = ["chunks_fts MATCH ?"]

    if subject_name:
        sql.append("JOIN documents d ON d.id = f.doc_id")
        where.append("d.subject_name = ?")
        params.append(subject_name)

    if doc_ids:
        placeholders = ",".join("?" * len(doc_ids))
        where.append(f"f.doc_id IN ({placeholders})")
        params.extend(doc_ids)

    sql.append("WHERE " + " AND ".join(where))
    sql.append("ORDER BY score DESC LIMIT ?")
    params.append(limit)

    rows = conn.execute("\n".join(sql), params).fetchall()
    return [
        Hit(
            chunk_id=str(row["chunk_id"]),
            doc_id=str(row["doc_id"]),
            section=row["section"],
            snippet=str(row["snippet"]),
            score=float(row["score"]),
        )
        for row in rows
    ]
