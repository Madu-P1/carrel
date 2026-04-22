from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from ..types import ExtractedElement
from ..utils import normalize_space, file_sha
from .common import ParserContext, build_asset, make_span

try:
    from striprtf.striprtf import rtf_to_text
except ImportError:
    rtf_to_text = None


def parse_rtf(path: Path, *, suffix: str, mime_type: str, context: ParserContext):
    if rtf_to_text is None:
        raise HTTPException(status_code=400, detail="RTF support requires striprtf")
    raw = path.read_text(encoding="utf-8", errors="ignore")
    text = normalize_space(rtf_to_text(raw))
    file_id = file_sha(path)[:16]
    return build_asset(
        path,
        detected_type=suffix,
        mime_type=mime_type,
        parser_name="striprtf",
        elements=[
            ExtractedElement(
                id="rtf-1",
                kind="paragraph",
                text=text,
                normalized_text=text,
                span=make_span(path, file_id, section="RTF", element_id="rtf-1"),
            )
        ],
        context=context,
        metadata={"page_count": 1},
        confidence=0.74,
    )
