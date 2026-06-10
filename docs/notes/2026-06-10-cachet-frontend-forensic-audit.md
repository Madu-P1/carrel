# Cachet frontend forensic audit + companion patch

- **Audited commit:** `dde839bba` (main, 2026-06-09). Every file:line below cites that commit unless marked FIXED.
- **Patch:** 11 commits on `claude/cool-mendel-9d9124`, `9ae068665..d8aa123f9`, each test-first and independently shippable.
- **Severity bar (from the brief):** (1) a pixel implying more certainty than the engine has; (2) a false accusation; (3) craft/slop.
- **Result of the gate after the patch:** generate-api-types no-drift, typecheck, lint, vitest 702/702 (48 new tests), build:macos, entry JS 128,986/129,024 gz, entry CSS 45,037/45,056 gz. Screens verified live at 1440 and 1920.

## 1. Frontend map: from the wire to the pixel

**Entry.** `src/main.tsx` statically imports both the Carrel `App` and `CachetApp` and switches at runtime on `VITE_CACHET_ONLY` (main.tsx:85-98). `src/cachet/main.tsx` is a second standalone entry (paper forced, `CachetApp` only). The macOS bundle is one HTML (`build-macos.mjs`); render-time code-splitting is forbidden under `file://` (bundle-size.test.ts:37-46).

**Shell.** `CachetApp` (CachetApp.tsx:83-115) renders route content from the `appShell.currentRoute` signal; no router is registered, so `navigateTo` falls back to `setCurrentRoute` (useAppShell.ts:279-287). **Every navigation unmounts the current view.** Durable state therefore lives in module signals: the draft in `liveDraft` (liveDraft.ts:16), the active record + library in `source.ts` signals with localStorage persistence (source.ts:47-70). The verify ENGINE state (`useVerify`, useState-based) does NOT survive navigation; persistence is via Save-to-Shelf + brief re-hydration.

**The verify data path.** `useVerify.verify()` (useVerify.ts:90-136) consumes `verify.draftStream` SSE (endpoints.ts:47-53; backend `services/verify.py::verify_draft_stream`). Events fold through the pure reducer `reduceStreamEvent` (streamProgress.ts:51-98). The backend contract (services/verify.py:816-822): skeleton cards carry the grounding verdict with EMPTY `case_verdicts`; the client must hold each claim's cite axis as could-not-check until its `cite_verdict` or the result. `useVerify` also carries the truncated-stream guard (useVerify.ts:122-126), the brief-hydration path (53-88), and the seal-seed lifecycle (99-103).

**The verify render path.** `VerifyResults` (VerifyResults.tsx) renders, in order: error banner → hydration/working indicators → the LIVE skeleton card list (streaming only; `VerdictCard` + `CaseVerdictLine` render here and only here) → provenance badge → `VerifyVerdictSummary` → refusal CTA → `QuotePanel` → the settled Workspace (`WorkspaceMargin`: document body with inline `ClaimMark`s, the collision-laid margin rail via pure `layoutRail`, the unplaced tray) → `ExaminationDrawer` (four checks via `checksFor` + `SourceInspectorBody`) → `CertificationExhibit` (focus-trapped, print-isolated, seal WAAPI with reduced-motion fallback). All claim-level semantics flow through one pure function, `dispositionForClaim` (claimDisposition.ts:147-296), used identically by the summary, marks, notes, tray, and certification.

**Hosts.** Carrel's `VerifyView` (composer + results) and Cachet's `LecternView` (the landing IS the verify surface; `onResolve` routes to `/vault`) plus `BriefReader` (`/verify?brief=` read-only re-hydration). Shelf/Vault/Settings/CommandPalette complete the shell.

## 2. Claims-vs-reality ledger

| The UI's promise | Verdict on `dde839bba` |
|---|---|
| A not-yet-checked claim never reads as a pass (invariant #6) | **BROKEN on the error edge.** Held during `checking`; on a mid-stream `error` event every unchecked skeleton released to its grounding verdict and rendered "Supported" while the stream stayed open (D1). FIXED. |
| A bounded-corpus miss is could-not-check, never an accusation | **BROKEN at two sub-claim surfaces.** Claim level was honest; the per-case sub-line said "Case not found" in oxblood, and the drawer's case-exists row said "flag" (D2). FIXED. |
| A holding mismatch is assistive, never the deterministic flag | **BROKEN in the drawer.** `checksFor` mapped `holding_match === false` to the oxblood `flag` state that claimDisposition.ts:78-90 explicitly forbids (D3). FIXED. |
| The four checks judge the claim's cited cases | **BROKEN for multi-cite claims.** `checksFor` read `cases[0]` only (ExaminationDrawer.tsx:39-41); one real case hid a second missing one (D3). FIXED. |
| The screen reader hears the same register the eye sees | **OVERCLAIMED.** Every non-pass mark announced "Statement flagged …", turning the honest refusal and assistive notes into accusations in the audio rendering (D4). FIXED. |
| ⌘K verbs do what they say | **BROKEN.** `cachet:command` had zero listeners; "Seal and save ⌘S" closed the palette and did nothing, and no ⌘S binding existed (D5). FIXED. |
| The cold register is Libre Caslon Display | **BROKEN, silently.** Files on disk + rebind in cachet.module.css:61, but no `@font-face` anywhere; it always fell back to Charter/Georgia and the woff2s were never bundled (D6). FIXED; verified rendering live. |
| No green on the verify surface | **BROKEN on Carrel's /verify.** `.verifyScope` never rebound `--color-success`; ProvenanceBadge's claude tone leaked green (D7). FIXED. |
| The lectern's "loaded as the record" names a real record | **BROKEN via fixture.** `?fixture=sources` ran in production and PERSISTED a fake executed MSA as the active record for later real sessions (D8). FIXED. |
| The exhibit's fingerprint is the checked draft's | **CONFIRMED with a latent hole:** `draft_text` missing → SHA-256("") while Save-to-Shelf hashed the composer draft; same brief, two fingerprints, phantom-cracked seal (D9). FIXED. |
| "Stored in the macOS Keychain by the app" (Settings) | **OVERCLAIMED.** Keychain wiring is planned, not built (the code comment concedes it). Copy now states what is true today (D12). FIXED. |
| Verify chain: generated types carry the API | **BROKEN.** `/api/vaults` was never regenerated into types.gen.ts; the no-drift gate fails on the base commit (D13). FIXED. |
| Zero egress / "nothing leaves this machine without your say" | **CONFIRMED** within the documented asterisks (runtime-provable, deterministic default; the LLM is an explicit env opt-out). Frame per `docs/notes` egress guidance; do not upgrade to "compiled out". |
| Quote panel, segmentation, rail layout, seal states, contrast, focus-visible, print isolation | **CONFIRMED.** Strong pure-logic test coverage; print CSS isolates the exhibit; AA contrast is test-locked; 100% `:focus-visible`. |

## 3. Defect register (worst-first, each reproduced before fixed)

**Tier 1 — manufactured certainty**

- **D1. Mid-stream error releases unchecked claims as "Supported".** `isCardChecking` returned false the moment `phase !== "checking"` (streamProgress.ts:109-114) while `VerifyResults` kept the live list mounted (`loading && !response`, VerifyResults.tsx:571): an `error` event flipped every unchecked card from "Checking…" to its skeleton disposition (verdict `verified`, no case verdicts → plain "Supported") for the whole remaining open-stream window. Repro: reducer fold [claims, cite_verdict(0), error] + render. Fix `9ae068665`: the live list unmounts on `phase === "error"` (the banner is the only verdict) and `isCardChecking` holds unchecked/indexless cards as defense in depth. Verified live against a dead backend at 1920: banner only.
- **D8. Production fixture persists a fake record.** VaultView.tsx:90-115 + the localStorage subscriber (source.ts:63-70). One `?fixture=sources` visit left "Apex–Northwind MSA (executed).pdf" as the persisted active record; the lectern then asserted it was loaded. Fix `5cf263944`: DEV-gated (compiled out of production) + the fixture clears its own persistence; helpers unit-locked.

**Tier 2 — false accusation**

- **D2. Bounded-corpus miss accused at the sub-claim surfaces.** `CaseVerdictLine` ignored `bounded_corpus` → oxblood "Case not found" (VerifyResults.tsx:85-98 + `.caseMissing` VerifyView.module.css:411); `checksFor` likewise flagged it with "No case matching this citation was found". A caption mismatch inversely rendered as a quiet "Case found · {the WRONG case}". Fix `470e88316`: "Outside the offline corpus checked" in the muted register; "Resolves to a different case" in the flag register; drawer three-states the corpus.
- **D3. Drawer register and aggregation.** `checksFor` judged `cases[0]` only and wore oxblood for the assistive holding contradiction. Fix `470e88316`: aggregates all cases; holding judgments stay queries. `checksFor` exported + 9 unit tests.
- **D4. Read-back accuses.** ClaimMark aria said "Statement flagged" for refusal and assistive tiers (WorkspaceMargin.tsx:206-209). Fix `baecd6cbd`: register-true announcements, test-locked.

**Tier 3 — correctness / trust-adjacent**

- **D5. Dead palette verbs** (commands.ts:46-50, no `cachet:command` listener repo-wide; false ⌘S hint). Fix `a754a0263`: verify-draft runs the guarded inline verify; seal/export open the exhibit (sealing stays the human's click; no-verdict case says so); hint dropped; ellipsis convention.
- **D9. Fingerprint divergence** (certification.ts:238 hashing `""` vs VerifyResults.tsx:475 hashing the composer draft). Fix `ee2bf7d74`: `buildCertification` takes the host draft fallback.
- **D10. `useVerify`, `source.ts` untested** (the truncated-stream guard, seal-seed clearing, in-flight guard, hydration; persistence). Fix `dc1c91ec8` + `5cf263944`: 14 tests; the truncated-stream test mutation-checked.
- **D11. VaultMark render impurity** (`markSeq += 1` in the render body, VaultMark.tsx:67,81): new SVG ids every re-render, defs churn. Fix `5cf263944`: one `useMemo`'d id per mount (preact `useId` rejected: positional per root, collides across roots).
- **D13. types.gen.ts drift** (missing `/api/vaults`): base commit fails the chain's first gate. Fix `d8aa123f9` (purely additive regeneration).

**Tier 4 — craft, copy, a11y, performance**

- **D6. Libre Caslon Display never wired** — fix `b61fb191d`, `fontsWired.test.ts` ties rebind ↔ declaration ↔ files. Confirmed rendering live (`document.fonts`: loaded).
- **D7. Green leak on Carrel's /verify** — `.verifyScope` now neutralizes `--color-success`; locked in verifyScope.test.ts.
- **D12. Settings Keychain overclaim; "TEMP DEBUG" banner in production (main.tsx:25-77); "Einstein" tab title; Shelf "Try again"** — fixes `56713e118`, `5cf263944`, `ee2bf7d74`.
- **D14. Hot render path** — `dispositionForClaim` computed 3× per card per render; `displaySafe` per-character loop × 11 linear ranges over the whole document on every selection change. Fix `cd8a1aaaf`: one compiled character class (ranges stay the source of truth) + one `useMemo` derivation.
- **D15. Margin note duplicate copy** — `detail` and `trail` printed the same sentence; corpus copy mirrored on both sides of the wire (claimDisposition.ts:192 vs services/verify.py:198). Fix `baecd6cbd`: prefer the wire reason, suppress identical trail.
- **D16. SR silence during verification** — working indicator aria-hidden by design but nothing announced the start. Fix `56713e118`: one constant-text status region.
- **D17. Summary stat row omitted `assessed`** (counts would not sum once T1 ships). Fix `56713e118`.

## 4. Open findings (documented, deliberately not patched here)

- **O1. Verdict state dies on navigation.** An unsaved verdict is destroyed by one rail click (engine state is useState; only the draft survives via `liveDraft`). Honest fix is moving engine state to a module signal or auto-saving an unsealed brief on result; both are product decisions. Highest-value follow-up.
- **O2. Entry split.** `CachetApp` ships inside the Carrel entry (bundle comment concedes it; budgets sit bytes from their ceilings). A boot-time `await import()` (not render-time Suspense) would split it, but dynamic chunk loading under `file://` WKWebView is unverified — do not land without testing in the real shell.
- **O3. Layout-animating transitions** on `.lecternMark` (width/height, cachet.module.css:194-197) and `.wordmark` (font-size) violate the transform/opacity-only rule; reduced-motion coverage in VerifyView.module.css guards only `.exam`. Operator visual gate before touching the lectern's signature feel.
- **O4. DESIGN.md staleness.** The bible still names Instrument Serif as the verify-adjacent display face; the locked 2026-06-02 decision (Libre Caslon Display) and the cachet shell palette deserve a decisions-log row.
- **O5. ~200 off-grid px values** across the three big CSS files; `.sourcePanel` reuses the dark palette inside the paper register (intentional "over the record" contrast — confirm with the operator); `vaults` endpoints should move onto the now-generated types.
- **O6. "Present in your sources" / holding-query wording** still needs validation with real lawyers (Harvey's standing caveat), not more engineering.

## 5. Sequenced build plan (additive, each its own PR)

1. **Land this patch** (11 commits; PR from `claude/cool-mendel-9d9124`).
2. **Verdict survival** (O1): module-signal engine state behind the lectern, or auto-save unsealed on result; test = navigate away and back mid-verdict.
3. **Vaults onto generated types** + drift gate in CI so D13 cannot recur.
4. **Reduced-motion completion + layout-transition fixes** (O3) under the operator's visual gate, with before/after screenshots at 1440/1920.
5. **Entry split spike** (O2): verify `import()` chunks under `file://` in the real WKWebView before any code moves.
6. **DESIGN.md decisions-log update** (O4) recording Libre Caslon Display and the shell palette.

## 6. What would make a lawyer trust this interface

What already earns it: the unmarked pass (no green wall, no VERIFIED badge); the refusal as a first-class composed register; four checks shown separately at unequal weights with no fused score; the exhibit that states its denominator, fingerprints the draft, names cloud vs on-device, and makes the seal a human act with an honest crack state; print isolation; AA contrast locked by test.

What this patch adds to that case: the screen now refuses identically in every rendering — mid-stream failure (banner only, never a half-checked "Supported"), the per-case sub-lines (coverage statements instead of accusations), the drawer (all cases, true registers), the audio read-back (a refusal never sounds like a flag), and the chrome (no command, hint, setting, or font that claims something the product doesn't do). A lawyer's trust dies on the first overclaim found anywhere; the standard is that every surface, down to an aria-label and a ⌘K hint, tells the same true story.

## 7. Gate report (run on the final tree)

RUN AND GREEN: `script/generate-api-types.sh` (no drift after `d8aa123f9`); `pnpm typecheck`; `pnpm lint`; `pnpm test` 702/702 (654 baseline + 48 added); `pnpm build:macos`; bundle budgets JS 128,986/129,024 gz, CSS 45,037/45,056 gz (no bumps needed — DEV-gating paid for the additions); Libre Caslon woff2s present in `dist/assets` and `assets.new/`, `@font-face` inlined in `app.new.html`. Visual at 1440 and 1920 (Vite dev, `VITE_CACHET_ONLY=true`): lectern (Caslon confirmed via `document.fonts`), vault, shelf, palette, dead-backend verify error path.

NOT RUN: backend-driven verdict renders (margin marks, case sub-lines, exhibit) screenshotted live — no engine in this worktree; covered by the render tests instead. The Python/Swift legs of the repo verify chain (out of scope for a frontend-only patch; CI runs them). `swift test`, benchmarks, evals: NOT RUN.
