from __future__ import annotations

import json
from pathlib import Path

from ..types import ExtractedElement
from ..utils import file_sha
from .common import ParserContext, build_asset, make_span


def parse_json(path: Path, *, suffix: str, mime_type: str, context: ParserContext):
    raw = path.read_text(encoding="utf-8", errors="ignore")
    file_id = file_sha(path)[:16]
    try:
        data = json.loads(raw)
        rendered = json.dumps(data, indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        rendered = raw
    elements = [
        ExtractedElement(
            id="json-1",
            kind="metadata_item",
            text=rendered,
            normalized_text=rendered,
            span=make_span(path, file_id, section="JSON", element_id="json-1"),
        )
    ]
    return build_asset(
        path,
        detected_type=suffix,
        mime_type=mime_type,
        parser_name="json-native",
        elements=elements,
        context=context,
        extraction_modes=["schema_aware"],
        metadata={"page_count": 1},
        confidence=0.86,
    )
