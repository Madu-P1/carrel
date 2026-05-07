from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from .common import ParserContext


def parse_audio(path: Path, *, suffix: str, mime_type: str, context: ParserContext):
    # Audio transcription is gated until the macOS app bundle wires
    # SFSpeechRecognizer (the CLI ingestion bridge cannot, see
    # docs/audio-transcription-plan.md). The upload allowlist excludes
    # audio suffixes, so this branch should not normally be reached;
    # if it is, the file got past the gate via direct API and the user
    # gets an honest message.
    raise HTTPException(
        status_code=400,
        detail=(
            "Audio transcription is coming in a follow-up release. "
            "For now, transcribe lecture recordings via Voice Memos and "
            "upload the resulting text."
        ),
    )


def parse_video(path: Path, *, suffix: str, mime_type: str, context: ParserContext):
    raise HTTPException(
        status_code=400,
        detail=(
            "Video transcription is not yet supported. Export the audio "
            "track separately and upload that once audio support ships."
        ),
    )
