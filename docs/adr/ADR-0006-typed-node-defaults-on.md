# ADR-0006: Typed-Node Ingest + Retrieval Default-On for Carrel V2

- Status: Accepted
- Date: 2026-05-26

## Context

Two long-lived feature flags have gated the typed-node pipeline since
PRs 1-4 of the typed-ingest series:

- `INGEST_USE_DOCLING` (master switch for typed-node ingestion via
  Docling → `services.ingestion.typed_walker` → `nodes` table)
- `RETRIEVAL_USE_NODES` (top-level switch for typed-node retrieval
  via `services.retrieval.typed_hybrid` → hydrated `nodes` rows)

Both defaulted to `false` so deploying any single PR never changed
user-facing behavior. The legacy chunks pipeline (PyPDF2 →
`services.extraction.parsers.pdf` heuristics → `chunks` table) was
the default retrieval surface.

In the May 2026 V2 strategic pivot session
(`/Users/madu/.gstack/projects/Codex/madu-main-design-20260522-015141.md`),
Carrel was repositioned as an independent AI verification layer. The
litigation pre-flight wedge requires that every cited quote can be
traced to a known semantic unit type (prose body vs. heading vs.
table cell vs. equation vs. caption) so the verification surface can
render source-type provenance and a future strict mode can refuse
to ground a claim on non-prose.

Audit of the live UNIFLOW PDF on 2026-05-26 confirmed the legacy
chunks pipeline produces heading-skeleton chunks for slide-deck
PDFs — heading-after-heading concatenated with body content because
PyPDF2 lacks structural typing and the chunker's heuristic
heading-detection mis-classifies short visually-distinct lines.
Docling's typed-node output for the same document was healthy (52
heading nodes, 39 body nodes, 21 list items, each at correct
type).

The typed-node infrastructure shipped in earlier PRs has been live
behind the off-by-default flags for weeks. The dual-path retrieval
contract (`services.tutor._hydrate_node_context` dispatching on
`retrieval_use_nodes_enabled()`) is unit-tested for both branches.
The Carrel V2 citation gate (`citation_non_prose_drop_count`,
landed 2026-05-26) and chip-level source-type badge depend on the
typed `node_type` field that only the nodes path populates with
real values; the chunks path stringly defaults to `"body"` since
chunk text concatenates multiple nodes without char-range
provenance.

## Decision

Flip both defaults to `true`:

- `INGEST_USE_DOCLING` default: `"false"` → `"true"`
  (`services/ingestion/orchestrator.py::_docling_enabled_for`).
- `RETRIEVAL_USE_NODES` default: `"false"` → `"true"`
  (`services/retrieval/typed_hybrid.py::retrieval_use_nodes_enabled`).

Both env vars remain readable so an explicit `=false` opts a single
install back to the legacy pipeline for the two exit scenarios
listed below.

## Why This Path

- The typed-node pipeline IS the verification-credibility pipeline.
  V2's value proposition collapses if the verifier cannot tell a
  diagram label from a sentence; the legacy chunks pipeline loses
  that distinction at parse time and cannot recover it downstream.
- Both pipelines still run side-by-side at ingestion time (the
  legacy chunks write is unchanged), so a doc that fails Docling
  parsing remains queryable via the chunks fallback path. Graceful
  degradation handled in
  `services.ingestion.orchestrator._docling_enabled_for` (Docling
  import absence) and `_hydrate_node_context` (no node rows for the
  cited ids).
- The off-default was a deploy-safety measure for the PR series,
  not a permanent product decision. The series is complete.

## Exit Scenarios (When To Set `=false`)

1. Operator is on a machine where the ~1-2 GB Docling install is
   unwanted (low-storage device, air-gapped builds without the
   wheel mirror). Set `INGEST_USE_DOCLING=false`; new uploads still
   index into `chunks` for retrieval. Set
   `RETRIEVAL_USE_NODES=false` too so queries hit the populated
   table.
2. Operator has a pre-V2 corpus where every doc was ingested
   without Docling (no rows in `nodes` for those doc_ids). New
   queries against those docs return empty under the nodes path
   (`_hydrate_from_nodes` does not silently fall back to chunks,
   per CLAUDE.md "no silent AI fallbacks"). Either re-ingest via
   `script/reingest_all.py` (recommended) or set
   `RETRIEVAL_USE_NODES=false` until the re-ingest completes.

## Quality Gate

The full-mode smoke eval comparison run on the flip commit must
preserve the CLAUDE.md thresholds on the nodes path:

- `groundedness@8 >= 0.7`
- `quote_validity >= 0.95`

Comparison report committed under `evals/reports/compare-flip-*.md`
showing nodes (new default) vs chunks (`=false` opt-out) side by
side. A regression on either threshold blocks the flip.

## Non-Goals

- Removing the legacy chunks pipeline. Both pipelines remain
  available; the chunks path is just no longer the default.
- Removing the env vars. They stay supported as the documented
  exit scenarios above.
- Forcing operators to re-ingest existing corpora. The chunks-only
  fallback covers pre-V2 docs until they are re-ingested via the
  reingest_all script on the operator's schedule.

## Test-Surface Changes

Several test classes that explicitly exercised the legacy chunks
path under the off-by-default contract added env pins to keep their
intent explicit under the new default:

- `tests/test_tutor_grounded.py::GroundedTutorTests` setUp pins
  `RETRIEVAL_USE_NODES=false` (class-wide; tests that need it on
  still wrap their own `mock.patch.dict` block).
- `tests/test_tutor_grounded.py::HydrateCitedContextsTests::test_chunks_path_resolves_uuid_chunk_ids_to_hydrated_contexts`
  pins `RETRIEVAL_USE_NODES=false`.
- `tests/test_retrieval_typed_hybrid.py::RetrievalUseNodesFlagTests::test_flag_defaults_on_when_unset`
  inverted from default-off.
- `tests/test_evals_runner.py::EvalsRunnerTests::test_full_mode_computes_metrics_from_stub_router`
  and `::test_structural_citation_count_increments_on_chunks_branch`
  pin `RETRIEVAL_USE_NODES=false` and `INGEST_USE_DOCLING=false`
  so the chunks-branch wiring under audit runs against a
  single-id-space expected set.
