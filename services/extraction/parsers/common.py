from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..chunking import ChunkBuilder
from ..types import ExtractedElement, ExtractionQualityReport, IngestedAsset, SourceSpan
from ..utils import file_sha


@dataclass(frozen=True)
class ParserContext:
    chunk_builder: ChunkBuilder


def make_span(path: Path, file_id: str, **kwargs: Any) -> SourceSpan:
    return SourceSpan(file_name=path.name, file_id=file_id, **kwargs)


def build_asset(
    path: Path,
    *,
    detected_type: str,
    mime_type: str,
    parser_name: str,
    elements: List[ExtractedElement],
    context: ParserContext,
    warnings: Optional[List[str]] = None,
    extraction_modes: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    fallback_chain: Optional[List[str]] = None,
    confidence: Optional[float] = None,
) -> IngestedAsset:
    metadata = dict(metadata or {})
    warnings = list(warnings or [])
    extraction_modes = list(extraction_modes or ["native"])
    fallback_chain = list(fallback_chain or [])
    raw_text = "\n\n".join(item.text for item in elements if item.text).strip()
    cleaned_text = "\n\n".join(
        item.normalized_text for item in elements if item.normalized_text
    ).strip()
    preview_text = cleaned_text[:1200]
    chunks = context.chunk_builder.build(elements, parser=parser_name)
    metrics = {
        "page_count": metadata.get("page_count"),
        "char_count": len(cleaned_text),
        "element_count": len(elements),
        "chunk_count": len(chunks),
        "warning_count": len(warnings),
    }
    quality = ExtractionQualityReport(
        parser=parser_name,
        extraction_modes=extraction_modes,
        warnings=warnings,
        metrics=metrics,
        confidence=confidence if confidence is not None else (0.91 if cleaned_text else 0.22),
        fallback_chain=fallback_chain,
    )
    return IngestedAsset(
        filename=path.name,
        detected_type=detected_type.lstrip("."),
        mime_type=mime_type,
        content_hash=file_sha(path),
        metadata=metadata,
        raw_text=raw_text,
        cleaned_text=cleaned_text,
        preview_text=preview_text,
        elements=elements,
        chunks=chunks,
        quality=quality,
    )
