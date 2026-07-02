# Engineering decision: build the Cachet frontend from the Claude Design handoff

Status: Decided 2026-07-02. Written as a from-scratch build brief because the
first attempt failed (see §1). The next context should execute this, not the
token-remap that preceded it.

Source of truth (read all three, in full, before writing code):
- `~/Downloads/design_handoff_cachet/Cachet.dc.html` — the working prototype.
  Every surface, every state, exact inline styles. This is the visual truth.
- `~/Downloads/design_handoff_cachet/README.md` — tokens, the four-tier table,
  per-screen specs, motion, assets, invariants.
- `~/Downloads/design_handoff_cachet/reference/CACHET-WORKFLOW.md` — the FIXED
  engine/API/SSE/domain/invariant contract. Binding.

---

## 1. Why attempt 1 failed (the decision error to not repeat)

The handoff says, in its own words: *"This is a ground-up redesign of how the
product looks and feels, not a reskin of the current UI."* Attempt 1 ignored
that. It kept every existing view component's markup and layout and only:
- remapped the CSS custom properties to the handoff's OKLCH values (as hex),
- split one red token into oxblood-accent + danger,
- adjusted the four tier edge styles,
- flipped a few buttons to oxblood.

Result: the same app in slightly different colors. Specifically, everything
that actually makes the handoff look different was left untouched:
- **Fonts never changed.** Still Charter + Libre Caslon Display. The handoff's
  entire reading feel is **Newsreader** (serif) on reading surfaces + **Hanken
  Grotesk** (sans) on chrome + **JetBrains Mono**. This alone makes it read as
  "the same."
- **Layouts unchanged.** The Lectern composer, the findings presentation (the
  app ships a one-at-a-time *carousel*; the handoff is a vertical **worst-first
  findings rail** beside a two-column read-back grid), the shell, the
  examination panel, the exhibit, shelf, bench, vault — all kept their old
  structure.
- **No splash.** No folder marks. No light/dark toggle UI.

**Decision rule for the rebuild: this is a rewrite of the presentation layer,
surface by surface, to match `Cachet.dc.html`. Not a CSS-variable pass.** If a
change only edits `*.module.css` custom properties and no component markup,
it is almost certainly wrong.

Verification rule: **do not trust "tests pass" as done.** The 1065 vitest tests
lock *behavior and honesty invariants*, not appearance — they passed on attempt
1 precisely because the markup didn't change. Done = open `Cachet.dc.html` and
the running app side by side and they match, surface by surface.

---

## 2. What is FIXED (reuse verbatim — do not re-derive)

Per CACHET-WORKFLOW §7 and README "State management", keep these and build the
new views on top of them. They encode the honesty rules:
- The SSE state machine (fail-closed: a stream that ends without `result` is an
  error, never a pass). `frontend/src/features/verify/useVerify.ts` + `streaming.ts`.
- The disposition→tier mapping. `claimDisposition.ts` / the tier logic.
- Draft segmentation (`placement` + `flagged_spans` → markable runs).
  `documentSegments.ts`.
- In-browser certificate seal verification. `features/attest/certificate.ts`.
- The API client + token + SSE grammar. `services/api/`. All loopback,
  `X-Carrel-Local-Token`. Endpoints in WORKFLOW §5. DO NOT change the wire shapes.
- The three terminal states, the six dispositions, the four tiers. Fixed.

## 3. What is REBUILT (markup + CSS + type, per surface)

Every view component's JSX structure and its CSS module. The components keep
their data props/hooks and swap their presentation to the prototype's. Expect
to rewrite, not tweak: `cachet/LecternView.tsx`, `cachet/CachetApp.tsx`,
`cachet/CachetRail.tsx`, `cachet/VaultView.tsx`, `cachet/SettingsView.tsx`,
`features/verify/VerifyResults.tsx`, `features/verify/ExaminationDrawer.tsx`,
`features/attest/SealBenchView.tsx`, `features/attest/CertificationExhibit.tsx`,
plus a new splash component and new folder-mark + open-ring assets.

---

## 4. Build order (each step ships + is verified against the prototype)

**Step 0 — Fonts (do this first; it is the single biggest visible gap).**
Self-host **Newsreader**, **Hanken Grotesk**, **JetBrains Mono** as woff2 under
`frontend/src/assets/fonts/` (offline requirement — no Google Fonts CDN at
runtime). Add `@font-face` in `design-system/tokens.css`. Set the three roles:
`--font-serif`/`--font-serif-body` = Newsreader, `--font-sans` = Hanken
Grotesk, `--font-mono` = JetBrains Mono, scoped so it applies inside Cachet.
Update `frontend/src/cachet/fontsWired.test.ts` — it currently PINS "Libre
Caslon Display"; repoint it to the new faces + assert the woff2 files exist.

**Step 1 — Tokens (mostly done, keep it).** The OKLCH→hex ramp + oxblood/danger
split from the prior commit is correct and matches the README table. Verify the
values against README §Color. Keep light/dark under `html[data-theme]`.

**Step 2 — Shell** (README §2 / dc.html lines ~70–120). 88px left rail on
`--surface` with a right `--border-subtle`; open-ring mark 30px in `--accent`;
nav items = icon 19px + 10px label, 68px wide, active = `--accent-subtle` fill +
`--accent-text`; Settings pinned bottom; the `LOCAL` provenance dot+label always
visible. Top strip: uppercase mono eyebrow + faint helper + right-aligned mono
"local corpus 2025.11 · network: none".

**Step 3 — Lectern composer** (README §3 / dc.html ~122–140). 760px column, the
"Checking against" pill row, a **Newsreader 18.5px/1.75** textarea min-height
340px, primary **Verify draft** button in `--accent` with ⌘↩, "{n} words · reads
only, never rewrites".

**Step 4 — Live stream + settled** (README §4–5 / dc.html ~142–260). This is the
biggest structural change from the current app: replace the findings carousel
with the handoff's **two-column grid** `minmax(0,1.35fr) minmax(300px,1fr)`,
44px gap: left = draft read-back (Newsreader 19px/2.05, ≤68ch, tier underlines +
mono superscript claim numbers + altered-token precise mark), right = **findings
rail, worst-first vertical list**. Progress line = pulsing dot + mono phase.
Skeleton cards → ink-in per `cachetInk`. Summary row = serif headline + mono
counts. Fail-closed error block. Actions: Open exhibit / Save to shelf / New draft.

**Step 5 — Examination side sheet** (README §6 / dc.html). Right sheet
min(480px,92vw), scrim, `cachetInk`. Tier chip + "claim N of 6". The four check
rows each with a state glyph (`✓/✕/⊘/◇/·`), the check name, a **DETERMINISTIC**
or **ASSISTIVE** mono tag, a filing-grade detail. Cited source passage with the
quoted run highlighted in its clause.

**Step 6 — Certification Exhibit + sealing** (README §7). Centered 720px doc,
`--surface`, near-square 4px radius, Newsreader; 2px `--text-primary` top rule;
centered mark + "CERTIFICATION EXHIBIT"; metadata grid (sha256s, kernel); claims
table with right-aligned per-tier state token (refusals = equal weight); the
on-device statement box; footer **Set the seal** → fingerprint reveal.

**Step 7 — Shelf** (README §8). 860px list, hover-lift rows, serif title + mono
date·counts + seal badge (INTACT / CRACKED / UNSEALED). Reopen = read-only
re-hydrate with a "Reopened brief" banner.

**Step 8 — Seal Bench** (README §9). Two columns 980px. Left mono textarea +
Check the seal + load sample buttons. Right verdict: SEAL INTACT / SEAL BROKEN /
NOT A CERTIFICATE with the metadata grids. Reuse the real in-browser seal check.

**Step 9 — Vault** (README §10). Grid (action cards + search + vault cards with
the **folder mark** + active dot) and detail (records, VERIFYING-AGAINST badge,
Use-as-record, Move confirm + 7s Undo, delete confirm). Build the folder mark as
inline SVG per the README geometry (`#FFC93E` back, white sheets, `#FFAA2B`
pocket) — the only saturated colors in the product.

**Step 10 — Settings** (README §11). 640px. **Appearance Light/Dark segmented
control** that sets `data-theme` on `<html>` (dark tokens already exist). Engine
card in mono. Remove the current "no dark mode by design" copy.

**Step 11 — Splash** (README §1 / dc.html ~56–68). New component: dark plate,
open-ring mark draws in via `cachetDraw` (two arcs, staggered), wordmark rises
(`cachetRise`), fixed bottom mono line "Verification runs on this device.
Nothing leaves it.", fade out ~1900ms, skippable via a flag.

Motion keyframes to add (README §Motion): `cachetDraw`, `cachetInk`,
`cachetRise`, `cachetPulse`. All transform/opacity only; full reduced-motion
collapse. NOTE the verify surface currently has a test lock
(`verifyScope.test.ts`) asserting **no `@keyframes` / `animation:`** in
`VerifyView.module.css` — the handoff DOES use `cachetInk`/`cachetPulse` on the
result reveal and skeletons, so that test must be updated to allow the named,
reduced-motion-safe keyframes (do not silently delete the lock; narrow it).

---

## 5. Verification bar (how the fresh context proves it is done)

1. **Side-by-side.** Open `Cachet.dc.html` in a browser and the running app; walk
   every surface. They should match in layout, type, spacing, and the four tiers.
2. **The four-beat demo** (WORKFLOW §6): litigator opener (verified / cited-not-
   found / could-not-check), the pivot, contract close (date + amount +
   exclusive/non-exclusive contradictions + one verbatim confirm + one untreated),
   the exhibit. It must land harder than a dashboard.
3. **Honesty invariants hold** (README §Honesty invariants 1–9) — verified quiet,
   refusal the hero, three states, deterministic≠assistive, fail-closed, exact
   token marked, exhibit-as-instrument, provenance shown, the voice rules.
4. Only then the mechanical gates: typecheck, lint, the full vitest suite (updating
   the two test locks named above), `build:macos`.

## 6. Gotchas that cost time in attempt 1

- **Preview cache.** `serve-cachet.py` on :8000 serves stable-named `index.js`/
  `index.css`; the preview browser caches them and shows a stale/mixed build. Use
  the **vite dev server** (`cachet-fe`, :5181) — it HMRs fresh. To get live
  verdicts on it, pass `VITE_CARREL_LOCAL_API_TOKEN=cachet-demo-token` (matches
  serve-cachet's token) and keep the `cachet` backend running on :8000; the client
  reads `API_BASE=http://127.0.0.1:8000` + that token. CORS already allows any
  localhost port.
- **Test locks that pin the OLD design:** `fontsWired.test.ts` (Libre Caslon) and
  `verifyScope.test.ts` (no-keyframes + hex-only AA contrast). Update them
  deliberately as part of the relevant step; the AA contrast helper parses
  `#rrggbb`, so keep tokens as hex (OKLCH→hex is lossless) unless you also rewrite
  that helper to parse `oklch()`.
- **`build:macos`** emits stable filenames for the file:// WKWebView inlining; the
  WKWebView loads fresh each launch, so the cache issue is preview-only.
- **Fonts must be offline** (self-hosted woff2). No runtime CDN.

## 7. First move for the fresh context

Read the three handoff files in full. Then do Step 0 (fonts) — it is the change
that most makes the current build "look the same," and it unblocks the reading
feel every other surface depends on. Do not start with colors; those are already
correct. Start with type and layout.

Prior (superseded) work on main: `d75d409a8` (token/tier/theme port — keep the
tokens, rebuild the rest), and the earlier "Docket" pass (historical). The OKLCH
token values there are correct; everything above them is not the handoff yet.
