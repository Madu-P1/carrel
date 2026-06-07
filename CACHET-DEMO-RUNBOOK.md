# Cachet demo runbook

Everything to open Cachet, run the litigator cite-check demo flawlessly, and close
it. Deterministic, offline, no LLM, no network. Verified working 2026-06-07 on
`main` (`a30f19b3f`).

## One-time setup (already done; redo only after a frontend change)

```bash
cd /Users/madu/Desktop/Codex/frontend
corepack pnpm vite build --mode cachet
```

Builds the standalone Cachet shell (Verify + Shelf, paper UI, no study chrome) to
`frontend/dist`.

## Open

```bash
cd /Users/madu/Desktop/Codex
./.venv/bin/python script/serve-cachet.py
```

It prints `Cachet demo -> http://127.0.0.1:8000`. Open that URL in any browser
(Safari/Chrome). One process serves both the UI and the API on the same origin,
with the local-API token injected, so verification works in a plain browser.

## Close

`Ctrl-C` in that terminal. To re-open, just run the command again (no rebuild
needed unless you changed the frontend).

## The demo (litigator cite-check + honest refusal)

1. Open `http://127.0.0.1:8000` -> the Verify view.
2. Paste a draft that mixes a real citation with a fabricated one. Verified script:

   > Segregation was rejected in 347 U.S. 483. The court also held in 999 U.S. 999
   > that the same rule applies to private contracts.

3. Run it. Expected, offline:
   - `347 U.S. 483` (Brown v. Board) -> **verified** (real case, resolved from the
     bundled local-caselaw corpus).
   - `999 U.S. 999` -> **unsupported**, reason "Cited case not found: 999 U.S. 999"
     -> the catch.
4. The point to land: every verdict came from the device, with the network off.
   `provider: deterministic`, no model, no cloud call. You can pull the network
   cable / turn off Wi-Fi and it behaves identically.

The honest-refusal gem: a sentence with no verifiable anchor (a bare assertion, or
a quote we cannot locate) reads **could-not-check**, never a guessed pass or a false
accusation. That refusal is the trust story; show one.

## What is real vs. roadmap (say this honestly if asked)

- **Real today:** deterministic case-existence (real cite verified, fabricated cite
  caught) and the 3-state honest verdicts (verified / unsupported / could-not-check),
  all offline.
- **Roadmap (building Monday):** the source viewer (open a cited source at the
  verified span), and the in-house contract-claim wedge (verify a draft's claims
  against an uploaded executed contract).

## Troubleshooting

- **Page loads but verify says "could not check" for every cite:** the launcher
  sets `COURTLISTENER_API_TOKEN=local` (the offline sentinel) itself; if you started
  the backend a different way, that guard is off. Use `script/serve-cachet.py`.
- **`Address already in use` on :8000:** a stale backend is running. Free it:
  `lsof -ti tcp:8000 | xargs kill`, then re-open.
- **Blank page / old UI:** you served a stale or non-cachet build. Rebuild:
  `cd frontend && corepack pnpm vite build --mode cachet`, then re-open.
- **Never demo from `vite dev` directly:** a plain dev server has no token injected,
  so POST /api/verify returns 403. Always use `script/serve-cachet.py`.

## Files

- `script/serve-cachet.py` - the single-process loopback launcher (restored from the
  deleted worktree; sets the fixed token + deterministic + offline-sentinel env,
  serves `frontend/dist` same-origin with the token injected).
- These two files are currently **untracked** in the working tree. Commit them so a
  future `git clean` or checkout cannot lose them again.
