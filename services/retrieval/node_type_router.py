"""Map a user query to the set of node_types worth retrieving against.

The typed-node retrieval path filters BM25 + vector candidates by
`node_type` so a question about "the table on page 3" doesn't compete
against caption text and a question about photosynthesis doesn't surface
table cells. The mapping is keyword-driven and deliberately conservative
— if no trigger word fires, retrieval defaults to `body` and `list_item`,
the node types that carry answer content.

`heading`, `header`, and `footer` are NEVER retrievable and never
citable (see `NON_CITABLE_NODE_TYPES`). They are structure, not answers:
a heading is a section label, a header/footer is page chrome (running
titles, page numbers). Grounding a claim on one produces an answer with
no informational value — it just echoes a title back. The heading text
is not lost to retrieval: the ingest path copies each node's
`heading_path` onto its body/list_item rows and `node_fts` indexes that
column, so a query whose terms appear only in a section title still
matches the answer-bearing nodes scoped under it. The heading node
itself stays out of the candidate pool.
"""

from __future__ import annotations

import re
from typing import FrozenSet

# Node types that are structure, not answer content. A claim must never
# be grounded on one: a heading is a section label, header/footer is page
# chrome. Retrieval keeps them out of the candidate pool and the tutor
# citation path filters them as a backstop. Single source of truth —
# imported by services.tutor and evals.run_evals.
NON_CITABLE_NODE_TYPES: FrozenSet[str] = frozenset({"heading", "header", "footer"})

# Default retrievable types — the answer-bearing prose backbone.
_BASE_TYPES: FrozenSet[str] = frozenset({"body", "list_item"})

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
