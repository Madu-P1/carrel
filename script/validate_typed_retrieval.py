#!/usr/bin/env python3
"""Side-by-side validation of typed-node retrieval against the legacy chunks path.

What this does
1. Walks every uploaded PDF that doesn't already have typed nodes,
   parses it with Docling, and indexes nodes / node_embeddings /
   node_fts. Idempotent — re-runs are cheap.
2. For each query in the question set, runs three retrieval paths:
       (A) legacy chunks via `search_hybrid`
       (B) typed-node hybrid via `search_typed_hybrid` (no rerank)
       (C) typed-node hybrid with cross-encoder rerank
   and prints the top results from each side-by-side.
3. Optionally writes machine-readable JSON for follow-up grading.

First run downloads the rerank model (~1 GB) into the fastembed cache.
Re-runs use the cache. Skip with --no-rerank if you only want to
compare BM25 + vector against the chunks path.

Usage
    ./.venv/bin/python script/validate_typed_retrieval.py
    ./.venv/bin/python script/validate_typed_retrieval.py --questions q.json
    ./.venv/bin/python script/validate_typed_retrieval.py --no-rerank --max-docs 5
"""

# Imports below the sys.path.insert call must NOT be sorted into the
# stdlib block by ruff/isort — they only resolve once REPO_ROOT is on
# the path. The per-line E402 noqa silences "import not at top of
# file"; this file-level skip silences the I001 import-sort rule.
# ruff: noqa: I001
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import db  # noqa: E402
from services.ingestion import docling_parser, typed_walker  # noqa: E402
from services.ingestion.persistence import (  # noqa: E402
    embed_and_index_nodes,
    insert_typed_nodes,
)
from services.retrieval.hybrid import search_hybrid  # noqa: E402
from services.retrieval.typed_hybrid import search_typed_hybrid  # noqa: E402


# Library-agnostic prompts — replace via --questions FILE for content
# the founder has actually uploaded (questions tied to known answers
# are the only way to read the side-by-side honestly).
DEFAULT_QUERIES = [
    "what is the main idea",
    "how does this work",
    "explain the key concept",
    "what are the components",
    "summarise the core argument",
]

SNIPPET_WIDTH = 110


def _truncate(text: str, width: int = SNIPPET_WIDTH) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= width else text[: width - 1] + "…"


def ensure_typed_nodes_for_doc(
    conn: sqlite3.Connection, doc_id: str, file_path: Path
) -> tuple[int, str]:
    """Run Docling -> walker -> persistence for `doc_id` if not yet indexed.

    Returns (nodes_inserted, status_message).
    """
    if not docling_parser.is_available():
        return 0, "skipped (docling not installed)"
    existing = conn.execute(
        "SELECT COUNT(*) AS n FROM nodes WHERE doc_id = ?", (doc_id,)
    ).fetchone()["n"]
    if existing > 0:
        return 0, f"already indexed ({existing} nodes)"
    if not file_path.exists():
        return 0, f"skipped (file missing: {file_path.name})"
    try:
        doc = docling_parser.parse_document(file_path)
        nodes = typed_walker.walk(doc)
    except Exception as exc:
        return 0, f"docling parse failed: {exc}"
    if not nodes:
        return 0, "docling parsed but emitted zero nodes"
    node_ids = insert_typed_nodes(conn, doc_id, nodes)
    embed_and_index_nodes(conn, nodes, node_ids)
    conn.commit()
    return len(node_ids), f"indexed {len(node_ids)} nodes"


def time_search(fn, *args, **kwargs) -> tuple[list, float]:
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, (time.perf_counter() - t0) * 1000


def _filename_for(conn: sqlite3.Connection, doc_id: str) -> str:
    row = conn.execute("SELECT filename FROM documents WHERE id = ?", (doc_id,)).fetchone()
    return row["filename"] if row else doc_id[:12]


def render_query_block(
    conn: sqlite3.Connection,
    query: str,
    chunks_hits,
    chunks_ms: float,
    nodes_hits,
    nodes_ms: float,
    rerank_hits: Optional[list],
    rerank_ms: Optional[float],
) -> str:
    lines = [f"## Query: `{query}`", ""]

    def _section(title: str, hits, ms: float) -> None:
        lines.append(f"### {title} — {ms:.1f} ms, {len(hits)} hit(s)")
        if not hits:
            lines.append("_(no hits)_")
            lines.append("")
            return
        for rank, hit in enumerate(hits, start=1):
            doc = _filename_for(conn, hit.doc_id)
            score = hit.score
            if hasattr(hit, "verbatim_text"):
                snippet = _truncate(hit.verbatim_text)
                tag = f" [{hit.node_type}]" if hasattr(hit, "node_type") else ""
                heading = f" · _{hit.heading_path}_" if getattr(hit, "heading_path", "") else ""
                rerank = (
                    f" rerank={hit.rerank_score:.3f}"
                    if getattr(hit, "rerank_score", None) is not None
                    else ""
                )
                lines.append(f"{rank}. **{doc}**{heading}{tag} · score={score:.3f}{rerank}")
                lines.append(f"   {snippet}")
            else:
                snippet = _truncate(getattr(hit, "snippet", ""))
                section = f" · _{hit.section}_" if getattr(hit, "section", None) else ""
                lines.append(f"{rank}. **{doc}**{section} · score={score:.3f}")
                lines.append(f"   {snippet}")
        lines.append("")

    _section("(A) Legacy chunks", chunks_hits, chunks_ms)
    _section("(B) Typed nodes (no rerank)", nodes_hits, nodes_ms)
    if rerank_hits is not None and rerank_ms is not None:
        _section("(C) Typed nodes + rerank", rerank_hits, rerank_ms)

    return "\n".join(lines)


def serialize_hits(hits) -> list[dict]:
    out = []
    for hit in hits:
        record = {"doc_id": hit.doc_id, "score": hit.score}
        if hasattr(hit, "node_id"):
            record.update(
                {
                    "node_id": hit.node_id,
                    "node_type": hit.node_type,
                    "heading_path": hit.heading_path,
                    "page": hit.page,
                    "char_start": hit.char_start,
                    "char_end": hit.char_end,
                    "verbatim_text": hit.verbatim_text,
                    "rerank_score": getattr(hit, "rerank_score", None),
                }
            )
        else:
            record.update(
                {
                    "chunk_id": hit.chunk_id,
                    "section": hit.section,
                    "snippet": hit.snippet,
                }
            )
        out.append(record)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-docs",
        type=int,
        default=None,
        help="Limit ingest to first N uploads (most recent first).",
    )
    parser.add_argument(
        "--questions",
        type=Path,
        default=None,
        help="JSON file with a list of query strings. Defaults to a generic prompt set.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write the markdown report to this path instead of stdout.",
    )
    parser.add_argument(
        "--json",
        dest="json_path",
        type=Path,
        default=None,
        help="Also write a machine-readable JSON report.",
    )
    parser.add_argument(
        "--skip-ingest",
        action="store_true",
        help="Don't re-run the typed-node ingest; only run queries.",
    )
    parser.add_argument(
        "--no-rerank",
        action="store_true",
        help="Skip the cross-encoder rerank path (saves the ~1 GB model download).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Hits per path to display (default 3).",
    )
    args = parser.parse_args()

    if args.questions is not None:
        queries = json.loads(args.questions.read_text(encoding="utf-8"))
    else:
        queries = DEFAULT_QUERIES

    conn = db.get_db()
    db.apply_migrations(conn)

    print("# Validating typed-node retrieval", flush=True)
    print(f"  questions: {len(queries)}", flush=True)

    if not args.skip_ingest:
        sql = (
            "SELECT id, storage_name, filename FROM documents "
            "WHERE storage_name IS NOT NULL ORDER BY upload_date DESC"
        )
        params: tuple = ()
        if args.max_docs is not None:
            sql += " LIMIT ?"
            params = (args.max_docs,)
        rows = conn.execute(sql, params).fetchall()
        print(f"# Ingest phase: {len(rows)} doc(s) eligible", flush=True)
        for row in rows:
            file_path = db.UPLOAD_DIR / row["storage_name"]
            count, status = ensure_typed_nodes_for_doc(conn, row["id"], file_path)
            print(f"  {row['filename']}: {status}", flush=True)

    n_chunks = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]
    n_nodes = conn.execute("SELECT COUNT(*) AS n FROM nodes").fetchone()["n"]
    print(f"# Library state: {n_chunks} chunks, {n_nodes} typed nodes", flush=True)

    if n_nodes == 0:
        print(
            "# WARNING: no typed nodes in the library — paths (B) and (C) will be empty.",
            file=sys.stderr,
        )

    md_lines = [
        "# Typed-node retrieval validation",
        "",
        f"- Library: **{n_chunks} chunks**, **{n_nodes} typed nodes**",
        f"- Queries: **{len(queries)}**",
        f"- Rerank path: **{'off' if args.no_rerank else 'on'}**",
        "",
    ]
    json_report: dict = {
        "library": {"chunks": n_chunks, "nodes": n_nodes},
        "rerank_enabled": not args.no_rerank,
        "queries": [],
    }

    for query in queries:
        print(f"\n# Query: {query}", flush=True)
        chunks_hits, chunks_ms = time_search(search_hybrid, conn, query, limit=args.limit)
        nodes_hits, nodes_ms = time_search(search_typed_hybrid, conn, query, limit=args.limit)
        rerank_hits = None
        rerank_ms: Optional[float] = None
        if not args.no_rerank:
            rerank_hits, rerank_ms = time_search(
                search_typed_hybrid,
                conn,
                query,
                limit=args.limit,
                use_reranker=True,
            )

        block = render_query_block(
            conn,
            query,
            chunks_hits,
            chunks_ms,
            nodes_hits,
            nodes_ms,
            rerank_hits,
            rerank_ms,
        )
        md_lines.append(block)
        print(block, flush=True)

        json_report["queries"].append(
            {
                "query": query,
                "chunks": {"latency_ms": chunks_ms, "hits": serialize_hits(chunks_hits)},
                "nodes": {"latency_ms": nodes_ms, "hits": serialize_hits(nodes_hits)},
                "nodes_rerank": (
                    None
                    if rerank_hits is None
                    else {"latency_ms": rerank_ms, "hits": serialize_hits(rerank_hits)}
                ),
            }
        )

    md = "\n".join(md_lines).rstrip() + "\n"
    if args.output:
        args.output.write_text(md, encoding="utf-8")
        print(f"\n# Wrote markdown report -> {args.output}", flush=True)
    if args.json_path:
        args.json_path.write_text(
            json.dumps(json_report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"# Wrote JSON report -> {args.json_path}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
