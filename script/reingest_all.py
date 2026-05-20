#!/usr/bin/env python3
"""Backfill typed nodes for documents that do not have them yet (T11).

Documents ingested before the Docling typed-node path covered their
format have rows in `chunks` but none in `nodes`. This script re-runs
the Docling parse for each such document and writes `nodes`,
`node_embeddings`, and `node_fts` rows. It never reads, writes, or
deletes `chunks`, so the legacy retrieval path is untouched.

Idempotent: a document that already has at least one `nodes` row is
skipped, so re-running only picks up the remainder. A document whose
original file is missing from UPLOAD_DIR is reported and skipped, not
failed.

The Docling parse is the slow step and runs across a thread pool
(`--concurrency`, default 4). Node insertion and embedding run serially
on the main connection, so there is no SQLite write contention. Four
parallel Docling parses are memory-heavy on OCR-bound PDFs; lower
`--concurrency` on a constrained machine.

Born-digital PDFs (textbooks, exported papers) carry a complete text
layer, so OCR over them is wasted compute that scales with page count.
This script probes each PDF (`docling_parser.has_rich_text_layer`) and
skips OCR when the text layer is dense, so a long textbook re-ingests
in minutes instead of hours. Scanned PDFs keep OCR on. The per-document
log record carries an `ocr` field recording which path each file took.

Docling's peak memory also scales with page count: a thousand-page
textbook parsed in one shot exhausts RAM. A PDF longer than
`--slice-pages` (default 60) is parsed in page-range slices, each freed
before the next, and the per-slice walks are stitched back into one
document-global node list (`typed_walker.stitch_walks`). The per-document
log record carries a `slices` field recording how many slices were used.

Each completed slice's walked nodes are persisted to a JSON sidecar in
`<data>/migrations/` (gitignored), so a process kill mid-parse resumes
from the last finished slice instead of restarting the whole document.
The sidecar is removed once the document's nodes are durably committed.

The script calls the Docling parser directly and so does not consult
INGEST_USE_DOCLING or INGEST_DOCLING_FORMATS; populating the typed-node
tables is its entire purpose.

Usage:
    .venv/bin/python script/reingest_all.py [--db PATH] [--dry-run] [--concurrency N]

Progress prints to stdout and appends to
`<data>/migrations/reingest-<UTC-date>.jsonl`, one JSON object per doc.
"""

from __future__ import annotations

import argparse
import gc
import json
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import db  # noqa: E402
from services.ingestion import docling_parser, typed_walker  # noqa: E402
from services.ingestion.persistence import (  # noqa: E402
    embed_and_index_nodes,
    insert_typed_nodes,
)


def _candidate_documents(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Documents that have a stored original file and zero typed nodes."""
    return conn.execute(
        """
        SELECT id, filename, storage_name
        FROM documents
        WHERE storage_name IS NOT NULL
          AND storage_name != ''
          AND NOT EXISTS (SELECT 1 FROM nodes WHERE nodes.doc_id = documents.id)
        ORDER BY upload_date ASC
        """
    ).fetchall()


# --- Per-slice resume ---------------------------------------------------
#
# A very large PDF is parsed in page-range slices (see _parse_one). The
# Docling parse is the slow, memory-heavy, kill-prone step — a 1480-page
# textbook takes hours, and memory pressure (or a watchdog) can kill the
# process mid-loop. The database write stays atomic per document, so a
# kill before the final commit would otherwise discard every parsed
# slice. Each completed slice's walked nodes are persisted to a JSON
# sidecar in data/migrations/ (gitignored); on resume the recorded
# slices are reused and only the missing ones are re-parsed, turning a
# total-loss restart into monotonic progress. The sidecar is deleted
# once the document's nodes are durably committed.


def _resume_path(doc_id: str) -> Path:
    """Sidecar path holding already-parsed slices for one document."""
    return db.DATA_DIR / "migrations" / f"reingest-resume-{doc_id}.json"


def _node_to_jsonable(node: typed_walker.TypedNode) -> dict[str, object]:
    """Serialize one TypedNode to a JSON-safe dict."""
    return asdict(node)


def _node_from_jsonable(data: dict[str, object]) -> typed_walker.TypedNode:
    """Rebuild a TypedNode from its serialized dict."""
    return typed_walker.TypedNode(**data)


def _load_resume(
    path: Path, page_count: int, slice_pages: int
) -> dict[int, list[typed_walker.TypedNode]]:
    """Return already-parsed slices keyed by 1-based slice index.

    Returns an empty dict when the sidecar is absent, unreadable, or its
    recorded slicing geometry does not match the current run. A change to
    page_count or slice_pages re-keys every slice, so a stale sidecar
    must be discarded rather than misapplied.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    if raw.get("page_count") != page_count or raw.get("slice_pages") != slice_pages:
        return {}
    slices_raw = raw.get("slices")
    if not isinstance(slices_raw, dict):
        return {}
    try:
        return {
            int(index): [_node_from_jsonable(node) for node in nodes]
            for index, nodes in slices_raw.items()
        }
    except (TypeError, ValueError):
        return {}


def _save_resume(
    path: Path,
    doc_id: str,
    filename: str,
    page_count: int,
    slice_pages: int,
    completed: dict[int, list[typed_walker.TypedNode]],
) -> None:
    """Atomically persist completed slices so a kill resumes from here."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "doc_id": doc_id,
        "filename": filename,
        "page_count": page_count,
        "slice_pages": slice_pages,
        "slices": {
            str(index): [_node_to_jsonable(node) for node in nodes]
            for index, nodes in completed.items()
        },
    }
    tmp = path.parent / f"{path.name}.tmp"
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(path)  # atomic rename: a kill mid-write leaves the prior file intact


def _clear_resume(doc_id: str) -> None:
    """Drop the resume sidecar once a document's nodes are committed."""
    _resume_path(doc_id).unlink(missing_ok=True)


def _parse_one(doc_id: str, filename: str, path: Path, *, slice_pages: int = 60):
    """Worker: Docling-parse one file.

    Returns (doc_id, filename, nodes, error, ocr_used, slice_count). A
    PDF with a dense text layer is parsed with OCR off, since OCR over a
    complete born-digital text layer is wasted compute that scales with
    page count. Every other file keeps OCR on (the flag is inert for the
    non-PDF formats, which carry text natively).

    A PDF longer than `slice_pages` is parsed in page-range slices to
    keep Docling's peak memory bounded — Docling holds the whole parsed
    document in memory, so a thousand-page textbook parsed in one shot
    exhausts RAM. Each slice's DoclingDocument is dropped before the next
    slice is parsed, and the per-slice walks are stitched back into one
    document-global node list. `slice_count` is the number of slices
    used (1 for a one-shot parse, 0 when the parse failed).
    """
    do_ocr = True
    if path.suffix.lower() == ".pdf" and docling_parser.has_rich_text_layer(path):
        do_ocr = False
    page_count = docling_parser.pdf_page_count(path)
    try:
        if page_count is not None and page_count > slice_pages:
            starts = list(range(1, page_count + 1, slice_pages))
            resume_path = _resume_path(doc_id)
            completed = _load_resume(resume_path, page_count, slice_pages)
            if completed:
                print(
                    f"  resuming {filename!r}: "
                    f"{len(completed)}/{len(starts)} slice(s) already parsed",
                    flush=True,
                )
            for index, start in enumerate(starts, start=1):
                if index in completed:
                    continue
                end = min(start + slice_pages - 1, page_count)
                # Per-slice progress: a large-PDF parse takes many
                # minutes, and without a heartbeat a watchdog (or an
                # operator) cannot tell a slow parse from a hung one.
                print(
                    f"  slicing {filename!r}: slice {index}/{len(starts)} (pages {start}-{end})",
                    flush=True,
                )
                document = docling_parser.parse_document(
                    path, do_ocr=do_ocr, page_range=(start, end)
                )
                slice_nodes = typed_walker.walk(document)
                # Drop the slice's DoclingDocument before the next slice
                # is parsed so peak memory stays at one slice, not the
                # whole textbook.
                del document
                gc.collect()
                completed[index] = slice_nodes
                # Persist after every slice: a kill during the multi-hour
                # loop then resumes from here, not from zero.
                _save_resume(resume_path, doc_id, filename, page_count, slice_pages, completed)
            ordered = [completed[index] for index in range(1, len(starts) + 1)]
            nodes = typed_walker.stitch_walks(ordered)
            return doc_id, filename, nodes, None, do_ocr, len(starts)
        document = docling_parser.parse_document(path, do_ocr=do_ocr)
        nodes = typed_walker.walk(document)
        return doc_id, filename, nodes, None, do_ocr, 1
    except Exception as exc:
        return doc_id, filename, None, f"{type(exc).__name__}: {exc}", do_ocr, 0


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
        "--slice-pages",
        type=int,
        default=60,
        help=(
            "Parse a PDF longer than this many pages in page-range "
            "slices to bound Docling's peak memory (default 60)."
        ),
    )
    args = parser.parse_args()

    if not docling_parser.is_available():
        print("Docling is not installed; cannot backfill typed nodes.", file=sys.stderr)
        return 1
    if args.concurrency < 1:
        print("--concurrency must be at least 1.", file=sys.stderr)
        return 2
    if args.slice_pages < 1:
        print("--slice-pages must be at least 1.", file=sys.stderr)
        return 2

    if args.db:
        db.DB_PATH = Path(args.db).resolve()
    conn = db.get_db()
    try:
        candidates = _candidate_documents(conn)
        todo: list[tuple[str, str, Path]] = []
        missing: list[sqlite3.Row] = []
        for row in candidates:
            path = (db.UPLOAD_DIR / str(row["storage_name"])).resolve(strict=False)
            if path.exists():
                todo.append((str(row["id"]), str(row["filename"] or ""), path))
            else:
                missing.append(row)

        print(
            f"{len(candidates)} document(s) without typed nodes: "
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
                    pool.submit(_parse_one, doc_id, filename, path, slice_pages=args.slice_pages)
                    for doc_id, filename, path in todo
                ]
                for future in futures:
                    doc_id, filename, nodes, parse_error, ocr_used, slice_count = future.result()
                    record: dict[str, object] = {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "doc_id": doc_id,
                        "filename": filename,
                        "ocr": ocr_used,
                        "slices": slice_count,
                    }
                    if parse_error is not None:
                        failed += 1
                        record["status"] = "failed"
                        record["error"] = parse_error
                        print(f"  fail (parse): {doc_id}  {filename!r}  {parse_error}")
                    else:
                        try:
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
                            # Nodes are durably committed; the per-slice
                            # resume sidecar (if any) is no longer needed.
                            _clear_resume(doc_id)
                            print(
                                f"  ok: {doc_id}  {filename!r}  "
                                f"{len(node_ids)} nodes, {embedded} embedded, "
                                f"ocr={'on' if ocr_used else 'off'}, "
                                f"slices={slice_count}"
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
