from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Tuple

from .utils import detect_mime


class FileTypeDetector:
    @staticmethod
    def detect(path: Path) -> Tuple[str, str]:
        suffix = path.suffix.lower()
        mime_type = detect_mime(path, suffix)
        try:
            header = path.read_bytes()[:16]
        except Exception:
            header = b""

        if header.startswith(b"%PDF"):
            return ".pdf", "application/pdf"
        if header.startswith(b"\x89PNG\r\n\x1a\n"):
            return ".png", "image/png"
        if header.startswith(b"\xff\xd8\xff"):
            return ".jpg", "image/jpeg"
        if header.startswith(b"GIF8"):
            return ".gif", "image/gif"
        if header.startswith(b"RIFF") and header[8:12] == b"WAVE":
            return ".wav", "audio/wav"
        if header.startswith(b"ID3"):
            return ".mp3", "audio/mpeg"
        if zipfile.is_zipfile(path) and suffix not in {".docx", ".pptx", ".xlsx", ".epub", ".zip"}:
            return ".zip", "application/zip"
        return suffix, mime_type
