from __future__ import annotations

import hashlib
import mimetypes
import re
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
# Centralised in ai/native_bridge_paths.py so the ingestion bridge and
# the AFM bridge use the same candidate-walking logic. The alias keeps
# this module's existing public name (`NATIVE_BRIDGE_CANDIDATES`)
# working for callers like services/extraction/native_bridge.py.
from ai.native_bridge_paths import INGESTION_BRIDGE_CANDIDATES as NATIVE_BRIDGE_CANDIDATES  # noqa: E402

TEXT_SUFFIXES = {
    ".txt",
    ".md",
    ".markdown",
    ".rst",
    ".log",
    ".tex",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".java",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".rs",
    ".go",
    ".rb",
    ".swift",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".srt",
    ".vtt",
}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".heic", ".tiff", ".tif", ".bmp", ".gif", ".webp"}
AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm"}
ARCHIVE_SUFFIXES = {".zip"}
SUPPORTED_SUFFIXES = (
    TEXT_SUFFIXES
    | {
        ".pdf",
        ".docx",
        ".doc",
        ".pptx",
        ".ppt",
        ".xlsx",
        ".xls",
        ".csv",
        ".tsv",
        ".html",
        ".htm",
        ".json",
        ".jsonl",
        ".xml",
        ".epub",
        ".rtf",
    }
    | IMAGE_SUFFIXES
    | AUDIO_SUFFIXES
    | VIDEO_SUFFIXES
    | ARCHIVE_SUFFIXES
)


def normalize_space(value: str) -> str:
    value = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def safe_text(value: Any) -> str:
    return normalize_space(str(value or ""))


def strip_slide_prefix(value: str) -> str:
    text = normalize_space(str(value or ""))
    text = re.sub(r"^\d+(?:\.\d+)+(?:\s*[:.-]?\s*)", "", text)
    text = re.sub(r"\(\d+\s+of\s+\d+\)", "", text, flags=re.IGNORECASE)
    return text.strip(" .,:;-_")


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text_sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def detect_mime(path: Path, suffix: str) -> str:
    if suffix == ".pdf":
        return "application/pdf"
    if suffix in IMAGE_SUFFIXES:
        return mimetypes.guess_type(path.name)[0] or "image/*"
    if suffix in AUDIO_SUFFIXES:
        return mimetypes.guess_type(path.name)[0] or "audio/*"
    if suffix in VIDEO_SUFFIXES:
        return mimetypes.guess_type(path.name)[0] or "video/*"
    if suffix in {".docx", ".doc"}:
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if suffix in {".pptx", ".ppt"}:
        return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    if suffix in {".xlsx", ".xls"}:
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"
