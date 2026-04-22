from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

from fastapi import HTTPException

from ..types import ExtractedElement
from ..utils import ARCHIVE_SUFFIXES, AUDIO_SUFFIXES, SUPPORTED_SUFFIXES, VIDEO_SUFFIXES, file_sha
from .common import ParserContext, build_asset, make_span


def parse_zip(path: Path, *, suffix: str, mime_type: str, context: ParserContext, extractor):
    file_id = file_sha(path)[:16]
    warnings: list[str] = []
    elements: list[ExtractedElement] = []
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > 120:
            raise HTTPException(status_code=400, detail="Archive is too large to inspect safely.")
        total_bytes = sum(info.file_size for info in infos)
        if total_bytes > 40 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Archive exceeds the safe extraction limit (40 MB).")
        member_count = 0
        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            for info in infos:
                if info.is_dir():
                    continue
                member_path = Path(info.filename)
                if member_path.name.startswith(".") or "__MACOSX" in member_path.parts:
                    continue
                child_suffix = member_path.suffix.lower()
                if child_suffix not in SUPPORTED_SUFFIXES - ARCHIVE_SUFFIXES - AUDIO_SUFFIXES - VIDEO_SUFFIXES:
                    continue
                if member_count >= 12:
                    warnings.append("Archive inspection stopped after 12 supported child files.")
                    break
                extracted_path = temp_dir / member_path.name
                extracted_path.write_bytes(archive.read(info))
                child_asset = extractor(extracted_path)
                member_count += 1
                child_label = f"{member_path.name} ({child_asset.detected_type})"
                span = make_span(path, file_id, section=child_label, element_id=f"zip-{member_count}")
                elements.append(
                    ExtractedElement(
                        id=span.element_id or f"zip-{member_count}",
                        kind="metadata_item",
                        text=f"{child_label}\n{child_asset.preview_text}",
                        normalized_text=f"{child_label}\n{child_asset.preview_text}",
                        span=span,
                        metadata={"child_diagnostics": child_asset.diagnostics},
                    )
                )
    return build_asset(
        path,
        detected_type=suffix,
        mime_type=mime_type,
        parser_name="zip-safe-recursive",
        elements=elements,
        context=context,
        warnings=warnings,
        extraction_modes=["archive_walk"],
        metadata={"page_count": None},
        confidence=0.7 if elements else 0.3,
    )
