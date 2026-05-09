"""Thin wrapper around Docling's DocumentConverter.

Docling is an optional dependency. `is_available()` lets the orchestrator
skip the typed-node path silently when Docling isn't installed, so users
who don't opt in to the new pipeline never pay the ~1-2 GB install cost.

The wrapper exists for two reasons:
1. Centralize the Docling import so every other module in the package
   can avoid a top-level `import docling`. Top-level import would crash
   on module load when Docling is absent — defeating the point of the
   feature flag.
2. Pin pipeline options once (OCR on, default backend) so callers don't
   need to know Docling internals. Apple Vision OCR is a follow-up; this
   PR ships with Docling's default OCR (rapidocr / easyocr) so the path
   is end-to-end exercised.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def is_available() -> bool:
    try:
        import docling  # noqa: F401
    except ImportError:
        return False
    return True


def parse_document(path: Path) -> Any:
    """Parse a file with Docling, return the DoclingDocument.

    Raises ImportError if Docling isn't installed (callers should gate on
    `is_available()` first). Other Docling failures bubble up — the
    orchestrator wraps the call in a try/except so a bad file never
    breaks the existing chunks ingest path.
    """
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat

    pipeline_opts = PdfPipelineOptions()
    pipeline_opts.do_ocr = True
    # ocr_options.kind defaults to "auto" which picks rapidocr or
    # easyocr based on what's installed. Apple Vision via NativeBridge
    # is a follow-up — see docs/algorithms/ask-pipeline-pr1-typed-nodes.md
    # risk #3.

    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_opts)}
    )
    return converter.convert(str(path)).document
