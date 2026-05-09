# Phase A — Mechanical Audit

**Date:** 2026-05-09
**Branch:** `main`
**Baseline commit:** `33b9b37e` (after legacy frontend + first-run tour removal)
**Scope:** All findings from machine-checkable tools. No fixes applied — this doc is the input to a separate refining sprint.

## Verify chain (clean)

| Check | Result |
|---|---|
| `swift build --package-path macos-app` | ✅ 1.91s, clean |
| `bun run tsc --noEmit` | ✅ clean |
| `bun run lint` | ✅ clean (with pre-existing ESLint 9 flat-config deprecation warning) |
| `bun run vitest run` | ✅ 70 files / 331 tests passing |
| `python -m unittest discover -s tests` | ✅ 340 tests, 1 skipped (pre-cleanup count was 320; +20 from cleanup baseline) |
| `python -m ruff check ai services evals tests main.py db.py routes api_models.py benchmarks` | ✅ clean |
| `python -m mypy --config-file mypy.ini` | ✅ no issues, 8 source files (mypy config is narrow — see Architectural-1) |
| `bun run build:macos` | ✅ 4.63s, JS 96.50 KB gz, CSS 32.78 KB gz |
| `bun audit --audit-level=moderate` | ⚠️ 2 moderate dev-only (vite path-traversal in `.map`, esbuild dev-server CORS) |

**LOC after cleanup:** Python 30,923 + TS/TSX 27,118 + Swift 1,730 = **~59.8 K**
**Tests:** 340 Python + 331 frontend = **671 total** (up from 616 pre-cleanup)
**Tech-debt markers:** 0 `any` in TS, 0 `@ts-ignore`/`@ts-nocheck`, 6 `eslint-disable`, 20 `# noqa` / `# type: ignore`, 1 TODO repo-wide

---

## CRITICAL findings

### CRIT-1: Live `ANTHROPIC_API_KEY` present in `.env` at repo root
- File: `.env` (gitignored, not in `git ls-files`)
- Risk: low for git push (`.env` and `.env.local` are in `.gitignore`), high for any zip/tar/manual share of the repo directory.
- Action: rotate the key in Anthropic console as a precaution since the value has been disclosed in screen sessions / terminal output. Add a clean-machine `.env.example` precaution to the runbook.
- Note: `README.md` already says *"Never commit .env. The gitignore excludes it; treat any past leak as a key to rotate."* — this is the user's own existing rule. The audit confirms it's still applicable.

### CRIT-2: Bandit B324 — SHA-1 used without `usedforsecurity=False` flag
- File: `services/documents.py:424`
- Severity: High (bandit), Confidence: High
- Reality: SHA-1 is almost certainly being used for **dedupe / fingerprinting**, not for security. Adding the `usedforsecurity=False` keyword silences bandit and makes intent explicit. Five-line fix.
- Verify by reading line 424 to confirm non-security usage before silencing.

---

## HIGH findings

### HIGH-1: 3 known CVEs in Python dependencies
- `pip 26.0.1` → CVE-2026-3219, CVE-2026-6357 — fix in `26.1`
- `python-multipart 0.0.26` → CVE-2026-42561 — fix in `0.0.27`
- pip itself is environment, not shipped — minor. python-multipart is in the FastAPI request stack and ships in production.

### HIGH-2: 2 moderate dev-only frontend CVEs (already documented, still open)
- `vite ≤ 6.4.1` — Path Traversal in Optimized Deps `.map` Handling (GHSA-4w7w-66w2-5vf9)
- `esbuild ≤ 0.24.2` — dev server CORS issue (GHSA-67mh-4wv8-2f99)
- Both dev-only: not present in shipped artifact. Closed by the chore-PR queued in this session's earlier `bun update` task.

### HIGH-3: ESLint 9 still on legacy `.eslintrc.cjs`
- The `lint` script wraps with `ESLINT_USE_FLAT_CONFIG=false` to keep eslintrc working under ESLint 9.
- Tracked debt; chore PR queued earlier this session.
- Cost of inaction: 1 deprecation warning per `bun run lint` run; ESLint 10 will hard-remove eslintrc support.

---

## MEDIUM findings — code complexity & maintainability

### MED-1: 11 functions at cyclomatic complexity D or worse (radon `cc -n D`)

| Function | File | Grade | CC |
|---|---|---:|---:|
| `ingest_document_record` | `services/ingestion/orchestrator.py:71` | **F** | 53 |
| `is_valid_concept_label` | `services/ingestion/concept_candidates.py:71` | **F** | 48 |
| `_segment_chunk_for_study` | `services/ingestion/topics.py:27` | **F** | 44 |
| `generate_artifact` | `services/artifact_studio.py:672` | E | 34 |
| `build_concept_payloads_from_chunks` | `services/ingestion/topics.py:171` | E | 34 |
| `build_momentum_engine` | `services/workspace.py:60` | E | 33 |
| `_format_expansion_markdown` | `services/notes/expand.py:158` | E | 32 |
| `_best_evidence_sentences` | `services/ingestion/answers.py:120` | D | 29 |
| `fetch_workspace_state_v2` | `services/workspace.py:304` | D | 29 |
| `build_phrase_candidates` | `services/ingestion/concept_candidates.py:144` | D | 26 |
| `_event_from_component` | `services/calendar/ical_parser.py:199` | D | 24 |

**Average complexity across 786 blocks:** A (4.6) — overall fine. The outliers are concentrated in the ingestion package. None are user-facing routes.

### MED-2: 5 modules at maintainability index below A (radon `mi`)

| File | Grade | MI |
|---|---:|---:|
| `services/artifact_studio.py` | **C** | 0.00 |
| `services/tutor.py` | **C** | 1.73 |
| `services/ingestion/concept_candidates.py` | C | 5.60 |
| `services/ingestion/topics.py` | B | 15.26 |
| `services/workspace.py` | B | 18.19 |

Three of the five (`artifact_studio.py`, `tutor.py`, `concept_candidates.py`) sit at the bottom of the C grade. These are the natural starting points for a Phase C deep-read.

### MED-3: 40 medium bandit findings — `B608` SQL string-construction
- Pattern: dynamic IN-clause with `?` placeholders, e.g. `f"SELECT … WHERE id IN ({','.join('?'*len(ids))})"`
- All locations use **parameterized placeholders** (`?`), so this is not real SQL injection — bandit can't statically tell the placeholders are bound. It's a false positive class.
- Action: add `# nosec B608` with a one-line comment explaining the pattern. Don't suppress globally; suppress per call-site so future legitimately-vulnerable string concatenation isn't missed.

---

## MEDIUM findings — frontend dead code (knip)

### MED-4: 2 unused source files
- `src/features/ask/components/AnswerMetaBar.tsx`
- `src/features/reader/hooks/useReaderMetadata.ts`

### MED-5: 2 unused dev dependencies (also flagged by depcheck)
- `openapi-typescript` — used by `script/generate-api-types.sh`. False positive: the script invokes it via shell, not via package import. Add to knip's `ignoreDependencies`.
- `prettier` — likely actually unused in CI; verify before removing.

### MED-6: 12 unused exports in non-design-system files

| Symbol | File |
|---|---|
| `clearRememberedReaderDocument` | `src/app/shell/useAppShell.ts` |
| `dismissToast` | `src/design-system/index.ts` (and re-export from `Toast/index.ts`) |
| `ASK_ANCHOR_DRAFTS_STORAGE_KEY` | `src/features/ask/anchorDrafts.ts` |
| `Button` | `src/features/library/components/SubjectCardGrid.tsx` |
| `documentsQuery` | `src/features/library/hooks/useDocumentsQuery.ts` |
| `paletteOpen, closePalette` | `src/features/palette/CommandPalette.tsx` |
| `formatTime` | `src/features/plan/utils/timezone.ts` |
| `ReaderDocumentViewForTests` | `src/features/reader/ReaderView.tsx` |
| `ApiTimeoutError, BackendOfflineError, isApiTimeout, isBackendOffline` | `src/services/api/errorMessages.ts` |
| `ensureMenuBus` | `src/services/native/menu.ts` |
| `duration, easing, motion, prefersReducedMotion, transition, transitions, useAnimation` | `src/design-system/motion.ts` (and re-exports) |

### MED-7: 24 unused exported types
- 22 are design-system primitive `*Props` types re-exported from index files (`BadgeProps`, `BoxProps`, etc.). These are intentional API surfaces for consumers — knip can't see the public-API intent. Add to knip ignore if knip ever lands in CI.
- 4 looked like deletion candidates but **are not**: `DuplicateDocumentRow`, `ConceptGraphNode`, `ConceptGraphEdge`, `DashboardActionTarget` in `src/services/api/endpoints.ts` are each referenced inside other exported interfaces (e.g. `DuplicateGroup.canonical: DuplicateDocumentRow`, `ConceptGraphResponse.nodes: ConceptGraphNode[]`). Knip flags them because nothing imports them by name; that's fine — they're load-bearing internal types. **Correction noted post-execution.**
- 2 are auto-generated from the schema (`webhooks`, `$defs`, `operations` in `types.gen.ts`) — leave as-is; regenerated on each `script/generate-api-types.sh` run.

---

## LOW findings — Python dead code (vulture)

### LOW-1: 4 confident dead imports / variables (`vulture --min-confidence 70`)
- `routes/calendar.py:21` — unused import `BackgroundTasks`
- `routes/calendar.py:33` — unused import `FeedURLRejected`
- `services/calendar/feed_client.py:34` — unused import `FeedURLRejected`
- `services/dashboard.py:312` — unused variable `last_studied_at` (100 % confidence)

Two of the three are imports of `FeedURLRejected` not used after a refactor. Trivial removals.

### LOW-2: 107 / 165 Python files would reformat
- `ruff format --check` shows the codebase is not auto-formatted. Behavior unchanged; formatting drift only.
- Action: run `ruff format` once, commit as a pure-format PR, add `ruff format --check` to CI. Order matters — do it as a single mechanical commit so blame stays clean.

---

## Architectural findings (low-effort observations from the mechanical pass)

### ARCH-1: `mypy --config mypy.ini` checks only 8 files
- Narrow config; the rest of the Python codebase is unchecked.
- Action: review `mypy.ini` and decide which packages to opt in incrementally. Adding `services/` first would cover the highest-value ground.

### ARCH-2: Madge — no circular dependencies
- ✅ Frontend dep graph is clean.

### ARCH-3: 0 circular Swift / Python deps tested
- Not measured (no `pydeps` run yet). Add to Phase B if needed; Carrel is small enough that visual inspection of `services/` imports is faster.

### ARCH-4: Per-file churn is low (1-3 commits per source file across full history)
- This is **good signal**: PRs are squash-merged and atomic, blame stays clean.
- Implication: hot-spot analysis (Phase C, "files most likely to be wrong because most-touched") will not be a productive lens for Carrel. The right Phase C lens is **largest files** (already known: `services/tutor.py` 1133 LOC, `services/artifact_studio.py` 886, `services/documents.py` 819) plus the MED-1 / MED-2 outliers.

---

## Categorization summary

| Category | Count |
|---|---:|
| Critical (security / secrets) | 2 |
| High | 3 |
| Medium | 4 (each with multiple sub-items) |
| Low | 2 |
| Architectural notes | 4 |

**Refining sprint candidates (top 20% by leverage):**

1. **CRIT-1** — rotate ANTHROPIC_API_KEY (5 min, but unavoidable)
2. **CRIT-2** — add `usedforsecurity=False` to `services/documents.py:424` (2 lines)
3. **HIGH-1** — bump `python-multipart` 0.0.26 → 0.0.27 (1 line in `requirements.txt`)
4. **HIGH-2** — land the queued `bun update` chore PR (vite + esbuild)
5. **HIGH-3** — land the queued ESLint flat-config chore PR
6. **MED-3** — add `# nosec B608` annotations across ~40 sites with one-line rationale (1 hour)
7. **LOW-1** — drop 3 unused imports + 1 unused variable (5 min)
8. **MED-4** — delete the 2 unused source files (`AnswerMetaBar.tsx`, `useReaderMetadata.ts`) (5 min)
9. **MED-5/6/7** — knip ignore-list for design-system primitive type re-exports + delete the 4 truly-dead exports (30 min)
10. **LOW-2** — `ruff format` + add to CI (one mechanical PR, 30 min)
11. **ARCH-1** — extend mypy coverage to `services/` (incremental opt-in)

Everything else (MED-1, MED-2 — complexity in `services/ingestion/orchestrator.py`, `artifact_studio.py`, `tutor.py`) belongs in **Phase B (architectural)** and **Phase C (hot-spot deep-read)**, not in this refining sprint. Premature refactor is the failure mode to avoid.

---

## What I deliberately did NOT run

- **Mutation testing (`mutmut`)** — high-cost, run only on the 5 most critical modules in Phase B+
- **Coverage (`pytest --cov`, `vitest run --coverage`)** — useful but slow; planned for Phase B
- **`semgrep --config=auto`** — pattern-based, planned for Phase B
- **Swift `periphery` / `swiftlint`** — not installed; Swift surface is only 1730 LOC, lower priority
- **Full read-through (Phase D)** — explicitly deferred per audit methodology

---

*This document is read-only. Acting on findings happens in a separate refining sprint after triage.*
