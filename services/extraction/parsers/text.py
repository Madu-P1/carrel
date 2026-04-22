from __future__ import annotations

import re
from pathlib import Path

from ..types import ExtractedElement
from ..utils import normalize_space, text_sha
from .common import ParserContext, build_asset, make_span


def parse_text(path: Path, *, suffix: str, mime_type: str, context: ParserContext):
    raw = path.read_text(encoding="utf-8", errors="ignore")
    file_id = text_sha(f"{path.name}:{raw}")[:16]
    elements: list[ExtractedElement] = []
    current_heading: str | None = None
    blocks = re.split(r"\n\s*\n", raw.replace("\r\n", "\n").replace("\r", "\n"))
    for index, block in enumerate(blocks, start=1):
        text = normalize_space(block)
        if not text:
            continue
        kind = "paragraph"
        if suffix in {".md", ".markdown"} and text.startswith("#"):
            level = len(text) - len(text.lstrip("#"))
            text = text[level:].strip()
            current_heading = text
            kind = "heading" if level > 1 else "title"
        elif len(text.split()) <= 12 and text == text.title():
            current_heading = text
            kind = "heading"
        span = make_span(path, file_id, section=current_heading, paragraph_id=f"p{index}", element_id=f"text-{index}")
        elements.append(
            ExtractedElement(
                id=f"text-{index}",
                kind=kind,
                text=text,
                normalized_text=text,
                span=span,
            )
        )
    return build_asset(
        path,
        detected_type=suffix,
        mime_type=mime_type,
        parser_name="text-native",
        elements=elements,
        context=context,
        metadata={"page_count": 1},
    )
