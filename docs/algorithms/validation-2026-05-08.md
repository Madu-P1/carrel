# Ask-pipeline validation — 2026-05-08

> First side-by-side measurement of the typed-node retrieval path from
> PRs 1+2+3 against the legacy chunks path. Recorded so future readers
> can see what the data actually said when the defaults in
> `services/retrieval/rerank.py` and `typed_hybrid.py` were chosen.

## Setup

- Library: 5 PDFs ingested via `script/validate_typed_retrieval.py`.
  Mix of finance textbook chapters (Berk/DeMarzo Chapter 8 + 10),
  international tax (Uniflow LW22), statistics (multiple linear
  regression slides), and the founder's CV.
- Indexed: 291 legacy chunks + 1,177 typed nodes after the Docling
  ingest path completed for all five.
- Queries: five hand-written, library-specific questions where the
  expected answer is in the library:
  1. How is HomeNet's free cash flow calculated?
  2. What is the formula for net working capital?
  3. Define material permanent establishment
  4. What is the reverse charge method for VAT?
  5. How is multiple linear regression specified?

Three retrieval paths were measured per query:
- **A** — legacy chunks via `services.retrieval.hybrid::search_hybrid`
- **B** — typed-node hybrid via `search_typed_hybrid` without rerank
- **C** — typed-node hybrid + cross-encoder rerank

## Quality verdict

| Query | A (chunks) | B (nodes) | C (nodes + bge-base) | C (nodes + MiniLM-L-12) |
|---|---|---|---|---|
| Q1 HomeNet FCF | substantive paragraphs | three section titles | 1 substantive list_item | 1 substantive **body** |
| Q2 NWC formula | formula buried in para | formula at #3 (body) | formula at #2 (body) | formula at #2 (body) |
| Q3 Material PE | canonical comparison row | wrong section (Corp Tax Residency) | same wrong answer | same wrong answer |
| Q4 Reverse-charge VAT | generic VAT page | right section, mostly headings | right section, body + heading mix | right section, body + heading mix |
| Q5 LinReg spec | section titles + objective | heading + body fragment | three real body lines | heading + body + heading |

Read across:
- Without rerank, the typed-node path is biased toward heading text —
  short strings outscore body paragraphs because BM25 favors low
  document length and vector similarity is high on thematic words.
- With rerank, the cross-encoder breaks the heading bias by reading
  the (query, document) pair jointly. Body content with substance
  surfaces where it should.
- The two reranker models we tested — `BAAI/bge-reranker-base`
  (1.04 GB) and `Xenova/ms-marco-MiniLM-L-12-v2` (120 MB) — produced
  near-identical rankings on Q1–Q4 and a slight regression on Q5
  (the most technical query) for MiniLM. The 5x latency win at
  near-equivalent quality is the trade we ship.

## Latency

Per-query latency for the rerank path, measured on M-series CPU:

| Query | bge-reranker-base | MiniLM-L-12-v2 |
|---|---:|---:|
| Q1 (first call, includes ONNX init) | 28.8 s | 8.3 s |
| Q2 | 2.2 s | 0.78 s |
| Q3 | 10.2 s | 1.95 s |
| Q4 | 31.3 s | 9.3 s |
| Q5 | 4.1 s | 0.36 s |

The parent algorithm spec budgets 400 ms for rerank top-50 — neither
model hits that budget today. PR 3.5 dropped `rerank_top` from 50 to
20, which on the same library halves the cost (fewer pairs scored).
Hitting the spec budget will require:
- Lazy-warming the ONNX session at app boot so first-query latency
  doesn't include init.
- Replacing `rerank_top=20` with a confidence-driven cutoff.
- Possibly an `onnxruntime` provider flag for Apple's Neural Engine
  (CoreML EP) — fastembed exposes `providers=` on the constructor.

## Known gap — Q3 content loss

For "Define material permanent establishment", the canonical answer
lives in the LW22 PDF as a side-by-side comparison row:

> Material PE / Personal PE — Based on physical presence like an
> office or factory / Based on the activities of a person…

The legacy chunks path returns this row verbatim. The typed-node path
returns "Corporate Tax Residency" instead — an adjacent body block.
The "Material PE" content is missing or fragmented in the `nodes`
table.

Hypotheses worth checking in a follow-up PR (does NOT block PR 4):

1. **Walker dropped table cells.** If Docling parsed the comparison as
   a `table`, the walker today emits one node per cell with text
   pulled from `element.text`, which may be empty. Look for table-
   structured nodes with `verbatim_text=""` — those got skipped.
2. **Layout-not-table.** If the slide rendered the comparison as two
   text blocks side by side rather than a table, Docling may have
   merged them into one body node whose verbatim text didn't include
   the "material" keyword.
3. **OCR fallback.** The slide may be raster, and rapidocr's English
   pass may have low confidence on the "Material PE" labels.

Diagnostic query for whoever picks this up:
```sql
SELECT id, node_type, page, char_start, char_end,
       substr(verbatim_text, 1, 80) AS preview
FROM nodes
WHERE doc_id = (
    SELECT id FROM documents WHERE filename LIKE '%LW22%' LIMIT 1
)
  AND (verbatim_text LIKE '%Material%' OR verbatim_text LIKE '%PE%')
ORDER BY reading_order;
```

## Decisions ratified by this validation

1. **Default reranker:** `Xenova/ms-marco-MiniLM-L-12-v2` (was
   `BAAI/bge-reranker-base`). Configurable via `RETRIEVAL_RERANKER_MODEL`.
2. **Default `rerank_top`:** 20 (was 50).
3. **Q3 content loss:** known gap. Not blocking PR 4, tracked in this doc.
4. **Latency budget:** still over spec on most queries. Investigate
   ONNX session warming + CoreML provider in a follow-up.
5. **Heading-bias problem:** real but partially fixed by rerank. PR 4's
   card UI surfaces `heading_path` as the eyebrow above the body, so
   headings stop competing for the answer slot in the user-visible UX.
