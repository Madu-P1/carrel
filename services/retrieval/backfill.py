from __future__ import annotations

import logging
import os
import threading
from typing import Any

from app_logging import get_logger, log_event

LOGGER = get_logger("retrieval.backfill")
_BACKFILL_LOCK = threading.Lock()
_BACKFILL_RUNNING = False


def _run_vector_backfill_enabled() -> bool:
    return os.getenv("RUN_VECTOR_BACKFILL", "true").lower() in ("1", "true", "yes")


def _backfill_flag_value(conn) -> str:
    row = conn.execute(
        "SELECT value FROM app_settings WHERE key = 'chunks_vec_backfill_pending'"
    ).fetchone()
    return str(row["value"]) if row and row["value"] is not None else "0"


def _set_backfill_flag(conn, value: str) -> None:
    conn.execute(
        """
        INSERT INTO app_settings (key, value)
        VALUES ('chunks_vec_backfill_pending', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (value,),
    )


def _missing_rows(conn, batch_size: int) -> list[tuple[int, str]]:
    rows = conn.execute(
        """
        SELECT c.rowid, c.content
        FROM chunks c
        LEFT JOIN chunks_vec v ON v.chunk_id = c.rowid
        WHERE v.chunk_id IS NULL
        ORDER BY c.rowid ASC
        LIMIT ?
        """,
        (batch_size,),
    ).fetchall()
    return [(int(row["rowid"]), str(row["content"] or "")) for row in rows]


def backfill_missing_embeddings(
    conn,
    *,
    embedder=None,
    batch_size: int = 32,
    max_batches: int | None = None,
) -> dict[str, Any]:
    from services.retrieval.embeddings import default_embedder
    from services.retrieval.vector import index_chunks_batch, vector_table_exists

    if not vector_table_exists(conn):
        return {"processed": 0, "remaining": 0, "completed": False}

    embedder = embedder or default_embedder()
    processed = 0
    batches = 0

    while True:
        rows = _missing_rows(conn, batch_size)
        if not rows:
            _set_backfill_flag(conn, "0")
            conn.commit()
            return {"processed": processed, "remaining": 0, "completed": True}

        row_ids = [row_id for row_id, _content in rows]
        contents = [content for _row_id, content in rows]
        vectors = embedder.embed_passages(contents)
        index_chunks_batch(conn, zip(row_ids, vectors))

        placeholders = ",".join("?" * len(row_ids))
        conn.execute(
            f"UPDATE chunks SET embedding_status = 'indexed' WHERE rowid IN ({placeholders})",
            row_ids,
        )
        conn.commit()

        processed += len(row_ids)
        batches += 1
        if processed % 100 == 0 or processed == len(row_ids):
            log_event(LOGGER, logging.INFO, "chunks_vec_backfill_progress", processed=processed)

        if max_batches is not None and batches >= max_batches:
            _set_backfill_flag(conn, "1")
            conn.commit()
            remaining = len(_missing_rows(conn, batch_size))
            return {"processed": processed, "remaining": remaining, "completed": False}


def _run_backfill_thread() -> None:
    global _BACKFILL_RUNNING

    try:
        import db

        with db.get_db() as conn:
            if _backfill_flag_value(conn) != "1":
                return
            result = backfill_missing_embeddings(conn)
            log_event(
                LOGGER,
                logging.INFO,
                "chunks_vec_backfill_completed",
                processed=result["processed"],
                remaining=result["remaining"],
                completed=result["completed"],
            )
    except Exception as exc:
        log_event(LOGGER, logging.WARNING, "chunks_vec_backfill_failed", error=str(exc))
    finally:
        with _BACKFILL_LOCK:
            _BACKFILL_RUNNING = False


def maybe_run_backfill() -> None:
    global _BACKFILL_RUNNING

    if not _run_vector_backfill_enabled():
        return

    with _BACKFILL_LOCK:
        if _BACKFILL_RUNNING:
            return
        _BACKFILL_RUNNING = True

    thread = threading.Thread(target=_run_backfill_thread, name="chunks-vec-backfill", daemon=True)
    thread.start()
