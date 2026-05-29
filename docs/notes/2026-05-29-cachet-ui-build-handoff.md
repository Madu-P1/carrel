# Cachet UI/UX build — handoff (2026-05-29)

New session or fresh clone picking up the Cachet UI work: read this. It pairs with the
machine-local auto-memory entry `cachet-ui-build`; this doc is the git-tracked, cross-machine
copy so the plan survives a clone on any machine.

## Objective
Build a new UI/UX frontend for **CACHET** on top of the existing Carrel backend. Stack is
unchanged: Preact + TypeScript + Vite + CSS Modules inside the WKWebView shell; the FastAPI
backend is reused as-is (the `/api/verify` engine: grounding + CourtListener case-existence +
holding-match). The product/engine is named **CACHET**; "Carrel" is only the codebase / old
product name. Use Cachet in all product-facing language.

## Hard constraint: an agent cannot open the macOS GUI
Launching the packaged WKWebView app from a shell or agent runs it in a non-GUI context — the
process starts (uvicorn + the app binary) but no window ever draws on the user's screen
(symptom observed 2026-05-29: "nothing opened"). So for the UI build, do NOT rely on launching
the packaged app. Use the dev-server path already documented in HANDOFF.md, Booting Carrel:

```bash
# Terminal 1
.venv/bin/python -m uvicorn main:app --reload
# Terminal 2
cd frontend && bun run dev      # then open http://localhost:5173
```

The human opens `localhost:5173` in their own browser to see it live; the agent verifies and
screenshots headlessly (browse / design-review). WKWebView packaging is the LAST step, never the
dev loop.

## What already exists (do not rebuild from zero)
The verify-as-hero surface shipped to `main` in PR #90 (`a19af3bb`):
`frontend/src/features/verify/` (`VerifyView`, `SourceInspector`, `CertificationExhibit`,
`claimDisposition.ts`, `certification.ts`); route `/verify`; nav item "Verify Draft" in
`frontend/src/app/shell/AppShell.tsx`. The new UI extends / reimagines this surface.

## Gaps the new UI must close
- **In-app API-key entry.** `ANTHROPIC_API_KEY` and `COURTLISTENER_API_TOKEN` are read only from
  the process env / repo `.env` (`ai/router.py` does `load_dotenv(repo/.env)`; `os.getenv` in
  `ai/providers.py` and `services/legal/courtlistener.py`). There is NO settings/onboarding
  screen to enter a key — the core reason a non-developer cannot use the app. Add a
  Keychain-backed key/settings screen.
- **Not solo-distributable.** The packaged `.app` (~7.8 MB) bundles no Python backend; it spawns
  repo `uvicorn`, so it only runs on a machine with the repo + `.venv` + `.env`. Standalone
  distribution (bundle the backend, in-app keys, sign + notarize) is Phase 4, unbuilt. Until
  then the validation pilot is **supervised** (founder runs it on their machine; the litigator
  uses it with the founder present). Playbook:
  `docs/validation/30-day-test-2026-05-26/supervised-session-protocol.md` (draft PR #91).

## Build pipeline (skills mapped 2026-05-29)
1. Screen-map spec — verify input, verdict + the refusal state, source inspector, certification
   export, and the **key/settings screen**. (`product-management:write-spec`.)
2. `atelier` — design taste + system (anti-AI-slop); the lawyer-grade trust look.
3. `plan-eng-review` — the risky wiring: `/api/verify` contract, the local-API-token handshake,
   WKWebView integration — plus `plan-design-review`.
4. Build with `karpathy-guidelines` + `freeze` (scope edits to the frontend dir).
5. `design-review` + `qa` + `design:accessibility-review`, run against the Vite dev server.
6. `code-review` then ship via the project's own verify chain.

Skip: the `vercel:*` cluster, `design-html` (Pretext), and `land-and-deploy` / `canary` /
`setup-deploy`. Wrong stack/target — this is Preact/Vite/WKWebView packaged as a macOS app, not
Next/Vercel/web.

## State at handoff
- `main`: verify-as-hero merged (PR #90, `a19af3bb`).
- Draft PR #91 (`claude/t65-validation-prep`): seed memos + answer keys + catch-test results +
  supervised-session protocol (T65 validation prep — keep it draft).
- Engine validated on the hard case (holding-match caught a backwards-cited Lochner with correct
  reasoning); full catch-rate unconfirmed at scale (CourtListener free tier is 5 req/min).
- First move when resuming: the screen-map spec, then `atelier`.
