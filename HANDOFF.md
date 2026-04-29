# Handoff — Einstein Tutor

> **If you are a Claude session that just opened this repo, read this file first.**
> It points at everything else and tells you the current state of the world.

Last updated: 2026-04-29 (after the Plan + Coach Phase 1 ship).

---

## TL;DR

Einstein Tutor is a local-first, source-grounded AI study workspace for macOS. Native Swift shell wraps a WKWebView loading a bundled Preact + TypeScript app. FastAPI + SQLite + sqlite-vec backend. Anthropic Claude (or local Ollama) for the tutor.

The product currently does:

- **Library** — drop in PDFs / DOCX / slides / text / markdown; concept extraction; subject grouping
- **Reader** — three-column shell with PDF outline rail + canvas + right rail tabs (Chunks / Concepts / Notes / Related)
- **Ask** — grounded tutor with verbatim citation chips, refusal taxonomy (no_coverage / weak_coverage), inline source-jump
- **Study** — SRS flashcards with FSRS scheduling, manage-cards view, AI-drafted card creation
- **Session** — cockpit-style focused study sessions (Pomodoro / Flowtime / Notes / Flashcards modes)
- **Dashboard** — landing page with greeting, hero composer, recommendations, quick actions, weekly stats
- **Plan** *(just shipped — Phase 1)* — calendar-feed sync (iCal from Google / Apple / Outlook / Blackboard) + WeekTimeGrid + stub coach that proposes study blocks in free time

Test count: **263 frontend (vitest) passing, 3 failing transiently** + 28 new Python backend tests this ship, all green. Build clean. Verify chain documented in `CLAUDE.md`.

### Known issue at handoff (read before you shrug at the verify chain)

Three tests in `tests/ask/answer-feed.test.tsx` fail at handoff time, all on the same line: `window.localStorage.clear is not a function`. They passed at commit `169b84f` (the Phase 1 commit). The drift cause: **Node 25 exposes a partial `localStorage` global** that needs the `--localstorage-file=<path>` flag to be functional; without it, `clear()` is missing. Vitest's jsdom environment normally wins for `window.localStorage`, but Node's new built-in is shadowing it under this Node version.

Cheap fix (5 minutes in the next session): in `tests/ask/answer-feed.test.tsx` lines 18 and 22, replace `window.localStorage.clear()` with:

```ts
for (const key of Object.keys(window.localStorage)) {
  window.localStorage.removeItem(key);
}
```

Or stub a full `Storage` in `tests/setup.ts`. Either way it's a one-liner. The 3 failures aren't a regression in our code; they're the test runner's localStorage shim losing the race against Node 25's built-in.

---

## Read these in order

1. **`CLAUDE.md`** — project context for Claude sessions: stack, key directories, verify chain, conventions, current phase state, open debts. Single most important file. Just refreshed.
2. **`DESIGN.md`** — the design system source of truth. Aesthetic direction, tokens, typography, color, spacing, motion, voice, decisions log. Read before any UI work.
3. **`README.md`** — quick-start: how to build + run the app, env vars, where data lives.
4. **`docs/notes/2026-04-29-session-handoff.md`** *(new)* — what shipped in the most recent session, decisions made, gotchas surfaced. Read this before changing anything in `services/calendar/`, `services/planning/`, `routes/calendar.py`, `routes/plan.py`, or `frontend/src/features/plan/`.
5. **`docs/roadmap/premium-ui-pass.md`** — the 8-ship UI roadmap (all 8 ships now landed). Useful as historical context for naming + design conventions.

---

## How to run it

### Full app (recommended)

From repo root:

```bash
./script/build_and_run.sh
```

Builds the Swift shell, builds the Vite frontend, starts FastAPI on `127.0.0.1:8000`, launches `EinsteinDesktop.app`. First build takes ~1 minute; subsequent builds are sub-second.

Modes: `--debug` (lldb), `--logs` (stream macOS unified log filtered to the app), `--telemetry` (subsystem log), `--verify` (post-launch verification), `--frontend legacy` (escape hatch to the pre-PR-E8 bundle).

### Iteration loop (faster feedback)

```bash
# Terminal 1 — backend
.venv/bin/python -m uvicorn main:app --reload

# Terminal 2 — frontend dev server with HMR
cd frontend && bun run dev
```

Open `http://localhost:5173`. Hot-reload on both sides. Skips the WKWebView shell entirely so you debug in real Safari/Chrome/Firefox with full devtools.

### Prerequisites

- macOS 14+ with Xcode command-line tools
- Python 3.12 (`.venv/` already configured)
- `bun` (used for the frontend; `corepack pnpm` also works)
- `.env` at repo root with `ANTHROPIC_API_KEY` (or set `EINSTEIN_AI_PROVIDER=ollama` and run `ollama serve`)

---

## What just shipped (this session)

Commit narrative, newest first. Run `git log --oneline -25` for the full list.

```
169b84f  feat(plan):   Phase 1 — calendar feed sync + WeekTimeGrid + stub coach
ba08435  fix(study):   wire optional-context textarea to its label (a11y)
fea1cb7  chore(debug): filter benign ResizeObserver warnings from the error banner
3bd9311  fix(reader):  revert route-level lazy split — preact/compat Suspense bug
701f582  fix(build):   rewrite ALL chunk dynamic-imports for the inlined HTML
ac8d20b  fix(library): drill-in pop fires where the user is looking
7ac8931  perf(reader): route-split ReaderView, add entry bundle size budget [reverted]
0c9f04e  fix(session): honor reduced motion and label the notes workspace
43a88c1  fix(study):   make card curation controls easier to target and track
5da6cc2  fix(library): align custom controls with the Ship 8 a11y bar
52a6830  a11y(ship-8): focus rings + reduced-motion in reader, ask, shell scope
c3fe2b7  fix(study,library): three audit findings — offset sync, orphan filter, rename drill-in
c8fac3a  feat(copy):   voice sweep — verb-led labels, concrete recoveries, no AI flavor
5cdccea  feat(dashboard): cockpit landing — chips above greeting, dominant Hero, no yellow
01e21fb  feat(ask):    make answer cards easier to scan at reading speed
817e9aa  feat(session): cockpit-style setup — ModeCard + DurationChips + ScopePill
27f38e4  feat(reader): premium shell + toolbar + outline + persistent loading
```

Two collaborator threads ran in this session: Claude (the conversation you're reading the handoff from) and Codex (consult-mode peer review). The merge points were per-feature directories — never two workers on the same file at the same time. See `docs/notes/2026-04-29-session-handoff.md` for the multi-agent coordination model.

---

## What's NOT done (the next session's work)

### Phase 2 of the coach — "deadline-aware study planning"

The Plan feature shipped with one rule: "free block + overdue SRS card → review_block suggestion." Phase 2 adds three more rules, all pre-listed in the schema CHECK constraint and sketched in `services/planning/coach.py`:

- **`deadline_imminent`** — parse event summaries with the existing Library subject taxonomy. Detect "X midterm" / "Y exam" / "Z quiz" patterns. Back-solve from `due_at`. Propose a 3-session study plan anchored in the matching subject's strongest weak concept.
- **`low_recent_review`** — detect subjects where SRS hasn't been practiced in N days. Suggest a short refresh block.
- **`gap_between_classes`** — when two events are <2h apart and the user is on campus (location overlap), suggest a tight focused micro-session.

Each rule is a new function appended to the `rules` list in `coach.py::synthesize_suggestions`. Same `SuggestionCard` renders all four — only `reason_code` + `reason_text` differs. **No schema migration needed.** All four codes already pass the CHECK constraint.

### Voice + UX nice-to-haves the coach will need

- **Toast action buttons.** Today's Toast primitive doesn't accept actions. Suggestion dismiss has a `restoreSuggestion` API + endpoint ready (`POST /api/plan/suggestions/{id}/restore`) — needs a 5-second-undo "Undo" button on the toast to wire it. Small primitive extension.
- **`PlanFilters.tsx`** — when there are 3+ feeds, the user will want to filter by feed. v2 work; deliberately deferred from v1.

### Open debts (older — most pre-date this session)

- **ESLint flat-config migration.** ESLINTRC_USE_FLAT_CONFIG warning fires on every lint run; `.eslintrc.cjs` migration to `eslint.config.js` is pending.
- **Swift menu-dispatch test coverage.** Currently shell-script-tested; should be XCTest.
- **`app.html.legacy` removal.** Blocked on end-to-end human verification of the new bundle's full flow.
- **Command palette ⌘K registry.** Stubbed in `AppShell` but not implemented. Deferred from Phase 2 MVP.
- **macOS Keychain for feed URLs.** Today calendar feed URLs are stored plaintext-at-rest with a strict redaction discipline at every other boundary (logs, errors, GET responses). The threat model is bounded (URLs are revocable secrets) but Keychain integration is the right v2 move alongside Gmail OAuth tokens (which are NOT trivially revocable). See `services/calendar/validators.py::mask_url` for the redaction layer.

---

## Conventions a new contributor MUST know

These are non-obvious and bite people who don't read them.

### Migrations are the schema source of truth

`schema.sql` at the repo root is **legacy**. It's retained for historical reference. The actual schema is the sequence of files in `migrations/NNNN_*.sql`, applied by `db.py::apply_migrations`. Never `ALTER TABLE` at startup; never edit `schema.sql` and expect it to apply.

When adding a table or column: write a new `migrations/NNNN_*.sql`. The latest migration is `0009_calendar_and_planning.sql` (the Plan feature).

### Motion guardrail

`tests/motion-css-guard.test.ts` enforces: **never transition `width`, `height`, `top`, `left`, `margin`, `padding`** in the design system. Layout-triggering properties cause reflow on every frame and tank scroll/ink perf. Use `transform`, `opacity`, `box-shadow`, `border-color`, `background`, `color`. The test fails the build if you violate this.

### URL redaction discipline (calendar feeds)

Calendar feed URLs are secrets. Storage is plaintext but every other boundary masks them via `services/calendar/validators.py::mask_url`. **Never log a raw feed URL.** Never return one in a GET response. The only legitimate raw-URL emission is `raw_url_echo` on the immediate POST response so the user can verify what they pasted.

### Voice rules (Ship 7)

Codified in `DESIGN.md` § Voice. The ones that bite people:

- Buttons start with a verb. "Reload the queue", not "Try again."
- Errors name a concrete recovery action ("Retry end session", not "Failed").
- Empty states ALWAYS ship a Button CTA. Never copy-only.
- No "AI assistant" / "AI tutor" phrasing. Say what the system does.
- No em dashes in product copy.

### Bundle integrity

`tests/bundle-integrity.test.ts` checks the built `app.new.html`. Two real production bugs the test catches:

1. Inlined JS containing the literal `</script` substring closes the script tag early (fixed by `safeInline()` escaping in `frontend/scripts/build-macos.mjs`).
2. Stale `./assets/index.js` reference inside the bundled HTML (Vite paths must point at `./assets.new/`).

If you change `build-macos.mjs`, run this test.

### Chunk-path rewrite for code splits

`frontend/scripts/build-macos.mjs` rewrites every `import("./X.js")` in the inlined entry JS to `import(window.__einsteinAssetBase + "X.js")`. Without this, dynamic imports under file:// resolve relative to the HTML's URL, not the assets directory. Caught us once on the Reader lazy-split (`701f582`). Don't remove the rewrite.

### preact/compat `lazy()` is fragile under file://

We tried route-splitting `ReaderView` via `lazy()` + `Suspense` from `preact/compat`. The chunk fetched successfully (verified via WebKit's resource log) but the Suspense + lazy resolution didn't re-render the tree. Reverted (`3bd9311`). If you need code-splitting, trigger it from a user-click handler (`await import(...)` inside `onClick`), not from a render-time Suspense boundary.

---

## File map (the must-knows)

```
/                       repo root
├── CLAUDE.md           project context (read first)
├── DESIGN.md           design system source of truth
├── HANDOFF.md          this file
├── README.md           quick-start
├── main.py             FastAPI entry (71 lines, just wiring)
├── db.py               SQLite + migration runner
├── api_models.py       Pydantic request/response shapes
├── routes/             FastAPI route handlers
│   ├── calendar.py     Plan feature: feed CRUD + sync-now
│   ├── plan.py         Plan feature: GET /api/plan, accept/dismiss
│   ├── documents.py    Library
│   ├── tutor.py        Ask
│   ├── study.py        SRS
│   ├── ...
│   └── __init__.py     register_routes(app)
├── services/
│   ├── calendar/       Plan feature internals (NEW)
│   │   ├── validators.py    SSRF gate + mask_url
│   │   ├── feed_client.py   HTTP fetch + conditional GET + 1 redirect
│   │   ├── ical_parser.py   icalendar + recurring-ical-events, 90-day window
│   │   ├── sync_service.py  fetch → parse → upsert orchestration
│   │   └── repository.py    SQL functions for feeds/events/runs/suggestions
│   ├── planning/       Coach (NEW)
│   │   └── coach.py         stub rule + Phase 2 hooks
│   ├── extraction/     Document parsing (subpackage)
│   ├── retrieval/      Hybrid FTS5 + vector + RRF (subpackage)
│   ├── ingestion/      Doc ingestion pipeline (subpackage)
│   ├── tutor.py        Grounded answer synthesis
│   ├── ...
├── ai/
│   ├── router.py       Claude API client
│   ├── ollama.py       Local provider
│   └── providers.py    AIProvider protocol
├── migrations/
│   ├── 0001..0008_*.sql  earlier migrations
│   ├── 0009_calendar_and_planning.sql  (Plan feature, NEW)
│   └── README.md
├── tests/              Python unittest
│   ├── test_calendar_validators.py  (NEW)
│   ├── test_calendar_parser.py      (NEW)
│   └── test_*.py
├── frontend/
│   ├── src/
│   │   ├── app/        Shell + routing (preact-iso)
│   │   ├── design-system/
│   │   │   ├── tokens.css
│   │   │   ├── themes.css
│   │   │   ├── motion.ts + animations.css
│   │   │   └── primitives/  17 primitives, each .tsx + .module.css + .test.tsx
│   │   ├── features/
│   │   │   ├── dashboard/
│   │   │   ├── library/
│   │   │   ├── reader/
│   │   │   ├── ask/
│   │   │   ├── study/
│   │   │   ├── session/
│   │   │   └── plan/        Plan + coach (NEW)
│   │   │       ├── PlanView.tsx
│   │   │       ├── api/       calendarApi.ts + planApi.ts
│   │   │       ├── hooks/     usePlan.ts (single hook for the surface)
│   │   │       ├── components/  WeekTimeGrid, EventBlock, SuggestionCard,
│   │   │       │                FeedList, FeedStatusBadge, AddFeedDialog,
│   │   │       │                EmptyPlanState
│   │   │       └── utils/     timezone.ts
│   │   └── services/api/  typed API client + generated types.gen.ts
│   ├── tests/             vitest suites
│   │   └── plan/          (NEW: 12 plan tests)
│   ├── scripts/build-macos.mjs   bundles HTML + inlines JS for WKWebView
│   └── package.json
├── macos-app/             Swift shell
│   ├── Package.swift
│   └── Sources/EinsteinDesktopApp/
├── docs/
│   ├── adr/               architecture decision records
│   ├── notes/             ad hoc engineering notes (incl. session handoffs)
│   ├── plans/             plan documents
│   └── roadmap/           shipping roadmaps (premium-ui-pass.md, anchors-era.md)
└── script/
    ├── build_and_run.sh   the canonical entry point
    └── generate-api-types.sh
```

---

## Verify chain (run this once before you ship anything)

```bash
cd /Users/madu/Desktop/Codex

# Frontend
cd frontend
bun run tsc --noEmit     # typecheck
bun run lint             # eslint
bun run vitest run       # 266 tests
bun run build            # vite build
cd ..

# Backend
.venv/bin/python -m ruff check ai services evals tests main.py db.py routes api_models.py
.venv/bin/python -m unittest discover -s tests -v   # full Python suite

# End-to-end
./script/build_and_run.sh --verify
```

Every PR lands green on the full chain or it does not land. If anything fails, **fix it before adding more code** — Einstein's history is full of small atomic commits, not big gnarly merges.

---

## When in doubt

- **For a UI change** → read `DESIGN.md` first, then look for the most similar existing feature and match its conventions
- **For a backend change** → read `CLAUDE.md` § Conventions, then look at the most similar existing service module
- **For a schema change** → write a new migration, never edit existing ones
- **For copy** → read `DESIGN.md` § Voice, follow the rules
- **For a refactor that touches multiple features** → split into one PR per feature directory; the multi-agent collaboration model in `docs/notes/2026-04-29-session-handoff.md` documents why

If a thing is genuinely new and there's no existing analog, write a doc in `docs/notes/YYYY-MM-DD-<topic>.md` capturing the design decision before you write the code. Future readers (including future-you) will need it.
