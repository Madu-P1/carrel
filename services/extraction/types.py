from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SourceSpan:
    file_name: str
    file_id: str
    page: Optional[int] = None
    section: Optional[str] = None
    paragraph_id: Optional[str] = None
    element_id: Optional[str] = None
    slide: Optional[int] = None
    sheet: Optional[str] = None
    row_range: Optional[str] = None
    cell_range: Optional[str] = None
    timestamp_start: Optional[float] = None
    timestamp_end: Optional[float] = None
    bbox: Optional[Dict[str, float]] = None
    parent_element_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedElement:
    id: str
    kind: str
    text: str
    normalized_text: str
    span: SourceSpan
    role: str = "body"
    confidence: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalChunk:
    content: str
    section: Optional[str]
    page_num: Optional[int]
    chunk_index: int
    provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractionQualityReport:
    parser: str
    extraction_modes: List[str]
    warnings: List[str]
    metrics: Dict[str, Any]
    confidence: float
    fallback_chain: List[str] = field(default_factory=list)


@dataclass
class IngestedAsset:
    filename: str
    detected_type: str
    mime_type: str
    content_hash: str
    metadata: Dict[str, Any]
    raw_text: str
    cleaned_text: str
    preview_text: str
    elements: List[ExtractedElement]
    chunks: List[RetrievalChunk]
    quality: ExtractionQualityReport

    def to_legacy(self) -> Dict[str, object]:
        metrics = self.quality.metrics or {}
        return {
            "text": self.cleaned_text or self.raw_text,
            "page_count": metrics.get("page_count"),
            "preview_text": self.preview_text,
            "parser_status": "ready" if self.cleaned_text else "warning",
            "parser_diagnostics": self.diagnostics,
        }

    @property
    def diagnostics(self) -> Dict[str, Any]:
        return {
            "filename": self.filename,
            "detected_type": self.detected_type,
            "mime_type": self.mime_type,
            "content_hash": self.content_hash,
            "metadata": self.metadata,
            "quality": asdict(self.quality),
            "preview_text": self.preview_text,
            "element_count": len(self.elements),
            "chunk_count": len(self.chunks),
        }
