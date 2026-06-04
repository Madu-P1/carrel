# Carrel — Project Context for Claude

Local-first, source-grounded AI study and research workspace for macOS. Native Swift + SwiftUI shell wraps a WKWebView loading a bundled Preact + TypeScript + Vite app. SQLite storage, FastAPI backend, Claude API for grounded answers with hybrid FTS5 + sqlite-vec retrieval. Renamed from Einstein Tutor; some internal identifiers (`com.madu.EinsteinDesktop` bundle, `EinsteinDesktop.app`, `data/einstein_tutor.db`) remain on the legacy names — see `docs/notes/2026-04-29-carrel-rename.md` for the deferred-rename list.

## Stack

- **Native shell:** Swift + SwiftPM, macOS 14+. `macos-app/Sources/EinsteinDesktopApp/`. WKWebView loads the bundled `app.new.html`. Menu bar.
- **OCR sidecar:** `EinsteinIngestionBridge` executable using PDFKit + Vision for PDF text + OCR extraction.
- **Frontend:** `frontend/` — Preact 10, TypeScript strict, Vite 6, CSS Modules + design tokens. Pinned via pnpm 9.12.0. Builds to `macos-app/Resources/app.new.html` via `frontend/scripts/build-macos.mjs`.
- **Backend:** FastAPI + Pydantic. `main.py` is 71 LOC of wiring only. Real logic in `routes/*` and `services/*`. `services/ingestion/` and `services/extraction/` are packages, not monoliths.
- **DB:** SQLite with WAL + FTS5 + sqlite-vec. Versioned migrations in `migrations/NNNN_*.sql` applied by `db.py::apply_migrations`. Schema is migrations-sourced; `schema.sql` is legacy.
- **AI:** Claude API via `ai/router.py`. Models: `claude-haiku-4-5` (fast), `claude-sonnet-4-6` (balanced), `claude-opus-4-7` (deep). Local default on macOS 26+ Apple Silicon with Apple Intelligence enabled and en_US locale: Apple Foundation Models via `ai/afm_client.py` and the `EinsteinAFMBridge` Swift sidecar. Ollama (`ai/ollama.py`) is the legacy fallback for macOS 14/15 or Intel Macs. Provider auto-resolution lives in `ai/providers.py`. Structured output via `request_tool_call` with forced tool use on Claude; system-prompt enforcement + post-hoc JSON parse on AFM and Ollama (neither has runtime guided-generation as of their respective public APIs). All calls return typed `ClaudeCallResult` with latency + token + cache metrics. Silent fallback to heuristic is forbidden; failures are visible. **Build note:** the `EinsteinAFMBridge` sidecar needs the FoundationModels macro plugin (`@Generable` / `@Guide`), which ships in full Xcode 26+, not the Command Line Tools. `build_and_run.sh` builds it only on a capable toolchain (passing `-DCARREL_AFM`) and skips it otherwise, so Carrel still installs and runs on Claude or Ollama. See the `EinsteinAFMBridge/main.swift` header.
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
./.venv/bin/python -m unittest tests.test_ai_router tests.test_tutor_grounded tests.test_retrieval_hybrid tests.test_retrieval_vector tests.test_retrieval_fts tests.test_db_migrations tests.test_phase0_foundation tests.test_phase0_batch_b tests.test_einstein_tutor tests.test_learning_os tests.test_evals_runner tests.test_memory_pressure tests.test_verify tests.test_verify_stream tests.test_quote_check tests.test_align tests.test_briefs tests.test_briefs_routes -v
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
- **Provider provenance on every result.** `ClaudeCallResult.provider`, `GroundedAnswer.provider`, `VerifyResult.provider`, `TutorQueryResponse.provider`, and `VerifyResponse.provider` carry the producing provider (`claude` / `afm` / `ollama` / `null`). Defaults: `"unknown"` on `ClaudeCallResult` (visible sentinel for misuse), `""` on the higher-level dataclasses and Pydantic models. Free string, not a `ProviderKind` enum, so the wire format stays forward-compatible. Added T64 Phase 2 (`docs/plans/answer-quality-2026-05-26.md`).
- **Every cited quote must be verbatim.** `services/tutor.py::_resolve_grounded_answer` validates + auto-corrects quotes against chunk content. Fabricated quotes get dropped; unsupported claims move to `unsupported_spans`.
- **Structural nodes are never citable.** `services.retrieval.node_type_router.NON_CITABLE_NODE_TYPES` is the single source of truth for non-citable types (currently `{heading, header, footer}`), imported by `services.tutor` and `evals.run_evals`. New ingestion pipelines and new citation surfaces must import the constant rather than re-deriving the set. Headings reach retrieval as FTS beacons via `node_fts` on `heading_path`, not as direct citations. See `docs/notes/2026-05-22-structural-citation-gate.md` for the design rationale; Gate 1 (chunks-path heuristic for the structurally-untyped path) is tracked in TODOS.md backlog.
- **Migrations are the schema source of truth.** Never `ALTER TABLE` at startup.
- **Test-gated, additive PRs.** Every PR ships small, keeps verify green, is independently shippable. Multi-day features land as 3-5 sub-PRs with visible sequencing.
- **No em dashes in prose. No AI-slop vocabulary.** See `DESIGN.md` voice notes (skill-imported).

## V2 strategic state (2026-05-26)

Carrel was repositioned on **2026-05-22** as an **independent AI verification layer for high-stakes AI output** (litigation pre-flight wedge). See [ADR-0008](docs/adr/ADR-0008-v2-pivot-validation-first-sequencing.md) for the pivot decision and validation-first sequencing; design doc at `/Users/madu/.gstack/projects/Codex/madu-main-design-20260522-015141.md`. V2 Stage 1 shipped on main 2026-05-26 (PR #82): typed-node defaults flipped on ([ADR-0006](docs/adr/ADR-0006-typed-node-defaults-on.md)), `Citation.node_type` + non-prose drop gate, CourtListener case-existence, holding-match verifier, `/api/verify` route, `VerifyView` UX. The tutor surface is structurally intact; it is the substrate for the verification engine, not the product.

**Active queue:** T64 (answer-quality investigation, blocker) → T65 (30-day validation test prep) → T66 (validation test run) → T67 (Stage 2/3 design, conditional on T66 verdict). V2 polish (T59-T63) paused. Chunks→nodes migration (T13-T58) deferred. See AUTONOMOUS_WORK_PLAN.md.

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
