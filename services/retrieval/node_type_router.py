"""Map a user query to the set of node_types worth retrieving against.

The typed-node retrieval path filters BM25 + vector candidates by
`node_type` so a question about "the table on page 3" doesn't compete
against caption text and a question about photosynthesis doesn't surface
table cells. The mapping is keyword-driven and deliberately conservative
— if no trigger word fires, retrieval defaults to `heading`, `body`,
`list_item` (the three node types that always carry prose).

`header` and `footer` are NEVER retrievable. They're page chrome
(running titles, page numbers) that the ingest path already excluded
from `node_embeddings`. Including them in the BM25 filter would still
let them surface from `node_fts`, so the filter clamps them out here.
"""

from __future__ import annotations

import re
from typing import FrozenSet

# Default retrievable types — the prose backbone.
_BASE_TYPES: FrozenSet[str] = frozenset({"heading", "body", "list_item"})

# Trigger word -> additional node_type to include. Order doesn't matter;
# matches are unioned.
_KEYWORD_EXPANSIONS: dict[str, str] = {
    # Tables / data
    "table": "table_cell",
    "tables": "table_cell",
    "row": "table_cell",
    "rows": "table_cell",
    "column": "table_cell",
    "columns": "table_cell",
    "cell": "table_cell",
    "data": "table_cell",
    # Figures / diagrams / images
    "figure": "caption",
    "figures": "caption",
    "diagram": "caption",
    "chart": "caption",
    "image": "caption",
    "photo": "caption",
    # Formulas / equations
    "formula": "equation",
    "formulas": "equation",
    "equation": "equation",
    "equations": "equation",
    # Footnotes / citations / references
    "footnote": "footnote",
    "footnotes": "footnote",
    "citation": "footnote",
    "citations": "footnote",
    "reference": "footnote",
    "references": "footnote",
}

_TOKEN_PATTERN = re.compile(r"[A-Za-z]+")


def node_types_for_query(query: str) -> FrozenSet[str]:
    """Return the set of node_types BM25/vector should consider for `query`.

    Always includes the base prose set. Adds extras when the query
    surfaces a trigger word. Matching is case-insensitive and
    whole-token (no substring matches — "tableau" must not pull in
    `table_cell`).
    """
    extras: set[str] = set()
    for token in _TOKEN_PATTERN.findall(query.lower()):
        target = _KEYWORD_EXPANSIONS.get(token)
        if target is not None:
            extras.add(target)
    return _BASE_TYPES | extras
