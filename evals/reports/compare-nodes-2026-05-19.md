# T08 first-pass — side-by-side eval: `RETRIEVAL_USE_NODES` on vs off

**Outcome:** T08 **parked**. The first-pass run produced identical metrics on both flag values, but the equality is **architectural artifact, not signal**. T08 reopens after **T57** (Phase 4.0 precursor — wire primary-retrieval dispatch + eval-harness id-space dispatch) lands.

**Date:** 2026-05-19 (UTC run timestamps below).
**Suite:** smoke (14 cases).
**Mode:** full (canonical quality bar per `CLAUDE.md` §Benchmarks+budgets; smoke mode is pre-existing broken — FTS5 conjunctive interrogative-token MATCH returns 0/14 groundedness, and `quote_validity` isn't computed in smoke mode at all per `_aggregate` short-circuit).
**Model:** `claude-sonnet-4-6` on both runs.
**Branch:** `feat/t08-eval-compare-nodes-2026-05-19` (PR #61).
**Raw reports:**
- USE_NODES=true → `evals/reports/_t08_nodes_on/2026-05-19T21-58-13.398251Z.{json,md}` (gitignored, local-only)
- USE_NODES=false → `evals/reports/_t08_nodes_off/2026-05-19T21-59-23.850960Z.{json,md}` (gitignored, local-only)

## Why the result is vacuous (the architectural ceiling)

Three coupled pieces conspire to make the eval blind to `RETRIEVAL_USE_NODES`:

1. **Primary retrieval is not flag-aware.** `services/tutor.py::grounded_tutor_response` calls `services.retrieval.search_hybrid` unconditionally at the two primary retrieval sites (~`:1228` and `:1310`), plus `grounded_citations` (~`:1196`). `search_hybrid` is the legacy chunks-based hybrid (queries `chunks_fts` + `chunks_vec`). The flag is read only at two downstream sites:
   - `_fallback_contexts_from_scope` (line 744) — dispatches `_fallback_contexts_from_scope_nodes` vs `_fallback_contexts_from_scope_chunks`. **Fires only when primary retrieval returns empty.** `fallback_rate = 0` and `scope_fallback_rate = 0` on both branches across all 14 cases, so this dispatch never executes.
   - `_hydrate_cited_contexts` (line 933) — dispatches `_hydrate_cited_contexts_nodes` vs `_hydrate_cited_contexts_chunks`. **Only called from `grounded_tutor_envelope`** (the route-handler wrapper), not from `grounded_tutor_response`. The eval calls `grounded_tutor_response` directly, so this dispatch is bypassed entirely.
2. **Typed-node ingestion is gated by `INGEST_USE_DOCLING` (default false).** Even if the dispatch is wired, the eval's isolated DB never populates the `nodes` / `node_fts` / `node_embeddings` tables. A flag-on run against an empty `nodes` table would correctly return empty primary hits + empty scope fallback (per CLAUDE.md "no silent fallbacks") and refuse every case — a regression, not a divergence.
3. **The eval harness speaks only the chunks id-space.** `evals/run_evals.py::_resolve_expected_chunks` collects str-UUID `chunks.id`s. `run_case` extracts `retrieved_chunk_ids = [hit.chunk_id for hit in hits]`. `quote_validity` is computed by `SELECT content FROM chunks WHERE id = ?`. There is no parallel `FROM nodes` path. If the nodes path ever surfaces `RetrievedNode` hits (int `node_id`), the harness either crashes or grades them as zero.

The first-pass run produces identical numbers because, by construction, both flag values walk the same chunks-based code path at every measurement surface the eval touches.

## Measured (vacuous) numbers — first-pass

| Metric | USE_NODES=true | USE_NODES=false | Delta |
|---|---|---|---|
| **groundedness@8** | **12/14 (85.71%)** | **12/14 (85.71%)** | **0** |
| **quote_validity** | **29/29 (1.0000)** | **26/26 (1.0000)** | **0** |
| citation_precision | 0.8571 | 0.8571 | 0 |
| citation_recall | 0.8571 | 0.8571 | 0 |
| citation_drop_rate | 0/29 (0%) | 0/26 (0%) | 0 |
| citation_repair_rate | 2/29 (6.9%) | 1/26 (3.9%) | +1 repair |
| fallback_rate | 0/14 (0%) | 0/14 (0%) | 0 |
| scope_fallback_rate | 0/14 (0%) | 0/14 (0%) | 0 |
| p50 latency | 3.43 s | 3.42 s | +0.01 s |
| p95 latency | 6.03 s | 5.74 s | +0.29 s |
| total cited claims | 29 | 26 | +3 (LLM jitter) |

The retrieval-side metrics are identical to the basis-point. The citation-count delta (29 vs 26) and small latency drift come from LLM non-determinism across two independent grounded-answer calls, not from flag-induced retrieval divergence. Both runs use identical retrieval (`search_hybrid`); the LLM happened to emit slightly different numbers of claim/citation tuples per question.

Per-case data showed 12/12 successful biology + photosynthesis cases at `groundedness=1`, `precision=1.00`, `recall=1.00`, `quote_validity=1.00` on both branches; both negative-control cases (gravity, black holes) correctly refused to ground on out-of-corpus topics on both branches.

## T57 — the precursor task

`AUTONOMOUS_WORK_PLAN.md` now lists **T57 (Phase 4.0 precursor)** at the end of the queue. T57 closes the three architectural pieces in one PR:

1. Wire `services/tutor.py:1228`, `:1310`, and `grounded_citations` to dispatch on `retrieval_use_nodes_enabled()`. Add a unit test in `tests/test_tutor_grounded.py` that mocks both retrieval functions, flips the flag, and asserts the right one is called.
2. Extend `evals/run_evals.py::run_case` to handle both `ScoredHit` and `RetrievedNode` hit shapes — dispatch the `retrieved_chunk_ids` extraction on type, and dispatch the `quote_validity` lookup on the type of `citation.node_id` (int → `nodes`; str → `chunks`). Extend `_resolve_expected_chunks` to compute matching `nodes.id` ints alongside the chunks set.
3. Document the eval invocation pattern: the USE_NODES=true run uses `INGEST_USE_DOCLING=true` so fixtures populate the nodes tables. The chunks-path run keeps the default.

T08's `Deps` line was updated to `T07, T57`. After T57 lands, T08 reopens, the comparison runs again, and the numbers become real signal.

## Why park rather than expand T08

The wiring T57 covers is genuinely Phase 4 work (T10/T11/T12 own the broader Docling-default-on + re-ingest + flag-flip flow). Expanding T08 to absorb it would:
- More than triple the diff and double the iteration count.
- Confound the comparison by mixing Docling-extracted text (nodes path) with the legacy chunker output (chunks path), since the two ingestion paths produce different chunks/nodes for the same source PDFs.
- Block the T08 deliverable behind a larger architectural change that already has its own queued slot.

Parking surfaces the architectural ceiling cleanly and isolates the wiring work into a focused PR (T57). T08 reopens as a half-iteration re-run.

## Honest reporting

The first-pass deliverable is this report. The work is not lost — the architectural finding tightens the Phase 4 plan and `tests/test_evals_runner.py::test_quality_thresholds_lock_invariants_on_both_branches` (added on the same commit as this rewrite) locks the threshold-invariant logic so a future T08 reopen has a regression net. Operator-followups (`.claude/logs/operator-followups.jsonl`) carries the same Phase-4-precursor note for the operator's review queue.

CLAUDE.md "no silent fallbacks" applies to eval reports as much as to runtime: rather than claim a vacuous "equal" as closure, the architectural ceiling is named, the precursor task is filed, and the comparison reopens once the precursor lands.
