# Changelog

All notable changes to Carrel will be recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the
project tracks [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The version source of truth is the top-level `VERSION` file. The
macOS Info.plist (`CFBundleShortVersionString` and `CFBundleVersion`)
is generated from it at build time.

## [Unreleased]

### Removed
- **Legacy frontend completely deleted.** The `app.html.legacy` bundle
  (303 KB), `Frontend.legacy` enum case, the entire `FrontendSelector`
  module, the `FrontendSwitchHandler` class, the Carrel > Frontend
  submenu, the `nativeFrontend` JS bridge, the `--frontend new|legacy`
  flag in `build_and_run.sh` + `measure_cold_launch.sh`, the
  `EINSTEIN_FRONTEND` env var, and the `system.switch-frontend-*`
  command-palette entries. Three stale Finder duplicates of the new
  HTML (`app.new 3.html` / `4.html` / `5.html`) cleaned up too.
  `loadBundledApp` now unconditionally loads `app.new.html`.

### Changed
- `LaunchTelemetry.markLaunch`/`markInteractive` now receive a
  hardcoded `frontend: "new"` (was: `FrontendSelector.resolved().rawValue`).

### Changed
- **`services/documents.py` split** (831 → 241 LoC, down 71%) into three
  focused modules: `services/document_duplicates.py` (243 LoC, source-hash
  duplicate detection), `services/library_subjects.py` (193 LoC, subject
  grouping + per-subject summaries), and `services/concept_labels.py`
  (391 LoC, label cleanup + selector ranking + curated-options cache).
  All public names re-exported from `services/documents.py` so the 11
  importing modules keep working unchanged.
- **`services/artifact_studio.py` split** (886 LoC flat module → 4-module
  package). Path: `services/artifact_studio/__init__.py` re-exports the
  public surface; `_orchestrator.py` (~270 LoC) holds `generate_artifact`,
  `list_artifacts`, `get_artifact`; `grounding.py` (~265 LoC) handles
  chunk + concept retrieval; `topic_map.py` (~155 LoC) is pure-function
  focus selection + topic grouping; `generators.py` (~305 LoC) houses
  the 9 markdown generators, 3 item builders, kind-dispatch, and the
  shadow JSON `_hidden_artifact_payload`. External callers
  (`routes/studio.py`, `benchmarks/phase0.py`) keep working via the
  re-export. Closes the audit's "god-object services" item completely.

### Added
- 45 new tests for the documents.py split (`test_document_duplicates.py`,
  `test_library_subjects.py`, `test_concept_labels.py`).
- 35 new tests for the artifact_studio package — `test_artifact_studio_grounding.py`,
  `test_artifact_studio_topic_map.py`, `test_artifact_studio_generators.py`,
  `test_artifact_studio_orchestrator.py`. The orchestrator tests are the
  first coverage this code has had since it landed.
- `requested_kind` field on the `/api/studio/generate` response payload.
  Surfaces unknown-`artifact_kind` rewrites to the frontend so a typo'd
  kind doesn't silently degrade. Backed by an `artifact_kind_rewritten`
  audit log entry.

### Security
- `StudioGenerateRequest.custom_prompt` now has `Field(max_length=4000)`
  cap. Bounds the persisted JSON and the reflected payload returned by
  `get_artifact`. Pydantic 422 at the route boundary on overflow.

### Companion cube perfection (12-item pass)
- **Drag math hardened**: threshold measured from `dragOriginScreen`
  (not per-event), increment posted from `lastPostedScreen` (not last
  pointermove). Slow drags + coalesced events both correct now.
- **Reduced-motion alarm fallback**: vestibular-sensitive users now
  see a slow color pulse instead of the spinning cube. Pre-fix they
  had no visual alarm signal at all.
- **Slowed alarm spin** from 0.55s/rev (~109 RPM, vestibular hazard)
  to 0.9s/rev (~67 RPM). Still reads as urgent peripheral motion.
- **Unknown-state warning**: `applyState('typo')` used to silently
  no-op. Now logs to console + posts `{action:'log', event:'unknown_state'}`
  to the Swift bridge.
- **Tokenized timing**: `--spin-alarm`, `--spin-drag`, `--drift-idle`,
  etc. in CSS `:root`; matching `TIMING` object in JS. Magic numbers
  gone.
- **Symmetric left face**: was `['b','b','o','b','o','o','o','o','o']`
  (4 brights, asymmetric). Now `DIAMOND` shared with front. Reads
  cleanly at all rotations.
- **Pointer-release-outside fallback**: `window.blur` and
  `document.mouseleave` now end a stuck drag the way `pointercancel`
  doesn't reliably.
- **Bounded timer registry**: `setT()` wrapper auto-removes fired
  timers from the Set; long idles can't grow it without bound.
- **Real `setStreakDays`**: was a no-op stub kept "for bridge compat."
  Now renders 1-3 brights on the front face's bottom row; >3 days
  adds a slow pulse. Re-applies after state transitions.
- **Tightened visibilitychange**: was `querySelectorAll('*')`, now
  scoped to `.face, .cell, .cube3d, .drift, .anchor, .aura`.
- **`idleTwinkle` skips streak row**: regression caught by
  adversarial review — pre-fix, twinkle clobbered streak cells every
  few seconds. Now filters positions 6..6+streakDays.
- **21 vitest+jsdom tests** pinning state machine, alarm orthogonality,
  drop-ready, streak rendering (including the regression), drag bridge
  contracts, and pointer-release-outside fallback.

## [0.1.0] — 2026-05-05

First tagged release. Carrel runs locally on macOS as a SwiftUI/WKWebView
shell over a FastAPI backend, with a Preact frontend, EventKit calendar
sync, deadline-aware study planning, an SRS-style review flow, an
LLM-driven tutor, and a floating NSPanel companion cube.

### Added
- Floating companion cube — draggable NSPanel above all spaces;
  accepts file drops routed to the Library; spins chaotically when a
  scheduled study session starts; tap to dismiss + open Carrel.
- Study-session alarm watcher — fires at the soonest of: a calendar
  study block (matched by `\b(study|studying|revision|revise)\b`) or
  a planner-suggested insertion. Re-arms after dismissal; 5-minute
  heartbeat covers SSE drops.
- Live calendar — 24-hour scrollable week grid with sticky day headers,
  auto-scroll to current hour, teal NowIndicator updating every 30s,
  SSE-driven `calendar-changed` live refresh.
- Apple Calendar (EventKit) sync — local calendar events flow through
  the shared `calendar_feeds` table with `kind='local'`, lighting up
  planning + coach pipelines with no parallel code path.
- Shared SSE multiplexer — one `EventSource` per URL with refcounted
  teardown and exponential 1.5 s → 30 s reconnect backoff. Replaces
  four independent EventSources across plan view, dashboard, jobs
  feed, and companion alarm.
- Library subjects — add, rename, group documents by subject; new
  `services/subjects.py` and `migrations/0013_library_subjects.sql`.
- Token-gated local API — every `/api/*` request now requires
  `X-Carrel-Local-Token` (header) or `?token=…` (query, for SSE);
  allowlist is `/`, `/api/health`, `/api/local-token`, `/api/metrics`,
  `/static/*`. Audit P0.
- Observability — `services/observability.py` adds request-id middleware
  (assigns/honors `X-Request-ID`, threads it into JSON logs via
  `ContextVar`), in-memory metrics counters with a `/api/metrics`
  JSON snapshot, and opt-in Sentry init via `SENTRY_DSN`.
- Backup + restore — `script/backup_db.sh` (atomic `sqlite3 .backup`,
  bzip2-compressed, 14 daily + 8 weekly retention), `script/restore_db.sh`
  (round-trips through `.pre-restore-<ts>` so it's reversible),
  `script/test_backup_restore_drill.sh` (end-to-end CI drill).
- macOS app hardening — `Info.plist` now includes `CFBundleVersion`,
  `LSApplicationCategoryType`, `NSDownloadsFolderUsageDescription` and
  the other folder usage descriptions required for drag-drop file
  uploads. Entitlements add `disable-library-validation`,
  `allow-dyld-environment-variables`, and `personal-information.calendars`
  so the EventKit prompt doesn't fail silently and the bundled native
  Python extensions load under the hardened runtime.
- Dependabot config + pinned `requirements.lock` / `requirements-dev.lock`.
  CI installs from the lockfile, with `setup-python@v5`'s `cache: pip`.
- `docs/runbook.md` — operational playbook for backups, common
  failures, observability access, and the release process.

### Fixed
- Auth fail-open: GET endpoints used to be world-readable on the
  local machine; now gated by the same token middleware as mutating
  verbs.
- Migration 14 was missing from the legacy-baseline detection in
  `db.py::_mark_legacy_baseline_if_needed`. Any DB whose
  `schema_migrations` table got dropped would crash on next start
  with "duplicate column name: kind".
- `WeekTimeGrid.tsx` ESLint warnings on complex dependency-array
  expressions (broke CI under `--max-warnings 0`).
- Dialog scroll glitch: both `.focus()` calls now pass
  `preventScroll: true`, fixing the visible scroll-jump on event
  detail open/close.

### Removed
- 23 macOS Finder duplicate files (`* 2.*`) that had accumulated
  across `routes/`, `services/`, `tests/`, `script/`, `frontend/`,
  and `macos-app/Resources/` — including diverged stale copies of
  `services/jobs.py`, `services/uploads.py`, and
  `tests/test_upload_security.py`. CI now fails fast if any
  reappear.
- Dead `frontend/src/features/companion/` directory (~400 LoC, never
  imported in production after the floating-cube migration to
  `FloatingCompanionWindow.swift`'s WKWebView). Tests deleted with it.

[Unreleased]: https://github.com/Madu-P1/carrel/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Madu-P1/carrel/releases/tag/v0.1.0
