from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from .common import ParserContext


def parse_audio(path: Path, *, suffix: str, mime_type: str, context: ParserContext):
    raise HTTPException(
        status_code=400, detail="Audio transcription runtime is not configured yet."
    )


def parse_video(path: Path, *, suffix: str, mime_type: str, context: ParserContext):
    raise HTTPException(
        status_code=400, detail="Video transcription runtime is not configured yet."
    )
