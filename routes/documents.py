import logging
import mimetypes
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

import db
from api_models import (
    DeleteResponse,
    DocumentDetailResponse,
    DocumentListItem,
    DocumentSubjectRequest,
    DocumentSubjectUpdateResponse,
    DocumentUploadResponse,
    TextDocumentCreateRequest,
)
from app_logging import get_logger, log_event
from services import extraction_pipeline
from services.app_state import fetch_workspace_state, log_study_event
from services.documents import (
    cleanup_duplicate_documents,
    compute_document_source_hash,
    delete_document_record,
    fetch_document_detail,
    fetch_documents,
    fetch_subject_groups,
    find_canonical_duplicate,
    find_duplicate_groups,
    list_subject_summaries,
    set_document_subject,
)
from services.ingestion import ingest_document_record, normalize_subject_name


LOGGER = get_logger("documents_api")
router = APIRouter()


@router.get("/api/documents", response_model=List[DocumentListItem])
def list_documents() -> List[Dict[str, object]]:
    with db.get_db() as conn:
        return fetch_documents(conn)


@router.get("/api/documents/{doc_id}", response_model=DocumentDetailResponse)
def get_document(doc_id: str) -> Dict[str, object]:
    with db.get_db() as conn:
        return fetch_document_detail(conn, doc_id)


@router.get("/api/documents/{doc_id}/file")
def get_document_file(doc_id: str) -> FileResponse:
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT filename, storage_name FROM documents WHERE id = ?",
            (doc_id,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Document not found")

    storage_name = row["storage_name"]
    if not storage_name:
        raise HTTPException(status_code=404, detail="Document file not available")

    upload_root = db.UPLOAD_DIR.resolve()
    candidate = (db.UPLOAD_DIR / storage_name).resolve(strict=False)

    try:
        candidate.relative_to(upload_root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Document file not found") from exc

    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Document file not found")

    media_type, _ = mimetypes.guess_type(str(candidate))
    return FileResponse(
        path=candidate,
        filename=row["filename"] or candidate.name,
        media_type=media_type or "application/octet-stream",
    )


def _duplicate_http_error(existing: Dict[str, Any]) -> HTTPException:
    """409 response used by both upload paths when a file's content hash
    already matches a canonical document. The frontend destructures `detail`
    to render "Already in library as X" with a button to open the existing
    document. Structured detail, not a flat string — React components parse it."""
    return HTTPException(
        status_code=409,
        detail={
            "code": "duplicate_source",
            "message": (
                f"This file is already in your library as "
                f"“{existing.get('filename') or 'an existing document'}”."
            ),
            "existing_doc_id": existing.get("id"),
            "existing_filename": existing.get("filename"),
            "existing_subject": existing.get("subject_name"),
            "existing_uploaded_at": str(existing.get("upload_date") or ""),
        },
    )


@router.post("/api/documents/text", response_model=DocumentUploadResponse)
def create_text_document(payload: TextDocumentCreateRequest) -> Dict[str, object]:
    title = (payload.title or "").strip() or "Untitled"
    content = (payload.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Content is required.")

    file_type = re.sub(r"[^a-z0-9]+", "", (payload.file_type or "txt").lower()) or "txt"
    filename = title if Path(title).suffix else f"{title}.{file_type}"

    source_hash = compute_document_source_hash(raw_text=content)
    with db.get_db() as conn:
        existing = find_canonical_duplicate(conn, source_hash)
        if existing:
            raise _duplicate_http_error(existing)
        result = ingest_document_record(
            conn=conn,
            filename=filename,
            file_type=file_type,
            extracted_text=content,
            page_count=1,
            storage_name=None,
            subject_name=payload.subject_name,
        )
        log_study_event(
            conn,
            "document_text_saved",
            doc_id=result["doc_id"],
            payload={
                "filename": filename,
                "file_type": file_type,
                "subject_name": normalize_subject_name(payload.subject_name),
            },
        )
        return result


@router.post("/api/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    subject_name: str = Form("General"),
) -> Dict[str, object]:
    suffix = Path(file.filename or "").suffix.lower()
    if not suffix:
        raise HTTPException(status_code=400, detail="File must have an extension.")

    content = await file.read()
    log_event(
        LOGGER,
        logging.INFO,
        "document_upload_started",
        filename=file.filename or "",
        subject_name=subject_name,
        bytes=len(content),
    )
    stored_name = f"{uuid.uuid4()}{suffix}"
    path = db.UPLOAD_DIR / stored_name
    path.write_bytes(content)
    try:
        asset = extraction_pipeline.extract_asset(path)
    except Exception as exc:
        if path.exists():
            path.unlink(missing_ok=True)
        log_event(
            LOGGER,
            logging.ERROR,
            "document_upload_failed",
            filename=file.filename or "",
            subject_name=subject_name,
            error=str(exc),
        )
        raise

    # Duplicate gate. Runs AFTER extraction because `asset.content_hash` is
    # the raw-bytes hash — same derivation the orchestrator stores. Before
    # extraction we'd need to re-hash the bytes ourselves. Cheap to run
    # extraction then bail because the real cost (embeddings, LLM cards) is
    # inside ingest_document_record, which we skip on a dup.
    source_hash = compute_document_source_hash(asset=asset)
    with db.get_db() as conn:
        existing = find_canonical_duplicate(conn, source_hash)
    if existing:
        # Clean up the bytes we wrote — we're not ingesting this one.
        if path.exists():
            path.unlink(missing_ok=True)
        log_event(
            LOGGER,
            logging.INFO,
            "document_upload_rejected_duplicate",
            filename=file.filename or "",
            subject_name=subject_name,
            existing_doc_id=str(existing.get("id") or ""),
            source_hash=source_hash,
        )
        raise _duplicate_http_error(existing)

    with db.get_db() as conn:
        result = ingest_document_record(
            conn=conn,
            filename=file.filename or stored_name,
            file_type=asset.detected_type,
            extracted_text=str(asset.cleaned_text or asset.raw_text),
            page_count=asset.quality.metrics.get("page_count"),
            storage_name=stored_name,
            subject_name=subject_name,
            asset=asset,
        )
        log_study_event(
            conn,
            "document_uploaded",
            doc_id=result["doc_id"],
            payload={
                "filename": file.filename or stored_name,
                "file_type": asset.detected_type,
                "subject_name": normalize_subject_name(subject_name),
            },
        )
    log_event(
        LOGGER,
        logging.INFO,
        "document_upload_completed",
        filename=file.filename or stored_name,
        subject_name=subject_name,
        doc_id=str(result.get("doc_id") or ""),
        file_type=str(result.get("file_type") or ""),
    )
    return result


@router.get("/api/library/subjects")
def library_subjects() -> Dict[str, Any]:
    """Subject dashboard payload. One row per subject with the stats the
    Library home grid needs — source count, failed-parse count, flashcard
    count, last-studied timestamp, plus the first failed doc for inline
    error rendering."""
    with db.get_db() as conn:
        subjects = list_subject_summaries(conn)
    return {"subjects": subjects}


@router.get("/api/library/duplicates")
def preview_duplicate_groups() -> Dict[str, Any]:
    """Surface every cluster of documents that share a source hash.

    UI consumes this to render a "Review duplicates" panel before the user
    confirms a cleanup. Safe to call repeatedly; read-only.
    """
    with db.get_db() as conn:
        groups = find_duplicate_groups(conn)
    return {
        "groups": groups,
        "total_groups": len(groups),
        "total_duplicates": sum(len(g["duplicates"]) for g in groups),
        "total_cards_in_duplicates": sum(int(g["total_cards"]) for g in groups),
    }


@router.post("/api/library/duplicates/cleanup")
def run_duplicate_cleanup(dry_run: bool = False) -> Dict[str, Any]:
    """Remove every non-canonical document in every duplicate cluster.

    Pass `dry_run=true` to get the same summary shape without writing.
    Without `dry_run`, each duplicate is cascaded via
    `delete_document_record` — same semantics as clicking "Delete" on the
    row — so concepts, SRS cards, notes, chunks, and chunk vectors all go
    with it. The canonical stays.
    """
    with db.get_db() as conn:
        result = cleanup_duplicate_documents(conn, dry_run=dry_run)
    log_event(
        LOGGER,
        logging.INFO,
        "library_duplicate_cleanup",
        dry_run=dry_run,
        groups=result.get("groups", 0),
        deleted=result.get("deleted", 0) if not dry_run else result.get("would_delete", 0),
    )
    return result


@router.get("/api/documents/{doc_id}/status")
def document_status(doc_id: str) -> Dict[str, object]:
    with db.get_db() as conn:
        row = conn.execute("SELECT id AS doc_id, status FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")
        return dict(row)


@router.delete("/api/documents/{doc_id}", response_model=DeleteResponse)
def delete_document(doc_id: str) -> Dict[str, bool]:
    with db.get_db() as conn:
        document = conn.execute("SELECT filename FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not delete_document_record(conn, doc_id):
            raise HTTPException(status_code=404, detail="Document not found")
        log_study_event(
            conn,
            "document_deleted",
            payload={"filename": document["filename"] if document else "Unknown document"},
        )
        return {"deleted": True}


@router.put("/api/documents/{doc_id}/subject", response_model=DocumentListItem)
def update_document_subject_put(doc_id: str, payload: DocumentSubjectRequest) -> Dict[str, Any]:
    with db.get_db() as conn:
        document = set_document_subject(conn, doc_id, payload.subject_name)
        log_study_event(
            conn,
            "document_grouped",
            doc_id=doc_id,
            payload={"subject_name": document["subject_name"]},
        )
        return document


@router.post("/api/documents/{doc_id}/subject", response_model=DocumentSubjectUpdateResponse)
def update_document_subject(doc_id: str, payload: DocumentSubjectRequest) -> Dict[str, Any]:
    with db.get_db() as conn:
        document = set_document_subject(conn, doc_id, payload.subject_name)
        log_study_event(
            conn,
            "document_grouped",
            doc_id=doc_id,
            payload={"subject_name": document["subject_name"]},
        )
        return {"document": document, "workspace": fetch_workspace_state(conn)}


def register_document_routes(app) -> None:
    app.include_router(router)
