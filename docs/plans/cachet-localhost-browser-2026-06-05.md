# Cachet localhost-browser delivery (cross-platform, validation-phase)

Locked via /plan-eng-review 2026-06-05 on `claude/nostalgic-mclaren-93d91a`.

## Goal

Let Windows + Mac lawyers run Cachet without the macOS-only WKWebView shell: the
Python backend (CACHET_ONLY) serves the built Cachet frontend over loopback and a
cross-platform launcher opens the user's own browser at it. This is the
validation-phase delivery; a packaged installer (PyInstaller) and an Electron
product shell are later, separate steps.

## What already exists (reuse, do not rebuild)

- `client.ts::resolveLocalApiToken()` already reads `window.__CARREL_LOCAL_API_TOKEN`
  (the insecure `/api/local-token` fallback was deleted in PR-S1). Server-side
  injection of that global IS the blessed pattern.
- `local_api_security.py::requires_local_api_token` already exempts every non-`/api/`
  path, so the HTML + assets bootstrap without a token. No chicken-and-egg.
- `main.py:165` already forks `register_cachet_routes` on `CACHET_ONLY`. New serving
  code lives only there, so Carrel and the `.app` are untouched.
- `run-cachet.sh` already starts the CACHET_ONLY backend (but shell-only, Vite-dev).

## Architecture / data flow

```
 launcher (script/serve-cachet.py, cross-platform)
   1. token = secrets.token_urlsafe(32)         # ephemeral, per run, never written to disk
   2. port  = pick a FREE port                  # avoids stale-:8000 collisions
   3. start uvicorn  CACHET_ONLY=1              # real token gate ON (never CARREL_API_OPEN_MODE)
   4. poll GET /api/health (exempt) until ok
   5. webbrowser.open(f"http://127.0.0.1:{port}/")   # Win / Mac / Linux
           |
           v
 Browser --GET / ------------------>  FastAPI (CACHET_ONLY)
          <-- HTML with injected           serve_cachet_index():
              <script>                        read built cachet.html
                window.__CARREL_LOCAL_API_TOKEN = "<token>";
                window.__CARREL_API_BASE = "";   # same-origin, port-agnostic
              </script> + app bundle          inject into <head>, HTMLResponse (ungated: path != /api/)
          |
          +--GET /assets/* --------->  StaticFiles(dist-cachet/assets)   (ungated)
          |
          +--POST /api/verify (X-Carrel-Local-Token: <token>) --> token middleware OK --> engine
                same-origin => token rides the header, no CORS preflight
```

## Locked decisions

- **D1 Token + API base both injected** into the served HTML (`window.__CARREL_LOCAL_API_TOKEN`
  + `window.__CARREL_API_BASE=""`). Same-origin relative calls make it port-agnostic.
  The `.app` (`file://`, no injection) keeps its `http://127.0.0.1:8000` default; Carrel
  never injects, so both are unaffected.
- **D2 Serve the multi-file `dist-cachet/` build** via StaticFiles + one token-injecting
  HTML route. The inlined `cachet.new.html` stays for the `.app`. Reuses `build:cachet`.
- **D3 Ephemeral token** owned by the backend and injected into the HTML it serves. No
  token file to coordinate; each launch is a fresh token. Never use `CARREL_API_OPEN_MODE`
  for this path (that disables the gate).
- **D4 Auto-pick a free port**; the launcher opens the browser at it. Same-origin (D1)
  makes the port irrelevant to the frontend.
- **D5 DNS-rebinding Host guard (CHOSEN).** A global middleware rejects any request whose
  Host host-part is not `127.0.0.1` / `localhost` / `[::1]` (any port). Closes the one hole
  that embedding the token in served HTML opens (an attacker page rebinding its hostname to
  loopback to read `/` and steal the token). Loopback-only Carrel/`.app` traffic is
  unaffected; it is defense-in-depth for them too.
- **D6 Launcher in Python (CHOSEN), installer deferred.** One cross-platform launcher
  (`webbrowser.open`, no bash) since Python already runs the backend. PyInstaller
  single-binary packaging is a follow-up (shared with the Electron step); validation runs
  supervised with Python present.

## Implementation steps

1. **`routes/cachet_web.py`** (new): `GET /` reads the built `dist-cachet/cachet.html`,
   injects the D1 script into `<head>` before the bundle, returns HTMLResponse (ungated).
   503 with a clear "run pnpm build:cachet first" if the build is missing. Mount
   `StaticFiles(dist-cachet/assets)` at `/assets`. Resolve the build dir via an env/config
   (default `frontend/dist-cachet`).
2. **`routes/__init__.py`**: `register_cachet_routes` registers the web router + static mount.
3. **`main.py`**: add a global Host-allowlist middleware (D5), explicit and commented,
   alongside the existing token middleware.
4. **`frontend/src/services/api/client.ts`**: `API_BASE` reads `window.__CARREL_API_BASE`
   first, then `import.meta.env.VITE_API_BASE`, then a `file:`-aware default
   (`location.protocol === 'file:' ? 'http://127.0.0.1:8000' : ''`). Mirrors the token read.
5. **`script/serve-cachet.py`** (new): free-port pick, set `CARREL_LOCAL_API_TOKEN`, start
   uvicorn `CACHET_ONLY=1`, poll `/api/health`, `webbrowser.open`, wait; Ctrl+C stops it.
6. **`frontend/scripts/build-cachet.mjs`**: confirm `dist-cachet/` asset URLs resolve when
   served at `/` (base `/` or `./`). Tweak only if needed.

## Tests (100% of new paths)

```
routes/cachet_web.py
  GET / injects token + base, 200, ungated                          [unit]
  GET / with foreign Host header -> 403 (D5)                        [unit]
  GET /assets/cachet.js served, ungated                            [unit]
  POST /api/verify without token -> 403 (gate still on)            [unit]
  GET / when dist-cachet missing -> 503 clear message              [unit]
client.ts
  API_BASE reads window.__CARREL_API_BASE; falls back when unset   [unit]
script/serve-cachet.py
  free-port pick + health-wait (webbrowser.open mocked)            [smoke]
```

## Failure modes
- Port busy -> auto-pick (D4); zero free -> fail loud.
- `dist-cachet/` absent -> 503 with the build instruction, not a stack trace.
- Foreign Host (DNS rebind) -> 403 (D5).
- Token mismatch (shouldn't occur; backend injects its own) -> 403, visible.

## NOT in scope
- PyInstaller single-binary installer (follow-up; shared with Electron).
- Electron product shell (post-validation).
- Windows secret storage + image-OCR cross-platform swap (separate backend-portability work).
- HTTPS / multi-user (loopback single-user only).

## Keep unaffected
- Carrel (`register_routes`) and the WKWebView `.app` (`file://`, port 8000). The serving
  route is CACHET_ONLY; D1's injection is absent under `file://`; the Host guard only rejects
  non-loopback Hosts, which neither product uses.
