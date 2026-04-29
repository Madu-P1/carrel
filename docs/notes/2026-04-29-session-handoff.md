# Session notes — 2026-04-26 to 2026-04-29

This is the handoff doc for the work that landed across the premium-UI roadmap closeout + Plan/Coach Phase 1 ship. Anyone (Claude or human) picking up the codebase next should read this in addition to `HANDOFF.md` and `CLAUDE.md`.

## What shipped

### Premium UI roadmap (8 ships, all complete)

The roadmap that kicked off this session was `docs/roadmap/premium-ui-pass.md`. All 8 ships landed:

| Ship | Result |
|---|---|
| 1–2 | Token refresh + primitive audit (deeper dark surfaces, control-height ladder, semantic radius, state-token ladder) |
| 3a | Reader shell rebuild — 280px outline rail, 44px three-zone toolbar, persistent skeleton loading |
| 3b | Reader right rail — MetadataStripe + Tabs (Chunks/Concepts/Notes/Related) + per-tab empty states |
| 4 | Session cockpit — ModeCard radiogroup, DurationChips, ScopePill, size-lg CTA |
| 5 | Answer card feed — tier hierarchy, fallback/refusal model, skeleton on Skeleton primitive (Codex) |
| 6 | Dashboard cockpit landing — status chips above greeting, dominant Hero composer, killed yellow callout, tile quick-actions, ContinueModule |
| 7 | Voice sweep — verb-led labels, concrete error recoveries, no AI flavor, voice rules codified in DESIGN.md |
| 8a | A11y in reader/ask/shell — focus rings via `--shadow-focus`, reduced-motion guards |
| 8b | A11y in library/study/session (Codex) — custom-control focus rings, shimmer/card-motion reduced-motion guards, Notes label association, timer-ring reduced-motion |
| 8c | A11y audit closeout — programmatic sweep found one real finding (CardAiDraftDialog optional-context textarea label), fixed + regression test |

### Plan + Coach (Phase 1)

The headline ship of this session. Commit `169b84f`. Calendar feed sync + WeekTimeGrid + stub coach.

**End-to-end works:** paste an iCal URL (Google Calendar / Apple Calendar / Outlook / ESCP Blackboard), events appear in the WeekTimeGrid for the next 7 days, and when you have ≥1 overdue SRS card AND a 60-min free block in the next 24h, the coach proposes a `review_block` with reason text "60-min gap and N cards overdue."

Smoke-tested against the running backend before commit; the coach fired with 7 real overdue cards.

## Architecture decisions worth documenting

### 1. The Plan spec went through hard pushback

The user proposed an enterprise-shaped backend (per-table repositories, separate planning services, separate jobs files, Postgres-shaped types). I pushed back; they pushed back on my pushback. The locked spec is significantly smaller than the original:

- **Repositories collapsed to module functions per concern.** No `class FeedRepository`. `services/calendar/repository.py` has `feeds.list_due()`, `events.upsert(...)`, `runs.record(...)` as direct module functions. Einstein's existing pattern. Fewer files, no async/sync boundary issues with sqlite3.
- **Planning collapsed to one `coach.py`.** Was three files (`suggestion_service.py` + `scoring.py` + `acceptance_service.py`). Acceptance is a route concern, not a service. Scoring is the suggestion logic — not a separate file. One file, ~300 lines.
- **No APScheduler / per-feed intervals / jittered backoff in v1.** Replaced with **stale-while-revalidate**: `/api/plan` reads from local DB (deterministic, fast); kicks background refreshes for stale feeds (>5min) into a thread pool; sets `is_freshening: true` so the UI shows a subtle "syncing in background" hint. Read path NEVER blocks on remote fetch.
- **One validated redirect, not zero.** Original instinct was "reject all redirects" for SSRF safety. User pushed back: Google / Apple / Outlook / Blackboard all redirect once for signed CDN delivery. Compromise: max 1 redirect, re-validate target through the same SSRF gate. Implemented in `services/calendar/feed_client.py`.
- **Plaintext URL storage is acceptable for v1.** Calendar feed URLs ARE secrets but are revocable from source. Discipline: never logged, never in error responses, never in exports. `services/calendar/validators.py::mask_url` enforces the redaction layer. macOS Keychain is v2 work alongside Gmail OAuth tokens.

The full pushback chain is in the conversation history; the spec lives in `migrations/0009_calendar_and_planning.sql` and the inline docstrings in `services/calendar/`.

### 2. The Plan view is a time-grid, not a list

Standard "day-grouped event list" hides free time visually. The user's job on this surface is finding free slots to study. A 7-day timeline (day = column, hours stacked vertically, events placed at their actual time) makes "I have a 90-min gap Wednesday afternoon" obvious — which is exactly where the coach lands its `SuggestionCard`. ~100 lines more than a list, dramatically more useful.

### 3. preact/compat lazy() does NOT work cleanly under file://

This bit us hard. Tried route-splitting `ReaderView` (`7ac8931`). Chunk fetched successfully (verified via WebKit's `[com.apple.WebKit:Network]` log: resource 463 finished at 27,304 bytes, HTTP 200, no errors). But Suspense + lazy resolution didn't re-render the tree. Reverted (`3bd9311`).

If you need code-splitting, trigger from a user-click handler:

```ts
async function onClick() {
  const { HeavyPanel } = await import("./HeavyPanel");
  setShown(<HeavyPanel />);
}
```

Don't use render-time `<Suspense fallback={...}><LazyComponent /></Suspense>` until preact/compat's behavior is verified under the bundled file:// shape.

The chunk-path rewrite generalization stayed (`701f582`) — it catches any future `import("./*.js")` in inlined entry JS, which would otherwise resolve relative to the HTML's URL instead of the assets directory. Defensive code for the case when you DO trigger a split correctly.

### 4. Multi-agent coordination model that worked

This session ran two collaborator threads in parallel for a few ships: Claude + Codex (consult mode). The coordination model:

- **Per-feature directory split.** One worker per feature directory, never two on the same file. Codex took ship 5 (`features/ask/`), I took ship 6 (`features/dashboard/`). Codex took ship 8b (`features/library/`, `features/study/`, `features/session/`), I took ship 8a (`features/reader/`, `features/ask/`, `features/shell/`).
- **Linear merges to `main`.** No feature branches, no merge conflicts because file scopes were disjoint. Whoever pushed second ran `git pull --rebase` and reapplied cleanly.
- **Code review as audit.** The three audit findings in `c3fe2b7` came from Codex doing a manual audit. I implemented the fixes + regression tests. Multi-agent worked because we used the second worker as a code-review surface, not a parallel feature builder.

Lesson for future sessions: **split parallel work BY FEATURE DIRECTORY, not by concern.** Concern-based splits (one worker on a11y across all features, another worker on copy across all features) produce merge hell.

## Gotchas surfaced in this session

### Schema must be a migration, not a `schema.sql` edit

The original Plan spec had a `db/schema.sql` directory. The user's pushback ("Einstein uses migrations, not schema.sql") was correct. `schema.sql` at repo root is **legacy** — retained for historical reference. Real schema is the sequence of `migrations/NNNN_*.sql` files. The 0009 migration is what actually applied.

If you write a new schema change: create `migrations/NNNN_<topic>.sql`. The migration runner in `db.py::apply_migrations` records applied versions in `schema_migrations`.

### SQLite quirks bit us once

`ORDER BY ... ASC NULLS FIRST` is supported in SQLite 3.30+ but not the version macOS bundles on older systems. SQLite's default `ASC` sorts NULLs first anyway, so the explicit `NULLS FIRST` keyword is redundant. We removed it in `services/calendar/repository.py::list_stale_feeds`. Comment in code.

### macOS Keychain integration is real but bounded threat model

Calendar feed URLs are stored plaintext-at-rest. Honest framing of the threat model:

- Stolen disk + encryption off → URL leaks → user revokes the URL in source UI in one click ✓
- Backup leak → same ✓
- Malware on the same Mac → already loses (has user privileges, can read both Keychain and DB) ✓

So plaintext is acceptable for v1. The discipline that matters is **redaction** at every other boundary (logs, errors, GET responses, exports). `services/calendar/validators.py::mask_url` is used at every emission point. Don't log a raw feed URL.

Keychain becomes the right move alongside Gmail OAuth tokens (which are NOT trivially revocable). Phase 2 work.

### ResizeObserver loop warnings are benign

WKWebView surfaces `ResizeObserver loop completed with undelivered notifications` constantly under PDF resize + Tabs + outline rail. Browser is detecting a potential layout-feedback loop and dropping a notification rather than spinning. Filtered in `frontend/src/main.tsx` via the global error banner's `BENIGN_ERROR_PATTERNS` allowlist (`fea1cb7`). The error banner stays armed for actual errors.

### The library drill-in pop animation needs scroll-into-view

The drill-in panel renders BELOW the subject grid. On a 13" display the panel often appears below the viewport fold while the user's eyes are on the card they just clicked → user reports "no animation." Fix: scroll the drill-in element into view when openSubject changes (`ac8d20b`). Same pattern likely applies to any future "click triggers panel below" UX.

### App goes blank if you don't think about Suspense fallbacks under file://

Already covered above. Worth repeating because it cost us a real debug session: if you see a blank pane in the bundled app and the chunk loaded successfully (per WebKit network log), suspect Suspense + lazy. The error banner trap in `main.tsx` catches uncaught JS errors and unhandled rejections; if neither fires AND the pane is blank, the render tree is silently empty. That points at Suspense.

## What's next

### Phase 2 of the coach

Three new rules in `services/planning/coach.py::synthesize_suggestions`. All three reason codes are pre-listed in the schema CHECK constraint (`migrations/0009_calendar_and_planning.sql`) so adding them is code-only, no migration:

```python
rules = [
    _rule_free_block_overdue_srs,           # v1 (shipped)
    # _rule_deadline_imminent,              # Phase 2: parse event summaries
    # _rule_low_recent_review,              # Phase 2: subject-staleness check
    # _rule_gap_between_classes,            # Phase 2: campus location match
]
```

The `deadline_imminent` rule is the one that makes the coach feel real:

1. Walk the next 14 days of events
2. Match each event's summary against subjects in the Library taxonomy (fuzzy match: "Corporate Finance Midterm" → "Finance" subject)
3. For matches, query SRS for the subject's weakest concepts (`mastery < 0.6`)
4. Back-solve from the event's `start_at`: 3 study sessions of 60 min each, spaced exponentially (3 days before, 1 day before, day-of)
5. Emit `study_block` suggestions with `reason_code = "deadline_imminent"`, `reason_text` like "Finance midterm in 5 days. Three sessions on weak concept Y."

Rough complexity: ~150 lines of Python, mostly fuzzy-matching + scheduler math. The hardest decision is the subject-matching heuristic — start with substring match on subject name, escalate to embedding similarity if substring fails. The match score becomes part of the suggestion's `score` field for ranking against the other rules.

### UX nice-to-haves the coach will benefit from

- **Toast action button.** `dismissSuggestion` already returns immediately and calls `POST /api/plan/suggestions/{id}/dismiss`. The hook also exposes `restoreSuggestion` which calls `POST /api/plan/suggestions/{id}/restore`. The 5-second-undo flow is fully wired EXCEPT the Toast primitive doesn't accept action buttons. Extending `ToastInput` with `{ action: { label, onClick } }` is the small primitive change. Wire it in PlanView's `handleDismissSuggestion`.
- **`PlanFilters.tsx`** — when the user has 3+ feeds, they'll want to filter by feed. Today the spec deliberately deferred this. v2 work.

### Older debts (pre-this-session)

- ESLint flat-config migration. The ESLINTRC_USE_FLAT_CONFIG warning fires on every lint run.
- `app.html.legacy` removal. Blocked on end-to-end human verification of the new bundle.
- Command palette ⌘K registry. Stubbed in `AppShell`; never built out.
- Swift menu-dispatch tests should be XCTest, not shell harness.

## File-level deltas this session

```
NEW:
  HANDOFF.md
  docs/notes/2026-04-29-session-handoff.md  (this file)
  migrations/0009_calendar_and_planning.sql
  services/calendar/__init__.py
  services/calendar/validators.py
  services/calendar/feed_client.py
  services/calendar/ical_parser.py
  services/calendar/repository.py
  services/calendar/sync_service.py
  services/planning/__init__.py
  services/planning/coach.py
  routes/calendar.py
  routes/plan.py
  tests/test_calendar_validators.py
  tests/test_calendar_parser.py
  frontend/src/features/plan/  (entire feature directory)
  frontend/tests/plan/         (entire test directory)

MODIFIED:
  CLAUDE.md                  (Current phase state + Open debts refresh)
  api_models.py              (Pydantic models for calendar/plan)
  main.py                    (lifespan startup tick)
  requirements.txt           (icalendar + recurring-ical-events)
  routes/__init__.py         (register calendar + plan)
  schema.sql                 (legacy mirror; canonical is 0009 migration)
  frontend/src/app/App.tsx
  frontend/src/app/shell/AppShell.tsx
  frontend/src/app/shell/WorkspaceSidebar.tsx
  frontend/src/features/palette/actions.ts
  frontend/src/services/native/menu.ts
  frontend/tests/bundle-size.test.ts  (budgets bumped 72→78 KB JS, 23→25 KB CSS)
```

## Known issue surfaced at handoff time (Node 25 localStorage drift)

Three tests in `tests/ask/answer-feed.test.tsx` flipped from passing to failing between the Phase 1 commit and the handoff. The error is `window.localStorage.clear is not a function`, all three on the same `beforeEach`/`afterEach` line.

Diagnosis: Node 25 added a built-in `localStorage` global that needs `--localstorage-file=<path>` to be functional — without that flag, methods like `clear()` are missing from the global. This new built-in is shadowing vitest's jsdom-provided `window.localStorage` under the current Node version. The tests were green at commit `169b84f` because Node hadn't shadowed jsdom yet (Node 25.9.0 vs whatever was running earlier).

Five-minute fix in the next session: at `tests/ask/answer-feed.test.tsx` lines 18 + 22, replace `window.localStorage.clear()` with a manual key-walk:

```ts
for (const key of Object.keys(window.localStorage)) {
  window.localStorage.removeItem(key);
}
```

Or add a setup hook in `tests/setup.ts` that explicitly defines a full Storage on `window.localStorage` per test. The latter is more durable as Node's built-in evolves.

The 3 failures are not a code regression. The Plan + Coach feature ships unaffected.

## Verify chain status

At commit time of `169b84f`:

- vitest: **266/266** (was 254 pre-Plan; +12 from `tests/plan/`)
- backend Python: **+28 new** (`tests/test_calendar_validators.py` + `tests/test_calendar_parser.py`); existing suite intact
- tsc: clean
- eslint: clean
- ruff: clean
- vite build: 226.48 KB / 73.58 KB gz JS + 144.41 KB / 22.56 KB gz CSS
- swift build: clean
- end-to-end smoke (`./script/build_and_run.sh`): app launches, all routes render, Plan view + coach work against real backend

At handoff time (after this doc was written):

- vitest: **263/266 passing, 3 failing** — all 3 in `tests/ask/answer-feed.test.tsx` due to the Node 25 localStorage drift documented above. NOT a code regression.
- backend Python: 28/28 still green
- tsc + eslint + ruff: still clean
- nothing in our code changed since `169b84f` other than this and adjacent handoff docs

If any of those go red beyond the localStorage drift after a future change, the most recent fully-green state is commit `169b84f`. Bisect against it.
