# Changelog

All notable changes to Carrel will be recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the
project tracks [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The version source of truth is the top-level `VERSION` file. The
macOS Info.plist (`CFBundleShortVersionString` and `CFBundleVersion`)
is generated from it at build time.

## [Unreleased]

### Changed
- **`services/documents.py` split** (831 → 241 LoC, down 71%) into three
  focused modules: `services/document_duplicates.py` (243 LoC, source-hash
  duplicate detection), `services/library_subjects.py` (193 LoC, subject
  grouping + per-subject summaries), and `services/concept_labels.py`
  (391 LoC, label cleanup + selector ranking + curated-options cache).
  All public names re-exported from `services/documents.py` so the 11
  importing modules keep working unchanged.

### Added
- 45 new focused unit tests covering the extracted modules
  (`test_document_duplicates.py`, `test_library_subjects.py`,
  `test_concept_labels.py`).

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
