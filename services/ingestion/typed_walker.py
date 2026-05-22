"""Walk a DoclingDocument and emit TypedNodes in reading order.

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


# Sentence-terminal punctuation. A body fragment that does not end with
# one of these (after peeling trailing closing quotes/brackets) is a
# hard-wrap continuation and merges into the next fragment.
_BOUNDARY = frozenset(".?!:;")
_TRAILING = frozenset("\"')]”’")


def _ends_at_boundary(text: str) -> bool:
    """True when `text` ends a complete unit (the next body node is separate)."""
    stripped = text.rstrip()
    while stripped and stripped[-1] in _TRAILING:
        stripped = stripped[:-1].rstrip()
    return bool(stripped) and stripped[-1] in _BOUNDARY


def _mergeable(node: TypedNode) -> bool:
    """Whether `node` may take part in a soft-wrap merge.

    Only plain `body` text qualifies. A body node carrying an internal
    newline is a fenced code block (Docling maps `code` to `body` and
    emits the whole block as one element) or other preformatted content,
    so it is never merged.
    """
    return node.node_type == "body" and "\n" not in node.verbatim_text


def _merge_soft_wrapped(nodes: list[TypedNode]) -> list[TypedNode]:
    """Rejoin body fragments that Docling split at physical line wraps.

    Docling emits one element per physical source line, so a hard-wrapped
    paragraph arrives as several `body` elements split mid-phrase, which
    makes verbatim citation impossible. A body fragment is merged into
    the next when it does not end at a sentence boundary and both sides
    are plain body text under the same heading. Non-body nodes, code
    blocks, and boundary-ending fragments are left alone. char_start,
    char_end, and reading_order are recomputed so the canonical
    "\\n\\n"-joined text stays consistent.

    A fragment ending in an abbreviation ("Inc.", "No.") is treated as a
    boundary and not merged: a rare, benign mis-split.
    """
    if not nodes:
        return nodes

    groups: list[list[TypedNode]] = []
    for node in nodes:
        tail = groups[-1][-1] if groups else None
        if (
            tail is not None
            and _mergeable(tail)
            and _mergeable(node)
            and tail.heading_path == node.heading_path
            and not _ends_at_boundary(tail.verbatim_text)
        ):
            groups[-1].append(node)
        else:
            groups.append([node])

    merged: list[TypedNode] = []
    canonical_offset = 0
    for order, group in enumerate(groups):
        head = group[0]
        text = " ".join(item.verbatim_text for item in group)
        if order > 0:
            canonical_offset += 2  # the "\n\n" separator, matches `walk`
        char_start = canonical_offset
        canonical_offset += len(text)
        merged.append(
            TypedNode(
                node_type=head.node_type,
                heading_path=head.heading_path,
                page=head.page,
                char_start=char_start,
                char_end=canonical_offset,
                verbatim_text=text,
                parent_block_id=head.parent_block_id,
                reading_order=order,
            )
        )
    return merged


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
        page = (
            int(prov[0].page_no) if prov and getattr(prov[0], "page_no", None) is not None else None
        )

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

    return _merge_soft_wrapped(nodes)
