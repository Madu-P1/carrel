from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, UploadFile


MAX_UPLOAD_BYTES = 100 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024
ALLOWED_SUFFIXES = {".pdf", ".txt", ".md", ".docx", ".pptx"}
GENERIC_CONTENT_TYPES = {"", "application/octet-stream", "binary/octet-stream"}
ALLOWED_CONTENT_TYPES = {
    ".pdf": {"application/pdf"},
    ".txt": {"text/plain"},
    ".md": {"text/markdown", "text/plain"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
    },
    ".pptx": {
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/zip",
    },
}


def validate_upload_suffix(filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    if not suffix:
        raise HTTPException(status_code=400, detail="File must have an extension.")
    if suffix not in ALLOWED_SUFFIXES:
        allowed = ", ".join(sorted(ALLOWED_SUFFIXES))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Supported types: {allowed}.",
        )
    return suffix


def validate_upload_metadata(filename: str | None, content_type: str | None) -> str:
    suffix = validate_upload_suffix(filename)
    declared_type = (content_type or "").split(";", 1)[0].strip().lower()
    if declared_type in GENERIC_CONTENT_TYPES:
        return suffix
    allowed_types = ALLOWED_CONTENT_TYPES.get(suffix, set())
    if declared_type not in allowed_types:
        allowed = ", ".join(sorted(item for item in allowed_types | GENERIC_CONTENT_TYPES if item))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported content type for {suffix}. Supported types: {allowed}.",
        )
    return suffix


async def save_upload_bounded(file: UploadFile, dest: Path) -> int:
    total = 0
    try:
        with dest.open("wb") as out:
            while True:
                chunk = await file.read(UPLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    dest.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail="File is too large.")
                out.write(chunk)
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    return total
