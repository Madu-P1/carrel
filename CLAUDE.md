# Carrel — Project Context for Claude

Local-first, source-grounded AI study and research workspace for macOS. Native Swift + SwiftUI shell wraps a WKWebView loading a bundled Preact + TypeScript + Vite app. SQLite storage, FastAPI backend, Claude API for grounded answers with hybrid FTS5 + sqlite-vec retrieval. Renamed from Einstein Tutor; some internal identifiers (`com.madu.EinsteinDesktop` bundle, `EinsteinDesktop.app`, `data/einstein_tutor.db`) remain on the legacy names — see `docs/notes/2026-04-29-carrel-rename.md` for the deferred-rename list.

## Stack

- **Native shell:** Swift + SwiftPM, macOS 14+. `macos-app/Sources/EinsteinDesktopApp/`. WKWebView loads the bundled `app.new.html`. Menu bar.
- **OCR sidecar:** `EinsteinIngestionBridge` executable using PDFKit + Vision for PDF text + OCR extraction.
- **Frontend:** `frontend/` — Preact 10, TypeScript strict, Vite 6, CSS Modules + design tokens. Pinned via pnpm 9.12.0. Builds to `macos-app/Resources/app.new.html` via `frontend/scripts/build-macos.mjs`.
- **Backend:** FastAPI + Pydantic. `main.py` is 71 LOC of wiring only. Real logic in `routes/*` and `services/*`. `services/ingestion/` and `services/extraction/` are packages, not monoliths.
- **DB:** SQLite with WAL + FTS5 + sqlite-vec. Versioned migrations in `migrations/NNNN_*.sql` applied by `db.py::apply_migrations`. Schema is migrations-sourced; `schema.sql` is legacy.
- **AI:** Claude API via `ai/router.py`. Models: `claude-haiku-4-5` (fast), `claude-sonnet-4-6` (balanced), `claude-opus-4-7` (deep). Structured output via `request_tool_call` with forced tool use. All calls return typed `ClaudeCallResult` with latency + token + cache metrics. Silent fallback to heuristic is forbidden; failures are visible.
- **Retrieval:** Hybrid FTS5 + vector via `services/retrieval/hybrid.py` with Reciprocal Rank Fusion. Quote validation at citation resolve time.

## Key directories

| Path | Role |
|---|---|
| `macos-app/Sources/EinsteinDesktopApp/` | Swift shell, menu, native bridge |
| `macos-app/Sources/EinsteinIngestionBridge/` | PDF + OCR sidecar CLI |
| `macos-app/Resources/` | Bundled HTML (`app.new.html`) + assets |
| `frontend/src/app/` | Shell + routing (preact-iso) |
| `frontend/src/design-system/` | Tokens, primitives, motion. See `DESIGN.md`. |
| `frontend/src/features/{library,reader,ask,study}/` | Feature views |
| `frontend/src/services/api/` | Typed API client + generated `types.gen.ts` |
| `routes/` | FastAPI route handlers |
| `services/` | Domain services (ingestion, extraction, retrieval, tutor, etc.) |
| `ai/` | Claude router + client |
| `migrations/` | Versioned SQL migrations |
| `benchmarks/` | Cold launch + phase0 benchmarks |
| `evals/` | Grounded-answer eval harness with smoke + full modes |
| `tests/` | Python unittest suites |
| `frontend/tests/` | Vitest suites |
| `docs/adr/` | Architecture decision records |
| `docs/notes/` | Ad hoc engineering notes |

## Verify chain (run before any merge)

```bash
./script/generate-api-types.sh
corepack pnpm --dir /Users/madu/Desktop/Codex/frontend typecheck
corepack pnpm --dir /Users/madu/Desktop/Codex/frontend lint
corepack pnpm --dir /Users/madu/Desktop/Codex/frontend test
corepack pnpm --dir /Users/madu/Desktop/Codex/frontend build:macos
./.venv/bin/python -m ruff check /Users/madu/Desktop/Codex/ai /Users/madu/Desktop/Codex/services /Users/madu/Desktop/Codex/evals /Users/madu/Desktop/Codex/tests /Users/madu/Desktop/Codex/main.py /Users/madu/Desktop/Codex/db.py /Users/madu/Desktop/Codex/routes /Users/madu/Desktop/Codex/api_models.py /Users/madu/Desktop/Codex/benchmarks
./.venv/bin/python -m unittest tests.test_ai_router tests.test_tutor_grounded tests.test_retrieval_hybrid tests.test_retrieval_vector tests.test_retrieval_fts tests.test_db_migrations tests.test_phase0_foundation tests.test_phase0_batch_b tests.test_einstein_tutor tests.test_learning_os tests.test_evals_runner -v
./script/build_and_run.sh --verify
./.venv/bin/python -m benchmarks.phase0 --compare /Users/madu/Desktop/Codex/data/benchmarks/baseline.json --fail-on-regression
```

Optional pre-release step (skipped on CI and on machines without Apple Foundation Models). Requires macOS 26+ Apple Silicon, Apple Intelligence enabled, en_US primary locale, and a built bridge under `macos-app/.build` or a packaged `.app`:

```bash
CARREL_RUN_AFM_INTEGRATION=1 ./.venv/bin/python -m unittest tests.integration.test_afm_real_bridge -v
```

Every PR lands green on the full chain or it does not land.

## Benchmarks + budgets

- **Cold launch:** p50 ≤ 800ms target, current 465ms p50, warm 200-250ms. Gate: `script/measure_cold_launch.sh` + `benchmarks/cold_launch_diff.py`.
- **Grounded answer:** p50 ~4s, p95 ~7s (Sonnet 4.6 latency envelope). Acceptable given product shape.
- **Ingestion:** phase0 benchmark fails on regression vs `data/benchmarks/baseline.json`.
- **Quality:** `evals-full` suite must keep `groundedness@8 ≥ 0.7` and `quote_validity ≥ 0.95` (currently 0.857 + 1.0 after PR-D3d quote retrofit).

## Design System

Always read `DESIGN.md` before making any visual or UI decisions. All font choices, colors, spacing, aesthetic direction, and motion specs are defined there. Do not deviate without explicit user approval. In QA or design-review, flag any code that drifts from `DESIGN.md`.

Motion is a first-class part of the design system, organized in three tiers:
- **Tier 1 (Functional):** CSS transitions on every hover/focus/press. 60-280ms.
- **Tier 2 (Narrative):** Keyframe library (`animations.css`) for route transitions, panel reveals. 180-280ms.
- **Tier 3 (Signature):** Five hand-tuned moments. Hand-coded, hand-reviewed. See `DESIGN.md` motion section.

Zero runtime motion libraries. CSS + WAAPI only.

## Conventions

- **No silent AI fallbacks.** Every Claude call returns `ClaudeCallResult` with visible ok/error/latency/tokens. Heuristic-only paths are gated behind explicit env vars and marked ok=False.
- **Every cited quote must be verbatim.** `services/tutor.py::_resolve_grounded_answer` validates + auto-corrects quotes against chunk content. Fabricated quotes get dropped; unsupported claims move to `unsupported_spans`.
- **Migrations are the schema source of truth.** Never `ALTER TABLE` at startup.
- **Test-gated, additive PRs.** Every PR ships small, keeps verify green, is independently shippable. Multi-day features land as 3-5 sub-PRs with visible sequencing.
- **No em dashes in prose. No AI-slop vocabulary.** See `DESIGN.md` voice notes (skill-imported).

## Current phase state (2026-04-29)

- Phase 0 + 1: complete.
- Phase 2 (frontend): functionally complete. The premium UI roadmap (8 ships) finished in this cycle. See `docs/roadmap/premium-ui-pass.md` for the spec and `docs/notes/2026-04-29-session-handoff.md` for the closeout notes. Motion system with 5 signature moments live. Cold launch p50 299 ms / p95 481 ms, well under 800 ms budget.
- Phase 3 (retrieval + grounded answers + evals): ~60% through. Hybrid retrieval + quote validation + eval harness landed. Reranker + job queue deferred.
- **Phase coach (NEW; Phase 1 of 2 complete):** calendar feed sync + WeekTimeGrid + stub coach landed in `169b84f`. Reads iCal feeds (Google / Apple / Outlook / Blackboard), renders the user's week, proposes study blocks where there's free time AND overdue SRS cards. Single rule (`free_block_overdue_srs`) ships; three more rules (`deadline_imminent`, `low_recent_review`, `gap_between_classes`) pre-listed in the schema CHECK and sketched in `services/planning/coach.py`. New tables via `migrations/0009_calendar_and_planning.sql`.
- Phase 4 (signing / notarization / Sparkle / telemetry / monetization): not started. Requires Apple Developer credentials and monetization/telemetry platform decisions.
- Phase 5 (sync / verticals / iOS companion / public API): not started.

## Open debts tracked

- ESLint 9 still on `.eslintrc.cjs` legacy config path. Flat-config migration pending.
- Swift-side menu dispatch test coverage is informal; XCTest coverage pending.
- Command palette (⌘K with action registry) is stubbed in `AppShell` but not implemented. Deferred from Phase 2 MVP.
- FLIP animations are approximated (not layout-perfect) when the source card and target header have very different aspect ratios. Acceptable for MVP; revisit if visual QA surfaces issues.
- **Toast primitive doesn't accept action buttons.** Suggestion dismiss has a `restoreSuggestion` API + endpoint ready (`POST /api/plan/suggestions/{id}/restore`) but no Undo button on the toast. Small primitive extension; documented in the Phase 2 plan in `docs/notes/2026-04-29-session-handoff.md`.
- **Calendar feed URLs stored plaintext-at-rest.** Bounded threat model: URLs are revocable secrets, redacted at every emission point via `services/calendar/validators.py::mask_url`. macOS Keychain is v2 work, planned alongside Gmail OAuth tokens (which are NOT trivially revocable).
- **`preact/compat lazy() + Suspense` is fragile under file://.** Verified failure mode: chunk loads, Suspense never re-renders the tree. Don't use render-time Suspense for code-splitting the bundled WKWebView app. Trigger code splits via user-click `await import(...)` instead. See `docs/notes/2026-04-29-session-handoff.md` § preact/compat.

## Handoff context

If you are a new Claude session opening this repo, read **`HANDOFF.md`** first. It points at every other doc in the right order.
