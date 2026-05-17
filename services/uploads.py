from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, UploadFile


# 500 MB — sized for textbook-scale PDFs (most run 50-300 MB; some
# scanned/figure-heavy texts push 400+). Bumped from 100 MB after a
# real 266 MB Biology textbook was rejected with status=413. The
# upload itself streams in 1 MB chunks (UPLOAD_CHUNK_BYTES below) so
# raising this does not increase peak memory at upload time; the
# downstream cost is extraction (parser loads the full PDF), which
# can take 1-2 min and a few GB RAM on the largest accepted file.
# If we ever see RAM pressure on small Macs, lower this OR move
# extraction off the request thread (it's already on a worker pool).
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024
ALLOWED_SUFFIXES = {".pdf", ".txt", ".md", ".docx", ".pptx"}


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
