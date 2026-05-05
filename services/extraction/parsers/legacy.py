from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi import HTTPException

from ..types import ExtractedElement
from ..utils import file_sha, normalize_space
from .common import ParserContext, build_asset, make_span

try:
    import xlrd
except ImportError:
    xlrd = None


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
    if xlrd is None:
        raise HTTPException(status_code=400, detail="XLS support requires xlrd")

    workbook = xlrd.open_workbook(str(path), formatting_info=False)
    file_id = file_sha(path)[:16]
    elements: list[ExtractedElement] = []
    for sheet in workbook.sheets():
        sheet_name = normalize_space(sheet.name) or "Sheet"
        sheet_span = make_span(path, file_id, sheet=sheet_name, section=sheet_name, element_id=f"sheet-{sheet_name}")
        elements.append(
            ExtractedElement(
                id=sheet_span.element_id or f"sheet-{sheet_name}",
                kind="sheet",
                text=sheet_name,
                normalized_text=sheet_name,
                span=sheet_span,
            )
        )
        for row_index in range(sheet.nrows):
            display_values: list[str] = []
            cell_meta: list[dict[str, object]] = []
            for col_index in range(sheet.ncols):
                cell = sheet.cell(row_index, col_index)
                value = cell.value
                if cell.ctype in {xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK}:
                    continue
                if cell.ctype == xlrd.XL_CELL_DATE:
                    try:
                        value = xlrd.xldate_as_datetime(value, workbook.datemode).isoformat(sep=" ")
                    except Exception:
                        value = str(value)
                elif cell.ctype == xlrd.XL_CELL_BOOLEAN:
                    value = "TRUE" if value else "FALSE"
                display_text = normalize_space(str(value))
                if not display_text:
                    continue
                coordinate = f"R{row_index + 1}C{col_index + 1}"
                display_values.append(f"{coordinate}: {display_text}")
                cell_meta.append({"coordinate": coordinate, "display": display_text})
                span = make_span(
                    path,
                    file_id,
                    sheet=sheet_name,
                    section=sheet_name,
                    row_range=f"{row_index + 1}:{row_index + 1}",
                    cell_range=coordinate,
                    element_id=f"{sheet_name}-{coordinate}",
                )
                elements.append(
                    ExtractedElement(
                        id=span.element_id or f"{sheet_name}-{coordinate}",
                        kind="cell",
                        text=display_text,
                        normalized_text=display_text,
                        span=span,
                        metadata={"coordinate": coordinate},
                    )
                )
            if display_values:
                row_text = "\n".join(display_values)
                span = make_span(
                    path,
                    file_id,
                    sheet=sheet_name,
                    section=sheet_name,
                    row_range=f"{row_index + 1}:{row_index + 1}",
                    element_id=f"{sheet_name}-row-{row_index + 1}",
                )
                elements.append(
                    ExtractedElement(
                        id=span.element_id or f"{sheet_name}-row-{row_index + 1}",
                        kind="table_row",
                        text=row_text,
                        normalized_text=row_text,
                        span=span,
                        metadata={"cells": cell_meta},
                    )
                )

    return build_asset(
        path,
        detected_type=suffix,
        mime_type=mime_type,
        parser_name="xlrd-structured",
        elements=elements,
        context=context,
        warnings=["Converted legacy .xls through xlrd; formulas are indexed from cached cell values."],
        extraction_modes=["table_aware"],
        metadata={"page_count": workbook.nsheets},
        confidence=0.76,
    )
