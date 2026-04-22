# UX Perfection Plan — Einstein Tutor

**Branch:** main · **Date:** 2026-04-23 · **Authored via:** /autoplan (inline planning)

## Goal

Lift Einstein from "functional phase-2 MVP" to "feels like a finished premium macOS reading tool." Prior session handled security, design-system drift, AI reliability, and one Rules-of-Hooks bug. This session closes the user-visible friction.

## Success criteria

After this lands, a user who opens the app should:
- See rich answers (emphasis, lists, code) instead of plain-text soup in Ask.
- Find any document in a library of 50+ without scrolling.
- Search inside a PDF with ⌘F like every other macOS reader.
- Know where they are in a study session ("7 of 18") and see a deliberate front→back transition.
- Preview a citation on hover before committing to the Reader flight.
- Retry a failed upload without re-dragging files.

## Scope — 6 initiatives, ordered by user impact

### I1 — Markdown rendering in Ask answers

**Problem.** `AnswerSummary` ([frontend/src/features/ask/components/AnswerSummary.tsx](frontend/src/features/ask/components/AnswerSummary.tsx)) and `ClaimList` render `summary` and `claim.text` as plain `<Text>`. When Claude produces `**emphasis**`, `- bullets`, `` `code` ``, or paragraph breaks, users see literal markdown punctuation. Looks unprofessional, hurts comprehension.

**Fix.** Ship a tiny inline markdown renderer (~60 LOC, zero deps) that handles the 95% case for tutor answers:
- Inline: `**bold**`, `*italic*`, `` `code` ``
- Block: paragraphs, `- ` and `1. ` lists, `> ` blockquotes, fenced code blocks, hard line breaks
- Everything escaped first to prevent XSS

Not in this pass: tables, images, links (not in tutor output by convention), full CommonMark compliance, KaTeX math. Math is a follow-up — the audit showed zero existing KaTeX integration; adding it is a separate initiative with bundle-size tradeoffs.

**Files.**
- New: `frontend/src/lib/markdown.tsx` — pure function `renderMarkdown(src: string): VNode[]`
- Modified: `AnswerSummary.tsx`, `ClaimList.tsx` — swap `<Text>{src}</Text>` for `<div>{renderMarkdown(src)}</div>`
- Tests: `frontend/tests/markdown.test.tsx` — covers each supported construct + XSS escape

**Verify.** Existing ask-view + ask-components vitest suites still pass. New markdown test suite passes. DESIGN.md voice preserved in the component's own copy.

### I2 — Library search + filter

**Problem.** `LibraryView` has no way to narrow a growing list. Audit confirmed: groups by subject only, no input, no filter chips. Users with 50+ docs scroll endlessly.

**Fix.** Add an always-visible search input at the top of Library:
- Filters by document title (substring, case-insensitive) and subject name
- Empty input → current grouped view unchanged
- Non-empty input → flat result list, preserving visual density
- Result count rendered as quiet caption ("12 matches")
- Keyboard: focused on mount if user navigated via `⌘3`, `/` shortcut to focus from elsewhere

**Files.**
- Modified: `frontend/src/features/library/LibraryView.tsx` — add search signal + filter memo
- Modified: `frontend/src/features/library/LibraryView.module.css` — search bar styling using existing tokens
- Tests: `frontend/tests/library/search-filter.test.tsx`

**Verify.** Existing library tests pass. New filter test covers empty, partial, zero-match, case-insensitive.

### I3 — Study progress indicator + front→back flip animation

**Problem.**
- No "N of M" counter during review — audit confirmed [StudyView.tsx](frontend/src/features/study/StudyView.tsx) has `completedCount` and `cards.length` but doesn't render them.
- Phase transitions (`front` → `back`) are instant state flips. DESIGN.md Tier-2 motion catalog includes `scalePress` and `fadeUp`; an SRS flip is a canonical use case for `scalePress` + opacity crossfade.

**Fix.**
- Render `{completedCount + 1} of {cards.length}` above the card during review phases.
- Animate front→back transition: the card fades out (120ms) while a brief scale-down (0.98) runs, then back content fades up (180ms) with scale back to 1. Respects `prefers-reduced-motion`. Uses `--dur-fast` + `--dur-base` tokens.

**Files.**
- Modified: `StudyView.tsx` — progress JSX; key the back content on phase for Preact to treat it as remount (triggers CSS enter animation)
- Modified: `StudyView.module.css` — add `.cardEnter` + `.cardExit` keyframes scoped to the flip

**Verify.** Reduced-motion user sees instant swap. Keyboard shortcut tests unaffected.

### I4 — Citation chip hover preview

**Problem.** [CitationChip.tsx](frontend/src/features/ask/components/CitationChip.tsx) is click-only. Users who want to glance at a citation without leaving Ask must click it and fire the full SM-2 flight. Too aggressive for exploration.

**Fix.** On hover (or keyboard focus), show a Tooltip-rendered preview of the chunk's verbatim quote + page/section. Delay 300ms so casual mouse passage doesn't flash tooltips everywhere. Uses the existing `Tooltip` primitive so the surface is consistent.

**Files.**
- Modified: `CitationChip.tsx` — wrap in Tooltip, pass quote + metadata
- Modified: `Citations.tsx` or wherever chips are composed — pass the quote through props (prop may already exist; reuse)
- Tests: extend existing `ask-components.test.tsx` with hover/focus assertion

**Verify.** Existing citation click (SM-2) behavior unchanged. Tooltip respects reduced motion.

### I5 — Upload retry-failed + outcome clarity

**Problem.** `ImportDropzone` reports per-file outcomes but offers no retry affordance. User dragged 20 PDFs, 3 failed with network hiccups, they must re-select those 3 manually.

**Fix.**
- Outcome summary gains a "Retry failed (N)" button when any outcomes are `error` (not `duplicate` — those are final).
- Click retries only the failed `File` objects, preserving subject assignment.
- Visual grouping of outcome rows: failures first (with retry icon), duplicates collapsed behind "N duplicates skipped" disclosure, successes muted.

**Files.**
- Modified: `ImportDropzone.tsx` — outcome grouping + retry button
- Modified: `useUploadDocument.ts` — expose a `retryFailed(files)` method or reuse existing surface with filtered list
- Tests: `frontend/tests/library/import-dropzone.test.tsx` extended

**Verify.** Happy-path upload unchanged. Retry re-runs only failed set.

### I6 — Reader in-document search (⌘F)

**Problem.** `PdfToolbar` has page input + prev/next + zoom but no search. Users default to browser Find, which breaks in a native WKWebView shell. Every competing reader (Preview, Acrobat, Arc, Readwise Reader) has ⌘F.

**Fix.** Use pdfjs's `PDFFindController` (bundled with `pdfjs-dist`, no new dep):
- ⌘F toggles a slim search bar under the toolbar
- Enter / ↓ → next match, ⇧Enter / ↑ → previous
- Results counter ("3 of 12") right-aligned
- Matches highlight in the text layer with `color-mix` accent tint (respecting theme)
- Esc closes the search bar and clears highlights

**Files.**
- Modified: `frontend/src/features/reader/components/pdf/PdfToolbar.tsx` or new `PdfSearchBar.tsx`
- Modified: `frontend/src/features/reader/hooks/usePdfDocument.ts` or similar to own the FindController
- Modified: `PdfViewer.tsx` to wire the find controller to the text layer
- Tests: `frontend/tests/reader/pdf-search.test.tsx` (mocked FindController — real pdfjs is slow in jsdom)

**Verify.** Existing reader test suites pass. New test asserts open/close/next/prev.

## Out of scope this pass

- KaTeX math rendering — needs its own bundle-size decision (~45KB gz). Flagged as follow-up.
- Global command palette search across documents + cards + notes — requires a backend search endpoint; scope too large for this session.
- Reader annotations — Phase 3 territory, not polish.
- First-run onboarding tour — nice to have, but blocked on content decisions.
- Settings modal — no concrete settings currently ship; wait until there's something to configure.
- Study session stats + undo rating — valid polish, parking for next cycle.
- Background task status bar — needs a backend event stream; substantial.

## What already exists (do not reinvent)

- Design tokens: `--dur-fast`, `--dur-base`, `--ease-*`, `--shadow-*`, `--color-accent`, `--text-*`, `--space-*`. Use these, do not introduce new values.
- Motion keyframes: `animations.css` already has `fadeUp`, `scalePress`, `shimmer`. Reuse for I3.
- Tooltip primitive: `frontend/src/design-system/primitives/Tooltip/`. Reuse for I4.
- Error message pattern from prior session: `frontend/src/features/ask/errorMessages.ts`. Extend the pattern for upload errors in I5.
- pdfjs-dist FindController: bundled dep, no new install needed for I6.
- Query helper: `@/lib/query` `useQuery`. Reuse for any new fetch in I2/I5.

## Risks

1. **Markdown rendering + XSS.** Must escape every user-visible string before parsing. No `dangerouslySetInnerHTML`. Tests must cover injection.
2. **Flip animation jank on older hardware.** Only animate `transform` + `opacity`. Never `height`/`width`. Gate on `prefers-reduced-motion`.
3. **PDF search perf on large docs.** FindController runs async; need loading state for "searching..." on >200-page PDFs.
4. **Library filter on large lists.** Cheap substring match on title is fine up to a few thousand docs. Memoize via `useMemo`.
5. **Bundle size creep.** Total code added ≤ 8KB gz. Measure before/after vite build. Current baseline after prior session: `161.08 kB` index.js, `52.77 kB` gzipped.

## Test plan

- `frontend/tests/markdown.test.tsx` — new. Covers bold/italic/code/lists/breaks/code-fence/blockquote + XSS escape.
- `frontend/tests/library/search-filter.test.tsx` — new. Covers empty/partial/no-match/case-insensitive.
- `frontend/tests/ask-components.test.tsx` — extend. Citation hover shows tooltip; click still fires flight.
- `frontend/tests/library/import-dropzone.test.tsx` — extend. Retry button fires only on failed outcomes.
- `frontend/tests/reader/pdf-search.test.tsx` — new. Mock FindController; verify open/close/next/prev/esc.
- `frontend/tests/study/*.test.tsx` — if any exist, extend. Progress indicator renders; reduced-motion test.
- Full `vitest run` must stay green (161 tests today).
- `tsc --noEmit`, `eslint --max-warnings 0`, `vite build` must stay clean.
- No ruff/unittest impact (backend untouched).

## Verify chain

1. `corepack pnpm --dir frontend typecheck`
2. `corepack pnpm --dir frontend lint`
3. `corepack pnpm --dir frontend test`
4. `corepack pnpm --dir frontend build:macos` (or equivalent `vite build`)
5. `./.venv/bin/python -m ruff check ai services evals tests main.py db.py routes api_models.py benchmarks`
6. `./.venv/bin/python -m unittest` (baseline preserved)
7. Bundle size check: `ls -la frontend/dist/assets/index.js` — must be < `172 kB` uncompressed (current `161 kB` + 8 kB headroom).

## Commit plan

Six commits, one per initiative, with verify run between each so regressions surface immediately:
- `feat(ask): render markdown in grounded answer claims + summary`
- `feat(library): keyword search across documents + subjects`
- `feat(study): progress indicator + front-to-back flip animation`
- `feat(ask): citation chip hover tooltip with chunk preview`
- `feat(library): retry-failed on upload outcome + clearer grouping`
- `feat(reader): in-document search (⌘F)`

Landing strategy: each commit is independently revertible. If I6 (pdfjs FindController) turns out to be hairier than estimated, I1-I5 still land.
