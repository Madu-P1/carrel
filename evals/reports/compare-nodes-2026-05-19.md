# T08 first-pass + reopen — side-by-side eval: `RETRIEVAL_USE_NODES` on vs off

**Outcome:** T08 **re-parked**. First pass discovered the primary-retrieval-dispatch ceiling, closed by T57 (PR #63, squash commit `fa20c2c0`). Reopen run with the wired dispatcher discovered a second ceiling: the eval's `_ingest_fixtures` calls `ingest_document_record(extracted_text=...)` without `storage_name`, so `_resolve_ingest_path` returns None and Docling silently skips (`docling_skipped_no_file`). The `nodes` table stays empty even with `INGEST_USE_DOCLING=true` + `INGEST_DOCLING_FORMATS=pdf,md,txt`. Re-parked behind **T58** (Phase 4.0 second precursor — wire eval fixture ingestion through the Docling path).

**Date:** 2026-05-19 (first pass) / 2026-05-20 (reopen). UTC run timestamps below.
**Suite:** smoke (14 cases).
**Mode:** full (canonical quality bar per `CLAUDE.md` §Benchmarks+budgets).
**Model:** `claude-sonnet-4-6`.
**Branches:**
- First pass: `feat/t08-eval-compare-nodes-2026-05-19` (PR #61, parked).
- Reopen: `feat/t08-reopen-non-vacuous-compare-2026-05-20` (this report).
**Raw reports (gitignored, local-only):**
- First-pass chunks-path: `evals/reports/_t08_nodes_off/2026-05-19T21-59-23.850960Z.{json,md}`.
- First-pass nodes-path (pre-T57): `evals/reports/_t08_nodes_on/2026-05-19T21-58-13.398251Z.{json,md}`.
- Reopen chunks-path (post-T57): `evals/reports/_t08_reopen_chunks/2026-05-20T00-22-42.496579Z.{json,md}`.
- Reopen nodes-path attempts (post-T57): `evals/reports/_t08_reopen_nodes/2026-05-20T00-23-20.088791Z.{json,md}` (without INGEST_DOCLING_FORMATS override) and `evals/reports/_t08_reopen_nodes_v2/2026-05-20T00-24-06.678926Z.{json,md}` (with `INGEST_DOCLING_FORMATS=pdf,md,txt`).

## Verdict

**REGRESSION on the nodes branch (vs chunks).** T08's acceptance ("node path must be equal or better on both `groundedness@8` and `quote_validity`") is violated: nodes path returns 0/14 (0.0%) on `groundedness@8` because retrieval is empty, and `quote_validity` is undefined (no citations attempted on any case). Per T08 guards, T08 stays `blocked` until T58 lands. The regression is **architectural, not algorithmic**: the typed-node retrieval path correctly returns empty when the nodes tables are empty (CLAUDE.md "no silent fallbacks"); the empty table is the bug, not the dispatcher.

## Reopen run side-by-side (post-T57 dispatcher, with `INGEST_USE_DOCLING=true INGEST_DOCLING_FORMATS=pdf,md,txt` on nodes path)

| Metric | Chunks (default) | Nodes (T57 + Docling envs) | Verdict |
|---|---|---|---|
| **groundedness@8** | **12/14 (85.71%)** | **0/14 (0.00%)** | **regression (-85.71pp)** |
| **quote_validity** | **1.0000 (25/25)** | **None (0/0)** | regression (undefined) |
| citation_precision | 0.8571 | 0.0000 | regression |
| citation_recall | 0.8571 | 0.0000 | regression |
| fallback_rate | 0/14 (0%) | 14/14 (100%) | every case fails closed |
| scope_fallback_rate | 0/14 (0%) | 0/14 (0%) | even fallback path empty |
| p50 latency | 4.15 s | <0.01 s | nodes path returns instantly (no LLM call) |
| p95 latency | 6.41 s | <0.01 s | same |
| total cited claims | 25 | 0 | nodes path emits zero claims |

**Chunks branch is unchanged vs first-pass (`groundedness@8 = 12/14`, `quote_validity = 1.00`)** — confirms T57's dispatcher wiring did not regress the legacy path. The +0.7s latency drift is LLM-side noise.

## Why the nodes branch is empty (the second ceiling)

The eval ingests fixtures via `evals/run_evals.py::_ingest_fixtures` which calls `services/ingestion::ingest_document_record(conn=conn, filename=..., file_type=..., extracted_text=text, page_count=1, subject_name=...)`. No `storage_name` is passed, so when `services/ingestion/orchestrator.py::_resolve_ingest_path(filename, storage_name=None)` runs, it returns None and the Docling branch logs `docling_skipped_no_file` (see line 336 of `orchestrator.py`) for every fixture. The chunks branch still populates because the legacy chunker operates on `extracted_text` directly; the Docling branch requires a file on disk under `db.UPLOAD_DIR`.

Setting `INGEST_USE_DOCLING=true` alone is not sufficient. `INGEST_DOCLING_FORMATS=pdf,md,txt` is not sufficient either. Both runs land at `docling_skipped_no_file` for every case.

## T58 — the second precursor task

`AUTONOMOUS_WORK_PLAN.md` now lists **T58 (Phase 4.0 second precursor)** at the end of the queue. T58's scope:

1. Extend `evals/run_evals.py::_ingest_fixtures` to copy each fixture file from `evals/fixtures/<path>` to `db.UPLOAD_DIR / storage_name` BEFORE calling `ingest_document_record`, and pass the `storage_name` so `_resolve_ingest_path` succeeds.
2. Ensure the fixture file-format set (currently `.md` + `.txt`) is supported by the Docling typed-node walker. `.md` and `.txt` round-tripped through Docling MUST produce valid `nodes` rows with `verbatim_text` matching the fixture content. If Docling can't parse `.md`/`.txt`, T58 either:
   - Adds a Docling-format fixture to `evals/fixtures/` (a small `.pdf`) and a smoke case keyed to it.
   - Or files a third precursor for Docling format coverage (T10 also touches this).
3. The chunks-path eval invocation MUST still work (default env) — the storage_name addition is additive, not destructive. Verify with a chunks-baseline run post-T58.
4. T08 reopens again (`Status: pending`) after T58 lands.

T08's `Deps` updated to `T07, T57, T58`.

## What this means for Phase 4 ordering

T10 ("extend Docling format coverage to 5 formats") currently has `Deps: T08`. With T08 re-parked, T10 stays blocked. The right move (operator decision) is to retarget T10 onto `T57` (or `T58`) so Phase 4's format-coverage work can proceed independently of the side-by-side eval. The work plan's circular sequencing is an artifact of the original plan not anticipating T08's diagnostic discovery process; the operator's review queue will see the T58 entry and the T10-dep-retargeting suggestion.

## Honest reporting (reiterated)

This is the third diagnostic pass on T08. Each pass closed a layer of the architectural ceiling:
1. First pass (PR #61, parked): identified primary-retrieval dispatcher gap.
2. T57 (PR #63, shipped): wired the dispatcher.
3. Reopen (PR #64, re-parked): identified eval-fixture-Docling-path gap.

T58 (in flight) closes the eval-fixture-Docling-path gap by adding the storage_name wiring + a PDF fixture + a node_fts isolated-runtime FTS5 fix. After T58, only one ceiling remains: the Docling parser at `services/ingestion/docling_parser.py` only registers `InputFormat.PDF`, so the 14 `.md` smoke fixtures still skip Docling under T58's wiring. T10 ("extend Docling format coverage to 5 formats") owns that final layer. T08's full reopen will work after T58 AND T10 are both landed.

### T58 measured outcome (proof that the wired path works)

With T58 in place (`INGEST_USE_DOCLING=true`, default `INGEST_DOCLING_FORMATS=pdf`):
- **Chunks branch (default env):** `groundedness@8 = 13/15 (86.67%)`, `quote_validity = 32/32 (1.0000)` — baseline preserved and slightly improved (new PDF fixture also passes on the chunks branch via `PyPDF2`-driven pre-extraction).
- **Nodes branch (RETRIEVAL_USE_NODES=true + INGEST_USE_DOCLING=true):** `groundedness@8 = 1/15 (6.67%)`, `quote_validity = 24/24 (1.0000)`. The single `grnd=1` case is `biology-mitosis-pdf-001` against the new `cell_division.pdf` fixture — Docling produced 2 nodes from the PDF and the typed-node retrieval found them. The other 14 cases register `grnd=0` because their expected fixtures are `.md`, which the Docling parser doesn't handle yet (T10).
- **Quote-validity = 1.0 on the nodes branch despite low groundedness:** the typed-node retrieval surfaces the PDF's nodes for biology questions across cases (BM25 + vector match on biology terms). The LLM cites the PDF's verbatim text correctly, but the case's expected ids belong to the `.md` fixture's chunks (a different id-space). Once T10 adds Docling parsing for `.md`, the 14 `.md` fixtures will populate matching nodes and `groundedness@8` rises accordingly.

Each precursor is a focused, shippable unit. The repeated re-parking is not failure — it's the discovery process working as intended (CLAUDE.md "no silent fallbacks" applied to eval reports: surface the ceiling rather than ship a false 100). T08 stays parked behind T58 + T10. The chunks-path baseline `groundedness@8 = 12/14, quote_validity = 1.00` is preserved across all diagnostic passes (improves to 13/15 with the T58 PDF fixture); T57's dispatcher and T58's storage_name wiring are both verified non-regressive.
