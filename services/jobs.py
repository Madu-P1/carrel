from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, Optional

import db
from app_logging import get_logger, log_event
from services import extraction_pipeline
from services.app_state import log_study_event
from services.documents import compute_document_source_hash, find_canonical_duplicate
from services.ingestion import ingest_document_record, normalize_subject_name
from services.subjects import ensure_subject


LOGGER = get_logger("jobs")
JOB_UPLOAD_DIR = db.DATA_DIR / "job-uploads"
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="carrel-job")
_SUBMITTED: set[str] = set()
_LOCK = threading.Lock()


def _row_to_job(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "kind": row["kind"],
        "status": row["status"],
        "stage": row["stage"],
        "filename": row["filename"],
        "subject_name": row["subject_name"],
        "document_id": row["document_id"],
        "error": row["error"],
        "progress": float(row["progress"] or 0),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
    }


def _fetch_job(conn: sqlite3.Connection, job_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM ingestion_jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_job(row) if row else None


def _emit_event(
    conn: sqlite3.Connection,
    job_id: str,
    *,
    event_type: str,
    status: str,
    stage: str,
    message: str = "",
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO job_events (job_id, event_type, status, stage, message, payload)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (job_id, event_type, status, stage, message, json.dumps(payload or {})),
    )


def _update_job(
    conn: sqlite3.Connection,
    job_id: str,
    *,
    status: Optional[str] = None,
    stage: Optional[str] = None,
    progress: Optional[float] = None,
    document_id: Optional[str] = None,
    error: Optional[str] = None,
    event_type: str = "job_updated",
    message: str = "",
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    current = _fetch_job(conn, job_id)
    if current is None:
        raise LookupError(f"job {job_id!r} not found")
    next_status = status or str(current["status"])
    next_stage = stage or str(current["stage"])
    assignments = ["updated_at = CURRENT_TIMESTAMP"]
    params: list[Any] = []
    for column, value in (
        ("status", status),
        ("stage", stage),
        ("progress", progress),
        ("document_id", document_id),
        ("error", error),
    ):
        if value is not None:
            assignments.append(f"{column} = ?")
            params.append(value)
    if status == "running":
        assignments.append("started_at = COALESCE(started_at, CURRENT_TIMESTAMP)")
    if status in {"ready", "partial", "failed", "cancelled"}:
        assignments.append("finished_at = CURRENT_TIMESTAMP")
    params.append(job_id)
    conn.execute(f"UPDATE ingestion_jobs SET {', '.join(assignments)} WHERE id = ?", params)
    _emit_event(
        conn,
        job_id,
        event_type=event_type,
        status=next_status,
        stage=next_stage,
        message=message,
        payload=payload,
    )
    conn.commit()
    updated = _fetch_job(conn, job_id)
    assert updated is not None
    return updated


def enqueue_import(
    *,
    source_path: Path,
    filename: str,
    subject_name: str = "General",
    kind: str = "document_import",
) -> Dict[str, Any]:
    JOB_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    job_id = str(uuid.uuid4())
    suffix = Path(filename).suffix or source_path.suffix or ".txt"
    temp_storage_name = f"{job_id}{suffix}"
    temp_path = JOB_UPLOAD_DIR / temp_storage_name
    shutil.copyfile(source_path, temp_path)
    normalized_subject = normalize_subject_name(subject_name)
    with db.get_db() as conn:
        ensure_subject(conn, normalized_subject)
        conn.execute(
            """
            INSERT INTO ingestion_jobs (
                id, kind, status, stage, filename, subject_name, temp_storage_name, progress
            ) VALUES (?, ?, 'queued', 'importing', ?, ?, ?, 0)
            """,
            (job_id, kind, filename, normalized_subject, temp_storage_name),
        )
        _emit_event(
            conn,
            job_id,
            event_type="job_created",
            status="queued",
            stage="importing",
            message=f"Queued {filename}",
        )
        conn.commit()
        job = _fetch_job(conn, job_id)
    submit_job(job_id)
    assert job is not None
    return job


def submit_job(job_id: str) -> None:
    with _LOCK:
        if job_id in _SUBMITTED:
            return
        _SUBMITTED.add(job_id)
    _EXECUTOR.submit(_run_import_job, job_id)


def list_jobs(limit: int = 50) -> list[Dict[str, Any]]:
    with db.get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM ingestion_jobs
            ORDER BY created_at DESC, rowid DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return [_row_to_job(row) for row in rows]


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with db.get_db() as conn:
        return _fetch_job(conn, job_id)


def list_events(after_id: int = 0, limit: int = 100) -> list[Dict[str, Any]]:
    with db.get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM job_events
            WHERE id > ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (int(after_id), int(limit)),
        ).fetchall()
        out = []
        for row in rows:
            try:
                payload = json.loads(row["payload"] or "{}")
            except json.JSONDecodeError:
                payload = {}
            out.append(
                {
                    "id": int(row["id"]),
                    "job_id": row["job_id"],
                    "event_type": row["event_type"],
                    "status": row["status"],
                    "stage": row["stage"],
                    "message": row["message"],
                    "payload": payload,
                    "created_at": row["created_at"],
                }
            )
        return out


def retry_job(job_id: str) -> Dict[str, Any]:
    with db.get_db() as conn:
        job = _fetch_job(conn, job_id)
        if job is None:
            raise LookupError("Job not found")
        if job["status"] not in {"failed", "cancelled"}:
            return job
        conn.execute(
            """
            UPDATE ingestion_jobs
            SET status = 'queued', stage = 'importing', error = NULL,
                progress = 0, updated_at = CURRENT_TIMESTAMP,
                started_at = NULL, finished_at = NULL
            WHERE id = ?
            """,
            (job_id,),
        )
        _emit_event(
            conn,
            job_id,
            event_type="job_retried",
            status="queued",
            stage="importing",
            message="Retry queued",
        )
        conn.commit()
        updated = _fetch_job(conn, job_id)
    submit_job(job_id)
    assert updated is not None
    return updated


def delete_job(job_id: str) -> bool:
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT temp_storage_name FROM ingestion_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            return False
        conn.execute(
            """
            UPDATE ingestion_jobs
            SET status = CASE WHEN status IN ('ready', 'failed', 'partial') THEN status ELSE 'cancelled' END,
                updated_at = CURRENT_TIMESTAMP,
                finished_at = COALESCE(finished_at, CURRENT_TIMESTAMP)
            WHERE id = ?
            """,
            (job_id,),
        )
        conn.execute("DELETE FROM ingestion_jobs WHERE id = ?", (job_id,))
        conn.commit()
    temp_name = str(row["temp_storage_name"] or "")
    if temp_name:
        (JOB_UPLOAD_DIR / temp_name).unlink(missing_ok=True)
    return True


def resume_unfinished_jobs() -> None:
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT id FROM ingestion_jobs WHERE status IN ('queued', 'running')"
        ).fetchall()
    for row in rows:
        submit_job(str(row["id"]))


def _run_import_job(job_id: str) -> None:
    try:
        with db.get_db() as conn:
            job = _fetch_job(conn, job_id)
            if not job:
                return
            temp_name = str(conn.execute(
                "SELECT temp_storage_name FROM ingestion_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()["temp_storage_name"] or "")
            temp_path = JOB_UPLOAD_DIR / temp_name
            if not temp_path.exists():
                _update_job(
                    conn,
                    job_id,
                    status="failed",
                    stage="importing",
                    progress=1,
                    error="Temporary import file is missing.",
                    event_type="job_failed",
                    message="Temporary import file is missing.",
                )
                return
            _update_job(
                conn,
                job_id,
                status="running",
                stage="extracting_text",
                progress=0.2,
                message="Extracting source text",
            )

        asset = extraction_pipeline.extract_asset(temp_path)
        with db.get_db() as conn:
            source_hash = compute_document_source_hash(asset=asset)
            existing = find_canonical_duplicate(conn, source_hash)
            if existing:
                _update_job(
                    conn,
                    job_id,
                    status="ready",
                    stage="ready",
                    progress=1,
                    document_id=str(existing.get("id") or ""),
                    event_type="job_ready",
                    message="Duplicate already exists in your library",
                    payload={"duplicate": True, "existing_doc_id": existing.get("id")},
                )
                return
            _update_job(
                conn,
                job_id,
                status="running",
                stage="indexing",
                progress=0.55,
                message="Indexing chunks and concepts",
            )
            storage_name = f"{uuid.uuid4()}{temp_path.suffix}"
            final_path = db.UPLOAD_DIR / storage_name
            shutil.copyfile(temp_path, final_path)
            result = ingest_document_record(
                conn=conn,
                filename=str(job["filename"] or temp_path.name),
                file_type=asset.detected_type,
                extracted_text=str(asset.cleaned_text or asset.raw_text),
                page_count=asset.quality.metrics.get("page_count"),
                storage_name=storage_name,
                subject_name=str(job["subject_name"] or "General"),
                asset=asset,
            )
            doc_id = str(result["doc_id"])
            log_study_event(
                conn,
                "document_uploaded",
                doc_id=doc_id,
                payload={
                    "filename": str(job["filename"] or temp_path.name),
                    "file_type": asset.detected_type,
                    "subject_name": str(job["subject_name"] or "General"),
                    "via": "jobs",
                },
            )
            _update_job(
                conn,
                job_id,
                status="ready",
                stage="ready",
                progress=1,
                document_id=doc_id,
                event_type="job_ready",
                message="Source is ready",
                payload={"document_id": doc_id},
            )
    except Exception as exc:
        log_event(LOGGER, logging.ERROR, "job_failed", job_id=job_id, error=str(exc))
        with db.get_db() as conn:
            try:
                _update_job(
                    conn,
                    job_id,
                    status="failed",
                    stage="importing",
                    progress=1,
                    error=str(exc),
                    event_type="job_failed",
                    message=str(exc),
                )
            except Exception:
                pass
    finally:
        with _LOCK:
            _SUBMITTED.discard(job_id)
