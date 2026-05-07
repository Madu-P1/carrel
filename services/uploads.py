from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, UploadFile

from services.extraction.utils import SUPPORTED_SUFFIXES


MAX_UPLOAD_BYTES = 100 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024
# Single source of truth: every suffix the parser registry knows how to
# handle is allowed at upload. Previously this set was hand-maintained and
# drifted, exposing only 10 of the ~50 formats the extractor supports.
#
# Excluded from the allowlist:
#   - .zip: parser exists but per-entry size sweep + format-validation
#     pass not yet implemented. Zip-bomb risk.
#   - .mp4 / .mov / .m4v / .mkv / .avi / .webm: video parser is a stub.
#   - .mp3 / .wav / .m4a / .aac / .flac / .ogg: audio parser depends on
#     SFSpeechRecognizer, which on macOS requires an Info.plist privacy
#     declaration and an app-bundle context. The CLI ingestion bridge
#     does not have either, so the system aborts the process. Real
#     audio transcription needs to move into the main EinsteinDesktopApp
#     (or an XPC service) before being re-enabled here. Tracked in
#     docs/audio-transcription-plan.md.
_VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm"}
_AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
ALLOWED_SUFFIXES = SUPPORTED_SUFFIXES - {".zip"} - _VIDEO_SUFFIXES - _AUDIO_SUFFIXES


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
