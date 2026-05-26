# Carrel — repo entry point

Picking up `/Users/madu/Desktop/Codex` after the **2026-05-22 V2
strategic pivot** repositioned the product as an **independent AI
verification layer for high-stakes AI output**, with litigation
pre-flight as the wedge. The tutor surface is still in the codebase
and still works; it is now the structural substrate for the
verification engine, not the product. See
[ADR-0008](docs/adr/ADR-0008-v2-pivot-validation-first-sequencing.md)
for the pivot decision + validation-first sequencing, and the V2
design doc at `/Users/madu/.gstack/projects/Codex/madu-main-design-20260522-015141.md`
for the strategic frame.

Active V2 surface on main: `/api/verify` route, [VerifyView](frontend/src/features/verify/VerifyView.tsx),
CourtListener case-existence ([courtlistener.py](services/legal/courtlistener.py)),
holding-match verifier ([case_verification.py](services/legal/case_verification.py)),
non-prose citation drop gate in [tutor.py](services/tutor.py),
typed-node retrieval default-on ([ADR-0006](docs/adr/ADR-0006-typed-node-defaults-on.md)).
All shipped in PR #82 (commit `57188d81`, 2026-05-26).

**Current focus (per ADR-0008 validation-first reset):** T64
answer-quality investigation → T65/T66 30-day validation test →
T67 Stage 2/3 design conditional on T66 verdict. V2 polish queue
(T59-T63) is paused, NOT killed. Pre-pivot tutor roadmap (T13-T58
chunks→nodes migration) is deferred behind the validation outcome.

Historical context (pre-pivot work that still informs the codebase):
this repo previously closed the 8-ship premium-UI roadmap, shipped
Plan + Coach Phase 1, and renamed the product from Einstein Tutor to
**Carrel**. Last green pre-pivot snapshot: commit **`169b84f`**.

This file isn't a template. It's specific to Carrel, specific to
this session's work, and specific to what the next agent (or future-
you) needs to know to NOT recreate the conversations we already had.

> **The rename is partial by design.** User-visible surfaces and
> internal JS / Python identifiers are now Carrel. System-level
> identifiers (`com.madu.EinsteinDesktop` macOS bundle ID,
> `EinsteinDesktop.app` bundle name, `data/einstein_tutor.db` SQLite
> path) stayed on the legacy names because renaming them is a data-
> migration / code-signing concern. See
> `docs/notes/2026-04-29-carrel-rename.md` for the deferred-rename
> list and the migration plan when that work picks up.

---

## What Carrel is

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

- **Repositories are module functions, not classes.** Carrel's
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

## Booting Carrel

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
(post-launch sanity check).

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

### Type-check findings (5 latent bugs, plus a verify-chain gap)

Running `mypy --ignore-missing-imports --follow-imports=silent ai services routes`
with `--config-file /dev/null` (so the typed-island exclude in `mypy.ini`
doesn't apply) finds **70 errors in 27 of 120 files** non-strict,
**185 errors in 58 files** strict. Current `mypy.ini` gate is clean on
the 8 typed-island files; this is the debt outside that gate.

Five of the 70 are real latent bugs sitting in the codebase today,
not annotation noise. Fix these first regardless of any decision
about expanding the verify chain.

**1. `services/local_api_security.py:42` — `compare_digest` receives `str | None`. — FIXED 2026-05-12.**

Resolved in commit `d5441bcd` by guarding upstream: `provided is None
or expected is None` returns `False` before `hmac.compare_digest`
sees either arg. Pattern shipped:

```python
if provided is None or expected is None:
    return False
if not hmac.compare_digest(provided, expected):
    return False
```

**2. `routes/calendar.py:126, 217, 269` — `FeedRow | None` assigned to `FeedRow`. — FIXED 2026-05-12.**

Resolved in commit `3c15a23f`. Deviated from the literal HANDOFF spec
(HTTPException(404)) because the failing path is a post-write
bookkeeping refresh — the caller has already observed a successful
insert/upload/sync, so a 404 would misrepresent the operation's
outcome. Fix logs a `LOGGER.warning(...)` and falls back to the
pre-write row at each of the three sites. Three regression tests
in `tests/test_calendar_feedrow_fallback.py` pin each fallback path.

**3. `services/tutor.py:1074` — `request_grounded_answer` called with unsupported `temperature=` kwarg. — FIXED 2026-05-12.**

Resolved by widening the `AIProvider` protocol to declare
`temperature: float = 0.0` and threading the same parameter through
the `NullProvider` and `ClaudeRouter` stubs (accept-and-ignore via
`del temperature`). AFM and Ollama implementations already honored it.
The call site is now type-correct; mypy delta on the broad sweep
(`mypy --config-file /dev/null --ignore-missing-imports
--follow-imports=silent ai services`): 56 → 54 errors.

**4. `ai/providers.py:329, 337` — `ClaudeRouter` does not satisfy the `AIProvider` protocol it is returned as. — FIXED 2026-05-12.**

Resolved by widening `ClaudeRouter.request_json` to accept
`fallback: Any = None`, mirroring the protocol declaration and
`NullProvider`'s behavior: on a failed call, `json_payload` is
replaced with the supplied fallback while `ok` stays `False` so
callers retain failure visibility. The `task: ClaudeTask` Literal
input was deemed acceptable (mypy treats it as compatible with the
protocol's `task: Any`; the older error notes were diagnostic
context, not the failing check). Three regression tests
(`ClaudeRouterFallbackContractTests` in `tests/test_ai_providers.py`)
pin the fallback-on-failure contract across the missing-API-key,
default-no-fallback, and `invalid_json` branches. mypy delta on the broad sweep:
54 → 52 errors; both Bug-4 conformance errors gone.

**5. `services/extraction/parsers/pdf.py:342-343` — `elements` and `warnings` redefined inside the same function. — FIXED 2026-05-12.**

Verified benign: the bridge branch above (lines 271-339) always exits
via `return build_asset(...)`, so reaching the PyPDF fall-through at
line 341 implies the bridge branch never executed. Re-init is correct
behavior. Resolved the mypy `[no-redef]` noise by dropping the type
annotations on the re-init (`elements = []` / `warnings = []`). The
earlier annotated declaration in the bridge branch does NOT carry
across because that branch always returns; instead, mypy infers
correct types at the usage sites — `elements.extend` consumes
`_pdf_page_elements`' typed return, `warnings.append` only sees
string literals, and `build_asset`'s typed parameters pin both lists
at the final call. mypy broad sweep delta: 52 → 50 errors; both
Bug-5 redef errors gone. No behavior change, ruff clean,
`tests/test_pdf_scanned_detection.py` green (7/7).

#### Verify-chain gap

The verify chain runs `ruff` on `ai services evals tests main.py db.py
routes api_models.py` but does not run `mypy` on the broader backend.
Only `app_runtime.py`, `app_logging.py`, `ai/router.py`, `benchmarks/*`,
and `evals/*` are mypy-gated today (the typed islands in `mypy.ini`).

After the 5 bugs above land, add this single line to the verify chain
in `CLAUDE.md` and to whatever script gates PRs:

```bash
./.venv/bin/python -m mypy --ignore-missing-imports --follow-imports=silent ai services routes
```

That run currently produces ~65 remaining errors after the 5 bug fixes.
Breakdown:

- ~8 Literal/enum mismatches in `services/anchors.py` and `routes/plan.py`
  (half a day to align producers with the declared Literals)
- ~10 optional-import shadowing in `services/extraction/parsers/*.py`
  (`docx`, `html`, `epub`, `pptx` use the `try: import X; except: X = None`
  pattern, which mypy reads as "Cannot assign to a type"; half a day
  with targeted `# type: ignore[assignment, misc]` or a small
  `Optional[type[X]]` restructure)
- ~25 `object` propagation through `services/ingestion/*` and
  `services/documents.py` (real typing work, 1 to 2 days; the root
  cause is dict values typed as `object` at the boundary, which then
  flow into call sites that need `str`, `int`, or richer types)
- ~5 mechanical (float assigned to int-typed variable, missing list
  annotations); 30 minutes

Total to zero on the broader gate and lock it in: roughly 1 to 2
engineer-days after the bug-fix PR lands.

**Do not pursue full `--strict` on this scope yet.** Strict adds another
~115 errors (185 total) that are mostly `[no-untyped-def]` on legacy
modules. Promote files into strict one at a time, the same way
`app_runtime.py`, `app_logging.py`, and `ai/router.py` were promoted
into the strict list in `mypy.ini`. The typed-island pattern is the
right discipline; just widen the perimeter.

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

### ~~Reader outline rail empty for most PDFs~~ — SHIPPED

Implementation landed in `frontend/src/features/reader/hooks/usePdfDocument.ts`:
`deriveOutlineFromChunks()` (line 80) is wired as the fallback when
`pdf.getOutline()` returns null/empty (line 154). Adjacent
same-section + same-page runs collapse to one node; non-adjacent
same sections stay separate so the rail reflects reading order.

Test coverage: `frontend/src/features/reader/hooks/usePdfDocument.test.ts`
(7 tests, all green) pins the contract — empty input, adjacent
dedup, non-adjacent kept separate, page-aware dedup key, empty
section fallback to "Source section", null page_num preservation,
flat-leaf node structure.

NOT done from the original plan: the optional `outlineSource:
"embedded" | "derived"` field that would let `OutlineRail` show
a subtle "auto-derived" hint to the user. Skipped because every
academic PDF would surface the hint, which is noise; if the rail
is reliable the user doesn't need to know which path produced it.
Re-add this only if the derived outlines turn out to be visibly
worse than embedded ones.

### Carry-overs from before this session

- ESLint flat-config migration (the `ESLINTRC_USE_FLAT_CONFIG`
  warning fires on every lint run)
- Command palette ⌘K registry (stubbed in `AppShell` but never
  built out)
- Swift menu-dispatch tests should be XCTest; informal coverage today
- macOS Keychain integration for feed URLs (Phase 2 work
  alongside Gmail OAuth tokens)

---

## Conventions specific to Carrel that bite people

These are Carrel-specific and non-obvious. New contributors
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
