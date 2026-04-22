from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from ..types import ExtractedElement
from ..utils import normalize_space, safe_text, file_sha
from .common import ParserContext, build_asset, make_span

try:
    from docx import Document as DocxDocument
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P
    from docx.table import Table as DocxTable
    from docx.text.paragraph import Paragraph as DocxParagraph
except ImportError:
    DocxDocument = None
    CT_Tbl = None
    CT_P = None
    DocxTable = None
    DocxParagraph = None


def parse_docx(path: Path, *, suffix: str, mime_type: str, context: ParserContext):
    if DocxDocument is None or CT_P is None or CT_Tbl is None or DocxParagraph is None or DocxTable is None:
        raise HTTPException(status_code=400, detail="DOCX support requires python-docx")
    doc = DocxDocument(str(path))
    file_id = file_sha(path)[:16]
    elements: list[ExtractedElement] = []
    current_heading: str | None = None

    def iter_blocks():
        body = doc.element.body
        for child in body.iterchildren():
            if isinstance(child, CT_P):
                yield DocxParagraph(child, doc)
            elif isinstance(child, CT_Tbl):
                yield DocxTable(child, doc)

    para_index = 0
    table_index = 0
    warnings = ["Comments, tracked changes, and footnotes are not fully preserved yet."]
    for block in iter_blocks():
        if isinstance(block, DocxParagraph):
            text = normalize_space(block.text)
            if not text:
                continue
            para_index += 1
            style_name = safe_text(getattr(getattr(block, "style", None), "name", ""))
            kind = "paragraph"
            if style_name.lower().startswith("heading"):
                current_heading = text
                kind = "heading"
            elif "list" in style_name.lower():
                kind = "bullet_list"
            span = make_span(
                path,
                file_id,
                section=current_heading,
                paragraph_id=f"p{para_index}",
                element_id=f"docx-paragraph-{para_index}",
            )
            elements.append(
                ExtractedElement(
                    id=span.element_id or f"docx-paragraph-{para_index}",
                    kind=kind,
                    text=text,
                    normalized_text=text,
                    span=span,
                    metadata={"style_name": style_name},
                )
            )
        else:
            table_index += 1
            rows: list[list[str]] = []
            for row in block.rows:
                values = [normalize_space(cell.text) for cell in row.cells]
                if any(values):
                    rows.append(values)
            if not rows:
                continue
            header = rows[0]
            body_rows = rows[1:] if len(rows) > 1 else []
            table_lines = []
            if header:
                table_lines.append(" | ".join(header))
            for row_index, row in enumerate(body_rows, start=2):
                table_lines.append(" | ".join(row))
                row_range = f"{row_index}:{row_index}"
                for col_index, value in enumerate(row, start=1):
                    if not value:
                        continue
                    coord = f"R{row_index}C{col_index}"
                    span = make_span(
                        path,
                        file_id,
                        section=current_heading,
                        paragraph_id=f"tbl{table_index}-r{row_index}-c{col_index}",
                        element_id=f"docx-table-{table_index}-cell-{row_index}-{col_index}",
                        cell_range=coord,
                    )
                    elements.append(
                        ExtractedElement(
                            id=span.element_id or coord,
                            kind="table_cell",
                            text=value,
                            normalized_text=value,
                            span=span,
                            metadata={"table_index": table_index, "row_range": row_range},
                        )
                    )
            table_text = "\n".join(table_lines)
            span = make_span(path, file_id, section=current_heading, element_id=f"docx-table-{table_index}")
            elements.append(
                ExtractedElement(
                    id=span.element_id or f"docx-table-{table_index}",
                    kind="table",
                    text=table_text,
                    normalized_text=table_text,
                    span=span,
                    metadata={"table_index": table_index, "row_count": len(rows), "column_count": len(header)},
                )
            )

    return build_asset(
        path,
        detected_type=suffix,
        mime_type=mime_type,
        parser_name="python-docx-structured",
        elements=elements,
        context=context,
        warnings=warnings,
        extraction_modes=["structured_text"],
        metadata={"page_count": None},
        confidence=0.87,
    )
