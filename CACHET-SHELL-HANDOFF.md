# Cachet Shell — Session Handoff (2026-06-02)

You are continuing the **Cachet** build in a fresh session. This file is self-contained.
Open a new session, read this top to bottom, then continue from "Next steps."

For brand truth also read: the brand docs in `cachet-landing/assets/brand/`
(`README.md`, `CLEARANCE.md`, `MOTION.md`), `DESIGN.md` (the verify-scope section is
locked), and the memory files listed under "Pointers."

---

## What Cachet is

An independent AI-verification layer for high-stakes AI output (litigation pre-flight
wedge). Core truths, all load-bearing:

- **The refusal is the gem.** The "Cannot verify, not in the record" state is what earns
  a litigator's trust. Defend it above every other state.
- **Never generate.** Be the red pen, never the pen. The moment Cachet writes argument or
  drafts a corrected cite it inherits the liability it sells freedom from. No
  fix-suggestion feature, even though it will be the most requested.
- **Four checks, unequal trust weights, shown separately:** case-exists (deterministic),
  quote-verbatim (deterministic workhorse), good-law (under-claim, "candidate to KeyCite"),
  holding-match (assistive/contestable, never the same confident treatment as the
  deterministic checks).
- **The artifact is a certification that looks like a filed court exhibit, not a dashboard
  screenshot.** That is the aesthetic north star.

---

## Where the project is (state as of 2026-06-02)

- The **V2 verify-port stack is merged to `main`**: PR3 (#95, streaming verify engine) +
  the consolidated PR4 through PR6d (#107: quote-verbatim check, claim alignment, the
  Margin layout, Shelf persistence, reopen/re-hydrate, warm Shelf craft, Save/Seal
  trigger). Backend and the verify/shelf UI components live on `main`.
- The **verify and shelf components are cleanly decoupled from Carrel**: across both
  feature dirs there is one cross-feature import (`@/features/shared`) and zero imports of
  the Carrel shell, sidebar, or any Carrel feature. They re-host into a new shell trivially.
- **Caution:** the main checkout (`/Users/madu/Desktop/Codex`) is currently on branch
  `landing-visual-deslop` (separate landing-site work), not `main`. Check out `main` (or
  branch from it) for the shell work. The verify-port worktree that did this work is
  `.claude/worktrees/infallible-proskuriakova-4fccbf` (branch `cachet/pr6d-save`).
- A running instance may still be up from this session: `script/build_and_run.sh` launched
  `EinsteinDesktop.app` plus the FastAPI backend on `127.0.0.1:8000`, reading the worktree
  `.env` (which holds `ANTHROPIC_API_KEY`). A mock preview server is on `:8745`. You will
  likely start fresh; restart what you need.

---

## The phase: build a STANDALONE Cachet frontend

**Operator-confirmed decision:** Cachet is its own frontend app (own shell, nav, entry,
eventually its own `.app`), reusing the existing FastAPI backend unchanged. It is **not**
Carrel with a Verify tab. What launches today (EinsteinDesktop with a Verify section in the
Carrel sidebar) is the substrate, not the product.

### Architecture (Option A, confirmed)

A separate Cachet entry and build inside the same `frontend/` repo:

- New: `frontend/cachet.html` + `frontend/src/cachet/main.tsx` mounting a `CachetApp` shell.
- Reuse directly (import, do not copy): `frontend/src/design-system/*`,
  `frontend/src/services/api/*`, `frontend/src/features/verify/*`,
  `frontend/src/features/shelf/*`, `frontend/src/features/shared`.
- New build: a `build-cachet.mjs` plus a Vite multi-entry config producing a separate
  Cachet bundle (mirror `frontend/scripts/build-macos.mjs`, which emits `app.new.html`).
- Later: a Cachet `.app` is the existing Swift shell (`macos-app/`) copied and pointed at
  the Cachet bundle (the shell is generic: it loads an HTML bundle and supervises the
  backend via `BackendSupervisor`). Iterate now via Vite dev against the backend on
  `localhost`, no Swift rebuild.
- `CachetApp` must re-provide the few app-level providers the components expect (the
  `preact-iso` router, the toast provider, theme), since it will not use Carrel's
  `AppShell`.

**Reuse map:** backend 100% reused; design-system, api client, verify and shelf components
reused as-is. Only the shell (nav rail, lectern landing, Sources, Settings) is net-new.
Carrel surfaces (ask, library, study, plan, reader) are excluded.

### Design direction, signed off: "The Instrument"

Cachet is a legal instrument, not a dashboard. A quiet frame around a single document under
examination. What comes out looks filed, not exported. Navigation recedes; the document and
its verdict carry the weight. Sobriety on verdicts, warmth only on the Shelf.

- **Nav (operator chose): a thin left rail.** Four quiet ink glyphs (Verify, Shelf,
  Sources, Settings), the document fills the rest. Active glyph is ink with a 2px left tick.
- **Landing (operator chose): the lectern.** A composed title page: the mark, one line of
  what Cachet verifies and refuses, and a paste affordance that reads as **a sheet of
  paper, not an input box** (a lighter fresh-sheet tone lifted off the warm desk with one
  soft shadow; the writing area on top; Verify sitting on a hairline foot-rule inside the
  sheet). Collapses to a recent-briefs index once the Shelf has entries.
- **Examination: document-as-hero.** The draft on paper, flagged claims underlined in
  oxblood with a margin note, a plain-word disposition, the seal in ink shown
  withheld or pressed. Holding-match shown separately, never certified the same way.
- **Refusal-as-hero: the signature screen.** The most composed view in the product. An
  oxblood kicker, the isolated claim, a large "Cannot verify" in the display face, a plain
  explanation, and the seal visibly withheld (a dashed ink ring plus "Seal withheld").

### Locked brand tokens

Paper `#f6f2ea`; fresh-sheet about `#fbf8f1`; ink ramp `#1c1814` / `#4e463c` / `#635b4d`;
oxblood `--verify-flag` `#7a2230` used for FLAGS ONLY; hairlines `rgba(28,24,20,.14)` and
`.08`; near-zero motion. "Warmth never touches a verdict": the warm register (Fraunces) is
Shelf-only. NO green, amber, gold, or brass. NO confidence numbers. The seal renders in
ink, not brass. Tokens live in `frontend/src/design-system/tokens.css` plus the verify and
shelf module CSS (`VerifyView.module.css`, `ShelfView.module.css`).

---

## TWO CORRECTIONS FROM THE OPERATOR (do these first, before scaffolding)

1. **Logo: use the REAL asset, do not hand-draw it.** The true withheld-strike mark is
   `cachet-landing/assets/brand/cachet-mark.svg` (viewBox `0 0 240 240`, two `currentColor`
   arcs forming the truncated C as an open ring severed in the upper-left, "the unfinished
   impression is the refusal"). Also available: `cachet-lockup.svg` (mark plus wordmark),
   `cachet-icon.svg`, `macos/` app icons, `web/` favicons. Pull the real path data into the
   shell. The throwaway mock drew a single rotated ring, which the operator correctly called
   inaccurate.

2. **Font: replace the display face.** The operator finds Instrument Serif "too plain and
   very AI-esque." It has become an AI-generation tell, so this is a real problem. **Reopen
   the display-font decision** (this overrides the previously-locked Instrument Serif).
   Find a characterful display serif for the COLD verify register with legal or editorial
   gravitas that does not read as AI-generated. Constraints: self-host as woff2 (no network;
   see the `@font-face` pattern at the top of `tokens.css`), OFL or properly licensed.
   Fraunces is already in the system but is reserved for the WARM Shelf register, so do not
   reuse it for the cold register. The body reading serif is Charter (a genuine system
   serif, much less of a tell); keep it unless the operator wants it revisited. **Bring 1 to
   3 candidates to the operator and let them choose. Do not self-approve the font.**

---

## The mock (reference only, throwaway)

- `/tmp/cachet-shell-mock/index.html`. Static mock of the three states. Preview config
  `cachet-shell-mock` (port 8745) is in `.claude/launch.json`. Screenshot via the
  Claude_Preview MCP (`preview_start` then `preview_eval` to call `show('lectern' |
  'examination' | 'refusal')`, then `preview_screenshot`; set the viewport with
  `preview_resize` first or it reports 0x0).
- **Keep:** the composition, the thin rail, the lectern-as-sheet, the oxblood discipline,
  the withheld seal, the refusal-hero staging.
- **Fix:** the logo (hand-drawn, inaccurate, use the real asset) and the font (replace
  Instrument Serif).
- It is static HTML. The real build is Preact reusing the actual components, not this file.

---

## Next steps for the new session

1. Check out `main`. Confirm `cachet-landing/assets/brand/cachet-mark.svg` is present.
2. Redo the mock (or go straight to a Preact scaffold) with the **real logo** and a **new
   display font** (1 to 3 candidates). Screenshot via Claude_Preview and re-gate with the
   operator. Craft is operator-gated: never self-approve the look.
3. On sign-off, scaffold the real Cachet build (Option A): `cachet.html` +
   `src/cachet/CachetApp` + the rail + the lectern, reusing the verify and shelf components.
   Add `build-cachet.mjs` and the Vite multi-entry config. Run via Vite dev plus the backend.
4. Then the Sources view (ingest verification material) and Settings (houses the API-key
   entry; macOS Keychain is the secure target; the native part is Xcode/GUI-gated, was
   tracked as PR7).

---

## Constraints and rules (in force)

- Merge-to-main and deploy are OPERATOR-GATED. Default PRs to draft; do not `gh pr ready`
  without the operator. Craft (the look) is operator-gated: bring options to a visual gate,
  never self-approve.
- Never commit or log secrets (`ANTHROPIC_API_KEY`, the local-API token, calendar feed
  URLs, Apple Developer creds). `.env` is gitignored.
- No "Generated with Claude Code" or co-author footers in commits or PRs.
- No em dashes, no AI-slop vocabulary in UI copy or prose.
- Reuse existing primitives. The verify and shelf components and the design-system are the
  substrate; do not rebuild them.
- The real gate ahead is the T66 validation pilot (ADR-0008). The product is functionally
  complete; getting it in front of litigators is the priority once the shell exists.

---

## Pointers

- Memory: `~/.claude/projects/-Users-madu-Desktop-Codex/memory/` and the files
  `cachet-form-discovery.md`, `cachet-logo.md`, `cachet-ui-build.md`, `v2-pivot.md`,
  `answer-quality-root-cause.md`.
- `DESIGN.md` (verify-scope locked section), `CLAUDE.md` (project), `HANDOFF.md`.
- Brand: `cachet-landing/assets/brand/` (mark, lockup, icon, macos icons, web favicons,
  README, CLEARANCE, MOTION).
- Components: `frontend/src/features/verify/*`, `frontend/src/features/shelf/*`,
  `frontend/src/design-system/*`, `frontend/src/services/api/*`.
- Backend: `main.py`, `routes/verify.py`, `routes/briefs.py`, `services/verify.py`,
  `services/legal/*`.
- Run the existing app for reference: `./script/build_and_run.sh` (builds frontend, builds
  the Swift shell, starts the backend with the `.env` key, opens the app).
