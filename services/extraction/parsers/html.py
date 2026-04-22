from __future__ import annotations

import re
from pathlib import Path

from ..types import ExtractedElement
from ..utils import normalize_space, file_sha
from .common import ParserContext, build_asset, make_span

try:
    from bs4 import BeautifulSoup as BS4
except ImportError:
    BS4 = None


def parse_html(path: Path, *, suffix: str, mime_type: str, context: ParserContext):
    raw = path.read_text(encoding="utf-8", errors="ignore")
    file_id = file_sha(path)[:16]
    if BS4 is None:
        stripped = normalize_space(re.sub(r"<[^>]+>", " ", raw))
        return build_asset(
            path,
            detected_type=suffix,
            mime_type=mime_type,
            parser_name="html-regex-fallback",
            elements=[
                ExtractedElement(
                    id="html-1",
                    kind="paragraph",
                    text=stripped,
                    normalized_text=stripped,
                    span=make_span(path, file_id, section="HTML", element_id="html-1"),
                )
            ],
            context=context,
            warnings=["BeautifulSoup is not installed; HTML structure is flattened."],
            metadata={"page_count": 1},
            confidence=0.56,
        )
    soup = BS4(raw, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    elements: list[ExtractedElement] = []
    current_heading: str | None = None
    counter = 0
    for tag in soup.find_all(["h1", "h2", "h3", "p", "li", "table", "caption"]):
        text = normalize_space(tag.get_text(" ", strip=True))
        if not text:
            continue
        counter += 1
        if tag.name in {"h1", "h2", "h3"}:
            current_heading = text
            kind = "title" if tag.name == "h1" else "heading"
        elif tag.name == "li":
            kind = "bullet_list"
        elif tag.name == "caption":
            kind = "caption"
        elif tag.name == "table":
            kind = "table"
        else:
            kind = "paragraph"
        span = make_span(path, file_id, section=current_heading, element_id=f"html-{counter}")
        elements.append(
            ExtractedElement(
                id=span.element_id or f"html-{counter}",
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
        parser_name="beautifulsoup-structured",
        elements=elements,
        context=context,
        extraction_modes=["dom_walk"],
        metadata={"page_count": 1},
        confidence=0.8,
    )
