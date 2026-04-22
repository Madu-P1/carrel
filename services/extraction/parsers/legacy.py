from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi import HTTPException

from ..types import ExtractedElement
from ..utils import file_sha, normalize_space
from .common import ParserContext, build_asset, make_span


def run_textutil_conversion(path: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["/usr/bin/textutil", "-convert", "txt", "-stdout", str(path)],
            capture_output=True,
            text=True,
            check=True,
            timeout=90,
        )
    except Exception:
        return None
    text = normalize_space(completed.stdout)
    return text or None


def parse_doc(path: Path, *, suffix: str, mime_type: str, context: ParserContext):
    converted = run_textutil_conversion(path)
    if converted is None:
        raise HTTPException(status_code=400, detail="Legacy .doc files require macOS textutil conversion.")
    return build_asset(
        path,
        detected_type=suffix,
        mime_type=mime_type,
        parser_name="textutil-doc-fallback",
        elements=[
            ExtractedElement(
                id="doc-1",
                kind="paragraph",
                text=converted,
                normalized_text=converted,
                span=make_span(path, file_sha(path)[:16], section=path.stem, element_id="doc-1"),
            )
        ],
        context=context,
        warnings=["Converted legacy .doc through textutil; rich structure may be lossy."],
        extraction_modes=["textutil"],
        metadata={"page_count": None},
        confidence=0.63,
    )


def parse_ppt(path: Path, *, suffix: str, mime_type: str, context: ParserContext):
    converted = run_textutil_conversion(path)
    if converted is None:
        raise HTTPException(status_code=400, detail="Legacy .ppt files are not yet supported without conversion.")
    return build_asset(
        path,
        detected_type=suffix,
        mime_type=mime_type,
        parser_name="textutil-ppt-fallback",
        elements=[
            ExtractedElement(
                id="ppt-1",
                kind="paragraph",
                text=converted,
                normalized_text=converted,
                span=make_span(path, file_sha(path)[:16], section=path.stem, element_id="ppt-1"),
            )
        ],
        context=context,
        warnings=["Converted legacy .ppt through textutil; slide boundaries and notes may be lossy."],
        extraction_modes=["textutil"],
        metadata={"page_count": None},
        confidence=0.58,
    )


def parse_xls(path: Path, *, suffix: str, mime_type: str, context: ParserContext):
    raise HTTPException(status_code=400, detail="Legacy .xls spreadsheets are not yet supported directly. Save as .xlsx or .csv.")
