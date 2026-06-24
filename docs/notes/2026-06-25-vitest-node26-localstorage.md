# Vitest + Node 26: the `--no-experimental-webstorage` flag

2026-06-25

## Symptom

On a machine running Node 26, the entire frontend vitest suite fails 100% —
every test, every feature — with:

```
TypeError: Cannot read properties of undefined (reading 'removeItem')
 ❯ tests/setup.ts:124
```

plus the runtime warning:

```
ExperimentalWarning: localStorage is not available because --localstorage-file was not provided.
```

`window.localStorage` is `undefined` inside the jsdom environment, so the
`beforeEach` cleanup in `frontend/tests/setup.ts` (which clears
`carrel.*` keys) throws before any test body runs.

## Root cause

Node 24 stabilized and Node 26 enables-by-default an experimental native
`localStorage`/`sessionStorage` web storage global. That native global takes
precedence over the one jsdom installs on its `window`. But the native store is
inert unless you pass `--localstorage-file` (it needs a backing file), so the
shadowing global resolves to `undefined` — and jsdom's working implementation
never gets a look in. Result: `window.localStorage` is `undefined`.

This is purely an environment issue, not a code regression. `main` fails the
same way on Node 26. CI is unaffected because it pins `node-version: "22"`
(`.github/workflows/ci.yml`), where web storage is still off by default.

## Fix

`frontend/package.json` `test` / `test:watch` scripts pass
`--no-experimental-webstorage` via `NODE_OPTIONS`. That disables Node's native
web storage global, so jsdom's real, spec-compliant `Storage` is the one the
tests see — no hand-rolled mock, identical behavior to a browser.

Why this is safe on CI: the flag has existed since Node 22.4.0 (when web
storage landed behind `--experimental-webstorage`). On CI's Node 22 web storage
is off by default, so `--no-experimental-webstorage` is a harmless no-op there;
on local Node 26 it is the actual fix.

## Alternatives considered

- **Pin Node < 26 via `.nvmrc`/`engines`.** Rejected as the primary fix: it
  does not make `pnpm test` pass on a machine that already has Node 26 — the
  dev would have to install a version manager and switch. Documentation, not a
  fix.
- **Polyfill `localStorage` in `tests/setup.ts` when missing.** Env-agnostic
  and self-documenting, but it is a partial reimplementation of `Storage`; any
  bracket-access or string-coercion semantics would silently diverge from a
  real browser. The flag restores jsdom's genuine implementation instead.
