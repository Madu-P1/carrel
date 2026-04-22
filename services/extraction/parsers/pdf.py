from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional

from PyPDF2 import PdfReader

from ..native_bridge import NativeBridge
from ..quality import classify_pdf_role, is_bullet_like, is_footer_or_noise, is_formula_text, is_outline_text, strip_bullet_prefix
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
    lines = [normalize_space(line) for line in str(text or "").splitlines() if normalize_space(line)]
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
        if len(title_lines) >= 3 or len(" ".join(title_lines)) >= 140 or is_bullet_like(next_line) or is_formula_text(next_line):
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
                span=make_span(path, file_id, page=page_num, section=current_topic, element_id=f"pdf-{page_num or 0}-title"),
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
        kind = "formula" if buffer_role == "formula" else "bullet_list" if is_bullet_like(buffer[0]) else "paragraph"
        counter += 1
        elements.append(
            ExtractedElement(
                id=f"pdf-{page_num or 0}-{counter}",
                kind=kind,
                text=text_value,
                normalized_text=normalized,
                span=make_span(path, file_id, page=page_num, section=current_topic, element_id=f"pdf-{page_num or 0}-{counter}"),
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
        role = "outline" if title_is_outline else classify_pdf_role(line, kind="paragraph", topic_hint=current_topic)
        if role in {"footer", "noise"}:
            counter = flush_buffer(counter)
            continue
        if buffer and role == buffer_role and not is_bullet_like(raw_line) and buffer_role in {"body", "formula", "outline"} and (len(buffer[-1]) < 110 or not re.search(r"[.!?]$", buffer[-1])):
            buffer[-1] = f"{buffer[-1]} {line}".strip()
            continue
        counter = flush_buffer(counter)
        buffer = [line]
        buffer_role = role
    flush_buffer(counter)
    return elements


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
        return build_asset(
            path,
            detected_type=suffix,
            mime_type=mime_type,
            parser_name=str(bridge.get("parser") or "apple-pdfkit-vision"),
            elements=elements,
            context=context,
            warnings=warnings,
            extraction_modes=extraction_modes,
            metadata={"page_count": bridge.get("page_count")},
            confidence=float(bridge.get("confidence") or 0.86),
        )

    reader = PdfReader(str(path))
    elements: list[ExtractedElement] = []
    warnings: list[str] = []
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
    if empty_pages:
        warnings.append(f"{empty_pages} page(s) had no native text layer. Build the macOS helper for OCR fallback.")
    return build_asset(
        path,
        detected_type=suffix,
        mime_type=mime_type,
        parser_name="pypdf2",
        elements=elements,
        context=context,
        warnings=warnings,
        extraction_modes=["native_text"],
        metadata={"page_count": len(reader.pages)},
        confidence=0.74 if empty_pages else 0.88,
    )
