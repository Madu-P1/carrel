# Ask pipeline — algorithm spec

> **Status:** locked v1, 2026-05-08. Audited against the live repo on the same day.
> **Owner:** Chimdindu Madubuike.
> **Replaces:** today's paragraph-chunk + flat-retrieval pipeline.
>
> **What already exists in the repo and is being extended, not replaced:**
> - `services/retrieval/{embeddings.py,fts.py,vector.py,hybrid.py,backfill.py}` — RRF fusion (k=60) is already implemented in `search_hybrid()`. The spec adds node-type filtering and cross-encoder re-rank on top.
> - `chunks` table + `chunks_fts` (FTS5, migration `0006`) + `chunks_vec` (vec0 float[384], migration `0007`). The spec adds `nodes`, `node_fts`, `node_embeddings` alongside; `chunks` stays for one release for backfill.
> - `BAAI/bge-small-en-v1.5` (`services/retrieval/embeddings.py:16`) — same model, no change.
> - `services/extraction/quality.py` — partial node-role classification today (`classify_pdf_role`, `is_footer_or_noise`, `is_formula_text`, `is_outline_text`, `is_bullet_like`). Reused as the fallback when Docling isn't available; Docling's structured output supersedes it when it is.
> - `services/extraction/parsers/pdf.py` already calls into `NativeBridge` (Swift). Apple Vision OCR path is plausibly already wired; verify before duplicating.

## Goal

Given a user question and a library of source documents, return the spans of source text that answer the question, with offsets sharp enough for the citation chip to land on the exact passage.

## Non-goals (v1)

- No answer synthesis on Free tier. The retrieved cards are the answer.
- No bundled local LLM. No Ollama dependency. Free tier ships with zero LLM weights.
- No multi-document synthesis. Each card cites one source.
- No image-content retrieval (figures, diagrams, photos). Captions only.

## Two invariants (cannot be violated)

1. **Every claim or card emitted to the user points to a `chunk_id` that was in the retrieved set.**
2. **Every quoted substring in the UI exists verbatim in the cited chunk's `verbatim_text`.** Whitespace-normalized exact substring match.

If either invariant fails at validation time, the answer is rejected and the user sees "I couldn't find a verifiable answer in your library" instead of a fabrication.

## Data model

### `nodes` table

One row per leaf in the document tree.

```sql
CREATE TABLE nodes (
  id              INTEGER PRIMARY KEY,
  doc_id          INTEGER NOT NULL,
  node_type       TEXT NOT NULL,          -- heading|body|list_item|caption|table_cell|equation|footnote|header|footer
  heading_path    TEXT NOT NULL,          -- "Chapter 3 > Photosynthesis > Light reactions"
  page            INTEGER,                -- 1-indexed page number
  char_start      INTEGER NOT NULL,       -- byte offset in source's normalized text
  char_end        INTEGER NOT NULL,
  verbatim_text   TEXT NOT NULL,          -- exact substring, no normalization
  parent_block_id INTEGER,                -- for table cells grouped under a table_block
  reading_order   INTEGER NOT NULL        -- monotonic per doc_id, resolves multi-column
);

CREATE INDEX idx_nodes_doc ON nodes(doc_id);
CREATE INDEX idx_nodes_type ON nodes(node_type);
```

### `node_embeddings` virtual table

```sql
CREATE VIRTUAL TABLE node_embeddings USING vec0(
  node_id INTEGER PRIMARY KEY,
  embedding FLOAT[384]                    -- bge-small-en-v1.5
);
```

### `node_fts` for BM25

```sql
CREATE VIRTUAL TABLE node_fts USING fts5(
  verbatim_text,
  heading_path,
  content='nodes',
  content_rowid='id'
);
```

## Stage 1 — Ingest

**Input:** raw file bytes + format hint.
**Output:** rows into `nodes`, `node_embeddings`, `node_fts`.

### Pipeline

1. **Format detect.** PDF / DOCX / EPUB / HTML / MD / TXT. Reject anything else with a typed error.
2. **Parse to `DoclingDocument`.** Use `docling.document_converter.DocumentConverter`. For PDF, enable `do_ocr=True` with `ocr_engine="apple_vision"` on macOS (CPU, free, fast).
3. **Walk the Docling tree** in reading order, emit one `nodes` row per leaf. Map Docling element types to our seven `node_type` values:

   | Docling element | Our type | Retrievable? |
   |---|---|---|
   | `TextItem(label=text)` | `body` | yes |
   | `SectionHeaderItem` | `heading` | yes (boost) |
   | `ListItem` | `list_item` | yes |
   | `CaptionItem` | `caption` | only if query mentions figure/table/diagram |
   | `TableItem` cells | `table_cell` (grouped to `table_block`) | yes if query mentions table/data |
   | `FormulaItem` | `equation` | only if query mentions formula/equation |
   | `FootnoteItem` | `footnote` | yes (lower boost) |
   | `PageHeaderItem` / `PageFooterItem` | `header` / `footer` | **no** (excluded from retrieval) |

4. **Compute `heading_path`.** Stack of section headings ancestors, joined with " > ".
5. **Compute `char_start` / `char_end`** against a normalized canonical text per doc (NFC unicode, line endings normalized to \n). These offsets are what the reader uses to scroll-and-highlight. Test on multi-column papers — Docling's reading order should give monotonic offsets but verify.
6. **Embed each retrievable node** with `fastembed` `BAAI/bge-small-en-v1.5` (384-dim, ~120MB model, CPU-only, already in your stack).
7. **Insert into `node_fts`** for BM25.

### Performance target

A 30-page PDF should ingest in under 15 seconds on M-series, under 30s on Intel. If it doesn't, profile Docling's OCR step first — that's almost always the bottleneck.

## Stage 2 — Retrieve

**Function signature:**

```python
def retrieve(
    query: str,
    library_doc_ids: list[int],
    k: int = 5,
) -> list[RetrievedChunk]:
    ...
```

`RetrievedChunk` shape:

```python
@dataclass
class RetrievedChunk:
    node_id: int
    doc_id: int
    page: int | None
    heading_path: str
    verbatim_text: str
    char_start: int
    char_end: int
    score: float            # final fused + reranked score
```

### Algorithm

1. **Filter by node_type.** Default: `body, list_item, heading`. Expand based on query keywords:
   - "table", "row", "column", "data" → add `table_cell`
   - "figure", "diagram", "chart", "image" → add `caption`
   - "formula", "equation" → add `equation`
   - "footnote", "citation", "reference" → add `footnote`

2. **BM25 candidates.** Top 50 from `node_fts` with `verbatim_text MATCH ?`.

3. **Vector candidates.** Top 50 from `node_embeddings` via cosine, embedding the query with the same `bge-small-en-v1.5`.

4. **Reciprocal Rank Fusion.** For each node appearing in either list:

   ```
   rrf_score(node) = sum over lists L: 1 / (60 + rank(node, L))
   ```

   `60` is the canonical RRF constant. Take top 50 by `rrf_score`.

5. **Cross-encoder re-rank.** Run `BAAI/bge-reranker-v2-m3` (568M params, CPU at ~150ms for 50 pairs) over `(query, verbatim_text)` for each of the top 50. Emit a relevance score in `[0,1]`.

6. **Final score:** `0.7 * cross_encoder_score + 0.3 * rrf_score_normalized`. Take top `k`.

7. **Return.** Each retrieved chunk is paired with its `heading_path` so the UI can show "Found in: Chapter 3 > Photosynthesis > Light reactions" above the verbatim quote.

### Latency budget

Target: under 600ms p50 from query string to ranked chunks on a 50-document library.

| Step | Budget |
|---|---|
| Query embed | 30ms |
| BM25 (FTS5) | 50ms |
| Vector kNN (sqlite-vec, 50k vectors) | 80ms |
| RRF | 5ms |
| Cross-encoder re-rank (top 50) | 400ms |
| Hydrate + return | 30ms |

If you blow past 600ms on a real corpus, drop re-rank top-50 → top-30. Don't drop the re-rank entirely.

## Stage 3 — Citation grounding

The retrieved chunk's `(doc_id, page, char_start, char_end)` is the citation's complete identity. The citation chip in the UI is just a serialized pointer.

**Click flow:**
1. User clicks chip with `node_id=N`.
2. UI fetches `nodes[N]`, opens the source's reader pane to `page`.
3. PDF renderer scrolls to page, then maps `(char_start, char_end)` against the rendered text layer to compute a DOM range.
4. Highlight is drawn for one beat, then fades.

**Test case that must pass:** open a real two-column academic paper. Click a chip on a body node from column 2 of page 5. The highlight must land on the column-2 span, not column-1. This is the test that exposes reading-order bugs.

## Stage 4 — Render

### Free tier — retrieval-only

UI: a vertical list of 3-5 `Card` components. Each card:

```
┌─────────────────────────────────────────────┐
│ Chapter 3 > Photosynthesis > Light reactions │  ← heading_path, mono uppercase, --text-3
│                                              │
│ "Photosystem II splits water molecules,      │  ← verbatim_text, serif italic
│  releasing oxygen and protons into the       │
│  thylakoid lumen..."                         │
│                                              │
│ Lehninger, p. 472                  [Open →]  │  ← doc + page, button to source
└─────────────────────────────────────────────┘
```

No synthesized prose. The cards ARE the answer. The eyebrow on the result list reads `MOST LIKELY ANSWERS IN YOUR LIBRARY` so the user's expectation is set.

### Pro tier — with synthesis

Same retrieval. Then call Claude (Haiku 4.5) with strict tool-use:

```python
tool = {
  "name": "answer_with_citations",
  "input_schema": {
    "type": "object",
    "required": ["claims"],
    "properties": {
      "claims": {
        "type": "array",
        "items": {
          "type": "object",
          "required": ["text", "citation_node_id"],
          "properties": {
            "text": {"type": "string"},
            "citation_node_id": {"type": "integer"}
          }
        }
      },
      "unsupported": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Parts of the question that the retrieved chunks don't address"
      }
    }
  }
}
```

The model must emit each claim as `{text, citation_node_id}`. The system prompt forbids the model from emitting any claim where `citation_node_id` is not in the retrieved set. Validators enforce this regardless of what the model says.

## Validators (post-synthesis, both tiers)

```python
def validate_answer(
    answer: AnswerEnvelope,
    retrieved: list[RetrievedChunk]
) -> ValidationResult:
    retrieved_ids = {c.node_id for c in retrieved}

    # Invariant 1: every citation is in the retrieved set
    for claim in answer.claims:
        if claim.citation_node_id not in retrieved_ids:
            return ValidationResult.fail(
                f"Citation {claim.citation_node_id} not in retrieved set"
            )

    # Invariant 2: every quoted span is verbatim in its cited chunk
    chunk_by_id = {c.node_id: c for c in retrieved}
    for claim in answer.claims:
        chunk = chunk_by_id[claim.citation_node_id]
        for quoted_span in extract_quoted_spans(claim.text):
            if normalize_ws(quoted_span) not in normalize_ws(chunk.verbatim_text):
                return ValidationResult.fail(
                    f"Quoted span not verbatim in chunk {chunk.node_id}"
                )

    return ValidationResult.ok()
```

If validation fails, the user sees a UI fallback: the retrieved cards (Free-tier UI) plus a banner "We couldn't synthesize a verified answer for this question. Here are the most relevant passages."

## What changes vs. current code

| Surface | Current (verified) | Change |
|---|---|---|
| Ingest | `services/ingestion/orchestrator.py` + `services/ingestion/concepts.py::chunk_text()` (paragraph-aware, 1200-char chunks). PDF parsing in `services/extraction/parsers/pdf.py` with role classification in `services/extraction/quality.py`. | Add Docling as a new parser path that produces `ExtractedElement` rows tagged with our seven node types. Keep the existing `quality.py` rules as the fallback when Docling isn't available or the user disables it. New module: `services/ingestion/typed_walker.py`. |
| DB schema | `chunks` (TEXT id, content, section, page_num, chunk_index, token_count, embedding_id) + `chunks_fts` (FTS5) + `chunks_vec` (vec0 float[384]). Migrations through `0015_calendar_manual_feed_kind.sql`. | New migration `0016_nodes_typed.sql`: add `nodes`, `node_embeddings`, `node_fts`. Old `chunks*` tables stay for one release behind feature flag, then drop in a follow-up migration. |
| Retrieval | `services/retrieval/hybrid.py::search_hybrid()` already does RRF (k=60) over BM25 + vector. | Add `services/retrieval/rerank.py` with a `bge-reranker-v2-m3` cross-encoder. Extend `search_hybrid()` signature with `node_types: set[str] | None` filter. |
| Ask renderer | Single answer view with chips. | Two paths: Free renders the retrieval cards directly (no synthesis); Pro adds Claude tool-use synthesis with the validated claim shape. UI tier flag drives which path runs. |
| Validators | Verbatim-quote check exists on intel anchors only (per CLAUDE.md). | Extend to every emitted claim and every quoted span in the synthesized answer. New module: `services/retrieval/validators.py`. |

## Migration plan

1. Land Docling ingest behind a feature flag `ingest.use_docling = false` (default). Run side-by-side with current ingestion on the next 10 documents the user adds; diff the retrieval quality.
2. Land cross-encoder re-rank behind `retrieval.use_reranker = false`. Compare retrieval quality with a small fixed query set (10-20 questions, manually graded).
3. When both feature flags pass quality bars, flip them on for new documents. Old documents stay on the old path until they're re-ingested.
4. Re-ingest all documents on a one-time migration. Drop `chunks` table after the migration completes successfully.

## Open questions

1. Docling's Apple Vision OCR integration on macOS — need to verify it actually works without an Apple Developer signing context. If it requires entitlements, the bundled-app version (signed) gets it but `python -m uvicorn` for backend dev mode might not.
2. Cross-encoder model: 568M params is a 1.1GB download on first run. Acceptable as a one-time fastembed-like cache, but call this out in onboarding.
3. The Free-tier UX needs design. The current Ask view assumes a synthesized answer. We need a card-list mode. New design pass needed.

## Acceptance test (must pass before this ships)

A 50-document library across mixed formats (PDFs both born-digital and scanned, DOCX, EPUB, slides). 30 hand-graded questions where the correct answer is known and the correct chunk is known.

- **Recall@5 ≥ 0.85.** The right chunk appears in the top 5 retrieved 85%+ of the time.
- **Citation precision = 1.0.** When a citation is shown, the click lands on the right passage 100% of the time. (Anything below 1.0 melts the trust pitch.)
- **p50 latency under 600ms.** Across the 30 test questions on the 50-doc library.

If any of those three numbers fails, the algorithm doesn't ship.
