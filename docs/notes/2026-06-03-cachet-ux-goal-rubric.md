# Cachet UX goal rubric (the 100/100)

Date: 2026-06-03
Source of truth: `docs/notes/2026-06-03-cachet-ux-dopamine-trust-research.md`.
Purpose: this is the operator's "achieve the research = 100/100" goal made concrete. It is the build's success criterion (karpathy: define verifiable success criteria) and the craft gate. A build is scored against it cold; 100 means the research is applied, not approximated.

How to read the checks: **[mech]** is mechanically verifiable (grep, test, token check) and must never regress. **[review]** needs a human or design-review eye. The mechanical items are the spine; the review items are the soul. You cannot buy back a failed [mech] with a strong [review].

The single governing principle the whole rubric serves (from the research reconciliation): **honest variable reward. The variability lives in the draft, never in the interface.** Any point that rewards manufactured emotion is a point scored wrong.

---

## A. The reconciled stance: honest variable reward (20)

- **A1 (8) [mech+review]** The only variability is the finding. No randomized celebration, no surprise token, no manufactured prediction-error in the UI. Mechanical: no `confetti`, `Math.random`-driven reward, `streak`, `surprise` in the verify/cachet surface. Review: the reveal feels like a real event, not a designed one.
- **A2 (6) [review]** The reveal of the finding is staged as the peak. The gap between "I expected a clean draft" and "it caught three" is dramatized honestly (weight, stillness, order), not flattened into a uniform list.
- **A3 (6) [mech+review]** The act of verifying is fast and keyboard-first. Sub-second to first sign of life on paste/verify. The instrument answers instantly (effectance is the daily-habit driver).

## B. Calibration, not confidence (20)

- **B1 (5) [mech]** No confidence percentage, no trust score, no pass-rate, no ratio, no progress bar anywhere on a verdict surface. Certainty is encoded in register only. (Backed: calibration-comms backfire, arXiv 2402.07632.)
- **B2 (5) [mech]** No green VERIFIED badge. Absence of a flag is the pass. (Backed: overreliance, Buçinca 2021; the green badge is the most dangerous element.)
- **B3 (5) [review]** Three finding registers preserved with distinct, UNEQUAL certainty: deterministic flag (oxblood struck mark), AI judgment (dotted pencil query, achromatic, "for your review"), refusal (composed ink bracket). The softer, less-certain finding never borrows the stronger one's confident treatment.
- **B4 (5) [mech]** Scope-honesty line on every result: "This confirms grounding, not legal correctness or strategy."

## C. The refusal as calibration instrument (15)

- **C1 (6) [review]** The refusal states, in order: (1) what it checked, (2) what it therefore cannot say, (3) the precise next action, as a button. It is the most complete card in the product, not the emptiest.
- **C2 (5) [review]** The refusal never shrugs ("could not check") and never accuses. Grave, neutral ink. Stillness is the design; it does not animate (a refusal that performs is a refusal lying).
- **C3 (4) [review]** Framed as reliance-calibrating, never as "confession builds trust" (that claim was refuted 0-3). Copy and composition reflect calibration, not endearment.

## D. The five honest loops, end to end (15)

- **D1 (3) [review]** Loop 1 The Catch: paste, one-keystroke verify, the finding, seal-to-Shelf investment all present.
- **D2 (3) [review]** Loop 2 The Clean Record: flags, fix-or-stand-by each, re-verify; the reward is the changed state of the work, not a rising score.
- **D3 (3) [mech]** Loop 3 Effectance: the full keyboard path exists. ⌘K verify, ⌘↵ seal, j/k between findings, ⌥↵/⌥click to drill a flag.
- **D4 (3) [review]** Loop 4 The Drill: the Examination drawer shows exactly WHY (the missing case at the reporter; the quoted passage against the source with altered words exposed).
- **D5 (3) [review]** Loop 5 The Shelf: warm register (Fraunces, cream), a body of work, no count; a sealed record whose draft drifted shows the cracked seal here too.

## E. Signature moments built to spec (15)

- **E1 (3) [review]** SM-V1 The Paste: textarea settles into a sheet; honest "Reading the draft. N statements." count before any judgment.
- **E2 (3) [review]** SM-V2 The Read: legible labor. Statements settle from "Checking..." into disposition as each lands; flags rise; NO progress bar. FLIP on transform/opacity only.
- **E3 (3) [review+gate]** SM-V3 The Catch: a drawn oxblood strike (`scaleX(0->1)`, transform-origin left, transform-only) across a deterministic miss only, a breath of stillness, then the plain finding line. OPERATOR-GATED motion exception (research §6.1).
- **E4 (3) [review]** SM-V4 The Reckoning + SM-V6 The Seal: verdict-as-finding headline in the cold display serif with supported set receding; the seal is the universal dignified session end (⌘↵), clean or flagged; crack-on-stale kept.
- **E5 (3) [review]** SM-V7 The Command Spine + SM-V8 The Shelf-as-ledger present.

## F. The refuse-list held (10) — refusing IS the brand

- **F1 (2) [mech]** No streak counter, no daily-goal ring.
- **F2 (2) [mech]** No confidence percentage or trust score (discipline mirror of B1).
- **F3 (2) [mech]** No green VERIFIED badge, ever (discipline mirror of B2).
- **F4 (2) [mech+review]** No manufactured variable reward: no surprise confetti, no randomized celebration, no "you caught a big one."
- **F5 (1) [review]** No fake urgency, no manufactured scarcity (FTC-named patterns).
- **F6 (1) [review]** No gotcha framing of the user. Clerk's voice, not a judge's. The tool strikes the citation, never the person.

## G. Brand and technical fidelity (5)

- **G1 (1) [mech]** Real `cachet-mark.svg` severed-ring logo, not a hand-drawn ring.
- **G2 (1) [mech]** Libre Caslon Display on the cold display register (self-hosted woff2, no CDN); Charter body; Fraunces reserved for the warm Shelf; warmth never touches a verdict.
- **G3 (1) [mech]** Palette is paper/ink plus a single grave oxblood for flags only. No green, amber, gold, or brass.
- **G4 (1) [mech]** Motion is transform/opacity only, near-zero on verify, every moment has a static reduced-motion end-state; no third-party motion or font CDN; no render-time Suspense (file:// constraint).
- **G5 (1) [mech]** No em dashes and no AI-slop vocabulary in any UI copy.

---

## Scoring

Total 100. Bands:
- **90-100** ships to the operator's craft gate as "research applied."
- **75-89** is close; name the specific failed items and fix before the gate.
- **< 75** is not the research; rework.

The mechanical floor: every **[mech]** item is pass/fail and contributes its full points only when fully passing. A build that fails any single refuse-list [mech] item (F1-F4, B1, B2) is capped at 70 regardless of other scores, because a single manufactured-engagement element poisons the credibility the rest of the product is buying.

## Current baseline (pre-build, 2026-06-03)

The shipped `frontend/src/features/verify/` already earns most of B and parts of D/E per the research §1 (counts-not-scores, no green badge, three registers, scope-honesty, the PR2 seal). The net-new work is the standalone shell (A3 keyboard entry, D5 Shelf framing in a Cachet context), and the signature-moment upgrades (E1-E5, C1-C3 refusal rebuild). This rubric scores the standalone Cachet product, not the Carrel substrate.
