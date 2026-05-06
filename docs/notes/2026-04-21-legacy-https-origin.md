# Legacy frontend loads under a synthetic https origin

> **RESOLVED 2026-05-06:** The legacy `app.html.legacy` bundle and its `--frontend legacy` escape hatch were deleted in commit `d1ba6a80`. This note is preserved as historical context — it explains why the synthetic `http://einstein.local/` origin existed during the dual-bundle period.

**Date:** 2026-04-21
**Scope:** `macos-app/Sources/EinsteinDesktopApp/WebAppView.swift::loadBundledApp`

## Problem

After PR-E8 and the native "Einstein > Frontend" menu landed, switching to
the legacy bundle produced a blank WebView. Root cause:

- The legacy bundle (`app.html.legacy`, 310 KB single-file UI, predates Phase 2)
  references several `https://` origins directly:
  - `cdnjs.cloudflare.com/ajax/libs/KaTeX/0.16.9/*` — math rendering stylesheet + scripts
  - `api.anthropic.com/v1/messages` — direct Claude calls from the legacy tutor
  - `api.openai.com/v1/chat/completions` — direct OpenAI calls
  - `i.imgur.com/...` — Einstein portrait + other images
  - Misc "open in X" links (calendar, drive, notebooklm, etc.)
- Under WKWebView's default file:// origin, `https://` resource fetches are
  blocked as cross-origin. KaTeX fails to load, the legacy app's init JS
  throws on the missing `katex` global, and `<div id="root">` never fills.
  Result: blank window.

## Options considered

1. **`configuration.preferences.setValue(true, forKey: "allowUniversalAccessFromFileURLs")`**
   — the "standard" KVC knob. Produced a Swift runtime crash
   (`Fatal error: failed to allocate 217298682020626496 bytes of memory`)
   on this macOS SDK when combined with our existing load path. Apple's
   private preferences surface has sharp edges; not production-safe here.

2. **Self-host KaTeX in the legacy bundle** — fixes math rendering but does
   nothing for the Anthropic + OpenAI direct calls, which were the whole
   point of the legacy path. Network still blocked.

3. **Move legacy off HTTPS direct calls entirely** — requires rewriting the
   310 KB single-file app to proxy via our local FastAPI. Out of scope for
   a bundle we already plan to retire.

4. **Load legacy with `loadHTMLString(_:baseURL:)` under a synthetic http
   origin (`http://einstein.local/`)** — chosen. The page thinks it lives at
   a real network origin, so every `https://` fetch to cdnjs / Anthropic /
   OpenAI is a normal cross-origin request and succeeds. No private
   preferences touched, no macOS version fragility.

   **HTTP, not HTTPS.** First pass used `https://einstein.local/`. That broke
   the local study engine: the legacy bundle fetches `http://127.0.0.1:8000`
   for its FastAPI backend, and WebKit blocked the HTTP request as mixed
   content under an HTTPS origin. Switching to `http://` keeps HTTPS outbound
   working (scheme upgrades are fine) and unblocks the loopback call.

## Why option 4 is safe

- The baseURL is synthetic. No real host lives at `einstein.local`.
- The new bundle still loads via `loadFileURL` because it uses relative
  paths to `./assets.new/...` that MUST resolve against a real file:// URL.
- The new bundle's `tests/bundle-integrity.test.ts` forbids third-party
  host references, so the local-first promise holds for the modern code
  path. Only legacy gets the network-origin treatment.
- `localStorage` keyed to `einstein.local` is a fresh namespace. Any prior
  legacy state under the file:// origin is effectively orphaned — minor
  cost, legacy users are opting into an escape hatch anyway.

## Behaviour summary

| Frontend | Load path            | Origin                     | CDN / API reach |
|----------|----------------------|----------------------------|-----------------|
| `new`    | `loadFileURL`        | `file:///.../app.new.html` | self-hosted only (enforced) |
| `legacy` | `loadHTMLString`     | `http://einstein.local/`   | full https egress + http loopback to local backend |

## Out of scope

- Retiring the legacy bundle entirely. Tracked as an open debt in
  `CLAUDE.md` until the new frontend reaches parity across the full demo
  flow.
- Moving the legacy bundle's Claude / OpenAI calls through the local
  FastAPI backend. Would be the right shape for a sustained product, but
  not worth the churn on a retired path.
