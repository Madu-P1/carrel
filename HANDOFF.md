# Einstein Tutor — repo entry point

Picking up `/Users/madu/Desktop/Codex` after a session that closed the
8-ship premium-UI roadmap and shipped Plan + Coach Phase 1.

Last green snapshot: commit **`169b84f`** (`feat(plan): Phase 1 — calendar feed sync + WeekTimeGrid + stub coach`).
Latest commit at handoff: **`c1a2e398`** (this doc + the session notes).

This file isn't a template. It's specific to Einstein, specific to
this session's work, and specific to what the next agent (or future-
you) needs to know to NOT recreate the conversations we already had.

---

## What Einstein Tutor is

Local-first, source-grounded AI study workspace for macOS. Native
Swift shell wraps a WKWebView loading a bundled Preact + TypeScript
app. FastAPI + SQLite + sqlite-vec backend. Anthropic Claude (or
local Ollama) for the tutor.

What the user does with it:

- **Library** — drop in PDFs, slides, DOCX, markdown, plain text.
  Concepts get extracted, chunks indexed for hybrid retrieval.
- **Reader** — three-column shell: outline rail (280px / 48px
  collapsed), PDF canvas with toolbar, right rail with Tabs
  (Chunks / Concepts / Notes / Related). Citation chips deep-link
  back into specific chunks.
- **Ask** — grounded tutor. Every claim cites a verbatim chunk
  span. Refusal taxonomy distinguishes `no_coverage`,
  `weak_coverage`, etc. — the model is not allowed to fabricate.
- **Study** — SRS flashcards (FSRS scheduling), Manage Cards view
  with subject filter chips, AI-drafted card creation.
- **Session** — focused study mode with cockpit setup
  (Pomodoro / Flowtime / Notes / Flashcards) + active timer.
- **Dashboard** — landing page (greeting + heartbeat date eyebrow,
  hero composer, recommendation card, quick action tiles, weekly
  stat strip with count-ups).
- **Plan** *(shipped this session)* — paste a Google / Apple /
  Outlook / Blackboard iCal URL, see the next 7 days as a time
  grid (day = column, hours stacked), and watch the coach propose
  study blocks where there's free time + overdue SRS cards.

The product values: local-first, source-grounded, no fabrication,
single-user, on-device. Don't add cloud-sync, multi-tenant logic,
or telemetry that crosses the device boundary without explicit
user approval.

---

## Read this before touching anything Plan-related

`docs/notes/2026-04-29-session-handoff.md` is the longest doc in
this handoff and the most useful one. It captures the architecture
pushback chain on the Plan spec — every decision that came out of
"the user said X, I pushed back with Y, we landed on Z" lives there.

The big ones to know before you touch `services/calendar/`,
`services/planning/`, or `frontend/src/features/plan/`:

- **Repositories are module functions, not classes.** Einstein's
  pattern. We rejected per-table repository classes during the
  spec.
- **No APScheduler.** SWR (stale-while-revalidate) instead. The
  read path at `/api/plan` NEVER blocks on a remote fetch; stale
  feeds get kicked into a background ThreadPoolExecutor.
- **One validated redirect, not zero.** Calendar providers
  redirect once for signed CDN delivery; rejecting redirects
  outright would create false negatives on Google + Apple +
  Outlook + Blackboard. The redirect target re-runs through the
  SSRF gate.
- **Plaintext URL storage with strict redaction at every other
  boundary.** Calendar feed URLs are revocable secrets. Storage
  is plaintext; logs / errors / GET responses always go through
  `services/calendar/validators.py::mask_url`. Don't emit a raw
  URL anywhere except the immediate POST-create response.
- **Stub coach has one rule today.** `free_block_overdue_srs`.
  The other three (`deadline_imminent`, `low_recent_review`,
  `gap_between_classes`) are pre-listed in the schema CHECK
  constraint and sketched in `services/planning/coach.py`.
  Adding them is a code change, NOT a migration.

If you change feed sync, the parser, or the coach without reading
that doc first, you'll re-derive a bad version of decisions we
already locked.

---

## Booting Einstein

```bash
./script/build_and_run.sh
```

Builds the Swift shell (`macos-app/`), builds the Vite frontend
(`frontend/`), starts FastAPI on `127.0.0.1:8000`, launches
`EinsteinDesktop.app`. First build ≈1 min; subsequent ≈1 sec
because Swift incremental builds are fast and Vite is fast.

Modes the script accepts: `--debug` (lldb against the Swift
binary), `--logs` (stream `log` filtered to the EinsteinDesktop
process), `--telemetry` (subsystem-filtered log), `--verify`
(post-launch sanity check), `--frontend legacy` (escape hatch to
the pre-PR-E8 bundle still shipped at
`macos-app/Resources/app.html.legacy`).

For tighter feedback during dev, skip the WKWebView shell:

```bash
# Terminal 1
.venv/bin/python -m uvicorn main:app --reload

# Terminal 2
cd frontend && bun run dev
```

Open `http://localhost:5173` in Safari/Chrome. Hot reload on both
sides. You lose the bundled-app behaviors (file:// chunk loading,
WKWebView devtools, native menu) but you gain real devtools and
fast iteration.

Prereqs: macOS 14+, Xcode CLI tools, Python 3.12 (`.venv/`
preconfigured), `bun` on PATH (`corepack pnpm` works too), and
`.env` at repo root with `ANTHROPIC_API_KEY` (or
`EINSTEIN_AI_PROVIDER=ollama` if you have `ollama serve` running
locally).

---

## What landed this session

Newest first. Run `git log --oneline -25` for the full list with
hashes.

```
c1a2e39  docs: handoff package — HANDOFF.md + session notes + CLAUDE.md refresh
169b84f  feat(plan): Phase 1 — calendar feed sync + WeekTimeGrid + stub coach
ba08435  fix(study): wire optional-context textarea to its label (a11y)
fea1cb7  chore(debug): filter benign ResizeObserver warnings from the error banner
3bd9311  fix(reader): revert route-level lazy split — preact/compat Suspense bug
701f582  fix(build): rewrite ALL chunk dynamic-imports for the inlined HTML
ac8d20b  fix(library): drill-in pop fires where the user is looking
0c9f04e  fix(session): honor reduced motion and label the notes workspace
43a88c1  fix(study): make card curation controls easier to target and track
5da6cc2  fix(library): align custom controls with the Ship 8 a11y bar
52a6830  a11y(ship-8): focus rings + reduced-motion in reader, ask, shell scope
c3fe2b7  fix(study,library): three audit findings — offset sync, orphan filter, rename drill-in
c8fac3a  feat(copy): voice sweep — verb-led labels, concrete recoveries, no AI flavor
5cdccea  feat(dashboard): cockpit landing — chips above greeting, dominant Hero, no yellow
01e21fb  feat(ask): make answer cards easier to scan at reading speed
817e9aa  feat(session): cockpit-style setup — ModeCard + DurationChips + ScopePill
27f38e4  feat(reader): premium shell + toolbar + outline + persistent loading
```

Two collaborator threads ran for parts of this session: this Claude
session + Codex (consult mode for code review + parallel ship 5
on the Ask feed + parallel ship 8b on Library/Study/Session a11y).
The merge points were per-feature directories. We never had two
workers on the same file at the same time. **If you're going to
parallelize work in a future session: split by feature directory,
not by concern.** Concern-based splits (one worker on a11y across
all features, another on copy across all features) cause merge
hell. The session notes capture this in detail.

---

## What is NOT done

### Coach Phase 2 — make the coach feel real

Phase 1 ships ONE rule (`free_block_overdue_srs`). The reason
codes for Phase 2 are already in the schema CHECK constraint:

```python
# services/planning/coach.py
rules = [
    _rule_free_block_overdue_srs,           # v1 (shipped)
    # _rule_deadline_imminent,              # Phase 2
    # _rule_low_recent_review,              # Phase 2
    # _rule_gap_between_classes,            # Phase 2
]
```

`deadline_imminent` is the rule that turns the coach from "useful
nudge" into "actually intelligent." Sketch:

1. Walk the next 14 days of `calendar_events`
2. Match each event's summary against subjects in the Library
   (substring first, embedding similarity if substring fails)
3. For matches, query SRS for the subject's weakest concepts
   (`mastery < 0.6`)
4. Back-solve from event `start_at`: 3 study sessions of 60 min,
   spaced exponentially (3 days before, 1 day before, day-of)
5. Emit `study_block` suggestions with reason text like
   "Finance midterm in 5 days. Three sessions on weak concept Y."

~150 lines of Python. No schema change required.

### Toast action buttons

Plan's "Dismiss suggestion" emits a toast that says "Suggestion
dismissed." It SHOULD have an "Undo" button that calls
`POST /api/plan/suggestions/{id}/restore` — that endpoint and the
hook (`restoreSuggestion`) are wired and tested. The blocker:
`Toast.tsx` doesn't accept action buttons. Extending `ToastInput`
with an optional `{ action: { label, onClick } }` field is the
fix. Small primitive change.

### Carry-overs from before this session

- ESLint flat-config migration (the `ESLINTRC_USE_FLAT_CONFIG`
  warning fires on every lint run)
- `app.html.legacy` removal (blocked on full end-to-end human
  verification of the new bundle)
- Command palette ⌘K registry (stubbed in `AppShell` but never
  built out)
- Swift menu-dispatch tests should be XCTest, not the
  `script/test_frontend_selector.sh` shell harness
- macOS Keychain integration for feed URLs (Phase 2 work
  alongside Gmail OAuth tokens)

---

## Conventions specific to Einstein that bite people

These are Einstein-specific and non-obvious. New contributors
miss them and re-introduce class-of-bug we already hunted down.

### Migrations are the schema source

`schema.sql` at repo root is **legacy retained for reference**.
The actual schema is the sequence of files in
`migrations/NNNN_*.sql`, applied by `db.py::apply_migrations`.
Latest is `0009_calendar_and_planning.sql`.

Don't edit `schema.sql` and expect it to apply. Don't `ALTER
TABLE` at startup. Write a new migration.

### `tests/motion-css-guard.test.ts` enforces the motion rule

Never transition `width`, `height`, `top`, `left`, `margin`, or
`padding` in any design-system or feature CSS module. Layout-
triggering properties reflow on every frame and tank scroll/ink
perf. Use `transform`, `opacity`, `box-shadow`, `border-color`,
`background`, `color`. The test fails the build if you violate.

### Calendar feed URL redaction discipline

Every emission of a feed URL outside the database column itself
must go through `services/calendar/validators.py::mask_url`.
That includes log lines, `last_error` fields on `calendar_feeds`
and `calendar_sync_runs`, error messages returned to the
frontend, and the `url` field on every `CalendarFeedRow`
response. The ONE legitimate raw-URL emission is `raw_url_echo`
on the immediate POST-create response so the user can verify
what they pasted.

### `frontend/scripts/build-macos.mjs` chunk-path rewrite

Every `import("./X.js")` inside the inlined entry JS gets
rewritten to `import(window.__einsteinAssetBase + "X.js")`.
Without this, dynamic imports under file:// resolve relative to
`app.new.html`'s URL instead of the `assets.new/` directory.
Caught us once on the Reader lazy-split (commit `701f582`).

If you change `build-macos.mjs`, run
`tests/bundle-integrity.test.ts` AND
`tests/bundle-size.test.ts`.

### preact/compat `lazy()` is fragile under file://

We tried route-splitting `ReaderView` via `lazy()` + `Suspense`
from `preact/compat` (`7ac8931`). The chunk fetched
successfully, but Suspense never re-rendered the tree. Reverted
in `3bd9311`. If you need code-splitting in the bundled WKWebView
app, trigger via user-click `await import(...)` instead of
render-time Suspense.

### Voice rules from Ship 7

Codified in `DESIGN.md § Voice`. The ones that bite:

- Buttons start with a verb. "Reload the queue", not "Try again".
- Errors name a concrete recovery action.
- Empty states ALWAYS ship a Button CTA.
- No "AI assistant" / "AI tutor" phrasing.
- No em dashes in product copy.

### Bundle size budgets are pinned

`tests/bundle-size.test.ts` fails if `index.js` exceeds 78 KB
gzipped or `index.css` exceeds 25 KB gzipped. Bumping a budget
is a deliberate decision documented in the test's history
comment. If you grow the entry chunk, tell the test why.

---

## Where things live

```
/                       repo root
├── HANDOFF.md          this file
├── CLAUDE.md           project context for Claude (read after this)
├── DESIGN.md           design system: tokens, voice, motion, decisions
├── README.md           build + run quick start
├── main.py             FastAPI entry (71 LOC, just wiring)
├── db.py               SQLite + migration runner
├── api_models.py       Pydantic shapes
├── routes/
│   ├── calendar.py     /api/calendar/feeds CRUD + sync-now
│   ├── plan.py         GET /api/plan + accept/dismiss/restore
│   └── ...             documents, tutor, study, session, etc.
├── services/
│   ├── calendar/       Plan internals (NEW THIS SESSION)
│   │   ├── validators.py    SSRF gate + mask_url
│   │   ├── feed_client.py   conditional GET + 1 validated redirect
│   │   ├── ical_parser.py   icalendar + recurring-ical-events, 90-day window
│   │   ├── sync_service.py  fetch → parse → upsert
│   │   └── repository.py    SQL functions for all 4 tables
│   ├── planning/coach.py    stub coach + Phase 2 hooks (NEW)
│   ├── extraction/    document parsing (subpackage)
│   ├── retrieval/     hybrid FTS5 + vector + RRF (subpackage)
│   ├── ingestion/     doc ingestion pipeline (subpackage)
│   ├── tutor.py       grounded answer synthesis
│   └── ...
├── ai/
│   ├── router.py       Claude API client
│   ├── ollama.py       local provider
│   └── providers.py    AIProvider protocol
├── migrations/
│   ├── 0001..0008      earlier migrations
│   ├── 0009_calendar_and_planning.sql  (NEW)
│   └── README.md
├── tests/              Python unittest
│   ├── test_calendar_validators.py  (NEW)
│   ├── test_calendar_parser.py      (NEW)
│   └── test_*.py
├── frontend/src/
│   ├── app/            shell + routing (preact-iso)
│   ├── design-system/
│   │   ├── tokens.css + themes.css + motion.ts + animations.css
│   │   └── primitives/  17 primitives, .tsx + .module.css + .test.tsx each
│   ├── features/
│   │   └── plan/        Plan view + Coach UI (NEW THIS SESSION)
│   │       ├── PlanView.tsx
│   │       ├── api/         calendarApi.ts + planApi.ts
│   │       ├── hooks/       usePlan.ts (one hook for the whole surface)
│   │       ├── components/  WeekTimeGrid, EventBlock, SuggestionCard,
│   │       │                FeedList, FeedStatusBadge, AddFeedDialog,
│   │       │                EmptyPlanState
│   │       └── utils/timezone.ts
│   └── services/api/   typed API client + generated types.gen.ts
├── frontend/tests/plan/  (NEW: 12 tests)
├── frontend/scripts/build-macos.mjs   bundles HTML + inlines JS for WKWebView
├── macos-app/Sources/EinsteinDesktopApp/   Swift shell, native bridge
└── docs/
    ├── notes/2026-04-29-session-handoff.md  (read for Plan internals)
    ├── roadmap/premium-ui-pass.md           (closed)
    ├── adr/                                 architecture decisions
    └── plans/                               plan documents
```

---

## Verify chain

```bash
cd /Users/madu/Desktop/Codex

# Frontend
cd frontend
bun run tsc --noEmit
bun run lint
bun run vitest run
bun run build
cd ..

# Backend
.venv/bin/python -m ruff check ai services evals tests main.py db.py routes api_models.py
.venv/bin/python -m unittest discover -s tests -v

# End-to-end
./script/build_and_run.sh --verify
```

State at handoff:

- vitest: **263 / 266 passing** (3 failing transiently, see below)
- Python: **28 new + existing suite green**
- tsc / eslint / ruff: clean
- vite build: 226.48 KB / 73.58 KB gz JS, 144.41 KB / 22.56 KB gz CSS
- Swift build: clean
- end-to-end smoke (PID-confirmed app launch + `/api/plan` returns
  events + the stub coach fired with 7 real overdue cards in the
  active database)

### The 3 transiently failing tests

`tests/ask/answer-feed.test.tsx` — all three fail on
`window.localStorage.clear is not a function` in `beforeEach` /
`afterEach`. They were green at commit `169b84f`. Cause: Node 25
exposes a partial `localStorage` global that needs the
`--localstorage-file=<path>` flag to function; without it,
`clear()` is missing, and Node's built-in shadows jsdom's full
implementation under this Node version.

Fix (5 min): in `tests/ask/answer-feed.test.tsx` lines 18 + 22,
replace `window.localStorage.clear()` with:

```ts
for (const key of Object.keys(window.localStorage)) {
  window.localStorage.removeItem(key);
}
```

Or stub a full `Storage` in `tests/setup.ts`. NOT a code
regression — environment drift between commit-time and handoff-
time.

---

## Decision tree for the next change

If you're about to:

- **Touch any UI** → `DESIGN.md` first, then look at the most
  similar existing feature and match its conventions.
- **Touch the Plan / Coach** → `docs/notes/2026-04-29-session-handoff.md`
  first. The pushback chain on the spec is in that doc, NOT here.
- **Add a backend service or route** → `CLAUDE.md § Conventions`,
  then look at the most similar existing service module.
- **Change the schema** → write a new
  `migrations/NNNN_<topic>.sql`. Never edit `schema.sql`.
- **Write product copy** → `DESIGN.md § Voice` rules apply.
- **Refactor across multiple features** → do it as one PR per
  feature directory; the multi-agent coordination notes in the
  session-handoff doc explain why.
- **Add a new design token** → check `tokens.css` + `themes.css`
  for an existing semantic name first. New token categories
  belong in `DESIGN.md` § Decisions Log.

If a thing is genuinely new and there's no existing analog,
write `docs/notes/YYYY-MM-DD-<topic>.md` capturing the design
decision before you write the code. Future readers (including
future-you) will need it.
