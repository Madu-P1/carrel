# PR 1 — Typed nodes + Docling ingest (feature-flagged)

> **Goal:** ship the foundation of the new Ask pipeline. Add a typed-node parallel ingest path that runs alongside the existing `chunks` pipeline behind a feature flag. No retrieval, UI, or behavior changes for end users in this PR.
>
> **Parent spec:** [ask-pipeline.md](./ask-pipeline.md)
> **Estimated effort:** 5-7 days for one engineer.
> **Out of scope:** retrieval changes (PR 2), cross-encoder re-rank (PR 3), Free-tier card UI (PR 4), Pro tool-use validators (PR 5), `chunks` deprecation (PR 6 after parity).

## Why this PR ships first

Everything downstream needs typed nodes to exist in the DB. Once `nodes` is populated alongside `chunks` for at least 10 real documents, the retrieval PR can compare the two side-by-side and prove the quality jump before it gets switched on.

## What lands

1. New migration `0016_nodes_typed.sql` — the three new tables.
2. New module `services/ingestion/typed_walker.py` — turns a `DoclingDocument` into a list of `TypedNode` rows.
3. Docling added to `requirements.txt` as an optional dep with a graceful import fallback.
4. New module `services/ingestion/docling_parser.py` — wraps Docling's `DocumentConverter` for PDF/DOCX/EPUB/HTML/MD.
5. Hook in `services/ingestion/orchestrator.py::ingest_document_record` — when feature flag is on, also run the typed-node path.
6. Persistence helpers in `services/ingestion/persistence.py` — `insert_typed_nodes()`, `delete_typed_nodes()`, parallel to existing chunk helpers.
7. Two env-var feature flags + an `app_settings` row for backfill state.
8. Tests covering: graceful Docling absence, single-column PDF, multi-column PDF reading order, DOCX, scanned PDF (Apple Vision OCR), node-type assignment accuracy.

## Migration `0016_nodes_typed.sql`

```sql
PRAGMA journal_mode = WAL;

-- Typed nodes — one row per leaf in the parsed document tree.
CREATE TABLE IF NOT EXISTS nodes (
    id              INTEGER PRIMARY KEY,
    doc_id          TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    node_type       TEXT NOT NULL CHECK (node_type IN (
        'heading', 'body', 'list_item', 'caption',
        'table_cell', 'equation', 'footnote', 'header', 'footer'
    )),
    heading_path    TEXT NOT NULL DEFAULT '',
    page            INTEGER,
    char_start      INTEGER NOT NULL,
    char_end        INTEGER NOT NULL,
    verbatim_text   TEXT NOT NULL,
    parent_block_id INTEGER REFERENCES nodes(id) ON DELETE CASCADE,
    reading_order   INTEGER NOT NULL,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_nodes_doc ON nodes(doc_id);
CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_nodes_doc_order ON nodes(doc_id, reading_order);

-- Vector index — same dimension as chunks_vec for embedding-model parity.
CREATE VIRTUAL TABLE IF NOT EXISTS node_embeddings USING vec0(
    node_id INTEGER PRIMARY KEY,
    embedding float[384]
);

-- BM25 index. content='nodes' makes it a contentless FTS that mirrors the nodes table.
CREATE VIRTUAL TABLE IF NOT EXISTS node_fts USING fts5(
    verbatim_text,
    heading_path,
    node_type UNINDEXED,
    id UNINDEXED,
    doc_id UNINDEXED,
    content='nodes',
    content_rowid='id'
);

-- Triggers keep node_fts in sync with nodes.
CREATE TRIGGER IF NOT EXISTS nodes_fts_insert AFTER INSERT ON nodes BEGIN
    INSERT INTO node_fts(rowid, verbatim_text, heading_path, node_type, id, doc_id)
    VALUES (new.id, new.verbatim_text, new.heading_path, new.node_type, new.id, new.doc_id);
END;

CREATE TRIGGER IF NOT EXISTS nodes_fts_delete AFTER DELETE ON nodes BEGIN
    INSERT INTO node_fts(node_fts, rowid, verbatim_text, heading_path, node_type, id, doc_id)
    VALUES ('delete', old.id, old.verbatim_text, old.heading_path, old.node_type, old.id, old.doc_id);
END;

CREATE TRIGGER IF NOT EXISTS nodes_fts_update AFTER UPDATE ON nodes BEGIN
    INSERT INTO node_fts(node_fts, rowid, verbatim_text, heading_path, node_type, id, doc_id)
    VALUES ('delete', old.id, old.verbatim_text, old.heading_path, old.node_type, old.id, old.doc_id);
    INSERT INTO node_fts(rowid, verbatim_text, heading_path, node_type, id, doc_id)
    VALUES (new.id, new.verbatim_text, new.heading_path, new.node_type, new.id, new.doc_id);
END;

INSERT OR IGNORE INTO app_settings (key, value)
VALUES ('node_embeddings_backfill_pending', '0');
```

Mirrors the patterns in `0006_chunks_fts5.sql` and `0007_chunks_vec.sql` exactly. Triggers are critical — without them the FTS index drifts the moment you delete or update a node.

## Feature flags

Two env vars, both default-off:

| Flag | Default | Effect |
|---|---|---|
| `INGEST_USE_DOCLING` | `false` | When true, the orchestrator also runs the Docling typed-node ingest for new documents. Old chunks ingest still runs (no behavior change). |
| `INGEST_DOCLING_FORMATS` | `pdf` | Comma-separated list of formats to route through Docling. Start with PDF only; expand to `pdf,docx,epub,html` in a follow-up after PDF parity is proven. |

Read in [services/ingestion/orchestrator.py](/Users/madu/Desktop/Codex/services/ingestion/orchestrator.py):

```python
def _docling_enabled_for(extension: str) -> bool:
    if os.getenv("INGEST_USE_DOCLING", "false").lower() not in ("1", "true", "yes"):
        return False
    formats = os.getenv("INGEST_DOCLING_FORMATS", "pdf").lower().split(",")
    return extension.lstrip(".").lower() in {fmt.strip() for fmt in formats}
```

## `TypedNode` dataclass

[services/ingestion/typed_walker.py](/Users/madu/Desktop/Codex/services/ingestion/typed_walker.py):

```python
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class TypedNode:
    node_type: str           # heading|body|list_item|caption|table_cell|equation|footnote|header|footer
    heading_path: str        # "Chapter 3 > Photosynthesis"
    page: int | None         # 1-indexed
    char_start: int          # offset in canonical normalized text
    char_end: int
    verbatim_text: str       # exact substring, no normalization
    parent_block_id: int | None  # only set after first insert pass
    reading_order: int       # monotonic per doc
```

## Docling parser wrapper

[services/ingestion/docling_parser.py](/Users/madu/Desktop/Codex/services/ingestion/docling_parser.py):

```python
from __future__ import annotations
from pathlib import Path
from typing import Any

def is_available() -> bool:
    try:
        import docling  # noqa: F401
        return True
    except ImportError:
        return False

def parse_document(path: Path) -> Any:
    """Returns a DoclingDocument or raises a typed error."""
    from docling.document_converter import DocumentConverter
    from docling.datamodel.pipeline_options import PdfPipelineOptions

    pipeline_opts = PdfPipelineOptions()
    pipeline_opts.do_ocr = True
    # On macOS, prefer Apple Vision OCR if available — verify with NativeBridge first.
    pipeline_opts.ocr_options.kind = "easyocr"  # default fallback; swap to apple_vision when wired

    converter = DocumentConverter(
        format_options={"pdf": {"pipeline_options": pipeline_opts}}
    )
    result = converter.convert(str(path))
    return result.document
```

The Apple Vision integration is a follow-up — for this PR, ship with Docling's default OCR (easyocr) so the path is verified end-to-end. Swap to `apple_vision` in PR 1.5 once the macOS-only OCR is benchmarked.

## The walker algorithm

[services/ingestion/typed_walker.py](/Users/madu/Desktop/Codex/services/ingestion/typed_walker.py):

```python
DOCLING_TYPE_MAP = {
    "section_header": "heading",
    "text": "body",
    "list_item": "list_item",
    "caption": "caption",
    "table": "table_cell",     # special: walk cells
    "formula": "equation",
    "footnote": "footnote",
    "page_header": "header",
    "page_footer": "footer",
}

def walk(doc) -> list[TypedNode]:
    """Walk a DoclingDocument in reading order, emit typed nodes."""
    nodes: list[TypedNode] = []
    heading_stack: list[tuple[int, str]] = []  # (depth, text)
    canonical_text_parts: list[str] = []
    canonical_offset = 0
    reading_order = 0

    for element in doc.iterate_items():
        text = (element.text or "").strip()
        if not text:
            continue

        node_type = DOCLING_TYPE_MAP.get(element.label, "body")

        # Update heading stack on every heading
        if node_type == "heading":
            depth = getattr(element, "level", 1)
            heading_stack = [(d, t) for d, t in heading_stack if d < depth]
            heading_stack.append((depth, text))

        heading_path = " > ".join(t for _, t in heading_stack)

        # Append to canonical text + record offsets
        if canonical_text_parts:
            canonical_text_parts.append("\n\n")
            canonical_offset += 2
        char_start = canonical_offset
        canonical_text_parts.append(text)
        canonical_offset += len(text)
        char_end = canonical_offset

        page = getattr(element.prov[0], "page_no", None) if element.prov else None

        nodes.append(TypedNode(
            node_type=node_type,
            heading_path=heading_path,
            page=page,
            char_start=char_start,
            char_end=char_end,
            verbatim_text=text,
            parent_block_id=None,
            reading_order=reading_order,
        ))
        reading_order += 1

    return nodes
```

(The Docling element-iteration API may differ slightly from `iterate_items()` — confirm against the installed version. Pin Docling version in `requirements.txt` to avoid drift.)

## Persistence helpers

Add to [services/ingestion/persistence.py](/Users/madu/Desktop/Codex/services/ingestion/persistence.py):

```python
def insert_typed_nodes(
    conn: sqlite3.Connection,
    doc_id: str,
    nodes: list[TypedNode],
) -> list[int]:
    """Insert nodes, return their assigned IDs in reading order."""
    ids: list[int] = []
    for node in nodes:
        cursor = conn.execute(
            """
            INSERT INTO nodes (
                doc_id, node_type, heading_path, page,
                char_start, char_end, verbatim_text,
                parent_block_id, reading_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc_id, node.node_type, node.heading_path, node.page,
                node.char_start, node.char_end, node.verbatim_text,
                node.parent_block_id, node.reading_order,
            )
        )
        ids.append(cursor.lastrowid)
    return ids


def delete_typed_nodes(conn: sqlite3.Connection, doc_id: str) -> None:
    conn.execute("DELETE FROM nodes WHERE doc_id = ?", (doc_id,))
    # node_embeddings cleared via ON DELETE CASCADE? vec0 doesn't support FKs;
    # do it explicitly:
    conn.execute(
        "DELETE FROM node_embeddings WHERE node_id NOT IN (SELECT id FROM nodes)"
    )
```

## Embedding the new nodes

Reuse `services/retrieval/embeddings.py::default_embedder()`. After `insert_typed_nodes` returns the IDs, embed each `verbatim_text` and insert into `node_embeddings`:

```python
def embed_and_index_nodes(
    conn: sqlite3.Connection,
    nodes: list[TypedNode],
    node_ids: list[int],
) -> None:
    embedder = default_embedder()
    # Only embed retrievable types — saves time + space
    retrievable = {"heading", "body", "list_item", "caption", "table_cell", "footnote", "equation"}
    payload = [
        (nid, n.verbatim_text)
        for nid, n in zip(node_ids, nodes)
        if n.node_type in retrievable
    ]
    if not payload:
        return
    vectors = embedder.embed_passages([text for _, text in payload])
    conn.executemany(
        "INSERT OR REPLACE INTO node_embeddings(node_id, embedding) VALUES (?, ?)",
        [(nid, _serialize(v)) for (nid, _), v in zip(payload, vectors)]
    )
```

`_serialize` follows the same convention as `services/retrieval/vector.py`.

## Orchestrator hookup

In [services/ingestion/orchestrator.py::ingest_document_record](/Users/madu/Desktop/Codex/services/ingestion/orchestrator.py), after the existing chunk ingest succeeds:

```python
if _docling_enabled_for(asset.extension):
    if not docling_parser.is_available():
        log_event(LOGGER, logging.WARNING, "docling_unavailable", doc_id=doc_id)
    else:
        try:
            doc = docling_parser.parse_document(asset.path)
            nodes = typed_walker.walk(doc)
            node_ids = persistence.insert_typed_nodes(conn, doc_id, nodes)
            persistence.embed_and_index_nodes(conn, nodes, node_ids)
            log_event(LOGGER, logging.INFO, "typed_nodes_indexed",
                      doc_id=doc_id, node_count=len(nodes))
        except Exception as exc:  # never fail the whole ingest if Docling chokes
            log_event(LOGGER, logging.ERROR, "docling_ingest_failed",
                      doc_id=doc_id, error=str(exc))
```

This is the critical safety: **the new path can never fail the existing path.** If Docling crashes on a weird PDF, the old chunks ingest still works, the user still gets retrieval (just on the old chunks).

## Tests to add

In `tests/`:

1. `test_typed_walker.py` — Docling not installed → walker raises typed error. Single-paragraph synthetic Docling doc → one body node. Two-section synthetic doc → heading_path correct.
2. `test_typed_nodes_persistence.py` — insert/select/delete round-trip. FTS triggers fire on insert and delete.
3. `test_docling_pdf_ingest.py` — fixture `tests/fixtures/single_column.pdf` and `tests/fixtures/two_column.pdf`. Assert reading order is monotonic and char_offsets are non-overlapping.
4. `test_docling_ingest_feature_flag.py` — flag off → no rows in `nodes`. Flag on, Docling unavailable → no rows + warning logged. Flag on, Docling available → rows present alongside `chunks`.
5. `test_db_migrations.py` — extend with `0016` migration round-trip.

## Acceptance criteria for the PR

1. `pytest tests/` passes with the flag off (no behavior change for existing tests).
2. `pytest tests/test_docling_pdf_ingest.py` passes with the flag on, assuming `pip install docling` succeeded.
3. Single-column PDF: every body paragraph in the source produces exactly one `body` node with correct `char_start`/`char_end` against the canonical text.
4. Two-column PDF: reading order is monotonic, no body node from column 2 has a `char_start` lower than any body node from column 1.
5. The PR adds zero new top-level failures to `script/demo-readiness.sh`.
6. Docling absence does not break the app — confirm by running tests in a venv without Docling installed.

## Rollout

1. Merge PR with both flags default off.
2. Set `INGEST_USE_DOCLING=true` in the founder's local env. Re-ingest 10 documents from `data/uploads/`.
3. Spot-check the `nodes` table — query a multi-column paper, confirm reading order looks right.
4. PR 2 (retrieval) ships next, reads from `nodes` behind its own flag for side-by-side comparison.

## Risks

1. **Docling install size and time.** First `pip install docling` pulls ~1.5GB of model weights. Document this in the README so the founder isn't surprised. Consider preloading in `script/build_and_run.sh` so first-launch isn't slow.
2. **Docling version drift.** The element-iteration API has changed across versions. Pin to a specific version in `requirements.txt`. When upgrading, run the test fixtures.
3. **OCR path on macOS.** Docling's default `easyocr` works but is slow and pulls another ~600MB. Apple Vision via `NativeBridge` is faster and free, but the wiring is non-trivial. Ship with easyocr in this PR; cut over in a follow-up.
4. **Char offset accuracy.** The walker's canonical text reconstruction must match exactly what the reader displays. If the reader uses `pypdf`-extracted text and the walker uses Docling-extracted text, the offsets won't align and citation chips will land in the wrong place. Either re-render the reader from the canonical text, or use Docling's source-coordinate provenance to compute offsets against the original. The spec in the parent doc assumes the canonical-text approach. Flag this for explicit testing in PR 2 (retrieval) when the citation flight starts using the new offsets.
