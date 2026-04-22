from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from ..native_bridge import NativeBridge
from ..types import ExtractedElement
from ..utils import normalize_space, file_sha
from .common import ParserContext, build_asset, make_span


def parse_image(path: Path, *, suffix: str, mime_type: str, context: ParserContext):
    bridge = NativeBridge.run(path)
    if not bridge or not bridge.get("text"):
        raise HTTPException(
            status_code=400,
            detail="Image OCR requires the macOS ingestion bridge. Rebuild the app and try again.",
        )
    file_id = file_sha(path)[:16]
    text = normalize_space(bridge.get("text") or "")
    elements = [
        ExtractedElement(
            id="image-text-1",
            kind="image_text",
            text=text,
            normalized_text=text,
            span=make_span(path, file_id, section=path.stem, element_id="image-text-1"),
            confidence=float(bridge.get("confidence") or 0.72),
            metadata={"exif": bridge.get("metadata") or {}},
        )
    ]
    return build_asset(
        path,
        detected_type=suffix,
        mime_type=mime_type,
        parser_name=str(bridge.get("parser") or "apple-vision-image"),
        elements=elements,
        context=context,
        warnings=list(bridge.get("warnings") or []),
        extraction_modes=list(bridge.get("extraction_modes") or ["ocr"]),
        metadata={"page_count": 1, **(bridge.get("metadata") or {})},
        confidence=float(bridge.get("confidence") or 0.72),
    )
