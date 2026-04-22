from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from ..types import ExtractedElement
from ..utils import normalize_space, file_sha
from .common import ParserContext, build_asset, make_span

try:
    import ebooklib
    from ebooklib import epub as epub_lib
    from bs4 import BeautifulSoup
except ImportError:
    ebooklib = None
    epub_lib = None
    BeautifulSoup = None


def parse_epub(path: Path, *, suffix: str, mime_type: str, context: ParserContext):
    if epub_lib is None or BeautifulSoup is None or ebooklib is None:
        raise HTTPException(status_code=400, detail="EPUB support requires ebooklib and beautifulsoup4")
    file_id = file_sha(path)[:16]
    book = epub_lib.read_epub(str(path), options={"ignore_ncx": True})
    elements: list[ExtractedElement] = []
    chapter_index = 0
    for item in book.get_items():
        if item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        soup = BeautifulSoup(item.get_content(), "html.parser")
        text = normalize_space(soup.get_text("\n", strip=True))
        if not text:
            continue
        chapter_index += 1
        span = make_span(path, file_id, section=f"Chapter {chapter_index}", element_id=f"epub-{chapter_index}")
        elements.append(
            ExtractedElement(
                id=span.element_id or f"epub-{chapter_index}",
                kind="paragraph",
                text=text,
                normalized_text=text,
                span=span,
            )
        )
    return build_asset(
        path,
        detected_type=suffix,
        mime_type=mime_type,
        parser_name="ebooklib",
        elements=elements,
        context=context,
        extraction_modes=["chapter_walk"],
        metadata={"page_count": chapter_index or None},
        confidence=0.78,
    )
