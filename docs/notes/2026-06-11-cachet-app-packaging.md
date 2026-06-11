# Cachet as a packaged, double-clickable macOS .app (2026-06-11)

`./script/build_and_run.sh --cachet` now assembles and launches
`dist/Cachet.app` beside (never clobbering) `dist/EinsteinDesktop.app`.
Signing/notarization remains deferred (Phase 4).

## Design: parameterize, never fork

One SwiftPM product (`EinsteinDesktop`) serves both products. Cachet-ness
lives in exactly three places, all applied at bundle-assembly time:

1. **Frontend bundle**: `pnpm build:cachet-macos` = the same pipeline with
   `vite build --mode cachet`, which bakes `VITE_CACHET_ONLY=true`
   (`frontend/.env.cachet`) so `main.tsx` renders `CachetApp`. The
   `app.new.html` name inside the bundle is the WKWebView shell's internal
   contract, not product identity; the staging copy under
   `macos-app/Resources/` is regenerated on every build, so the two
   products overwriting it in turn is benign. `build-macos.mjs` takes
   `CARREL_BUNDLE_TITLE` (default `Einstein`) for the pre-boot `<title>`.
2. **Info.plist `CarrelProductMode=cachet`**, read at runtime by
   `ProductMode.swift`: window title, suppression of study chrome
   (floating companion, EventKit calendar bridge), and the
   `BackendSupervisor` env overlay mirroring `script/serve-cachet.py`
   (`CACHET_DETERMINISTIC_VERIFY=1` hard-pinned; `EMBED_ON_INGEST`,
   `COURTLISTENER_API_TOKEN`, `CARREL_FASTEMBED_CACHE_DIR` setdefault).
   `ensure_backend` in the launcher exports the same set in `--cachet`
   mode so dev-spawned and app-spawned backends behave identically.
3. **Bundle identity**: display name/`CFBundleName` Cachet, bundle id
   `com.madu.Cachet`, executable `Contents/MacOS/Cachet`, icon copied
   from the committed brand asset
   `cachet-landing/assets/brand/macos/AppIcon.icns` (withheld-strike ring
   on the ink squircle). Absent plist key means Carrel; existing bundles
   are unchanged.

## Launcher hardening found during verification

The first `--cachet --verify` run passed VACUOUSLY: a stale
`serve-cachet.py` from the morning held port 8000, the fresh uvicorn died
on bind, and `wait_for_backend` green-lit against the wrong backend.
`pkill -f "uvicorn main:app"` cannot match in-process `uvicorn.run`
servers. `ensure_backend` now also kills the actual TCP listener on 8000
(`lsof -tiTCP:8000 -sTCP:LISTEN`). Lesson: a health probe alone does not
identify WHICH backend answered; check provenance (`base_dir` in
`/api/health`) when it matters.

## Verified (all green 2026-06-11)

- FE: lint + full vitest suite (exit 0), `build:cachet-macos` integrity
  guards, Carrel `build:macos` unchanged (`<title>Einstein</title>`).
- Swift: build + 78/78 tests.
- `--cachet --verify` exit 0 with the backend provably the launcher's own
  spawn (health `base_dir` = the build tree) and the three Cachet env pins
  visible on the process.
- Bundled artifact served statically and screenshotted at 1440 + 1920:
  paper/ink register, Libre Caslon Display `loaded` per `document.fonts`,
  `--color-success` resolves to ink `#1c1814` (no green leak), zero
  console errors.
- Native window screenshot of the running `Cachet.app` (computer-use):
  correct title, rail mark, live vault data over the authed local API.

## Knowingly out of scope

- Signing/notarization/Sparkle (Phase 4; needs Apple Developer creds).
- A truly standalone distributable (the .app still resolves the repo
  checkout for Python/backend; bundling a runtime is the Electron-or-
  PyInstaller decision tracked with extraction P3).
- Vault/DB separation between products: both products' backends use the
  same port-8000 slot and the repo DB. One product at a time.
- The Vault header folder renders in oxblood outside the verify surface;
  pre-existing UI from the merged Cachet shell, flagged for the next
  design pass, not a packaging concern.
