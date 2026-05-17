from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional

from PyPDF2 import PdfReader

from ..native_bridge import NativeBridge
from ..quality import (
    classify_pdf_role,
    is_bullet_like,
    is_footer_or_noise,
    is_formula_text,
    is_outline_text,
    strip_bullet_prefix,
)
from ..types import ExtractedElement
from ..utils import file_sha, normalize_space, strip_slide_prefix
from .common import ParserContext, build_asset, make_span


def _pdf_page_elements(
    path: Path,
    file_id: str,
    *,
    page_num: Optional[int],
    text: str,
    confidence: float,
    metadata: Optional[Dict[str, Any]] = None,
) -> list[ExtractedElement]:
    lines = [
        normalize_space(line) for line in str(text or "").splitlines() if normalize_space(line)
    ]
    if not lines:
        return []

    elements: list[ExtractedElement] = []
    current_topic = f"Page {page_num}" if page_num is not None else path.stem
    page_meta = dict(metadata or {})
    index = 0
    title_lines: list[str] = []
    while index < len(lines):
        line = lines[index]
        if is_footer_or_noise(line) and not is_outline_text(line):
            index += 1
            continue
        if is_bullet_like(line) or is_formula_text(line):
            break
        if title_lines and (re.search(r"[.!?]$", line) or len(line.split()) > 8):
            break
        title_lines.append(strip_bullet_prefix(line))
        index += 1
        next_line = lines[index] if index < len(lines) else ""
        if (
            len(title_lines) >= 3
            or len(" ".join(title_lines)) >= 140
            or is_bullet_like(next_line)
            or is_formula_text(next_line)
        ):
            break

    title_is_outline = False
    if title_lines:
        title_text = strip_slide_prefix(" ".join(title_lines))
        title_role = classify_pdf_role(title_text, kind="heading")
        if title_role in {"title", "heading"}:
            current_topic = title_text
        title_is_outline = title_role == "outline"
        normalized_title = title_text if title_role not in {"outline", "footer", "noise"} else ""
        elements.append(
            ExtractedElement(
                id=f"pdf-{page_num or 0}-title",
                kind="title" if page_num == 1 and title_role == "title" else "heading",
                text=title_text,
                normalized_text=normalized_title,
                span=make_span(
                    path,
                    file_id,
                    page=page_num,
                    section=current_topic,
                    element_id=f"pdf-{page_num or 0}-title",
                ),
                role=title_role,
                confidence=confidence,
                metadata=page_meta,
            )
        )

    buffer: list[str] = []
    buffer_role: str | None = None

    def flush_buffer(counter: int) -> int:
        nonlocal buffer, buffer_role
        if not buffer or not buffer_role:
            buffer = []
            buffer_role = None
            return counter
        text_value = " ".join(buffer).strip()
        normalized = text_value if buffer_role not in {"outline", "footer", "noise"} else ""
        kind = (
            "formula"
            if buffer_role == "formula"
            else "bullet_list"
            if is_bullet_like(buffer[0])
            else "paragraph"
        )
        counter += 1
        elements.append(
            ExtractedElement(
                id=f"pdf-{page_num or 0}-{counter}",
                kind=kind,
                text=text_value,
                normalized_text=normalized,
                span=make_span(
                    path,
                    file_id,
                    page=page_num,
                    section=current_topic,
                    element_id=f"pdf-{page_num or 0}-{counter}",
                ),
                role=buffer_role,
                confidence=confidence,
                metadata=page_meta,
            )
        )
        buffer = []
        buffer_role = None
        return counter

    counter = 1 if title_lines else 0
    for raw_line in lines[index:]:
        line = strip_bullet_prefix(raw_line)
        if not line:
            counter = flush_buffer(counter)
            continue
        role = (
            "outline"
            if title_is_outline
            else classify_pdf_role(line, kind="paragraph", topic_hint=current_topic)
        )
        if role in {"footer", "noise"}:
            counter = flush_buffer(counter)
            continue
        if (
            buffer
            and role == buffer_role
            and not is_bullet_like(raw_line)
            and buffer_role in {"body", "formula", "outline"}
            and (len(buffer[-1]) < 110 or not re.search(r"[.!?]$", buffer[-1]))
        ):
            buffer[-1] = f"{buffer[-1]} {line}".strip()
            continue
        counter = flush_buffer(counter)
        buffer = [line]
        buffer_role = role
    flush_buffer(counter)
    return elements


# A scanned PDF whose only native text layer is a per-page watermark
# ("Reproduced with permission..." stamps from ProQuest, library scans,
# etc.) leaks through both the macOS NativeBridge and PyPDF2 with a
# suspiciously low usable-text-per-page density. The user-visible
# symptom: 18-page paper renders as a single 170-char chunk in the
# Reader and produces zero useful concepts in the Atlas.
#
# When usable text is below this threshold per page we treat the
# extraction as scanned-only and retry with Docling, which has built-in
# RapidOCR. Threshold tuned against the Daft & Lengel 1986 paper (a
# real first-user case): bridge yielded ~9 chars/page of body text;
# Docling-OCR yielded 145 typed nodes from the same file.
_SCANNED_PDF_USABLE_CHARS_PER_PAGE = 30


def _usable_chars(elements: list[ExtractedElement]) -> int:
    """Sum the lengths of element text after the parser's own
    footer/noise/outline filtering. Watermark and copyright stamps are
    classified as `footer` and excluded from `normalized_text`, so we
    measure the body content the chunker will actually see."""
    return sum(len(element.normalized_text or "") for element in elements)


def _looks_like_scanned_pdf(elements: list[ExtractedElement], page_count: int | None) -> bool:
    """Density heuristic: real academic / business PDFs carry hundreds
    of body chars per page. When the bridge or PyPDF2 returns a tiny
    fraction of that across many pages, it almost always means the text
    layer is just per-page metadata and the body is image-only."""
    if not page_count or page_count < 2:
        return False
    return _usable_chars(elements) / page_count < _SCANNED_PDF_USABLE_CHARS_PER_PAGE


def _docling_ocr_fallback(path: Path, file_id: str) -> tuple[list[ExtractedElement], int | None]:
    """Best-effort OCR re-extract via Docling. Returns (elements, pages)
    on success and ([], None) when Docling is missing, throws, or
    produces nothing usable. Caller decides whether to use the result.

    Lazy-import keeps services.extraction free of a hard Docling
    dependency — Docling is ~1-2 GB and the typed-nodes path was the
    first place it landed. Reusing the same wrapper here means the
    ~1-2 GB cost is only paid once, by users who installed Docling
    deliberately."""
    try:
        from services.ingestion import docling_parser, typed_walker
    except Exception:
        return [], None
    if not docling_parser.is_available():
        return [], None
    try:
        doc = docling_parser.parse_document(path)
        nodes = typed_walker.walk(doc)
    except Exception:
        return [], None
    if not nodes:
        return [], None

    elements: list[ExtractedElement] = []
    page_numbers: set[int] = set()
    counter = 0
    for node in nodes:
        text = (node.verbatim_text or "").strip()
        if not text:
            continue
        page = node.page if node.page else None
        if page is not None:
            page_numbers.add(int(page))
        section = node.heading_path or (f"Page {page}" if page else path.stem)
        # Map the typed-walker node_type onto the ExtractedElement.kind
        # vocabulary used by the chunk builder. Anything that is not a
        # heading, list_item, caption, footnote, equation, header, or
        # footer becomes a paragraph — same default the bridge path
        # uses for body text.
        kind_map = {
            "heading": "heading",
            "list_item": "bullet_list",
            "caption": "caption",
            "footnote": "footnote",
            "equation": "formula",
            "header": "heading",
            "footer": "paragraph",
        }
        kind = kind_map.get(node.node_type, "paragraph")
        counter += 1
        element_id = f"docling-ocr-{counter}"
        elements.append(
            ExtractedElement(
                id=element_id,
                kind=kind,
                text=text,
                normalized_text=text,
                span=make_span(
                    path,
                    file_id,
                    page=page,
                    section=section,
                    element_id=element_id,
                ),
                role="body",
                confidence=0.72,
                metadata={"used_ocr": True, "source": "docling-rapidocr"},
            )
        )
    page_count = max(page_numbers) if page_numbers else None
    return elements, page_count


def parse_pdf(path: Path, *, suffix: str, mime_type: str, context: ParserContext):
    file_id = file_sha(path)[:16]
    bridge = NativeBridge.run(path)
    if bridge and bridge.get("pages"):
        elements: list[ExtractedElement] = []
        warnings = list(bridge.get("warnings") or [])
        extraction_modes = list(bridge.get("extraction_modes") or ["native_text"])
        for page in bridge["pages"]:
            text = normalize_space(page.get("text") or "")
            if not text:
                continue
            page_num = int(page.get("page") or 0) or None
            metadata = {
                "used_ocr": bool(page.get("used_ocr")),
                "native_char_count": page.get("native_char_count"),
                "ocr_char_count": page.get("ocr_char_count"),
            }
            elements.extend(
                _pdf_page_elements(
                    path,
                    file_id,
                    page_num=page_num,
                    text=text,
                    confidence=0.78 if metadata["used_ocr"] else 0.93,
                    metadata=metadata,
                )
            )
        bridge_page_count = bridge.get("page_count")
        if _looks_like_scanned_pdf(elements, bridge_page_count):
            ocr_elements, ocr_page_count = _docling_ocr_fallback(path, file_id)
            ocr_chars = _usable_chars(ocr_elements)
            bridge_chars = _usable_chars(elements)
            if ocr_elements and ocr_chars > bridge_chars * 4:
                # Docling beat the bridge by a wide margin — replace.
                # The 4x guard avoids triggering the swap on a marginal
                # win where Docling hallucinated a couple of lines.
                return build_asset(
                    path,
                    detected_type=suffix,
                    mime_type=mime_type,
                    parser_name="apple-pdfkit-vision+docling-rapidocr",
                    elements=ocr_elements,
                    context=context,
                    warnings=warnings
                    + [
                        f"Native text layer was watermark-only "
                        f"({bridge_chars} chars across {bridge_page_count} pages). "
                        f"Re-extracted via Docling OCR — recovered {ocr_chars} chars."
                    ],
                    extraction_modes=["ocr_fallback"],
                    metadata={"page_count": ocr_page_count or bridge_page_count},
                    confidence=0.72,
                )
            warnings.append(
                f"PDF appears to be a scanned document. Only {bridge_chars} chars "
                f"of usable body text recovered from {bridge_page_count} pages, "
                "and Docling OCR was not available or produced no improvement. "
                "The Reader and Concept Atlas will be sparse — re-upload an OCR'd "
                "version if you have one."
            )
        return build_asset(
            path,
            detected_type=suffix,
            mime_type=mime_type,
            parser_name=str(bridge.get("parser") or "apple-pdfkit-vision"),
            elements=elements,
            context=context,
            warnings=warnings,
            extraction_modes=extraction_modes,
            metadata={"page_count": bridge_page_count},
            confidence=float(bridge.get("confidence") or 0.86),
        )

    reader = PdfReader(str(path))
    # The native-bridge branch above always returns, so we reach this
    # PyPDF fall-through only when the bridge failed. Re-init `elements`
    # and `warnings` to fresh empty lists for this path. Annotations
    # are intentionally dropped on the re-init to satisfy mypy's
    # `no-redef` rule. The element types stay pinned: `elements.extend`
    # consumes `_pdf_page_elements`' typed return, `warnings.append`
    # only sees string literals, and `build_asset`'s typed parameters
    # constrain both lists at the call site.
    elements = []
    warnings = []
    empty_pages = 0
    for index, page in enumerate(reader.pages, start=1):
        text = normalize_space(page.extract_text() or "")
        if not text:
            empty_pages += 1
            continue
        elements.extend(
            _pdf_page_elements(
                path,
                file_id,
                page_num=index,
                text=text,
                confidence=0.84,
                metadata={"used_ocr": False, "native_char_count": len(text), "ocr_char_count": 0},
            )
        )
    pdf_page_count = len(reader.pages)
    if empty_pages:
        warnings.append(
            f"{empty_pages} page(s) had no native text layer. Build the macOS helper for OCR fallback."
        )
    if _looks_like_scanned_pdf(elements, pdf_page_count):
        ocr_elements, ocr_page_count = _docling_ocr_fallback(path, file_id)
        ocr_chars = _usable_chars(ocr_elements)
        pypdf_chars = _usable_chars(elements)
        if ocr_elements and ocr_chars > pypdf_chars * 4:
            return build_asset(
                path,
                detected_type=suffix,
                mime_type=mime_type,
                parser_name="pypdf2+docling-rapidocr",
                elements=ocr_elements,
                context=context,
                warnings=warnings
                + [
                    f"PyPDF2 found only {pypdf_chars} chars across "
                    f"{pdf_page_count} pages. Re-extracted via Docling OCR — "
                    f"recovered {ocr_chars} chars."
                ],
                extraction_modes=["ocr_fallback"],
                metadata={"page_count": ocr_page_count or pdf_page_count},
                confidence=0.72,
            )
        warnings.append(
            f"PDF appears to be a scanned document. Only {pypdf_chars} chars "
            f"of usable body text recovered from {pdf_page_count} pages, "
            "and Docling OCR was not available or produced no improvement."
        )
    return build_asset(
        path,
        detected_type=suffix,
        mime_type=mime_type,
        parser_name="pypdf2",
        elements=elements,
        context=context,
        warnings=warnings,
        extraction_modes=["native_text"],
        metadata={"page_count": pdf_page_count},
        confidence=0.74 if empty_pages else 0.88,
    )
