# Cachet PR5b — the Margin / Workspace / Examination layout (craft handoff)

Date: 2026-06-01
Status: **NOT built. Deferred to an operator-led atelier session by design.**
Depends on: PR5a (draft PR #97, `cachet/pr5-alignment`), which ships the data this UI renders.

## Why this is a handoff, not an autonomous build

PR5b is craft: the document-with-margin visual layout, the warm/cold register, motion,
"feels right." Two hard constraints make it an operator gate, not an autonomous task:

1. **Craft is a human gate.** A rubric cannot score "feels right"; the atelier loop + the
   operator's eye lead craft-heavy surfaces. This is a standing rule for Cachet.
2. **Claude cannot visually verify it.** Launching the WKWebView from a tool runs headless
   (no window draws); jsdom returns zeroed `getBoundingClientRect` and no-ops `scrollIntoView`,
   so headless tests can assert render/role/className/motion-spy but CANNOT prove visual
   placement, rail collision, or scroll-to-source. Pixel-accurate margin pinning can only be
   verified in the live WKWebView on the operator's machine (or the `Claude_Preview` Vite-dev
   harness the operator drives).

So PR5b should run as: atelier design pass → build against a Vite-dev preview the operator
watches → operator approves the look → ship. Do not self-approve craft on a rubric score.

## What PR5a already gives you (the data contract — DONE, tested)

Every verify result now carries, per claim card:

    placement: { char_start: int|null, char_end: int|null, placed: bool, method: "exact"|"fuzzy"|"unplaced" } | null

and the response carries a top-level `unplaced: number[]` (claim_index values in the tray).
- `placed: true` → `char_start`/`char_end` are a real, unambiguous range in `draft_text`.
- `placed: false` (or `placement: null`) → the claim belongs in the unplaced tray; never pin it.
- The alignment is deterministic and **never mis-pins** (ambiguity goes to the tray), so the UI
  can trust a placed range absolutely and must surface unplaced claims as a first-class tray,
  not hide them.
Types are in `frontend/src/services/api/endpoints.ts` (via the regenerated `types.gen.ts`):
`VerifyClaimVerdict.placement` and `VerifyResponse.unplaced`.

## What to build (the craft)

Per the locked plan (`docs/plans/cachet-verify-port-2026-05-29.md` PR5) + the prototype
(`prototypes/cachet-shell.html`, the "warm chambers around a cold record" synthesis):

1. **Workspace / the Margin.** Render `draft_text` as a read-back **document body** (not the
   current `<textarea>` + flat card list). Pin each `placed` claim's disposition into a **margin
   rail** at its `char_start..char_end`, with rail-collision avoidance when claims are close.
   The disposition tiers already exist in `claimDisposition.ts` (supported / citation_not_found /
   proposition_unsupported / claim_unsupported / could_not_check; tiers flag/assistive/refusal/
   pass) — map the prototype's data-tier visuals onto them; no taxonomy work needed.
2. **The unplaced tray.** A data-driven list of `unplaced` claims (filter `placement.placed===false`),
   mirroring how `QuotePanel` filters `status!=='verbatim'`. The DECISION is PR5a's (tested);
   PR5b is ONLY rendering. Keep it that way — do not re-derive placement in JSX.
3. **Examination / the Bench.** A slide-in drawer surfacing the four checks at unequal trust
   weights, plus scroll-to-source spatial continuity (`claim.scrollIntoView`).
4. **AppShell route.** Near-zero cost: `App.tsx` already routes `/verify`; `AppShell.tsx` already
   has the nav entry. If PR5b introduces a distinct Workspace shell the swap rides with it.

Optional follow-on: per-claim quote attribution (use PR5a's offsets to locate which claim a
PR4 brief-level `quote_result` belongs to). Natural but deferrable.

## Guardrails (carry from the rest of the verify surface)

- DESIGN.md verify-scope: warm paper / near-black ink / single oxblood accent; **no green, no
  confidence numbers**; motion only on the working indicator, the verdict sits still like ink.
- No em dashes, no AI-slop vocabulary in copy.
- Resolve the known "lawyer-grade look vs DESIGN.md" tension (memory: cachet-form-discovery) with
  the operator, not unilaterally.

## Verification

Headless tests (the `CertificationExhibit.test.tsx` pattern) can assert: the tray renders the
right claims, a placed claim renders in the margin with the right disposition class, the drawer
opens. They CANNOT assert visual placement. The pixel/scroll/collision pass is the operator's
live-WKWebView gate.
