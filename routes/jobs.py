from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List

from fastapi import APIRouter, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from services import jobs as jobs_service
from services.uploads import save_upload_bounded, validate_upload_suffix


router = APIRouter()


@router.post("/api/jobs/import")
async def import_document_job(
    file: UploadFile = File(...),
    subject_name: str = Form("General"),
) -> Dict[str, Any]:
    suffix = validate_upload_suffix(file.filename)
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = Path(tmp.name)
    await save_upload_bounded(file, tmp_path)
    try:
        job = jobs_service.enqueue_import(
            source_path=tmp_path,
            filename=file.filename or tmp_path.name,
            subject_name=subject_name,
        )
        return {"job": job}
    finally:
        tmp_path.unlink(missing_ok=True)


@router.get("/api/jobs")
def list_jobs(limit: int = Query(default=50, ge=1, le=200)) -> Dict[str, List[Dict[str, Any]]]:
    return {"jobs": jobs_service.list_jobs(limit=limit)}


@router.get("/api/jobs/events")
def list_job_events(
    after_id: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> Dict[str, Any]:
    events = jobs_service.list_events(after_id=after_id, limit=limit)
    return {"events": events, "last_event_id": events[-1]["id"] if events else after_id}


@router.get("/api/jobs/stream")
async def stream_jobs(after_id: int = Query(default=0, ge=0)) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        cursor = after_id
        while True:
            events = jobs_service.list_events(after_id=cursor, limit=100)
            for event in events:
                cursor = max(cursor, int(event["id"]))
                yield (f"id: {event['id']}\nevent: job\ndata: {json.dumps(event)}\n\n")
            await asyncio.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> Dict[str, Any]:
    job = jobs_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job": job}


@router.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: str) -> Dict[str, Any]:
    try:
        return {"job": jobs_service.retry_job(job_id)}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


@router.delete("/api/jobs/{job_id}")
def delete_job(job_id: str) -> Dict[str, bool]:
    if not jobs_service.delete_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return {"deleted": True}


def register_job_routes(app: FastAPI) -> None:
    app.include_router(router)
