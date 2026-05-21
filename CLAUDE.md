# Carrel — Project Context for Claude

Local-first, source-grounded AI study and research workspace for macOS. Native Swift + SwiftUI shell wraps a WKWebView loading a bundled Preact + TypeScript + Vite app. SQLite storage, FastAPI backend, Claude API for grounded answers with hybrid FTS5 + sqlite-vec retrieval. Renamed from Einstein Tutor; some internal identifiers (`com.madu.EinsteinDesktop` bundle, `EinsteinDesktop.app`, `data/einstein_tutor.db`) remain on the legacy names — see `docs/notes/2026-04-29-carrel-rename.md` for the deferred-rename list.

## Stack

- **Native shell:** Swift + SwiftPM, macOS 14+. `macos-app/Sources/EinsteinDesktopApp/`. WKWebView loads the bundled `app.new.html`. Menu bar.
- **OCR sidecar:** `EinsteinIngestionBridge` executable using PDFKit + Vision for PDF text + OCR extraction.
- **Frontend:** `frontend/` — Preact 10, TypeScript strict, Vite 6, CSS Modules + design tokens. Pinned via pnpm 9.12.0. Builds to `macos-app/Resources/app.new.html` via `frontend/scripts/build-macos.mjs`.
- **Backend:** FastAPI + Pydantic. `main.py` is 71 LOC of wiring only. Real logic in `routes/*` and `services/*`. `services/ingestion/` and `services/extraction/` are packages, not monoliths.
- **DB:** SQLite with WAL + FTS5 + sqlite-vec. Versioned migrations in `migrations/NNNN_*.sql` applied by `db.py::apply_migrations`. Schema is migrations-sourced; `schema.sql` is legacy.
- **AI:** Claude API via `ai/router.py`. Models: `claude-haiku-4-5` (fast), `claude-sonnet-4-6` (balanced), `claude-opus-4-7` (deep). Local default on macOS 26+ Apple Silicon with Apple Intelligence enabled and en_US locale: Apple Foundation Models via `ai/afm_client.py` and the `EinsteinAFMBridge` Swift sidecar. Ollama (`ai/ollama.py`) is the legacy fallback for macOS 14/15 or Intel Macs. Provider auto-resolution lives in `ai/providers.py` (`select_provider` stays a pure env reader; `probe_all_providers` gives a live per-provider availability verdict). Structured output via `request_tool_call` with forced tool use on Claude; system-prompt enforcement + post-hoc JSON parse on AFM and Ollama (neither has runtime guided-generation as of their respective public APIs). All calls return typed `ClaudeCallResult` with latency + token + cache metrics. Silent fallback to heuristic is forbidden; failures are visible.
- **AI settings (user-facing):** Provider choice and the Claude API key are configurable from the in-app **Settings** page (`frontend/src/features/settings/`, sidebar entry / `⌘,`), backed by `routes/settings.py` (`GET`/`POST /api/settings/ai`). The provider choice persists to the `app_settings` table; the Claude API key persists via `services/secret_store.py` to the macOS Keychain (memory fallback for CI/unsigned) — never SQLite or `.env`. `main.py` hydrates both into `os.environ` at startup before any provider is built. Switching the provider at runtime is a **hot-swap, no restart**: the route mutates `os.environ` and drops the cached provider/AFM singletons. The `EINSTEIN_AI_PROVIDER` / `CARREL_AI_PROVIDER` env var still works as the startup default.
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
./.venv/bin/python -m ruff format --check /Users/madu/Desktop/Codex/ai /Users/madu/Desktop/Codex/services /Users/madu/Desktop/Codex/evals /Users/madu/Desktop/Codex/tests /Users/madu/Desktop/Codex/main.py /Users/madu/Desktop/Codex/db.py /Users/madu/Desktop/Codex/routes /Users/madu/Desktop/Codex/api_models.py /Users/madu/Desktop/Codex/benchmarks
./.venv/bin/python -m unittest tests.test_ai_router tests.test_tutor_grounded tests.test_retrieval_hybrid tests.test_retrieval_vector tests.test_retrieval_fts tests.test_db_migrations tests.test_phase0_foundation tests.test_phase0_batch_b tests.test_einstein_tutor tests.test_learning_os tests.test_evals_runner -v
./script/build_and_run.sh --verify
./.venv/bin/python -m benchmarks.phase0 --compare /Users/madu/Desktop/Codex/data/benchmarks/baseline.json --fail-on-regression
bash /Users/madu/Desktop/Codex/tests/test_watchdog_kill.sh
swift test --package-path /Users/madu/Desktop/Codex/macos-app
```

Optional pre-release step (skipped on CI and on machines without Apple Foundation Models). Requires macOS 26+ Apple Silicon, Apple Intelligence enabled, en_US primary locale, and a built bridge under `macos-app/.build` or a packaged `.app`:

```bash
CARREL_RUN_AFM_INTEGRATION=1 ./.venv/bin/python -m unittest tests.integration.test_afm_real_bridge -v
```

Every PR lands green on the full chain or it does not land.

## Local pre-commit hook

Run once per fresh clone:

```bash
bash script/install-hooks.sh
```

This activates the committed hook at `.githooks/pre-commit`. On every
`git commit` it runs the fast subset of the verify chain on staged
files only: `ruff format --check`, `ruff check`, and (if frontend
files staged) `pnpm lint`. The slow checks (typecheck, tests, build,
benchmarks) stay in CI. Total local budget: <5s.

The hook is committed to the repo so it's identical for every
contributor. Bypass with `--no-verify` only for genuine emergencies;
the full CI chain still runs against the push regardless.

## Running the autonomous routine

Two scripts at `script/` arm and supervise unattended `/carrel-build`
sessions:

```bash
./script/start-autonomous.sh /carrel-build          # one armed session
./script/autonomous-watchdog.sh                     # relaunch loop
nohup ./script/autonomous-watchdog.sh > /tmp/carrel-watchdog.log 2>&1 &
```

`start-autonomous.sh` exports `CARREL_AUTONOMOUS=true` so the four
hooks at `.claude/hooks/` (`route-task`, `audit-gate`, `debate-trigger`,
`score-loop`) actually fire, and passes `--permission-mode bypassPermissions`
so claude doesn't deadlock on its own UI prompts. The `audit-gate.py`
hook is the actual safety net. Without `CARREL_AUTONOMOUS=true` the
hooks exit silently so ad-hoc edits don't trigger the auditor + rater.

`autonomous-watchdog.sh` relaunches after rate-limit freezes using
idleness-primary detection (log growth < 512 B in 10 min ⇒ kill) with
a tight `LIMIT_PATTERN` regex fast-path gated on idleness ≥ 60s so
prose mentioning "rate limit" cannot false-positive. Each relaunch is
safe because `/carrel-build` reads `TODOS.md` + the active plan at the
top of every iteration; state lives in the filesystem, not the session.

Halt the routine with:

```bash
touch .claude/HALT       # graceful: finishes current cycle and exits
```

The HALT file is checked at the top of every watchdog iteration, inside
the poller, and during the retry sleep, so a graceful stop registers
within seconds. Verify the kill path with `bash tests/test_watchdog_kill.sh`.

## Benchmarks + budgets

- **Cold launch:** p50 ≤ 800ms target, current 465ms p50, warm 200-250ms. Gate: `script/measure_cold_launch.sh` + `benchmarks/cold_launch_diff.py`.
- **Grounded answer:** p50 ~4s, p95 ~7s (Sonnet 4.6 latency envelope). Acceptable given product shape.
- **Ingestion:** phase0 benchmark fails on regression vs `data/benchmarks/baseline.json`.
- **Quality:** `evals-full` suite must keep `groundedness@8 ≥ 0.7` and `quote_validity ≥ 0.95` (currently 0.857 + 1.0 after PR-D3d quote retrofit, reaffirmed 2026-05-19 post-T05+T06 citation rename). `--mode smoke` is the fast retrieval-only path and does NOT produce `quote_validity`; the canonical quality bar is `--mode full`.
- **Side-by-side `RETRIEVAL_USE_NODES` comparison run (T08 reopen, post-T57):** the chunks-path run keeps the default env; the nodes-path run sets BOTH `RETRIEVAL_USE_NODES=true` AND `INGEST_USE_DOCLING=true` so the eval's isolated DB populates the `nodes` / `node_fts` / `node_embeddings` tables via the Docling typed-node ingest path. Without `INGEST_USE_DOCLING=true` on the nodes-path run the nodes tables stay empty and the comparison regresses vacuously. The eval-harness id-space dispatch (`tutor_primary_retrieval` in `services/tutor.py` + `RetrievedNode` handling in `evals/run_evals.py::run_case`) is wired in T57. Commit comparison reports under `evals/reports/compare-*.md`.

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
- **Flashcards focus campaign — COMPLETE 2026-05-13.** Plan in `docs/plans/flashcards-focus-2026-05-09.md`. PRs 1–3 + 7 shipped earlier; PR 4 (citation reveal on the back face) shipped 2026-05-12; PR 5.1 (cloze, ADR 0002) and PR 5.2 (reverse-pair, ADR 0003) shipped 2026-05-13; PR 6 (session pacing) fully shipped: item 1 ETA (87f7e867), item 2 per-card timing (2f9e248d, 2026-05-10), item 3 defer-this-card (b3f7deda+e08d302f+66da9d7d), item 4 streak (5993a248).
- **Phase coach (Phase 1 + Phase 2 complete):** calendar feed sync + WeekTimeGrid + stub coach landed in `169b84f`. Reads iCal feeds (Google / Apple / Outlook / Blackboard), renders the user's week, proposes study blocks where there's free time AND overdue SRS cards. All four rules ship: `free_block_overdue_srs` (v1, Phase 1), `deadline_imminent` (Phase 2, commit `940966bf`, study_block before exam/midterm/final/quiz deadlines), `low_recent_review` (Phase 2, commit `b12359d2`, review_block when >=5 SRS cards last touched 7+ days ago and not overdue), and `gap_between_classes` (Phase 2, this commit, catchup micro-session when two adjacent calendar events at the same location are 30-120 min apart). `refresh_active_suggestions` dedupes on `(kind, start_at, reason_code)` so different rules' same-`kind` candidates keep their distinct signals visible across refreshes. Tables via `migrations/0009_calendar_and_planning.sql`.
- Phase 4 (signing / notarization / Sparkle / telemetry / monetization): not started. Requires Apple Developer credentials and monetization/telemetry platform decisions.
- Phase 5 (sync / verticals / iOS companion / public API): not started.

## Open debts tracked

- Swift-side menu dispatch test coverage was informal. XCTest scaffold added 2026-05-16 (`macos-app/Tests/EinsteinDesktopTests/`, 75/75 green) now covers `UploadMimeTypes.swift`, `LocalApiToken.swift`, `LaunchTelemetry` end to end (`format(milliseconds:)`, `markLaunch()`, `markInteractive(route:performanceNowMilliseconds:)` via a `dup2`-based `StderrCapture` harness), and `MainMenuBuilder.swift` end to end (every submenu's structure + key equivalents + command-bus wiring; `WebViewBridgeDispatcher.escapeForJSStringLiteral`; `WebViewRegistry` register/unregister/current). The `MainMenuBuilder` coverage surfaced and fixed a latent bug in `install()` where `NSApp.windowsMenu`/`helpMenu` were never wiring because `mainMenu.item(withTitle:)?.submenu` returned nil (outer `NSMenuItem` titles were empty). Item closed.
- Command palette (⌘K with action registry) is stubbed in `AppShell` but not implemented. Deferred from Phase 2 MVP.
- FLIP animations are approximated (not layout-perfect) when the source card and target header have very different aspect ratios. Acceptable for MVP; revisit if visual QA surfaces issues.
- ~~Toast primitive doesn't accept action buttons.~~ **Resolved.** The `ToastInput.action` field (label + onClick) shipped in `frontend/src/design-system/primitives/Toast/Toast.tsx`; the suggestion-dismiss flow in `frontend/src/features/plan/PlanView.tsx::handleDismissSuggestion` wires the Undo action to `restoreSuggestion(id)` and toasts success/error. Vitest coverage at `Toast.test.tsx::"Clicking a toast action runs the callback and dismisses the toast"`.
- **Calendar feed URLs stored plaintext-at-rest.** Bounded threat model: URLs are revocable secrets, redacted at every emission point via `services/calendar/validators.py::mask_url`. macOS Keychain is v2 work, planned alongside Gmail OAuth tokens (which are NOT trivially revocable).
- **`preact/compat lazy() + Suspense` is fragile under file://.** Verified failure mode: chunk loads, Suspense never re-renders the tree. Don't use render-time Suspense for code-splitting the bundled WKWebView app. Trigger code splits via user-click `await import(...)` instead. See `docs/notes/2026-04-29-session-handoff.md` § preact/compat.

## Imported conventions from Next.js AGENTS.md (2026-05-16)

After reading Vercel's `AGENTS.md` (mirrored at `CLAUDE.md` in their repo), the following habits are now in force for Carrel sessions. Each maps onto a real Carrel constraint, not blind copying.

### Context-efficient workflows

- **Grep before Read.** Find line numbers first, then Read with `offset`/`limit`. Don't re-read sections you already saw without intervening edits. Treat `dist/`, `node_modules/`, `frontend/src/services/api/types.gen.ts`, and `data/` as search-only.
- **Capture once, analyze repeatedly.** For slow runs (`./script/build_and_run.sh`, the verify chain, eval suites, phase0 benchmarks), tee to `/tmp/<name>.log` and grep the log. Re-running burns minutes and the prompt cache.
- **Batch edits before validating.** Group related edits across files, then run the smallest sufficient check: `pnpm typecheck` is ~seconds; the full verify chain is minutes. Only escalate to the full chain when batches are coherent.

### Read local context before editing

Carrel has no nested `README.md` files, but `docs/notes/` and `docs/adr/` carry the equivalent. Before editing under `services/<slice>/` or `frontend/src/features/<slice>/`, check `docs/notes/` for any recent entry that names the slice. The Apr 28+29 notes contain non-obvious gotchas (route-split Suspense, FLIP edge cases, calendar URL plaintext) that the code alone doesn't reveal.

### Secrets and env safety

- Never print or paste secret values (`ANTHROPIC_API_KEY`, the local-API token, future Apple Developer credentials, calendar feed URLs) in chat, commits, or shared logs.
- Mirror CI env names and modes exactly. Do not inline literal secret values in shell commands.
- If a required secret is missing locally, stop and ask the user rather than inventing placeholders.
- The local-API token is injected via `WKUserScript` at runtime. Never commit it; never log it.

### Commit and PR style

- Do not add "Generated with Claude Code" or co-author footers to commits or PRs. Carrel is shipped by a human; assistant context stays out of the git log.
- Keep commit titles concise; put rationale in the body.
- Default PRs to draft. Do not `gh pr ready` unless the user says so.

### Task decomposition and verification

Sharpening Carrel's existing "Test-gated, additive PRs" rule with AGENTS.md framing: every step produces an independently checkable result before the next step begins. Choose the smallest verification that proves the change is correct, not the largest. The verify chain is slow; respect it.

## Primitives and helpers added with the AGENTS.md import (2026-05-16)

These ship as additive utilities. Existing call sites are unchanged. Use them rather than hand-rolling new ones.

| Surface | Path | Use it when |
|---|---|---|
| `ErrorBoundary` | `frontend/src/design-system/primitives/ErrorBoundary/` | Wrap any subtree so a render throw can't blank the whole app. Class component using `componentDidCatch`. No Suspense. |
| `LoadingBoundary` | `frontend/src/design-system/primitives/LoadingBoundary/` | Show a fallback (Skeleton, Spinner) while a `loading` flag is true. Pure props. No Suspense. |
| `Markdown` | `frontend/src/design-system/primitives/Markdown/` | Render notes, citations, grounded answers as rich text. Outputs VNodes directly (no `innerHTML`). Accepts a `components` prop for MDX-style overrides (citation chips, custom code blocks). Zero new deps. |
| `streamSse<T>`, `streamTextDeltas` | `frontend/src/services/api/streaming.ts` | Consume Server-Sent Events from the backend. Uses fetch + `ReadableStream` so the local-API token still travels by header. Use this, not `EventSource`. |
| `uploadWithProgress<T>` | `frontend/src/services/upload/withProgress.ts` | Upload a file with `xhr.upload.onprogress`. `fetch` cannot report upload progress; the dropzone UX needs XHR. |
| `stream_claude_text` | `ai/streaming.py` | Yield Claude text deltas for prompt streaming. Pattern endpoint; the citation-validated path stays in `services/tutor.py`. |
| `POST /api/tutor/query/stream` | `routes/tutor.py` | Frontend-facing SSE endpoint demoing the pattern. Emits `{text: "..."}` chunks. Not yet wired into `AskView`; that's a separate design call (streaming with citation validation is non-trivial). |

Patterns deliberately not imported: full `@next/mdx` (heavy; we hand-rolled a minimal subset), Suspense-driven streaming (broken under `file://`), App Router parallel routes (Preact router has no equivalent).

## Handoff context

If you are a new Claude session opening this repo, read **`HANDOFF.md`** first. It points at every other doc in the right order.
