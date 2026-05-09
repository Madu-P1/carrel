from __future__ import annotations

from dataclasses import asdict
from typing import List, Optional, Sequence

from .types import ExtractedElement, RetrievalChunk


class ChunkBuilder:
    def build(self, elements: Sequence[ExtractedElement], *, parser: str) -> List[RetrievalChunk]:
        chunks: List[RetrievalChunk] = []
        bucket: List[ExtractedElement] = []
        current_section = "Overview"
        current_page: Optional[int] = None
        current_sheet: Optional[str] = None

        def flush() -> None:
            if not bucket:
                return
            content = "\n\n".join(
                item.normalized_text for item in bucket if item.normalized_text
            ).strip()
            if not content:
                bucket.clear()
                return
            section = next(
                (item.span.section for item in bucket if item.span.section), current_section
            )
            page_num = next(
                (item.span.page for item in bucket if item.span.page is not None), current_page
            )
            provenance = {
                "parser": parser,
                "source_spans": [asdict(item.span) for item in bucket],
                "element_ids": [item.id for item in bucket],
                "element_kinds": [item.kind for item in bucket],
                "span_roles": [item.role for item in bucket],
                "sheet": current_sheet,
            }
            chunks.append(
                RetrievalChunk(
                    content=content,
                    section=section,
                    page_num=page_num,
                    chunk_index=len(chunks),
                    provenance=provenance,
                )
            )
            bucket.clear()

        for element in elements:
            text = element.normalized_text.strip()
            if not text:
                continue
            if element.kind in {"title", "heading", "slide", "sheet"}:
                flush()
                current_section = text[:180]
            if (
                element.span.page is not None
                and current_page is not None
                and element.span.page != current_page
            ):
                flush()
            if (
                element.span.sheet
                and current_sheet is not None
                and element.span.sheet != current_sheet
            ):
                flush()
            current_page = element.span.page if element.span.page is not None else current_page
            current_sheet = element.span.sheet or current_sheet
            if bucket:
                preview = "\n\n".join(
                    item.normalized_text for item in bucket if item.normalized_text
                )
                if len(preview) + len(text) + 2 > 1200:
                    flush()
            bucket.append(element)
        flush()
        return chunks
