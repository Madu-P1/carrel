# Ship Hardening + User-Facing AI Provider Selector

> **Plan created:** 2026-05-21 · **Target repo:** `/Users/madu/Desktop/Codex` (Carrel)
> **Author:** orchestrated via `make-plan` after a 3-subagent discovery pass.
> **Status:** awaiting founder sign-off on the open decisions in §Open Decisions.

## Goal

Two connected workstreams that together let Carrel ship to real users:

- **A — Shipping & terminal-build hardening:** make the package/ship pipeline fast,
  reliable, and verifiable so a signed public-beta DMG can be cut with confidence.
- **B — User-facing AI provider selector:** an in-app Settings surface where the user
  picks Claude / Ollama / Apple Intelligence, enters a Claude API key (stored in the
  macOS Keychain), and sees live per-provider availability — replacing the
  `CARREL_AI_PROVIDER` env-var-only mechanism.

Each phase below is **independently shippable** and ends green on the verify chain.

### Verify chain (every phase)

```bash
# Frontend  (cd frontend)
pnpm exec tsc --noEmit && pnpm exec vitest run
# Backend   (repo root)
./.venv/bin/python -m ruff check . && ./.venv/bin/python -m pytest
# Swift      (cd macos-app)
swift build
```

Baselines at plan time: frontend ~346 Vitest tests, backend ~364 pytest, all green.

---

## Phase 0 — Documentation Discovery (COMPLETE)

This section is the **Allowed APIs** list. Every later phase cites it. Do not invent
APIs beyond what is listed here without re-verifying against the repo.

### A. Build / ship pipeline — verified facts

| Fact | Evidence |
|------|----------|
| `swift build` (no `--target`) builds **all 3** targets incl. `EinsteinAFMBridge` | `macos-app/Package.swift:15-41`; `script/build_and_run.sh:240` |
| Build is **debug config** — no `-c release` anywhere | `build_and_run.sh:240-241` |
| `swift build` invoked **twice** (2nd is `--show-bin-path`, redundant) | `build_and_run.sh:240-241` |
| `.app` assembly **already copies BOTH bridges** + `chmod +x` | `build_and_run.sh:254-256` |
| `Info.plist` written via heredoc; `LSMinimumSystemVersion` 14.0 | `build_and_run.sh:294-322` |
| `CARREL_BUNDLE_MACOS` set **only** by the Swift supervisor (Finder/DMG launch) | `BackendSupervisor.swift:187-188` |
| Bash-spawned dev backend does **NOT** export `CARREL_BUNDLE_MACOS` (asymmetry) | `build_and_run.sh:146-178` exports only `CARREL_LOCAL_API_TOKEN` |
| Python reads `CARREL_BUNDLE_MACOS`, falls back to `.build/{debug,release}` | `ai/native_bridge_paths.py:30-33` |
| `install.sh` **already** detects macOS version + `arm64` + `en_US` locale | `install.sh:75-113` (`AFM_ELIGIBLE`) |
| `install.sh` does **NOT** probe runtime AFM/Ollama availability or validate the key | `install.sh:86-87` |
| `package_public_beta.sh` codesigns + notarizes + builds DMG | `script/package_public_beta.sh:42-104` |
| `validate_public_beta_package.sh` does **NOT** check bridge-binary presence | `script/validate_public_beta_package.sh:43-78` |
| `EinsteinAFMBridge/main.swift` **already handles `kind == "availability"`** | `main.swift:328`; states mapped at `main.swift:204-212` |

### B. AI provider layer — verified facts

| Fact | Evidence |
|------|----------|
| `AIProvider` Protocol — `@runtime_checkable`, 8 methods | `ai/providers.py:55-153` |
| `ProviderKind = Literal["claude","ollama","afm","null"]` | `ai/providers.py:52` |
| Protocol does **not** declare `kind`; only `NullProvider` + `AFMClient` carry it | `providers.py:168`, `afm_client.py:64` |
| `ClaudeRouter` / `OllamaClient` have **no `kind` attr** — inferred by class name | `routes/system.py:25-39` |
| `select_provider()` reads `CARREL_AI_PROVIDER` ‖ `EINSTEIN_AI_PROVIDER` ‖ `"auto"` | `ai/providers.py:311-349` |
| auto-resolution order: Claude → AFM → Ollama → Null | `ai/providers.py:311-349` |
| `get_default_provider()` caches, keyed by env-signature hash; **no restart needed** | `providers.py:357-407` |
| `reset_default_provider()` + `reset_default_afm_client()` exist | `providers.py:410-417`, `afm_client.py:737-740` |
| `ClaudeRouter._client()` re-reads `ANTHROPIC_API_KEY` **every call** | `ai/router.py:223-224` |
| Claude key today: `ANTHROPIC_API_KEY` env only, from `.env` at import | `ai/router.py:224`, `app_runtime.py:11-31` |
| `app_settings(key TEXT PRIMARY KEY, value TEXT)` table exists | `schema.sql:112-115` |
| `get_setting()` / `set_setting()` helpers (upsert, commit) | `services/app_state.py:17-31` |
| `routes/system.py` exposes **read-only** `GET /api/system/provider` + `/api/shell/status` | `routes/system.py:64-102` |
| Local-API token middleware gates **all `/api/*`** (except `/api/health`) | `main.py:144-156`, `services/local_api_security.py:45-66` |
| **Keychain precedent:** `MacOSKeychainCalendarSecretStore` via `security` CLI + memory fallback | `services/calendar/secrets.py:69-153` |
| **No live health probe** on any provider — `ai_enabled()` is config-only everywhere | `router.py:239-240`, `ollama.py:193-201`, `afm_client.py:96-100` |
| Backend routers registered in `register_routes()` | `routes/__init__.py:23-47` |

### C. Frontend — verified facts

| Fact | Evidence |
|------|----------|
| Feature folder anatomy: `<Name>View.tsx` + `.module.css` + `components/` + opt `hooks/` | `frontend/src/features/library/` |
| Nav items literal: `navLinks: SidebarNavItem[]` | `app/shell/AppShell.tsx:56-70` |
| `SidebarNavItem.key` + `.icon` are **string-literal unions** — both must be extended | `app/shell/WorkspaceSidebar.tsx:10-40` |
| Sidebar sections filter by `key` — a new key needs a section entry | `WorkspaceSidebar.tsx:89-104` |
| **TWO routers**: `BoundedRoutes` (preact-iso, dev) AND `renderBundledRoute` (file://, prod) | `app/App.tsx:92-152` + `164-184` |
| API client: `api<T>(path, init)`; token auto-attached; 403 path documented | `services/api/client.ts:74-128` |
| Typed endpoint wrappers live in `services/api/endpoints.ts` (1138 lines) | `services/api/endpoints.ts` |
| Data fetching: `createQuery` from `@/lib/query` + `@preact/signals` | `features/library/hooks/useDocumentsQuery.ts:8` |
| Design-system primitives from `@/design-system`: `Input Button Card Dialog Stack Text Badge Tabs` + `showToast` | `design-system/index.ts` |
| **No radio-group primitive** — use `Tabs` or a `Button` group for the picker | `design-system/index.ts` (absence) |
| Provider chip already rendered in the sidebar footer (`ProviderFooter`) | `WorkspaceSidebar.tsx:291-372` |
| Tests colocated as `*.test.tsx`; every design-system primitive has one to copy | `design-system/primitives/Input/Input.test.tsx` |

### Anti-patterns to avoid (discovered)

- **Do NOT** add an `availability` *kind* to `EinsteinAFMBridge/main.swift` — it already
  exists (`main.swift:328`). Only the Python wrapper is missing.
- **Do NOT** route-split the Settings page via `lazy()` + `Suspense` — preact/compat
  Suspense is broken under the bundled `file://` shell (see `App.tsx:21-37`). Static
  import only.
- **Do NOT** make `select_provider()` import `db` — that couples the AI layer to
  persistence. Bridge via env mutation (see Phase 2).
- **Do NOT** assume a backend restart is needed for runtime switching — it is not
  (`router.py:223-224`). Only the AFM singleton needs `reset_default_afm_client()`.
- **Do NOT** write the Claude API key into SQLite or `.env` in plaintext (see Phase 2 +
  Open Decisions).
- **Do NOT** add a second router branch and forget the other — `App.tsx` has two; both
  need the Settings entry.

---

## Phase 1 — Provider identity + availability probes (backend + Python)

**Why first:** both the install-time probe (Phase 3) and the Settings UI (Phase 4)
need live per-provider availability. Today no provider has a health probe. This phase
builds that foundation with **zero UI and zero behavior change** to existing flows.

### What to implement

1. **Add `kind` to the two providers missing it.** Copy the pattern from
   `NullProvider` (`providers.py:168`: `kind: ProviderKind = "null"`):
   - `ai/router.py` → `ClaudeRouter`: add `kind: ProviderKind = "claude"`.
   - `ai/ollama.py` → `OllamaClient`: add `kind: ProviderKind = "ollama"`.
   - Then simplify `routes/system.py:25-39` to read `provider.kind` directly (keep the
     class-name fallback as defence, but `kind` is now always present).

2. **Add `AFMClient.probe_availability()`.** The Swift bridge already answers
   `kind == "availability"` (`main.swift:328`) returning `availability_state` ∈
   `{available, device_not_eligible, apple_intelligence_not_enabled, model_not_ready}`
   (`main.swift:204-212`). Add a Python method that sends `{"kind": "availability"}`
   through the existing `_call()` round-trip (`afm_client.py:542-674`) and returns a
   typed result. Mirror the request shape already used for `request_text`.

3. **Add `OllamaClient.probe_reachable()`.** No ping exists today. Add a method that
   GETs `<base_url>/api/tags` with a short timeout (~1.5 s) using the injected
   `_http_client` seam (`ollama.py:142-178`) and returns reachable / unreachable.

4. **Add a `ProviderAvailability` dataclass + `probe_all_providers()`** in
   `ai/providers.py`. Returns, for each of `claude / ollama / afm`:
   `{kind, configured: bool, available: bool, detail: str, error_code: str | None}`.
   - claude: `configured` = `_claude_has_key()` (`providers.py:264`); `available` same
     (no cheap network probe — documented).
   - ollama: `configured` = `_ollama_has_endpoint()`; `available` = `probe_reachable()`.
   - afm: `configured` = `_afm_available()` (OS gate); `available` from
     `probe_availability()`; `error_code` carries `apple_intelligence_not_enabled` etc.

### Documentation references

- Copy `kind` declaration: `ai/providers.py:168`.
- Copy bridge round-trip shape: `ai/afm_client.py:542-674` (`_call`), request kinds at
  `afm_client.py:563`.
- Copy availability-state names verbatim from `main.swift:204-212`.
- Test template: `tests/test_afm_client.py` (mocks `subprocess.run` via the
  `run_subprocess` constructor seam) and `tests/test_ai_providers.py`.

### Verification checklist

- [ ] `grep -rn "kind: ProviderKind" ai/` shows 4 providers (claude, ollama, afm, null).
- [ ] New tests: `test_afm_client.py::test_probe_availability_*` (happy + each error
      state, mocked subprocess); `test_ollama_client.py::test_probe_reachable_*`
      (mocked httpx); `test_ai_providers.py::test_probe_all_providers`.
- [ ] `routes/system.py` GET responses unchanged in shape (regression: existing
      `test` for `/api/system/provider` still green).
- [ ] Full verify chain green; pytest count up, none down.

### Anti-pattern guards

- Do not add an `availability` kind to the Swift bridge — it exists.
- Do not make `probe_reachable()` block longer than ~1.5 s — the UI calls it live.
- Do not call the Anthropic API to "probe" Claude — `configured` is enough; a real
  call costs tokens. Surface reachability only at actual call time (existing contract).

---

## Phase 2 — Secure settings backend (keychain key store + provider persistence + route)

**Why second:** the UI (Phase 4) needs a durable place to write the provider choice
and the API key, and a route to call. This phase adds persistence + a read/write route
with **no UI** — testable entirely via pytest + curl.

### What to implement

1. **Generalize the keychain store for the API key.** Copy `services/calendar/secrets.py`
   (`MacOSKeychainCalendarSecretStore` + `FallbackCalendarSecretStore` + memory
   fallback, `secrets.py:38-153`) into a new `services/secret_store.py` with a generic
   `store_secret(name, value) / get_secret(name) / delete_secret(name)` shape. Service
   id: `carrel.ai.anthropic-key`. Keep the **memory fallback** — keychain is
   unavailable in CI / unsigned builds, and the fallback keeps the key out of SQLite.

2. **Persist the provider choice** to the existing `app_settings` table via
   `services/app_state.py` helpers — key `ai.provider`, value ∈
   `claude|ollama|afm|auto|off`. The API key is **never** in `app_settings`; only a
   boolean "key is set" flag is derivable from the keychain.

3. **Bridge persistence → `select_provider()` without coupling.** On backend startup
   (`main.py` lifespan / startup), read `app_settings['ai.provider']` and the keychain
   key, then set `os.environ["CARREL_AI_PROVIDER"]` and `os.environ["ANTHROPIC_API_KEY"]`
   accordingly **before** any provider is constructed. `select_provider()` stays a pure
   env reader (anti-pattern guard above).

4. **New route module `routes/settings.py`** — copy the structure of
   `routes/onboarding.py` (minimal `APIRouter` + `register_settings_routes(app)`) and
   the provider-payload pattern from `routes/system.py:23-61`:
   - `GET /api/settings/ai` → `{provider, key_set: bool, availability: {...}}` where
     `availability` is `probe_all_providers()` from Phase 1.
   - `POST /api/settings/ai` body `{provider?, anthropic_key?}` →
     persists provider to `app_settings`; stores/clears the key in the keychain;
     mutates `os.environ`; calls `reset_default_provider()` + `reset_default_afm_client()`;
     returns the fresh `GET` payload. **No backend restart.**
   - Register in `routes/__init__.py:register_routes()` (add `register_settings_routes(app)`).
   - Auth is automatic — the local-API-token middleware (`main.py:144-156`) gates all
     `/api/*`.

5. **Input validation.** `provider` must be in the allowed set (422 otherwise).
   `anthropic_key` length-capped; trimmed; never logged (see security note).

### Documentation references

- Copy keychain store: `services/calendar/secrets.py:38-153`.
- Copy settings persistence: `services/app_state.py:17-31`.
- Copy route skeleton: `routes/onboarding.py` (whole file) + `routes/system.py:23-76`.
- Copy singleton reset: `ai/providers.py:410-417`, `ai/afm_client.py:737-740`.
- Route registration: `routes/__init__.py:23-47`.

### Verification checklist

- [ ] `tests/test_settings_route.py`: GET returns shape; POST switches provider and a
      follow-up GET reflects it; POST with bad provider → 422; key store/clear round-trips
      (memory fallback in CI).
- [ ] `tests/test_secret_store.py`: store→get→delete round-trip on the memory fallback;
      keychain path skipped unless `platform.system() == "Darwin"` and signed.
- [ ] Manual: `curl -H "X-Carrel-Local-Token: $TOK" -X POST .../api/settings/ai
      -d '{"provider":"ollama"}'` flips the sidebar `ProviderFooter` after one refresh.
- [ ] Full verify chain green.

### Security (call out explicitly)

- **API key at rest:** macOS Keychain via the `security` CLI — never SQLite, never
  `.env` written by the app. Memory fallback only for CI/unsigned. See Open Decision #1.
- **Never log the key.** `GET` returns `key_set: bool`, never the value. Audit
  `app_logging` call sites in the new route — no key, no PII.
- **Local-API token** already protects the POST — no new auth code, but confirm the
  route path starts with `/api/` so the middleware catches it.

---

## Phase 3 — Shipping & terminal-build hardening (Workstream A)

**Why third:** with Phase 1's probes available, `install.sh` can give the user a real
availability verdict. This phase makes the ship pipeline fast, correct, and verifiable.

### What to implement

1. **Fix the `CARREL_BUNDLE_MACOS` asymmetry.** `build_and_run.sh::ensure_backend`
   (`:146-178`) spawns uvicorn without exporting `CARREL_BUNDLE_MACOS`. Add an
   `export CARREL_BUNDLE_MACOS="$APP_MACOS"` before the spawn (insert near `:107-110`
   alongside the existing token export) so dev and bundled launches resolve bridges
   identically.

2. **Make the validator assert the bridges ship.** `validate_public_beta_package.sh`
   checks `app.new.html` / `assets.new` / icon / demo PDFs (`:46-51`) but **not** the
   bridge binaries. Add, after `:51`:
   `test -x "$APP/Contents/MacOS/EinsteinIngestionBridge"` and
   `test -x "$APP/Contents/MacOS/EinsteinAFMBridge"` with a clear failure message.

3. **Install-time availability probe in `install.sh`.** After the existing
   `AFM_ELIGIBLE` block (`:75-113`), once the `.venv` exists, run a one-shot:
   `./.venv/bin/python -c "from ai.providers import probe_all_providers; ..."`
   (the Phase 1 function) and print the verdict per provider — specifically surface
   AFM `apple_intelligence_not_enabled` vs `model_not_ready` vs `device_not_eligible`,
   and document the **post-enable model-download wait window** (1–30 min; watch
   `modelcatalogd`/`mobileassetd`). Source this text from the existing AFM runbook
   (`docs/plans/afm-runbook-2026-05-10.md`).

4. **Build-speed optimization.** In `build_and_run.sh`:
   - Run the frontend `pnpm build:macos` and `swift build` **in parallel** (they are
     independent — frontend writes `Resources/`, swift writes `.build/`). `wait` on
     both before `.app` assembly. This is the largest realistic win.
   - Remove the redundant second `swift build` at `:241`; capture `--show-bin-path`
     once or derive the path.
   - Add coarse timing (`SECONDS` checkpoints) printed at the end so regressions show.
   - `package_public_beta.sh` should build the swift targets with `-c release`
     (`build_and_run.sh` gains an opt-in `--release` flag the packager passes).

5. **Codesigning readiness.** `package_public_beta.sh:42-104` is already correct; the
   blocker is operational, not code — see Open Decision #4. Document in
   `CARREL_BUILD_RUNBOOK.md` (or a correctly-named new `docs/SHIP.md`) the exact env
   vars (`CARREL_CODESIGN_IDENTITY`, `CARREL_NOTARY_PROFILE`) and the
   `xcrun notarytool store-credentials` one-time step.

### Documentation references

- Insertion points: `build_and_run.sh:107-110` (env), `:146` (backend spawn), `:240-241`
  (swift build), `:244-256` (bundle assembly).
- Validator insertion: `validate_public_beta_package.sh:51`.
- Install probe insertion: `install.sh:113`.
- Wait-window copy: `docs/plans/afm-runbook-2026-05-10.md`.

### Verification checklist

- [ ] `bash script/build_and_run.sh` still produces a launchable `dist/EinsteinDesktop.app`;
      timing line printed; parallel build verified faster than the sequential baseline.
- [ ] Dev-launched backend log shows `CARREL_BUNDLE_MACOS` set (grep the backend log).
- [ ] `bash script/validate_public_beta_package.sh --allow-unsigned` fails loudly if a
      bridge binary is removed from the bundle (test by `rm` then restore).
- [ ] `bash script/package_public_beta.sh --local-unsigned` produces a DMG that passes
      the validator.
- [ ] `install.sh` dry-run prints a per-provider availability verdict.
- [ ] `swift build` in `macos-app/` green; full verify chain green.

### Anti-pattern guards

- Do not add a "build the AFM target" step — `swift build` already builds all targets.
- Do not add a "copy AFM bridge into bundle" step — `build_and_run.sh:254-256` does it.
- Do not parallelize the `.app` assembly with the builds — assembly *consumes* both
  outputs; only the two builds parallelize.
- Do not skip notarization to "ship faster" — an un-notarized DMG is Gatekeeper-blocked
  on every other Mac. It is a hard requirement, not an optimization.

---

## Phase 4 — Settings UI feature (Workstream B, frontend)

**Why fourth:** depends on Phase 2's route. Adds the actual user-facing surface.

### What to implement

1. **New feature folder `frontend/src/features/settings/`** — copy the anatomy of
   `features/library/`: `SettingsView.tsx`, `SettingsView.module.css`,
   `components/`, `hooks/useAiSettings.ts`.

2. **Typed endpoint wrappers** in `services/api/endpoints.ts` — add a `settings`
   object with `getAi()` / `updateAi(body)` calling `api()` against
   `/api/settings/ai`, mirroring the existing `documents` wrappers.

3. **Data hook `useAiSettings.ts`** — copy the `createQuery` + `@preact/signals`
   pattern from `features/library/hooks/useDocumentsQuery.ts`. Exposes current
   provider, `key_set`, and per-provider availability; a `save()` action that POSTs
   and refetches.

4. **`SettingsView.tsx`** — three provider cards (Claude / Ollama / Apple Intelligence):
   - Picker via a `Button` group or `Tabs` (no radio primitive exists).
   - Claude card: an `Input` (type `password`) for the API key; shows "key set" not the
     value; a Save button. Optional cheap key validation — see Open Decision #3.
   - Apple Intelligence card: when availability `error_code` is
     `apple_intelligence_not_enabled`, render a button that deep-links to System
     Settings (`x-apple.systempreferences:com.apple.Siri-Settings.extension` — verify
     the exact URL scheme on macOS 26 before shipping); when `model_not_ready`, show
     the download-wait note; when `device_not_eligible`, disable the card with a reason.
   - Ollama card: reachable / "Ollama not running" with the `ollama serve` hint.
   - Use `showToast` from `@/design-system` for save success/failure.

5. **Wire navigation — all four sites:**
   - `app/shell/WorkspaceSidebar.tsx:10-40`: add `"settings"` to the `key` union and a
     `"settings"`/`"command"`-style value to the `icon` union (pick an existing
     `IconName`; add one only if none fits).
   - `app/shell/AppShell.tsx:56-70`: add
     `{ key: "settings", label: "Settings", commandHint: "⌘,", icon: "...", path: "/settings" }`.
   - `WorkspaceSidebar.tsx:89-104`: add `"settings"` to a section filter (a new
     "Workspace" section, or the Tools section).
   - `app/App.tsx`: add `<Route component={SettingsView} path="/settings" />` to
     `BoundedRoutes` (`:164-184`) **and** an `if (path.startsWith("/settings"))` branch
     to `renderBundledRoute` (`:92-152`). Both routers — see anti-pattern guard.

6. **Make the sidebar `ProviderFooter` a shortcut** — clicking it navigates to
   `/settings` (it already shows provider state; `WorkspaceSidebar.tsx:291-372`).

### Documentation references

- Feature anatomy: `features/library/` (`LibraryView.tsx`, `hooks/`, `components/`).
- Data hook: `features/library/hooks/useDocumentsQuery.ts:8` (`createQuery`).
- API wrapper pattern: `services/api/endpoints.ts` (`documents` object).
- Nav literal: `app/shell/AppShell.tsx:56-70`; type unions:
  `app/shell/WorkspaceSidebar.tsx:10-40`.
- Both routers: `app/App.tsx:92-152` and `:164-184`.
- Component test template: `design-system/primitives/Input/Input.test.tsx`.
- Static-import-only constraint: `App.tsx:21-37`.

### Verification checklist

- [ ] `SettingsView.test.tsx`: renders three cards; picking a provider calls
      `updateAi`; entering a key + Save posts it; availability error states render the
      right affordance (deep-link / wait note / disabled).
- [ ] `pnpm exec tsc --noEmit` green — the union extensions compile.
- [ ] Manual in the bundled app: `/settings` reachable from the sidebar **and** the
      `⌘,` hint; switching provider updates the sidebar footer; nav works in both dev
      (`vite`) and bundled (`file://`) modes.
- [ ] Vitest count up, none down; full verify chain green.

### Anti-pattern guards

- Do not `lazy()`/`Suspense` the Settings route — static import (see `App.tsx:21-37`).
- Do not update only one router — `App.tsx` has two; QA both modes.
- Do not render the API key value back to the client — `key_set` boolean only.
- Do not invent a `RadioGroup` primitive — `Tabs` or `Button` group.

---

## Phase 5 — Verification, documentation, release dry-run

### What to implement

1. **Anti-pattern grep sweep:**
   - `grep -rn "lazy(" frontend/src/features/settings/` → empty.
   - `grep -rn "anthropic_key\|api_key" routes/ services/` → no logging of values.
   - `grep -rn "from db" ai/providers.py` → empty (no AI↔DB coupling).
2. **Full verify chain** on all three stacks; record final test counts.
3. **Docs reconciliation:**
   - `README.md` + `CLAUDE.md`: provider selection is now a UI setting, not just an
     env var; document the keychain-stored key.
   - `docs/install-beta.md`: the new install-time availability verdict + wait window.
   - `CARREL_BUILD_RUNBOOK.md` is mis-named (it documents the autonomous agent loop) —
     either rename it or add a real `docs/SHIP.md` for the codesign/notarize runbook.
4. **Release dry-run:** `package_public_beta.sh --local-unsigned` end-to-end; then a
   real signed run once Open Decision #4 is resolved; install the DMG on a clean Mac
   (or VM) and walk the first-run → pick-provider → ask-a-question path.

### Verification checklist

- [ ] All three verify chains green; counts recorded in the PR description.
- [ ] Anti-pattern greps clean.
- [ ] Signed, notarized, stapled DMG opens on a second Mac without Gatekeeper warnings.
- [ ] Cold first-run on a clean machine: Settings reachable, all three providers
      selectable, AFM card shows the correct state for that machine.

---

## Open Decisions (need founder sign-off before Phase 2)

1. **API key at rest — Keychain vs encrypted file vs `.env`.**
   *Recommendation: macOS Keychain.* Carrel already has a working, tested keychain
   abstraction (`services/calendar/secrets.py`) with a memory fallback for CI/unsigned
   builds. Reusing it is the lowest-risk, most secure option. `.env` is rejected
   (plaintext, syncs to backups); an encrypted file just reinvents the Keychain badly.
   *Counter considered:* a plain file is simpler and works pre-signing — but the memory
   fallback already covers the unsigned/CI case, so the Keychain path loses nothing.

2. **Runtime switch — restart the backend or hot-swap?**
   *Recommendation: hot-swap, no restart.* Discovery proved it is safe:
   `ClaudeRouter._client()` re-reads the key every call (`router.py:223-224`) and the
   provider cache invalidates on env change (`providers.py:360-385`). The settings POST
   sets `os.environ` + calls `reset_default_provider()` + `reset_default_afm_client()`.
   A restart would be a worse UX for no correctness gain.

3. **Validate the Claude key on save?**
   *Recommendation: yes, one cheap call* (a 1-token request) so the user learns
   immediately if the key is wrong, with a clear opt-out if offline. *Counter:* it
   costs a token and adds latency — acceptable; a silently-wrong key is a worse first
   impression. Make it best-effort: a failed probe warns but still saves.

4. **Codesigning / notarization identity (operational, not code).**
   `package_public_beta.sh` needs `CARREL_CODESIGN_IDENTITY` (a Developer ID
   Application cert) and `CARREL_NOTARY_PROFILE` (a stored `notarytool` profile). This
   requires an active Apple Developer account ($99/yr). **This is the single hard
   blocker to shipping to other Macs** — an unsigned DMG is Gatekeeper-blocked. Decide
   the account/identity before Phase 3's signed dry-run.

5. **Bundle-ID rename (`com.madu.EinsteinDesktop` → Carrel).** Out of scope here;
   tracked in `docs/notes/2026-04-29-carrel-rename.md`. Flagged only so it is not
   discovered late during notarization.

---

## Execution sequence summary

| Phase | Workstream | Ships | Depends on |
|-------|-----------|-------|-----------|
| 0 | — | (this doc) | — |
| 1 | B-foundation | provider `kind` + availability probes | 0 |
| 2 | B-backend | keychain key store + settings route | 1, Decision #1–3 |
| 3 | A | build/ship hardening + install probe | 1 |
| 4 | B-frontend | Settings UI | 2 |
| 5 | — | verify + docs + release dry-run | 3, 4, Decision #4 |

Phases 3 and 4 are independent after 1+2 and may run in parallel. Each phase is one PR,
green on the full verify chain before merge.
