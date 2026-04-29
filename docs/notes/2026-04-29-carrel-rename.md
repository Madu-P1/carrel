## 2026-04-29 — Einstein Tutor → Carrel rename

**Scope:** Rename the product from "Einstein Tutor" to "Carrel" across user-visible
copy, brand assets, and code-internal identifiers that don't carry user data or
cross-process contracts. Defer the items where rename = data migration or
coordinated multi-process change.

**Why "Carrel":** A carrel is a small enclosed study booth in a library — semantically
aligned with the "scholarly study workspace at night" aesthetic the new design
package codifies (dark-first, single teal accent, Instrument Serif for moments
that matter). Einstein-the-name was a placeholder.

**Why three tiers:** Big-bang sed across a 1-year-old codebase is the textbook
way to ship a silently-broken weekend. There are JS globals that Swift inspects
by name, env vars that point at user data, log filenames that operators have
been tailing for weeks, and a SQLite file with months of anchors. Each of those
needs its own migration story.

---

### Tier 1 — User-visible (shipped, two commits)

**Follow-up:** the first rename commit missed the macOS Swift app's
user-visible strings. Spotted when `script/build_and_run.sh` produced a
window with the title bar still reading "Einstein". Fixed in a second
commit:

- `WindowGroup("Einstein")` → `WindowGroup("Carrel")` (window title bar)
- `NSMenu(title: "Einstein")` → `NSMenu(title: "Carrel")` and the
  `?? "Einstein"` fallback inside `MainMenuBuilder.buildAppMenu` →
  `?? "Carrel"`. The macOS app menu (leftmost bold menu) is now
  "Carrel" (resolved from `CFBundleDisplayName`, with the Swift
  fallback also up-to-date).
- "Einstein Help" → "Carrel Help" (Help menu item)
- `<h1>Einstein failed to load</h1>` → `<h1>Carrel failed to load</h1>`
  (error-fallback page rendered when the bundled HTML resource is
  missing)
- `alert.messageText = "Einstein"` → `alert.messageText = "Carrel"`
  (alert dialog title)
- `script/build_and_run.sh` — `CFBundleDisplayName` and `CFBundleName`
  in the generated `Info.plist` flipped from `Einstein` to `Carrel`.
  Bundle id, executable name, and `.app` filename stay on the
  legacy `EinsteinDesktop` per Tier 3.



What an end user sees, hears from the LLM, or reads in screenshot.

- App-shell top bar: "Einstein Workspace" → "Carrel"
  (`frontend/src/app/shell/AppShell.tsx`)
- BrandMark alt + aria + monogram fallback: "Einstein Tutor" → "Carrel" / "Cr"
  (`frontend/src/app/shell/BrandMark.tsx` + `BrandMark.module.css`)
- Shortcut overlay copy: "Fly through Einstein." → "Fly through Carrel."
- Ask view header copy + toast strings: dropped or rephrased "Einstein"
- Dashboard / Library: same
- LLM system prompts: "You are Einstein Tutor" → "You are Carrel" in
  `services/tutor.py` and `ai/claude.py`. The model now refers to itself as
  Carrel when it identifies in-conversation.
- FastAPI app title (`/docs` page): "Einstein Tutor" → "Carrel" in `main.py`
- HTTP User-Agent on calendar feed sync: `Einstein/1.0` → `Carrel/1.0` in
  `services/calendar/feed_client.py` (visible to remote calendar admins in their
  access logs)
- Repo entry-point docs: README.md, DESIGN.md, HANDOFF.md, CLAUDE.md titled
  "Carrel" with rename note + carrel etymology blockquote

### Tier 2 — Internal identifiers (shipped this commit)

Code-internal contracts that DO NOT cross process boundaries or own user data.
Renamed atomically here.

- Synthetic origin for the bundled-mode router: `https://einstein.local`
  → `https://carrel.local` in `frontend/src/app/App.tsx`,
  `frontend/src/app/shell/useAppShell.ts`,
  `frontend/src/features/ask/AskView.tsx`. (Swift legacy-frontend code path
  in `WebAppView.swift` still uses `http://einstein.local/` — see Tier 3.)
- Build-script chunk-base global: `__einsteinAssetBase` → `__carrelAssetBase`
  in `frontend/scripts/build-macos.mjs` (4 sites: writer + 3 readers) and the
  PDF worker shim (`__einsteinPdfWorkerUrl` → `__carrelPdfWorkerUrl`, 2 sites).
  Verified frontend-only via `grep -r '__einsteinAssetBase' macos-app/` returning empty.
- pdfjs setup contract: `__carrelPdfWorkerUrl` in
  `frontend/src/features/reader/lib/pdfjs-setup.ts`
- AI provider env var: `CARREL_AI_PROVIDER` is the canonical name post-rename;
  `EINSTEIN_AI_PROVIDER` is honoured as a legacy alias by both
  `ai/providers.py::select_provider` and `routes/system.py::system_status` so
  existing `.env` files don't break. The legacy alias stays supported until
  the Tier 3 sweep migrates the rest of the env namespace.
- CSS keyframe: `anim-einstein-pulse` → `anim-carrel-pulse` in
  `frontend/src/features/ask/AskView.module.css` (definition + sole usage in
  the same file; no cross-module reference).
- Error / status copy referencing the env var: updated to mention
  `CARREL_AI_PROVIDER` in `frontend/src/features/ask/errorMessages.ts` and
  `frontend/src/features/study/CardAiDraftDialog.tsx`. Backend equivalents in
  `ai/providers.py` mention both names.

### Tier 3 — Deferred (NOT in this commit)

Renaming any of these requires a real migration plan: either user-data
movement, a coordinated Swift-bundle rename, or a long backward-compat
window for env vars / log namespaces operators are already using.

#### A. SQLite database file — `data/einstein_tutor.db`

- Owner: `app_runtime.py:60`, env var `EINSTEIN_DB_PATH`
- Risk: every existing user who has been studying in the app for weeks has
  anchors, cards, calendar feeds, and review history in this file.
  Renaming without a migration loses everything.
- Migration plan when this lands:
  1. Add `CARREL_DB_PATH` env var with same default file name initially.
  2. On first boot post-rename: if `data/einstein_tutor.db` exists and
     `data/carrel.db` does not, atomically rename (or copy + verify + delete).
  3. Bump app version, document in CHANGELOG.
  4. Remove `EINSTEIN_DB_PATH` shim after one stable release window.
- Until then: the DB file keeps the legacy name. The brand says "Carrel"
  but the SQLite path on disk is `einstein_tutor.db`. That's fine — users
  don't see the path; we do.

#### B. App-runtime env namespace — `EINSTEIN_*`

- Owners: `app_runtime.py:57-63` (`EINSTEIN_BASE_DIR`, `EINSTEIN_DATA_DIR`,
  `EINSTEIN_UPLOAD_DIR`, `EINSTEIN_DB_PATH`, `EINSTEIN_SCHEMA_PATH`,
  `EINSTEIN_LOG_DIR`, `EINSTEIN_BENCHMARK_DIR`), and `services/tutor.py:828`
  (`EINSTEIN_WEAK_COVERAGE_MIN_CONTEXTS`).
- Risk: ops/devs who set these in `.env` or shell don't expect them to
  silently stop working.
- Plan: same shim pattern as `CARREL_AI_PROVIDER` — accept both names with
  the new one preferred, log a deprecation warning when the legacy name
  resolves a value, drop the legacy name after one release.

#### C. Logger namespace + log filename — `app_logging.py`

- Owners: `app_logging.py:8` (`_LOGGER_NAMESPACE = "einstein"`),
  `app_logging.py:44` (log file `einstein-backend.jsonl`).
- Risk: anyone tailing `einstein-backend.jsonl` (or grepping logs by the
  `einstein.*` logger prefix) hits a wall the day this changes.
- Plan: add a config flag (or just rename, since logs are local-only and
  there is no contract with external systems). Lean toward rename + a one-line
  note in the runbook.

#### D. Swift-bridge JS globals — `__einstein*`

- Cross-process contracts read by Swift in
  `macos-app/Sources/EinsteinDesktopApp/NativeBridge.swift` and
  `WebAppView.swift`:
  - `window.__einsteinDesktopBridgeInstalled` (idempotency flag)
  - `window.__einsteinMenuBus` (menu command pump)
  - `window.__einsteinMainStarted` (boot signal)
  - `window.__einsteinInteractiveReported` /
    `window.__einsteinInteractivePayload` (telemetry)
  - DOM IDs `__einstein_debug_banner`, `__einstein_frontend_switch_pill`
- Risk: a frontend-only rename leaves Swift looking for the old name; nothing
  works. A Swift-only rename does the same in reverse. Must be atomic across
  both sides + the macOS app build.
- Plan: when ready to do this, ship in a single commit that updates both
  trees + runs the Swift build + the frontend build + a smoke test against
  the WKWebView. Until then, the underscored prefix doesn't leak to users
  and the cost of the inconsistency is just code-reading friction.

#### E. Synthetic baseURL in legacy frontend code path — `WebAppView.swift:162`

- Swift loads the legacy (pre-Preact) bundled HTML with
  `baseURL: URL(string: "http://einstein.local/")`. This is the legacy
  frontend code path only; the modern Preact frontend uses `loadFileURL`.
- Risk: localStorage keyed under `einstein.local` is in the legacy origin's
  namespace. Renaming the synthetic origin orphans that data. The legacy
  frontend isn't actively maintained, so this is mostly a cosmetic
  inconsistency (`carrel.local` in modern frontend, `einstein.local` in legacy).
- Plan: rename when the legacy frontend code path is removed entirely
  (which is on the roadmap — see `docs/notes/2026-04-21-legacy-https-origin.md`).

#### F. localStorage key — `einstein.ask.anchor-drafts`

- Owner: `frontend/src/features/ask/anchorDrafts.ts:3`
- Risk: every user who has typed an anchor draft in the Ask view but not
  saved it has it persisted under this key. Renaming = data loss.
- Plan: when ready, do the rename + a one-time read-old-write-new-delete-old
  migration on app start. Cheap, ~10 lines.

#### G. Logo asset — `frontend/src/assets/logo.png` ✅ SHIPPED

- Owner: the BrandMark component renders this PNG.
- 2026-04-29: Carrel logo dropped in by the user — a 474×444 dark navy
  squircle with a white lowercase "c" and a teal accent dot at the
  bottom-right of the bowl. Same file simultaneously serves as the
  macOS dock-tile icon source via `macos-app/Resources/icon-source.png`
  (kept in sync — copied from the frontend asset, then
  `script/generate-icon.sh --force` regenerates the multi-resolution
  `AppIcon.icns` bundle).
- Future iterations: if a higher-resolution version (1024×1024)
  becomes available, drop it at the same path and rerun
  `script/generate-icon.sh --force`. macOS Big Sur and later prefer
  1024×1024 sources for the sharpest Retina rendering.

#### H. macOS bundle identity

- `com.madu.EinsteinDesktop` (bundle ID), `EinsteinDesktop.app` (bundle name),
  `macos-app/Sources/EinsteinDesktopApp/` (Swift target dir),
  `EinsteinDesktopApp` (Swift `@main` struct), `EinsteinIngestionBridge`
  (helper binary referenced from `services/extraction/utils.py:12-14`).
- Risk: changing the bundle ID re-prompts the user for every privacy-scoped
  permission (Documents, Downloads, calendar). Renaming the .app and the
  Swift target dir is a coordinated Xcode + filesystem rename.
- Plan: do this when a new release rolls a fresh installer. Treat it like a
  product re-release. Keep the old install discoverable for users who
  upgrade in place — provide a migration assistant or an in-app one-time
  notice that points them to the new install.

---

### What this means for the next session

If you see "Einstein" in the codebase, check this list:

- In a UI string, comment about the brand, system prompt, or doc title? → fix it.
- In an env var literal, log filename, DB path, Swift bridge global, or the
  legacy frontend's `einstein.local` baseURL? → leave it; it's deferred here.

If you're unsure, leave it and add the file path to this note's deferral
section. The cost of a missed rename is one extra grep pass; the cost of
an unplanned rename of a contract identifier is data loss or a broken
desktop launch.

Also: `docs/plans/`, `docs/roadmap/`, and historical `docs/notes/` files
keep their original "Einstein" naming as historical record. Don't sweep
them; they document what the project was called when those decisions were
made.
