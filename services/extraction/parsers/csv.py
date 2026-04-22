from __future__ import annotations

import csv
import io
from pathlib import Path

from ..types import ExtractedElement
from ..utils import normalize_space, file_sha
from .common import ParserContext, build_asset, make_span


def parse_csv(path: Path, *, suffix: str, mime_type: str, context: ParserContext):
    file_id = file_sha(path)[:16]
    raw = path.read_text(encoding="utf-8", errors="ignore")
    delimiter = "\t" if suffix == ".tsv" else ","
    reader = csv.reader(io.StringIO(raw), delimiter=delimiter)
    elements: list[ExtractedElement] = []
    headers: list[str] = []
    for row_index, row in enumerate(reader, start=1):
        values = [normalize_space(cell) for cell in row]
        if not any(values):
            continue
        if row_index == 1:
            headers = values
        row_bits = []
        for col_index, value in enumerate(values, start=1):
            if not value:
                continue
            header = headers[col_index - 1] if col_index - 1 < len(headers) else f"Column {col_index}"
            coord = f"R{row_index}C{col_index}"
            text = f"{header}: {value}"
            row_bits.append(text)
            span = make_span(
                path,
                file_id,
                sheet="Sheet1",
                section="Sheet1",
                row_range=f"{row_index}:{row_index}",
                cell_range=coord,
                element_id=f"csv-{coord}",
            )
            elements.append(
                ExtractedElement(
                    id=span.element_id or f"csv-{coord}",
                    kind="cell",
                    text=text,
                    normalized_text=text,
                    span=span,
                )
            )
        if row_bits:
            joined = "\n".join(row_bits)
            span = make_span(path, file_id, sheet="Sheet1", section="Sheet1", row_range=f"{row_index}:{row_index}", element_id=f"csv-row-{row_index}")
            elements.append(
                ExtractedElement(
                    id=span.element_id or f"csv-row-{row_index}",
                    kind="table_row",
                    text=joined,
                    normalized_text=joined,
                    span=span,
                )
            )
    return build_asset(
        path,
        detected_type=suffix,
        mime_type=mime_type,
        parser_name="csv-structured",
        elements=elements,
        context=context,
        extraction_modes=["table_aware"],
        metadata={"page_count": 1},
        confidence=0.84,
    )
