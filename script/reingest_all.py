#!/usr/bin/env python3
"""Backfill typed nodes for documents that do not have them yet (T11).

Documents ingested before the Docling typed-node path covered their
format have rows in `chunks` but none in `nodes`. This script re-runs
the Docling parse for each such document and writes `nodes`,
`node_embeddings`, and `node_fts` rows. It never reads, writes, or
deletes `chunks`, so the legacy retrieval path is untouched.

Idempotent by default: a document that already has at least one `nodes`
row is skipped, so re-running only picks up the remainder. Pass
`--rebuild` to re-ingest every document, deleting its existing typed
nodes first; use this after a change to the walker. A document whose
original file is missing from UPLOAD_DIR is reported and skipped, not
failed.

The Docling parse is the slow step and runs across a thread pool
(`--concurrency`, default 4). Node insertion and embedding run serially
on the main connection, so there is no SQLite write contention. Four
parallel Docling parses are memory-heavy on OCR-bound PDFs; lower
`--concurrency` on a constrained machine.

The script calls the Docling parser directly and so does not consult
INGEST_USE_DOCLING or INGEST_DOCLING_FORMATS; populating the typed-node
tables is its entire purpose.

Usage:
    .venv/bin/python script/reingest_all.py [--db PATH] [--dry-run] [--rebuild] [--concurrency N]

Progress prints to stdout and appends to
`<data>/migrations/reingest-<UTC-date>.jsonl`, one JSON object per doc.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import db  # noqa: E402
from services.ingestion import docling_parser, typed_walker  # noqa: E402
from services.ingestion.persistence import (  # noqa: E402
    delete_typed_nodes,
    embed_and_index_nodes,
    insert_typed_nodes,
)


def _candidate_documents(conn: sqlite3.Connection, *, rebuild: bool) -> list[sqlite3.Row]:
    """Documents to (re-)ingest typed nodes for.

    Default: documents with a stored original file and zero typed nodes
    (backfill). With `rebuild`: every document with a stored file, so
    existing nodes can be dropped and rebuilt. Use rebuild after a
    change to the walker.
    """
    backfill_only = """
        SELECT id, filename, storage_name
        FROM documents
        WHERE storage_name IS NOT NULL
          AND storage_name != ''
          AND NOT EXISTS (SELECT 1 FROM nodes WHERE nodes.doc_id = documents.id)
        ORDER BY upload_date ASC
        """
    rebuild_all = """
        SELECT id, filename, storage_name
        FROM documents
        WHERE storage_name IS NOT NULL
          AND storage_name != ''
        ORDER BY upload_date ASC
        """
    return conn.execute(rebuild_all if rebuild else backfill_only).fetchall()


def _parse_one(doc_id: str, filename: str, path: Path):
    """Worker: Docling-parse one file. Returns (doc_id, filename, nodes, error)."""
    try:
        document = docling_parser.parse_document(path)
        nodes = typed_walker.walk(document)
        return doc_id, filename, nodes, None
    except Exception as exc:
        return doc_id, filename, None, f"{type(exc).__name__}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default=None, help="SQLite path (defaults to db.DB_PATH).")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List the documents that would be re-ingested and write nothing.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Number of parallel Docling parses (default 4).",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help=(
            "Re-ingest every document, deleting existing typed nodes first. "
            "Use after a walker change; default backfills only zero-node docs."
        ),
    )
    args = parser.parse_args()

    if not docling_parser.is_available():
        print("Docling is not installed; cannot backfill typed nodes.", file=sys.stderr)
        return 1
    if args.concurrency < 1:
        print("--concurrency must be at least 1.", file=sys.stderr)
        return 2

    if args.db:
        db.DB_PATH = Path(args.db).resolve()
    conn = db.get_db()
    try:
        candidates = _candidate_documents(conn, rebuild=args.rebuild)
        todo: list[tuple[str, str, Path]] = []
        missing: list[sqlite3.Row] = []
        for row in candidates:
            path = (db.UPLOAD_DIR / str(row["storage_name"])).resolve(strict=False)
            if path.exists():
                todo.append((str(row["id"]), str(row["filename"] or ""), path))
            else:
                missing.append(row)

        scope = "document(s)" if args.rebuild else "document(s) without typed nodes"
        print(
            f"{len(candidates)} {scope}: "
            f"{len(todo)} re-ingestable, {len(missing)} missing the original file."
        )
        for row in missing:
            print(f"  skip (file missing): {row['id']}  {str(row['filename'] or '')!r}")

        if args.dry_run:
            for doc_id, filename, _path in todo:
                print(f"  would re-ingest: {doc_id}  {filename!r}")
            print("Dry run; no rows written.")
            return 0

        if not todo:
            print("Nothing to re-ingest.")
            return 0

        log_dir = db.DATA_DIR / "migrations"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"reingest-{datetime.now(timezone.utc):%Y%m%d}.jsonl"

        done = 0
        failed = 0
        with log_path.open("a", encoding="utf-8") as log_file:
            with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
                futures = [
                    pool.submit(_parse_one, doc_id, filename, path)
                    for doc_id, filename, path in todo
                ]
                for future in futures:
                    doc_id, filename, nodes, parse_error = future.result()
                    record: dict[str, object] = {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "doc_id": doc_id,
                        "filename": filename,
                    }
                    if parse_error is not None:
                        failed += 1
                        record["status"] = "failed"
                        record["error"] = parse_error
                        print(f"  fail (parse): {doc_id}  {filename!r}  {parse_error}")
                    else:
                        try:
                            if args.rebuild:
                                delete_typed_nodes(conn, doc_id)
                            node_ids = insert_typed_nodes(conn, doc_id, nodes)
                            embedded = embed_and_index_nodes(conn, nodes, node_ids)
                            conn.commit()
                        except Exception as exc:
                            conn.rollback()
                            failed += 1
                            record["status"] = "failed"
                            record["error"] = f"{type(exc).__name__}: {exc}"
                            print(f"  fail (write): {doc_id}  {filename!r}  {exc}")
                        else:
                            done += 1
                            record["status"] = "reingested"
                            record["node_count"] = len(node_ids)
                            record["embedded"] = embedded
                            print(
                                f"  ok: {doc_id}  {filename!r}  "
                                f"{len(node_ids)} nodes, {embedded} embedded"
                            )
                    log_file.write(json.dumps(record) + "\n")

        print(
            f"Done. {done} re-ingested, {failed} failed, "
            f"{len(missing)} skipped for a missing file. Log: {log_path}"
        )
        return 0 if failed == 0 else 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
