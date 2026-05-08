"""Walk a DoclingDocument and emit one TypedNode per leaf in reading order.

Mirrors what `services.ingestion.concepts.chunk_text` does for the legacy
chunks pipeline, but at a finer grain — the walker keeps Docling's
structure (headings, list items, captions, tables, footnotes) instead of
collapsing everything into ~1200-char paragraph chunks. Downstream PRs
will use the typed metadata to filter retrieval (table_cell only when the
query mentions tables, footnote with a lower boost, etc.).

The output is a flat list of TypedNode rows in reading order. Char
offsets are computed against a canonical text built incrementally as the
walker proceeds — joining text with "\\n\\n" — so they index into the
same canonical document the rest of the pipeline consumes. PR 2 wires
those offsets into the citation chips.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Docling element labels (DocItemLabel.value strings) mapped to our
# nine-value node_type enum from migration 0016. Anything not in the map
# falls through to "body" so the walker never silently drops content.
DOCLING_TYPE_MAP: dict[str, str] = {
    "title": "heading",
    "section_header": "heading",
    "text": "body",
    "paragraph": "body",
    "list_item": "list_item",
    "caption": "caption",
    "formula": "equation",
    "footnote": "footnote",
    "page_header": "header",
    "page_footer": "footer",
    "code": "body",
    "reference": "footnote",
}


@dataclass(frozen=True)
class TypedNode:
    """One leaf in a parsed document tree.

    char_start / char_end index into the canonical text that the walker
    builds while iterating — same offsets the reader pane will use for
    scroll-and-highlight once PR 2 wires them in.
    """

    node_type: str
    heading_path: str
    page: int | None
    char_start: int
    char_end: int
    verbatim_text: str
    parent_block_id: int | None
    reading_order: int


def walk(doc: Any) -> list[TypedNode]:
    """Walk a DoclingDocument in reading order, emit typed nodes.

    Accepts the doc as `Any` because importing DoclingDocument at module
    load time would defeat the graceful-fallback design of the optional
    Docling dependency. The duck-typed call surface is small:
    `doc.iterate_items()` yields `(NodeItem, level)` tuples, and each
    NodeItem exposes `label`, `text`, and optional `prov` / `level`.
    """
    nodes: list[TypedNode] = []
    heading_stack: list[tuple[int, str]] = []
    canonical_offset = 0
    reading_order = 0

    for element, _level in doc.iterate_items():
        text = (getattr(element, "text", "") or "").strip()
        if not text:
            # GroupItems, pictures, tables-as-blocks (we walk cells in a
            # follow-up PR), and any element whose text rolled up to a
            # parent: skip without consuming reading_order.
            continue

        label_obj = getattr(element, "label", None)
        label_value = getattr(label_obj, "value", None) or str(label_obj or "")
        node_type = DOCLING_TYPE_MAP.get(label_value, "body")

        if node_type == "heading":
            depth = int(getattr(element, "level", 1) or 1)
            heading_stack = [(d, t) for d, t in heading_stack if d < depth]
            heading_stack.append((depth, text))

        heading_path = " > ".join(t for _, t in heading_stack)

        if reading_order > 0:
            canonical_offset += 2  # account for the "\n\n" separator
        char_start = canonical_offset
        canonical_offset += len(text)
        char_end = canonical_offset

        prov = getattr(element, "prov", None) or []
        page = int(prov[0].page_no) if prov and getattr(prov[0], "page_no", None) is not None else None

        nodes.append(
            TypedNode(
                node_type=node_type,
                heading_path=heading_path,
                page=page,
                char_start=char_start,
                char_end=char_end,
                verbatim_text=text,
                parent_block_id=None,
                reading_order=reading_order,
            )
        )
        reading_order += 1

    return nodes
