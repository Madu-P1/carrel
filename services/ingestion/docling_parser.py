"""Thin wrapper around Docling's DocumentConverter.

Docling is an optional dependency. `is_available()` lets the orchestrator
skip the typed-node path silently when Docling isn't installed, so users
who don't opt in to the new pipeline never pay the ~1-2 GB install cost.

The wrapper exists for two reasons:
1. Centralize the Docling import so every other module in the package
   can avoid a top-level `import docling`. Top-level import would crash
   on module load when Docling is absent — defeating the point of the
   feature flag.
2. Pin pipeline options once (default backend; OCR on by default,
   caller-overridable via the `do_ocr` argument) so callers don't need
   to know Docling internals. Apple Vision OCR is a follow-up; this
   ships with Docling's default OCR (rapidocr / easyocr) so the path
   is end-to-end exercised.

`has_rich_text_layer` lets a caller skip OCR for born-digital PDFs
(textbooks, papers) whose programmatic text layer is already complete.
OCR over such a document is wasted compute that scales with page count.

`pdf_page_count` and the `page_range` argument to `parse_document` let a
caller parse a very large PDF in page-range slices. Docling's peak
memory scales with page count, so a thousand-page textbook parsed in one
shot exhausts RAM; sliced parsing keeps the envelope bounded.
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


def has_rich_text_layer(
    path: Path,
    *,
    sample_pages: int = 12,
    min_avg_chars: int = 100,
) -> bool:
    """True when a PDF carries a programmatic text layer dense enough
    that Docling OCR would add nothing.

    Born-digital PDFs (textbooks, exported papers, slide decks) embed
    their text; scanned PDFs do not. Running OCR over a born-digital PDF
    is wasted compute that scales with page count. A long textbook can
    take hours. Callers use this to pass `do_ocr=False` to
    `parse_document` for such files.

    Samples up to `sample_pages` pages spread evenly across the document
    and returns True when their mean extracted-text length clears
    `min_avg_chars`. The default threshold sits far above scanned-PDF
    noise (page numbers, stray marks) and far below any real text page,
    so the two classes separate cleanly.

    Returns False for non-PDF inputs, unreadable files, or a missing
    pypdf dependency: the safe default is "leave OCR on".
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        return False
    try:
        pages = PdfReader(str(path)).pages
    except Exception:
        return False
    page_count = len(pages)
    if page_count == 0:
        return False
    step = max(1, page_count // sample_pages)
    indices = list(range(0, page_count, step))[:sample_pages]
    total_chars = 0
    for index in indices:
        try:
            total_chars += len((pages[index].extract_text() or "").strip())
        except Exception:
            continue
    return total_chars / len(indices) >= min_avg_chars


def pdf_page_count(path: Path) -> int | None:
    """Return a PDF's page count, or None when it can't be determined.

    A caller uses this to decide whether a PDF is large enough to need
    sliced parsing (see the `page_range` argument to `parse_document`).
    Returns None for non-PDF inputs, unreadable files, or a missing pypdf
    dependency: the safe default is "treat it as un-sliceable" and parse
    in one shot.
    """
    if path.suffix.lower() != ".pdf":
        return None
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        return len(PdfReader(str(path)).pages)
    except Exception:
        return None


def parse_document(
    path: Path,
    *,
    do_ocr: bool = True,
    page_range: tuple[int, int] | None = None,
) -> Any:
    """Parse a file with Docling, return the DoclingDocument.

    Six formats are registered as explicit Docling `InputFormat`
    handlers: PDF, DOCX, HTML, Markdown, PPTX, and LaTeX. The allowlist
    here is the upper bound; `orchestrator._docling_enabled_for` gates
    which extensions actually reach this function via
    `INGEST_DOCLING_FORMATS`.

    `do_ocr` controls Docling's PDF OCR pass and defaults to True, which
    preserves the behavior every existing caller relies on. Pass
    `do_ocr=False` for born-digital PDFs whose text layer is already
    complete (see `has_rich_text_layer`); OCR there is wasted compute
    that scales with page count. The flag is inert for the five non-PDF
    formats, which carry text natively.

    `page_range` is a 1-based inclusive `(first, last)` page span. When
    None (the default) Docling parses the whole document, preserving the
    behavior every existing caller relies on. Pass an explicit span to
    parse one slice of a very large PDF: Docling's peak memory scales
    with page count, so a thousand-page textbook is parsed slice by
    slice and the per-slice walks are stitched with
    `typed_walker.stitch_walks`.

    Raises ImportError if Docling isn't installed (callers should gate on
    `is_available()` first). Other Docling failures bubble up — the
    orchestrator wraps the call in a try/except so a bad file never
    breaks the existing chunks ingest path.
    """
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import (
        DocumentConverter,
        HTMLFormatOption,
        LatexFormatOption,
        MarkdownFormatOption,
        PdfFormatOption,
        PowerpointFormatOption,
        WordFormatOption,
    )

    pdf_pipeline_opts = PdfPipelineOptions()
    pdf_pipeline_opts.do_ocr = do_ocr
    # ocr_options.kind defaults to "auto" which picks rapidocr or
    # easyocr based on what's installed. Apple Vision via NativeBridge
    # is a follow-up — see docs/algorithms/ask-pipeline-pr1-typed-nodes.md
    # risk #3. OCR pipeline options apply to PDF only; the other five
    # formats carry text natively and use Docling's default backend.
    format_options = {
        InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_pipeline_opts),
        InputFormat.DOCX: WordFormatOption(),
        InputFormat.HTML: HTMLFormatOption(),
        InputFormat.MD: MarkdownFormatOption(),
        InputFormat.PPTX: PowerpointFormatOption(),
        InputFormat.LATEX: LatexFormatOption(),
    }
    converter = DocumentConverter(
        allowed_formats=list(format_options),
        format_options=format_options,
    )
    convert_kwargs: dict[str, Any] = {}
    if page_range is not None:
        convert_kwargs["page_range"] = page_range
    return converter.convert(str(path), **convert_kwargs).document
