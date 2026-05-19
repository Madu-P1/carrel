# AUTONOMOUS WORK PLAN

> **Source of truth for the `/carrel-build` autonomous routine.** Each iteration of the routine: (1) reads this file, (2) picks the highest-priority `pending` task whose dependencies are all `done`, (3) implements it, (4) opens a PR through audit-gate, (5) spawns the quality-rater (see `.claude/RATER_RUBRIC.md`) until score is 100, (6) marks the task `done` and commits the status update, (7) checks `.claude/HALT` and loops or stops.
>
> **Full implementation detail per task lives in [`docs/plans/everything-to-100-2026-05-17.md`](docs/plans/everything-to-100-2026-05-17.md).** This file is the queue + status; the master plan is the contract.
>
> **Scope:** build-only. No outreach, DMs, marketing posts, or external sends. See `.claude/AUTONOMOUS_SCOPE.md`. Operator lifts via editing `OUTREACH_BASH_PATTERNS` in `.claude/hooks/audit-gate.py`.
>
> **Verify chain canonical:** see [`CLAUDE.md`](CLAUDE.md) §"Verify chain (run before any merge)" lines 39-49. Every task that lands code runs the full chain before ship.
>
> **Date created:** 2026-05-17. **Last status update:** 2026-05-19.

## Operator decisions — 2026-05-19 (max-autonomy directive)

Operator authorized the routine to run at maximum autonomy within the existing build-only scope. The two T03 questions surfaced in `.claude/logs/status.md` (2026-05-18) are answered:

1. **PR strategy from T04 onward:** branch fresh off `main` for every task. No more stacked PRs on a long-lived staging branch. T03's work on `staging/loop-batch-2-2026-05-18` (PR #54) must reach `main` before T04 starts; the loop opens a `staging/loop-batch-2-2026-05-18 → main` PR, gets auditor approval, merges, then branches T04 off the now-T03-containing `main`.
2. **T03 chunk-to-node translation:** the page-level `(doc_id, page_num)` join is acceptable as the interim translation key. The concept-scoped fallback returns empty when no node rows resolve, which is the correct behavior under the "no silent fallbacks" rule. Re-ingestion in Phase 4 will re-key `concepts.source_chunks` directly to node ids and the translation becomes 1:1 anyway.
3. **No voluntary halts.** The loop does not pause to ask the operator about PR strategy, branch naming, scope ambiguity within a single task, context budget, or "should I continue?". Decide-and-proceed per `.claude/commands/carrel-build.md`. Halt only on the runtime conditions in that file (HALT file, rater 25-nudge cap, auditor 3-rejection cap, destructive action requested, 8-hour wall clock, scope drift, test count regression > 3 without justification, plan exhausted).
4. **Outreach + destructive gates unchanged.** Build-only scope still enforced by `OUTREACH_BASH_PATTERNS` and `DESTRUCTIVE_BASH_PATTERNS` in `.claude/hooks/audit-gate.py`. Operator owns those.
5. **Kill switch.** `touch /Users/madu/Desktop/Codex/.claude/HALT` stops the routine cleanly at next hook fire.
6. **Skill orchestration mandatory.** Before any substantive action the loop runs the pre-action routine in `.claude/commands/carrel-build.md` step 2: state the desired outcome, scan the available skills, pick 1-3 that fit the task type, run them inline, log the decision to `.claude/logs/skill-orchestration.jsonl`. Trivial tasks (formatting, status flip, doc reconciliation, dead-code removal) may skip with a populated `skipped_reason`. Rater rubric criterion D penalizes skipped orchestration on non-trivial work and wrong skill combinations.

## How the loop picks tasks

1. Read this file top-to-bottom.
2. Skip every task with `Status: done` or `Status: blocked`.
3. Among remaining `pending` tasks, find the lowest-numbered task whose `Dependencies:` line lists only tasks already `done` (or `none`).
4. Mark that task `Status: in_progress` (commit the status flip on the feature branch).
5. Execute per the master plan section referenced by the task.
6. On commit / push / `gh pr create`, audit-gate fires; auditor subagent approves per `.claude/RATER_RUBRIC.md` §"Audit checklist".
7. After the PR opens, spawn quality-rater per `.claude/RATER_RUBRIC.md` §"100-point rubric". Iterate until score is 100 or rater-nudge cap (25) hits.
8. On rater 100, mark the task `Status: done` with the PR number and commit hash. Loop to step 1.

## Stop conditions

- `.claude/HALT` exists → finish current iteration cleanly, then stop. Surface status in `.claude/logs/status.md`.
- All tasks `done` → write a final status summary and stop.
- Rater-nudge cap (25) hit on a single task → mark the task `Status: blocked` with reason in `notes`, commit, and loop to the next eligible task.
- Auditor REJECTS a major action three times in a row → mark `Status: blocked`, surface to operator, loop to next eligible task.

---

# TASK QUEUE

Conventions per task:
- **Title:** one-line scope.
- **Plan ref:** section of `docs/plans/everything-to-100-2026-05-17.md`.
- **Status:** `pending` / `in_progress` / `done` / `blocked`.
- **Deps:** task IDs that must be `done` first, or `none`.
- **Effort:** rough autonomous-loop iterations (1 iter ≈ 1-4 hours).
- **Acceptance:** the rateable bar.
- **Verify:** canonical chain plus task-specific spot-checks.
- **Guards:** anti-patterns (do-not list).
- **PR:** filled by the loop on land.

---

## T00 — Reconcile #43 (Notes Phase A) onto main

**Plan ref:** Phase 25 (Plan/Coach Phase 2) + Phase 27 items 2-3 + the Notes editor itself.
**Status:** done — PR #51, commit `961f0c74`, squash-merged 2026-05-18 (supersedes #43, which is CLOSED).
**Deps:** none
**Effort:** ~1 iteration (stash WIP, abort rebase, switch to squash-merge, resolve 24 conflict markers across 14 files, bump JS bundle budget 108→112 KB, verify chain green, admin-merge).
**Acceptance:** Coach Phase 2 rules (`deadline_imminent`, `low_recent_review`, `gap_between_classes`) + Swift XCTest scaffold (MainMenuBuilder/LaunchTelemetry/LocalApiToken/UploadMimeTypes) + Toast Undo action wiring + Notes editor (NotesPage, NoteEditor, NoteTile, SubjectRail, UnsortedInbox, note_folders table, folder_id on notes) + per-doc card linkage (migration 0022, doc_id column, COALESCE joins) + autonomous routine v1 scripts + new primitives (ErrorBoundary, LoadingBoundary, Markdown) + AI streaming module + companion-cube refinements. All on main.
**Verify:** ruff + ruff format clean; 89 backend unittest pass with 1 skipped; 429 frontend vitest pass; build:macos completes with index.js 110.6 KB gz under 112 KB budget; Swift build + build_and_run --verify + phase0 benchmark deferred to CI on PR #51.
**Guards:** do not blind-merge a CONFLICTING PR; rebase or cherry-pick. If rebase is hairy, cherry-pick the commits named in `docs/plans/everything-to-100-2026-05-17.md` Phase 25 + Phase 27 banner onto a fresh branch off main.
**Notes:** 50-commit rebase hit 6+ conflicts on commit 1 of 75. Pivoted to `git merge --squash` for one-shot conflict resolution. All conflicts resolved by either taking notes-phase-a's version (feature additions) or taking main's version (PR #50 routine updates).

## T01 — Phase 3 slice β.1: rename Citation chunk_id → node_id

**Plan ref:** Phase 3 task 1 + 2 (the dataclass rename, type change str → int).
**Status:** done — PR #53 (draft), commits `1b2f45c9` (functional rename) + `b77f75c0` (rater fix: seen-set typing), rated 100/100 SHIP on 2026-05-18.
**Deps:** none (main has the validators module from #46 + slice α from #48)
**Effort:** 1 iteration
**Acceptance:** `services/tutor.py` `Citation` dataclass uses `node_id: int` (was `chunk_id: str`). `HydratedChunkContext` renamed to `HydratedNodeContext` with `node_id: int` + `verbatim_text: str` (was `chunk_id: str` + `content: str`). All internal references updated. tutor.py compiles + `tests/test_tutor_grounded.py` updated to use new names and passes.
**Verify:** canonical chain + `pytest tests/test_tutor_grounded.py` green.
**Guards:** do not yet change the 5 `FROM chunks` SQL queries; that's T02. Do not yet change the LLM tool schema; the model still emits `chunk_index` (1-based, a position into contexts list) which the tutor maps to node_id internally.

## T02 — Phase 3 slice β.2: port _hydrate_chunk_context to nodes

**Plan ref:** Phase 3 task 1, the primary `FROM chunks` query at the old line 560.
**Status:** done — PR #53 (draft), commits `4786cc34` (dual-shape rename) + `7866e7bd` (rater gap-closure: orphaned-node log + tests + plan-doc), rated 100/100 SHIP on 2026-05-18.
**Deps:** T01
**Effort:** 1 iteration
**Acceptance:** `_hydrate_chunk_context` (renamed `_hydrate_node_context`) sources its `verbatim_text` / `heading_path` / `page` / integer `node_id` from `nodes` rather than from `chunks`. In practice the data arrives pre-populated on the `RetrievedNode` dataclass at retrieval time (see `services/retrieval/typed_hybrid.py:32-54`, which selects `FROM nodes JOIN node_embeddings JOIN node_fts`), so the hydration helper only needs a `SELECT id, filename FROM documents` round-trip for the user-facing citation label. Returns a list of `HydratedNodeContext` with `verbatim_text` populated from `nodes.verbatim_text`. `services.retrieval.search_hybrid` callers continue to work; if `RETRIEVAL_USE_NODES=true`, they get nodes; if false, they fall back through the legacy `ScoredHit` shape (already supported).
**Verify:** canonical chain + manual smoke: ask a question, confirm node-id-keyed citations appear in the response.
**Guards:** do not break the `RETRIEVAL_USE_NODES=false` path; both paths coexist until Phase 4 flips the flag. If both code paths get too tangled, surface a refactor request rather than ship spaghetti.

## T03 — Phase 3 slice β.3: port 3 fallback queries to nodes

**Plan ref:** Phase 3 task 1, fallback queries at old lines 655, 671, 686.
**Status:** done — PR #54 on `staging/loop-batch-2-2026-05-18` (commit `7a75a05d`), landed on `main` via PR #55 (squash commit `2c56ca09`) on 2026-05-19. The landing PR included a dual-path fix (`fix(tutor): gate T03 scope-fallback on RETRIEVAL_USE_NODES`) that restores T02's `RETRIEVAL_USE_NODES=false` contract at the fallback layer — caught by `tests.test_learning_os.LearningOSBackendTests.test_tutor_exchange_persists_evidence_and_workspace_v2_surfaces_it` on the merge. Operator approved the page-level `(doc_id, page_num)` translation key in the 2026-05-19 max-autonomy directive (see operator-decisions section above).
**Deps:** T02
**Effort:** 1 iteration
**Acceptance:** `_fallback_contexts_from_scope` queries `FROM nodes` for the concept-scoped, doc-scoped, and subject-scoped fallback paths. `concepts.source_chunks` column is read as before (semantic links to old chunks); the lookup translates chunk_ids to node_ids via a join on `(doc_id, page_num)` — operator-approved interim key since `chunks` lacks a `char_start` column. If translation fails (no node rows resolve), the path returns empty per the "no silent fallbacks" rule. Re-ingestion in Phase 4 re-keys `concepts.source_chunks` to node ids directly and the translation becomes 1:1.
**Verify:** canonical chain + scope-fallback unit tests pass; manually confirm a concept-scoped Ask query returns nodes from the right concept.
**Guards:** do not silently fall back from nodes to chunks at runtime. Either both work or surface ok=False; CLAUDE.md "no silent fallbacks".

## T04 — Phase 3 slice β.4: port post-grounded-answer chunks lookup

**Plan ref:** Phase 3 task 1, the 5th `FROM chunks` query at old line 1206.
**Status:** done — PR #56, commit `aa23381b`, rated 97/100 (structural pre-merge ceiling per rubric Criterion F) on 2026-05-19. Dual-path from day one (T01/T02/T03 contract honored): `_hydrate_cited_contexts` dispatches on `RETRIEVAL_USE_NODES`; nodes branch SELECTs FROM nodes, chunks branch preserved verbatim until Phase 4. No silent runtime fallback between paths.
**Deps:** T03
**Effort:** 0.5 iteration
**Acceptance:** the post-`grounded` chunks lookup that builds `flat_contexts` for `_flatten_claim_citations` queries `FROM nodes` instead. Citation flattening works end-to-end on the node-id path.
**Verify:** canonical chain + integration smoke: a multi-claim Pro answer returns flattened citations with `node_id` populated and `quote` verbatim.
**Guards:** see T03.

## T05 — Phase 3 slice β.5: api_models + response_model

**Plan ref:** Phase 3 task 2.
**Status:** done — bundled with T06 on PR #59, squash commit `e6e26a88`, rated 100/100 SHIP on 2026-05-19. Dual-shape `int | str` preserves the T01-T04 `RETRIEVAL_USE_NODES=false` contract (chunks-branch str-UUID flow); narrows to `int` after Phase 4 re-ingest + Phase 5 chunks-table drop.
**Deps:** T04
**Effort:** 0.5 iteration
**Acceptance:** `api_models.py::TutorCitationItem` carries `node_id: int | str` (was `chunk_id: str`). Dual-shape honors T01-T04's `RETRIEVAL_USE_NODES=false` contract: chunks-branch flows str UUIDs through `Citation.node_id` (see `services/tutor.py:622`, the T01 transitional comment); strict `int` would 500 the legacy path. Narrows to `int` after Phase 4 re-ingest and Phase 5 chunks-table drop. `TutorQueryResponse` updated by reference. `routes/tutor.py` `@router.post("/api/tutor/query", response_model=TutorQueryResponse)` continues to emit a 200 response with `node_id`-keyed citations. `./script/generate-api-types.sh` regenerates `frontend/src/services/api/types.gen.ts`.
**Verify:** canonical chain + curl `/api/tutor/query` and confirm `node_id` in the response JSON.
**Guards:** do not leave `chunk_id` as an alias in the response — break clean. Frontend gets updated in T06 (same PR).

## T06 — Phase 3 slice γ.1: frontend citation chip + flight to node_id

**Plan ref:** Phase 3 task 2.
**Status:** done — bundled with T05 on PR #59, squash commit `e6e26a88`, rated 100/100 SHIP on 2026-05-19. CitationChip + AskView + label components + anchorDrafts + useCitationFlight + FlightEntry + fixtures + 5 tests all flipped to `node_id`. AskView navigates `?node=`. SM-2 ghost flight degrades silently on the nodes branch (DOM target stays `[data-chunk-id]` until reader migration in T13).
**Deps:** T05
**Effort:** 1 iteration
**Acceptance:** `frontend/src/features/ask/components/CitationChip.tsx` accepts `node_id: number` (was `chunk_id: string`). `useCitationFlight.ts` and `useNodeDeepLink.ts` navigate by `node_id`. `ReaderView` deep-link route is `/reader/{doc_id}?node={node_id}` (the existing PR 4.2 contract). `frontend/tests/ask-components.test.tsx` updated.
**Verify:** canonical chain + manual smoke in dev: click a citation chip, land on the right node in the reader.
**Guards:** do not preserve a `chunk_id`-named fallback prop; clean rename.

## T07 — Phase 3 slice γ.2: re-key evals/cases/smoke.jsonl + smoke run

**Plan ref:** Phase 3 task 4.
**Status:** done — PR #60, squash commit `9c0f7ada`, rated 100/100 SHIP on 2026-05-19 (fresh-context re-rate after gap closure). Data-side rename was vacuous (`smoke.jsonl` cases key on filenames / topics / quote-substrings, never on `chunk_id`). Substantive deliverables: (1) eval-full rerun confirmed `groundedness@8 = 0.857` / `quote_validity = 1.000` (matches CLAUDE.md baseline), (2) new `test_smoke_mode_short_circuits_before_answer_metrics` locks the invariant the acceptance pivot rests on, (3) CLAUDE.md quality-bar bullet refreshed, (4) variable rename `cited_chunk_ids` → `cited_node_ids` in `evals/run_evals.py`, (5) smoke-mode brokenness surfaced to operator-followups.
**Deps:** T06
**Effort:** 0.5 iteration
**Acceptance:** every case in `evals/cases/smoke.jsonl` that referenced `chunk_id` now references `node_id` (vacuous — none do). The eval suite returns `groundedness@8 ≥ 0.7` and `quote_validity ≥ 0.95` (the CLAUDE.md quality bars). Acceptance pivot: the canonical quality run is `--mode full` (per CLAUDE.md §Benchmarks+budgets), not `--mode smoke`. Smoke mode is pre-existing broken — it skips embeddings (FTS5-only) and `_sanitize_query` rejoins interrogative tokens ("What is mitosis?") into a conjunctive `MATCH` query whose `What`/`How`/`When` tokens never appear in source chunks, so retrieval returns empty on every case; quote_validity isn't even computed in smoke mode (the runner returns at the `if mode == "smoke"` short-circuit). Fixing smoke is surfaced as a separate operator follow-up; it is out of T07's scope.
**Verify:** the eval run itself (full mode).
**Guards:** if a case can't translate cleanly (chunk_id had no node equivalent), drop the case and add a note rather than fabricate a node_id.

## T08 — Phase 3 slice γ.3: side-by-side smoke (`RETRIEVAL_USE_NODES` on vs off)

**Plan ref:** Phase 3 task 5.
**Status:** blocked — first-pass attempt landed via PR #61 (squash commit `84bd080d`, 2026-05-20) discovered an architectural ceiling: the eval harness cannot distinguish the two flag paths today. Comparison report committed at `evals/reports/compare-nodes-2026-05-19.md` (vacuous-equality outcome, architectural ceiling documented), gap-2 threshold-invariant regression test landed in `tests/test_evals_runner.py`, fresh-context rater scored the park deliverable 100/100 SHIP. T08 is parked behind a new precursor task **T57** (Phase 4.0 precursor); reopen after T57 lands and the comparison will then exercise real divergence.
**Deps:** T07, T57
**Effort:** 0.5 iteration (after T57)
**Acceptance:** run `evals/run_evals.py --mode full` with `RETRIEVAL_USE_NODES=true`, then with `RETRIEVAL_USE_NODES=false`. Compare metrics; the node path must be equal or better on both `groundedness@8` and `quote_validity`. Commit the comparison report under `evals/reports/compare-nodes-{date}.md`. **Mode pivot from smoke to full** mirrors T07: smoke is pre-existing broken (FTS5 conjunctive interrogative-token MATCH returns 0/14 groundedness, and `quote_validity` isn't computed in smoke mode at all per `_aggregate` short-circuit). Full mode is the canonical quality bar per CLAUDE.md §Benchmarks+budgets.
**Architectural ceiling found in first-pass (documented in `evals/reports/compare-nodes-2026-05-19.md`):** the eval harness calls `grounded_tutor_response` directly, which dispatches `search_hybrid` (legacy chunks-based) unconditionally at `services/tutor.py:1228` and `:1310` and inside `grounded_citations`. The `RETRIEVAL_USE_NODES` flag is only consulted at two downstream sites — `_fallback_contexts_from_scope` (fires only on empty primary retrieval; 0 cases in the smoke suite) and `_hydrate_cited_contexts` (only called from `grounded_tutor_envelope`, which the eval bypasses). Layered on top, typed-node ingestion is gated by `INGEST_USE_DOCLING` (default false), so even if dispatch is wired the eval's isolated DB has an empty `nodes` table on the USE_NODES=true run; the harness's `_resolve_expected_chunks` and `quote_validity` lookup also speak only the chunks id-space. The first-pass run produced **equal** numbers on both branches (groundedness@8 = 12/14, quote_validity = 1.00) but the equality is vacuous, not informative. T57 (below) wires the three pieces required for a non-vacuous comparison.
**Verify:** the comparison report numbers (after T57 lands and T08 reopens), plus the canonical chain.
**Guards:** do not ship T08 as `done` while the comparison is vacuous. Honest reporting trumps performative measurement: if the eval's measurement surface can't distinguish the two paths, say so and park rather than fabricating divergence. CLAUDE.md "no silent fallbacks" applies to eval reports too.

## T09 — Phase 3 slice γ.4: fail-closed regression test on Null provider

**Plan ref:** Phase 3 task 6.
**Status:** pending
**Deps:** T06
**Effort:** 0.5 iteration
**Acceptance:** new test in `tests/test_tutor_grounded.py::test_pro_tutor_fails_closed_on_null_provider` that asserts the tutor returns `ok=False, error="ai_synthesis_unavailable", citations=[]` when `select_provider()` returns the Null provider.
**Verify:** canonical chain + the new test passes.
**Guards:** no silent fallback to heuristic answers. CLAUDE.md "no silent fallbacks".

## T10 — Phase 4.1: extend Docling format coverage to 5 formats

**Plan ref:** Phase 4 task 2.
**Status:** pending
**Deps:** T08
**Effort:** 1 iteration
**Acceptance:** `INGEST_DOCLING_FORMATS` default extended from `pdf` to `pdf,docx,epub,html,md,txt`. New `tests/integration/test_docling_format_coverage.py` with 5 fixture cases (one per format), all green.
**Verify:** canonical chain + the new test passes.
**Guards:** do not flip `INGEST_USE_DOCLING` to default-on yet; T11 owns that.

## T11 — Phase 4.2: write script/reingest_all.py

**Plan ref:** Phase 4 task 3.
**Status:** pending
**Deps:** T10
**Effort:** 1 iteration
**Acceptance:** new `script/reingest_all.py` that iterates every doc in `documents`, calls `_run_import_job` with the original file bytes, logs progress to stdout + `data/migrations/reingest-{date}.jsonl`, idempotent (skips docs with non-zero node count), default concurrency 4.
**Verify:** canonical chain + dry-run the script on a temp DB with 2 fixture docs.
**Guards:** do not delete chunks rows during re-ingest; just add nodes alongside.

## T12 — Phase 4.3: flip 5 typed-node flags to default-on + run re-ingest

**Plan ref:** Phase 4 task 1 + 4 + 5.
**Status:** pending
**Deps:** T11
**Effort:** 1 iteration (plus overnight re-ingest)
**Acceptance:** defaults flipped in `services/ingestion/orchestrator.py:43`, `services/retrieval/typed_hybrid.py:63,74`, `frontend/src/features/ask/AskView.tsx:33`. Run `script/reingest_all.py` against the live DB; verify `SELECT COUNT(*) FROM documents WHERE id NOT IN (SELECT DISTINCT doc_id FROM nodes)` returns 0. Insert `app_settings('chunks_to_nodes_migration_complete', '<date>')` row.
**Verify:** canonical chain + the SQL invariant check.
**Guards:** do not start T13 until the SQL invariant holds.

## T13 — Phase 5.1: port 8 remaining chunks readers

**Plan ref:** Phase 5 task 1.
**Status:** pending
**Deps:** T12
**Effort:** 1-2 iterations
**Acceptance:** `services/documents.py:580,693-698`, `services/artifact_studio.py:72,84`, `services/evidence_resolution.py:19`, `services/retrieval/fts.py:37-42`, `services/retrieval/vector.py:17-59`, `services/ingestion/orchestrator.py:292` (INSERT INTO chunks), `services/extraction/quality.py`, `services/concepts/*` audited and ported to nodes. `grep -rn "FROM chunks\|INSERT INTO chunks\|UPDATE chunks" services/ routes/` returns zero (outside historical migrations).
**Verify:** canonical chain + the grep gate.
**Guards:** do not drop the chunks table here; T15 owns the drop migration.

## T14 — Phase 5.2: migrate anchors.chunk_id → anchors.node_id

**Plan ref:** Phase 5 task 2.
**Status:** pending
**Deps:** T13
**Effort:** 0.5 iteration
**Acceptance:** new migration `migrations/0017_anchors_chunk_to_node.sql` adds `anchors.node_id INTEGER REFERENCES nodes(id) ON DELETE SET NULL`, UPDATEs from a best-effort join, indexes the new column.
**Verify:** canonical chain + apply migration on a snapshot and inspect anchor node_id population rate.
**Guards:** if join coverage < 90% on the snapshot, surface a follow-up (some anchors may need manual reconciliation).

## T15 — Phase 5.3: drop chunks table (0018_drop_chunks.sql)

**Plan ref:** Phase 5 task 3.
**Status:** pending
**Deps:** T14
**Effort:** 0.5 iteration
**Acceptance:** new migration `migrations/0018_drop_chunks.sql` drops `chunks`, `chunks_fts`, `chunks_vec`, with a top-level guard `SELECT RAISE(ABORT, '...') WHERE NOT EXISTS (SELECT 1 FROM app_settings WHERE key='chunks_to_nodes_migration_complete')`. Regression test in `tests/test_db_migrations.py::test_chunks_drop_requires_migration_marker`.
**Verify:** canonical chain + the abort-on-missing-marker test.
**Guards:** never run this migration without verifying `T13`'s grep gate is still zero.

## T16 — Phase 6.1: Jobs Tray add OCR fallback stage + Partial status

**Plan ref:** Phase 6 tasks 1 + 2.
**Status:** pending
**Deps:** none (Ship 4 plumbing already in main)
**Effort:** 1 iteration
**Acceptance:** new migration `0019_jobs_partial_status.sql` extends `ingestion_jobs.status` CHECK to include `'partial'`. `services/jobs.py` emits `ocr_fallback` event on extraction fallback. `_update_job` computes `partial` when `successful_pages < total_pages`. UI tray shows the new event row + partial status badge.
**Verify:** canonical chain + manual smoke: ingest a scanned PDF, see OCR fallback event in tray.
**Guards:** do not promote `services/jobs.py` to a package; flat-module is intentional.

## T17 — Phase 6.2: Jobs Tray stuck detection + auto-archive + orphan guard

**Plan ref:** Phase 6 tasks 3-5.
**Status:** pending
**Deps:** T16
**Effort:** 1 iteration
**Acceptance:** `services/jobs.py::stuck_jobs()` returns jobs idle 5+ min. Badge labels real causes ("Stuck at OCR — Apple Vision unavailable"). `archive_old_jobs()` archives jobs older than 7 days in `(ready, failed_acked)`. `_run_import_job` wraps the document write + final `_update_job` in try/except that deletes the partial document row on crash; regression test in `tests/test_jobs_orphan_guard.py`.
**Verify:** canonical chain + the orphan-guard test.
**Guards:** no APScheduler; use SWR-on-boot per HANDOFF.md.

## T18 — Phase 6.3: JobsTray SSE multiplexer + Open log action

**Plan ref:** Phase 6 tasks 6 + 7.
**Status:** pending
**Deps:** T17
**Effort:** 0.5 iteration
**Acceptance:** `frontend/src/features/shell/jobsStore.ts` uses `frontend/src/services/sse.ts` multiplexer with `Last-Event-ID` reconnect. JobsTray row overflow menu has `Open log` action that renders the full event timeline.
**Verify:** canonical chain + DevTools shows exactly one `EventSource` connection to `/api/jobs/stream`.
**Guards:** -

## T19 — Phase 7.1: capture pdfjs text-layer offsets at ingest

**Plan ref:** Phase 7 task 1.
**Status:** pending
**Deps:** T12 (Docling default-on)
**Effort:** 1-2 iterations
**Acceptance:** Docling parse populates `nodes.char_start` and `nodes.char_end` against canonical normalized text per doc. `script/reingest_all.py --audit-offsets` flag re-validates char-offset alignment for sample of nodes per doc, reports rate.
**Verify:** canonical chain + audit-offsets pass at ≥95% on a 100-doc sample.
**Guards:** -

## T20 — Phase 7.2: PDF viewer scroll-to-bbox

**Plan ref:** Phase 7 tasks 2 + 3.
**Status:** pending
**Deps:** T19
**Effort:** 1-2 iterations
**Acceptance:** `frontend/src/features/reader/components/PdfPage.tsx` exposes `scrollToBbox(bbox)`; converts PDF points to viewport pixels via `viewport.scale`; triggers `fadeUp` + `scalePress` flash (motion tokens). `useCitationFlight.ts` calls `scrollToBbox` when node has populated bbox; falls back to text-offset substring search otherwise.
**Verify:** canonical chain + manual smoke on a two-column paper.
**Guards:** respect `prefers-reduced-motion`.

## T21 — Phase 7.3: Evidence Inspector additional actions + accuracy harness

**Plan ref:** Phase 7 tasks 4-7.
**Status:** pending
**Deps:** T20
**Effort:** 1 iteration
**Acceptance:** EvidenceInspector adds "show other anchors on this page", "restrict scope to this source", "open OCR text" (approximate fallback) actions. New eval harness `evals/cases/anchor-accuracy.jsonl` (50 cases across PDF/DOCX/EPUB); `evals/run_evals.py::run_anchor_accuracy()` reports `accuracy@1` and `accuracy@5`. Passes at `accuracy@1 ≥ 0.95` on clean-text PDFs.
**Verify:** canonical chain + the harness numbers.
**Guards:** do not claim ≥95% without the harness green.

## T22 — Phase 8.1: PDF text-layer selection → weak anchor

**Plan ref:** Phase 8 task 1.
**Status:** pending
**Deps:** T19
**Effort:** 1 iteration
**Acceptance:** `frontend/src/features/reader/components/PdfPage.tsx` on text selection POSTs `/api/anchors` with `origin='highlight'`, `bbox` + `text_offset_start/end` + `quote_text` populated.
**Verify:** canonical chain + manual smoke: highlight in PDF, see new anchor row.
**Guards:** -

## T23 — Phase 8.2: auto-create anchors for every AI citation + thread_id

**Plan ref:** Phase 8 task 2.
**Status:** pending
**Deps:** T01 (Pro tutor on nodes)
**Effort:** 1 iteration
**Acceptance:** `services/tutor.py` server-side calls `create_anchor(conn, origin='ai_answer_citation', thread_id=<tutor_thread_id>, ...)` for every citation; idempotent. `AnchorCreateRequest` + `services.anchors.create_anchor` accept optional `thread_id`.
**Verify:** canonical chain + a 3-citation answer creates exactly 3 anchors on the server.
**Guards:** create anchors only for citations that reached the user's screen.

## T24 — Phase 8.3: right-click context menu + strength flags + batch save-all

**Plan ref:** Phase 8 tasks 3 + 4 + 5.
**Status:** pending
**Deps:** T23
**Effort:** 1 iteration
**Acceptance:** `frontend/src/features/reader/components/PdfPage.tsx` on right-click shows Make card / Make cloze / Make 3 cards / Save for later. Drawer renders strength flags (`good`, `too_long`, `ambiguous` in addition to existing `duplicate_warning`). `Save all (N)` button on drawer for >3 drafts.
**Verify:** canonical chain + manual smoke.
**Guards:** cloze action stays a "Coming soon" toast until T26 lands the schema.

## T25 — Phase 8.4: improve dup detection + memoize AnchorColumn

**Plan ref:** Phase 8 tasks 6 + 8.
**Status:** pending
**Deps:** T23
**Effort:** 0.5 iteration
**Acceptance:** `services/anchors.py::jaccard_similarity(a, b, n=3)` true jaccard; threshold 0.85 for `duplicate_warning`. `AnchorColumn.tsx` rows wrapped in `memo()` keyed on `(anchor.id, anchor.updated_at)`.
**Verify:** canonical chain + React DevTools profiler shows no unnecessary re-renders.
**Guards:** -

## T26 — Phase 9.1: unify card prompts in ai/card_prompts.py

**Plan ref:** Phase 9 task 1.
**Status:** pending
**Deps:** none
**Effort:** 0.5 iteration
**Acceptance:** new `ai/card_prompts.py` carries the rich 7-rule prompt + banned-words list. `routes/study.py::_AI_DRAFT_CARDS_SYSTEM` and `ai/claude.py::generate_srs_cards` both import from it. Test asserts both call sites use the same template (string equality on the system prompt).
**Verify:** canonical chain + the equality test.
**Guards:** -

## T27 — Phase 9.2: add card-quality eval suite + baseline

**Plan ref:** Phase 9 tasks 2-5.
**Status:** pending
**Deps:** T26
**Effort:** 1 iteration
**Acceptance:** new `evals/cases/cards.jsonl` (30 cases across biology, history, CS). `evals/run_evals.py::run_card_quality()` runs deterministic + LLM-as-judge checks. Baseline recorded in `data/benchmarks/card-quality-baseline.json`. Kill-condition documented in `docs/notes/2026-XX-XX-flashcard-quality.md` (auto-gen stays off if baseline < 0.7).
**Verify:** baseline run + the doc.
**Guards:** do not flip `CARREL_AUTO_CARD_DRAFT` to true here.

## T28 — Phase 10: citation reveal on flashcard back face

**Plan ref:** Phase 10.
**Status:** pending
**Deps:** T05 (api_models for node_id)
**Effort:** 0.5 iteration
**Acceptance:** `services/study.py::fetch_due_cards` SELECT extended with LEFT JOIN to `flashcard_evidence` + `evidence_references` + `anchors`; returns `node_id`, `chunk_id`, `page_num`, `quote_text`, `document_id`. `SrsDueCard` type extended. New `SourceCitation.tsx` renders on back face; click deep-links via existing PR 4.2 path. Test `frontend/tests/study/source-citation.test.tsx` covers present/missing/document-missing.
**Verify:** canonical chain + manual smoke.
**Guards:** -

## T29 — Phase 11.1: cloze schema migration + AI cloze tool

**Plan ref:** Phase 11 tasks 1 + 2 + 3 + 6.
**Status:** pending
**Deps:** T27
**Effort:** 0.5 iteration
**Acceptance:** new `migrations/0019_srs_cards_kind_and_paired.sql` adds `kind TEXT CHECK IN ('qa','cloze')` and `paired_card_id TEXT REFERENCES srs_cards(id) ON DELETE SET NULL` + 2 indexes. New `submit_cloze_drafts` tool in `ai/card_prompts.py` with rule 8 (one high-value term to blank). `SrsCard` type extended.
**Verify:** canonical chain + migration applies cleanly + Phase 9 baseline still met.
**Guards:** reuse front/back storage for cloze (no new columns).

## T30 — Phase 11.2: cloze rendering + reverse card generation

**Plan ref:** Phase 11 tasks 4 + 5.
**Status:** pending
**Deps:** T29
**Effort:** 0.5 iteration
**Acceptance:** `FlashcardFace.tsx` branches on `card.kind`: cloze front has `____`, back fills in `--color-accent`. Reverse-card generation in `routes/anchors.py::promote-card`: detects short-back cards, creates paired row with `paired_card_id` mutual reference.
**Verify:** canonical chain + manual smoke.
**Guards:** -

## T31 — Phase 12: flashcard PR-6 leftovers (defer + streak + ETA)

**Plan ref:** Phase 12.
**Status:** pending
**Deps:** none
**Effort:** 0.5 iteration
**Acceptance:** `StudyView.tsx` defer button rotates card to end of `sessionQueue` without /api/srs/review. Streak chip renders at `:531` after 2 consecutive Good/Easy; resets on Again/Hard. New `GET /api/srs/timing-stats` returns median seconds-to-rate; ETA renders.
**Verify:** canonical chain + manual smoke.
**Guards:** no emoji on streak chip. CLAUDE.md voice rule.

## T32 — Phase 13: bulk card generation from document

**Plan ref:** Phase 13.
**Status:** pending
**Deps:** T27, T28
**Effort:** 1-2 iterations
**Acceptance:** new `POST /api/srs/cards/from-document` with `{document_id, section_id?, chunk_range?, target_count}`. Reuses `services/ingestion/cards.py::build_flashcard_deck` (port to nodes). Persists evidence links via `link_evidence_to_card`. New `BulkDeckReview.tsx` full-page review. Entry button on document detail view. SSE progress for >20 cards. Card quality eval still meets baseline.
**Verify:** canonical chain + generate 50 cards on a 30-page doc in <60s warm.
**Guards:** atomic bulk-save; no per-card POST loop.

## T33 — Phase 14: outline data richness (heading_level)

**Plan ref:** Phase 14.
**Status:** pending
**Deps:** T12
**Effort:** 0.5 iteration
**Acceptance:** new migration `0020_nodes_heading_level.sql` adds `heading_level INT NULL`. `services/extraction/parsers/pdf.py` + `text.py` populate the column on ingest. Backfill script `script/backfill_heading_levels.py` for existing rows. `OutlineRail` consumes the field for 16px-per-level indentation (cap 3).
**Verify:** canonical chain + outline indentation visible in dev.
**Guards:** -

## T34 — Phase 15: Premium UI Ship 3 (Reader)

**Plan ref:** Phase 15 + master plan Phase 15 section.
**Status:** pending
**Deps:** T33
**Effort:** 2 iterations
**Acceptance:** outline rail 280px / 48px collapsed; toolbar 44px three-zone; right rail 340px with Tabs primitive (Chunks/Notes/Related/Ask); PDF canvas surface tokens; doc meta 72px header strip; loading uses Skeleton + SkeletonGroup; ≤900px toolbar two-row collapse documented in `frontend/tests/reader/responsive-toolbar.test.tsx`.
**Verify:** canonical chain + manual visual diff against `docs/roadmap/premium-ui-pass.md:15-83`.
**Guards:** do not change `--text-h3` size here; that's T36.

## T35 — Phase 16: Premium UI Ship 4 (Session Setup)

**Plan ref:** Phase 16.
**Status:** pending
**Deps:** none
**Effort:** 1 iteration
**Acceptance:** mode cards 2-col ≥900px + tokens; selected state `--state-bg-selected` + `--state-border-selected` + accent title + `--shadow-card`; duration chips 28px tall + 40×40 hit target; CTA size-lg.
**Verify:** canonical chain + DevTools spot-check.
**Guards:** -

## T36 — Phase 17: Premium UI Ship 5 (Answer Card Feed) + card unification

**Plan ref:** Phase 17.
**Status:** pending
**Deps:** T01 (Pro tutor on nodes; CitationChip on node_id)
**Effort:** 1 iteration
**Acceptance:** `ClaimList.tsx` becomes canonical Pro-tier card. Delete `AskCard.tsx` and `AnswerFeedCard.tsx` (migrate callers). Tier hierarchy typography per `premium-ui-pass.md:152-170`. Max width 68ch. Bulk-ops 20×20 checkbox top-left.
**Verify:** canonical chain + grep returns zero imports of deleted files.
**Guards:** do not merge `FallbackAnswer.tsx` into `ClaimList.tsx`.

## T37 — Phase 18: Premium UI Ship 6 (Dashboard) — kill yellow callout

**Plan ref:** Phase 18.
**Status:** pending
**Deps:** T35
**Effort:** 1 iteration
**Acceptance:** no yellow callout in DashboardView or NextBestAction (use `--state-bg-selected`). Hero composer clamps to `min(760px, 100%)`. Scope-pill hydrates from `/ask?scope=...`. 4 quick-action tiles 80px. translateY(-1px) hover on tiles.
**Verify:** canonical chain + grep zero yellow tokens.
**Guards:** no fifth quick-action tile.

## T38 — Phase 19: Premium UI Ship 7 (Copy + state polish sweep)

**Plan ref:** Phase 19.
**Status:** pending
**Deps:** T34, T35, T36, T37
**Effort:** 0.5 iteration
**Acceptance:** grep returns zero for `"Try again"`, `"AI assistant"`, `"your assistant"`, `"as an AI"` across `frontend/src/`. Every `*EmptyState.tsx` renders a Button. No full-page Spinner patterns. DESIGN.md voice section updated with swept rules + grepable patterns subsection.
**Verify:** canonical chain + the greps.
**Guards:** -

## T39 — Phase 20: Premium UI Ship 8 (A11y + QA pass)

**Plan ref:** Phase 20.
**Status:** pending
**Deps:** T38
**Effort:** 1 iteration
**Acceptance:** `axe-core` zero violations on every primary route. Lighthouse a11y ≥ 95 on Dashboard / Reader / Ask / Study / Plan / Session. Every icon-only Button has `aria-label`. `prefers-reduced-motion` honored across animations.
**Verify:** axe + Lighthouse runs.
**Guards:** no `aria-hidden="true"` on interactive as workaround.

## T40 — Phase 21: voice refresh app-wide (two-registers)

**Plan ref:** Phase 21.
**Status:** pending
**Deps:** T38
**Effort:** 1-2 iterations
**Acceptance:** Library, Reader, Ask, Plan, Dashboard, Session, Study audited per the master plan checklist. DESIGN.md gains "Two registers" subsection (cockpit + welcome) with examples.
**Verify:** canonical chain + grep no em dashes in user-facing copy.
**Guards:** preserve cockpit voice in Session section labels.

## T41 — Phase 22.1: Einstein rename Tier 3A (DB) + 3B (env namespace)

**Plan ref:** Phase 22 sections A + B.
**Status:** pending
**Deps:** none (independent track)
**Effort:** 1 iteration
**Acceptance:** `data/einstein_tutor.db` → `data/carrel.db` via boot-time atomic rename in `db.py::apply_migrations` with `CARREL_DB_PATH` env shim. `EINSTEIN_*` (7 vars) → `CARREL_*` with dual-honor + deprecation warning. Tests cover both.
**Verify:** canonical chain + boot the app twice (pre + post rename) and confirm DB transitions cleanly.
**Guards:** never delete the old DB without verifying new is loadable.

## T42 — Phase 22.2: rename Tier 3C (logger) + 3D (bridge globals atomic) + 3F (localStorage)

**Plan ref:** Phase 22 sections C + D + F.
**Status:** pending
**Deps:** T41
**Effort:** 1 iteration
**Acceptance:** logger namespace + `einstein-backend.jsonl` → `carrel-backend.jsonl`. Swift + JS bridge globals atomic across `NativeBridge.swift`, `WebAppView.swift`, JS side (single commit). DOM IDs renamed. localStorage key migrated with 10-line read-old/write-new/delete-old on app start.
**Verify:** canonical chain + boot the app and confirm no console errors about missing bridges.
**Guards:** Tier 3D MUST be one atomic commit.

## T43 — Phase 22.3: rename Tier 3H (bundle identity)

**Plan ref:** Phase 22 section H.
**Status:** pending
**Deps:** T42
**Effort:** 1-2 iterations
**Acceptance:** `com.madu.EinsteinDesktop` → `com.madu.Carrel`; `EinsteinDesktop.app` → `Carrel.app`; `EinsteinDesktopApp/` → `CarrelApp/`; `EinsteinIngestionBridge` → `CarrelIngestionBridge`; `EinsteinAFMBridge` → `CarrelAFMBridge`. In-app migration assistant migrates user data + re-prompts privacy-scoped permissions.
**Verify:** canonical chain + clean install on a fresh Mac OR migration on a pre-rename install (both paths).
**Guards:** do not skip the migration assistant; existing users lose data without it.

## T44 — Phase 23.1: paid-tier schema (users + licenses + usage_events.user_id)

**Plan ref:** Phase 23 schema section.
**Status:** pending
**Deps:** T43
**Effort:** 1 iteration
**Acceptance:** new migrations `0021_users.sql`, `0022_licenses.sql`, `0023_usage_events_user_id.sql`. Documented constraints. Migration tests.
**Verify:** canonical chain + migration tests.
**Guards:** -

## T45 — Phase 23.2: auth middleware (offline license validation)

**Plan ref:** Phase 23 auth section.
**Status:** pending
**Deps:** T44
**Effort:** 1 iteration
**Acceptance:** `services/auth/license.py` validates against bundled public key. `services/auth/require_plan.py` decorator. Token shape: signed JWT. Online check only at activation.
**Verify:** canonical chain + unit tests on token validation.
**Guards:** never store license tokens in localStorage.

## T46 — Phase 23.3: licenses + billing routes (Stripe)

**Plan ref:** Phase 23 routes section.
**Status:** pending
**Deps:** T45
**Effort:** 1-2 iterations
**Acceptance:** `routes/licenses.py` (`POST /api/licenses/activate`, `GET /api/licenses/status`, `POST /api/licenses/deactivate`). `routes/billing.py` (`POST /api/billing/checkout`, `POST /api/billing/portal`, `POST /api/billing/webhook` with signing-secret verification). Webhook handles `checkout.session.completed`, `invoice.paid`, `customer.subscription.deleted`.
**Verify:** canonical chain + Stripe CLI smoke against test mode.
**Guards:** never skip signature verification on the webhook.

## T47 — Phase 23.4: Settings feature directory

**Plan ref:** Phase 23 frontend section.
**Status:** pending
**Deps:** T46
**Effort:** 1-2 iterations
**Acceptance:** `frontend/src/features/settings/` with `SettingsView.tsx`, `LicenseSection.tsx`, `BillingSection.tsx`, `BYOKSection.tsx`, `UsageSection.tsx`. Plan-gating UI on Pro-tier features. .edu MX check at activation.
**Verify:** canonical chain + manual smoke (Settings panel renders all 4 sections).
**Guards:** -

## T48 — Phase 23.5: macOS Keychain bridge

**Plan ref:** Phase 23 Keychain section.
**Status:** pending
**Deps:** T43 (bundle rename for Keychain service identifier), T47 (BYOK section consumes)
**Effort:** 1 iteration
**Acceptance:** `macos-app/Sources/CarrelApp/KeychainBridge.swift` using `Security.framework` with `kSecClass = kSecClassGenericPassword`, service = `com.madu.Carrel`. Exposes via `NativeBridge.swift` as `window.__carrelKeychain.{set,get}`. Migration prompts to move `ANTHROPIC_API_KEY` from `.env` into Keychain on first paid-tier launch.
**Verify:** canonical chain + persist Keychain entry across app restarts.
**Guards:** never store in JS-readable localStorage.

## T49 — Phase 24.1: pricing reconciliation + /study landing

**Plan ref:** Phase 24 tasks 1 + 2.
**Status:** pending
**Deps:** T47 (paid tier real)
**Effort:** 1 iteration
**Acceptance:** `docs/marketing/landing-page.html:1127-1180` pricing updated to $0/$8/$25/$25/$150-300 per `docs/outreach/pricing-2026-05-17.md`. New `docs/marketing/study.html` (Study wedge: deadline planner; Free + Student $8 + Cohort $25).
**Verify:** canonical chain + manual review of landing copy against DESIGN.md voice.
**Guards:** no em dashes in landing copy.

## T50 — Phase 24.2: /research landing + onboarding split + README

**Plan ref:** Phase 24 tasks 3 + 5 + 6.
**Status:** pending
**Deps:** T49
**Effort:** 1 iteration
**Acceptance:** new `docs/marketing/research.html` (Research wedge: citations + privacy; Pro $25 + Institutional $150-300). First-launch onboarding asks Study-vs-Research question + routes accordingly. README.md updated with two-product framing.
**Verify:** canonical chain + the onboarding flow on first run.
**Guards:** "Same codebase, two marketing surfaces" — do not fork.

## T51 — Phase 26.1: command palette action registry + central registry

**Plan ref:** Phase 26 tasks 1 + 2.
**Status:** pending
**Deps:** T39 (premium UI a11y complete)
**Effort:** 1 iteration
**Acceptance:** every feature exports `actions.ts`. `frontend/src/app/command-palette/registry.ts` collects on boot.
**Verify:** canonical chain + registry assembled on boot.
**Guards:** no third-party palette library.

## T52 — Phase 26.2: ⌘K overlay + search + recent/favorites

**Plan ref:** Phase 26 tasks 3 + 4 + 5 + 6.
**Status:** pending
**Deps:** T51
**Effort:** 1-2 iterations
**Acceptance:** Cmd+K opens palette from every route. Fuzzy-search action labels. Keyboard nav. Grouped by feature. New `GET /api/search?q=...` for content search across documents + anchors + recent answers + cards. Recent + favorite actions at top when empty.
**Verify:** canonical chain + search latency <200ms on 500-doc library.
**Guards:** debounce 150ms on server search calls.

## T53 — Phase 27.1: ESLint 9 flat-config migration

**Plan ref:** Phase 27 task 1.
**Status:** pending
**Deps:** none
**Effort:** 0.5 iteration
**Acceptance:** new `eslint.config.js` flat config. `pnpm lint` runs against it. Deprecated-rule audit done.
**Verify:** canonical chain.
**Guards:** -

## T54 — Phase 27.4: FLIP animation layout-perfect

**Plan ref:** Phase 27 task 4.
**Status:** pending
**Deps:** none
**Effort:** 0.5 iteration
**Acceptance:** FLIP from wide-aspect source to tall-header target lands layout-perfect. Use `getBoundingClientRect()` on actual target node at flight start. Visual diff confirms.
**Verify:** canonical chain + visual diff on a wide → tall flight.
**Guards:** -

## T55 — Phase 27.5: calendar feed URLs in Keychain

**Plan ref:** Phase 27 task 5.
**Status:** pending
**Deps:** T48
**Effort:** 0.5 iteration
**Acceptance:** `services/calendar/` reads + writes calendar feed URLs via the Keychain bridge from T48. Migration nulls plaintext column on existing rows after moving values to Keychain.
**Verify:** canonical chain + plaintext column null on existing rows.
**Guards:** never localStorage.

## T56 — Phase 28: final verification + ship-readiness audit

**Plan ref:** Phase 28.
**Status:** pending
**Deps:** ALL above (T01-T55, T57)
**Effort:** 1 iteration
**Acceptance:** canonical chain green from clean checkout. `evals --mode full` meets all bars (groundedness@8 ≥ 0.7, quote_validity ≥ 0.95, card_quality@1 ≥ Phase 9 baseline, anchor_accuracy@1 ≥ 0.95). cold launch p50 ≤ 800ms. axe-core zero violations. Manual smoke test of E2E flow (drop PDF → ask → flight → save anchor → promote → review → activate → upgrade → bulk generate). Launch checklist written.
**Verify:** all eval + benchmark bars + the manual smoke.
**Guards:** never ship without the rollback plan documented.

## T57 — Phase 4.0 (precursor): wire `RETRIEVAL_USE_NODES` primary-retrieval dispatch + eval-harness id-space dispatch

**Plan ref:** Phase 4 precursor (discovered during T08's first-pass attempt; documented in `evals/reports/compare-nodes-2026-05-19.md`).
**Status:** pending
**Deps:** T07
**Effort:** 1 iteration
**Acceptance:** three coupled pieces land in one PR:
1. `services/tutor.py`: dispatch on `retrieval_use_nodes_enabled()` at the three primary-retrieval call sites — `grounded_tutor_response` (line ~1228), the post-`grounded` sister site (line ~1310), and `grounded_citations` (line ~1196). When the flag is on, call `search_typed_hybrid` (returns `list[RetrievedNode]`); when off, call `search_hybrid` (returns `list[ScoredHit]`). Existing `_hydrate_node_context` already dispatches on hit type, so downstream code keeps working. Add a unit test in `tests/test_tutor_grounded.py` that asserts the dispatch (mock both retrieval functions, flip the flag, assert the right one is called).
2. `evals/run_evals.py::run_case`: handle both hit types — extract `hit.node_id if isinstance(hit, RetrievedNode) else hit.chunk_id` for the `retrieved_chunk_ids` set; dispatch `quote_validity` lookup on the type of `citation.node_id` (int → `SELECT verbatim_text FROM nodes WHERE id = ?`; str → `SELECT content FROM chunks WHERE id = ?`). `_resolve_expected_chunks` returns an expected set that covers both id-spaces (extend it to also match against `nodes.verbatim_text` and collect matching `nodes.id` ints).
3. The eval invocation pattern documented in CLAUDE.md and the comparison-report runbook updated to include `INGEST_USE_DOCLING=true` on the USE_NODES=true run path (so the fixtures populate the nodes tables). The chunks-path run keeps the default. This is the documented invocation pattern, not a code change in the runner itself.
**Verify:** canonical chain + new dispatch unit test + a fresh side-by-side eval comparison run that produces real divergence numbers (chunks branch vs nodes branch).
**Guards:** no silent fallbacks; the nodes-branch primary retrieval surfaces ok=False rather than falling back to chunks. The eval-harness id-space dispatch is symmetric (chunks lookups stay on the chunks branch, nodes lookups on the nodes branch). After T57 lands, reopen T08 (`Status: pending`) and re-run the comparison.

---

# Status legend

- `pending`: not started, eligible if deps `done`.
- `in_progress`: a routine iteration has claimed it. The routine should NOT take another `in_progress` task; finish this one first or mark `blocked`.
- `done`: shipped to main, rater scored 100. PR + commit hash in `notes`.
- `blocked`: rater never reached 100, or auditor rejected 3×, or external blocker. Skip and surface.

# Cross-cutting notes for the loop

- **Loop concurrency:** one iteration at a time. Do not run two `in_progress` tasks simultaneously. The score-loop hook's per-session counter assumes serial execution.
- **PR base:** always `main`. If a task naturally depends on an unmerged PR, mark `blocked` and skip; do not create stacked PRs (we learned in this session that stacked PRs auto-close on parent squash, losing the head PR).
- **Verify chain:** run the FULL chain from `CLAUDE.md:39-49` including the `ruff format --check` line added 2026-05-18. Local-CI parity gate.
- **Adversarial review:** when subagent budget is available, run an adversarial review pass on every PR before opening. Findings of severity P1 or P2 block ship until addressed.
- **No em dashes** in PR titles, commit messages, or product copy. CLAUDE.md voice rule.
- **No silent fallbacks.** CLAUDE.md. Pro tutor must surface ok=False on failure rather than degrade.
- **No `dangerouslySetInnerHTML`.** ux-perfection rule.

# Updating this file

When marking a task `done`:

```diff
- **Status:** pending
+ **Status:** done — PR #XX, commit abc1234, rated 100/100 on 2026-MM-DD
```

The routine commits the status flip as part of the same PR that lands the work, OR as a follow-up commit on main immediately after merge.

# When the queue is empty

If every task is `done` or `blocked`, write a closeout summary to `.claude/logs/closeout-{date}.md` listing:
- Master plan phases delivered
- Open `blocked` items with reasons
- Score-out-of-100 estimate vs the master plan
- Recommended next quarterly cycle (Phase 28+ would be the post-launch evolution)

Then exit cleanly.

---

*Last updated 2026-05-18. Authored alongside `docs/plans/everything-to-100-2026-05-17.md`. The master plan is the contract; this file is the queue.*
