# Cachet UX craft pass + the remaining jaw-drop roadmap (2026-07-01)

Operator asked for the full-potential UX/UI/workflow revamp of Cachet. This note
records what shipped in the first pass (commit `6e48c63e6`, display layer only,
engine sealed) and the ranked roadmap for the rest. DESIGN.md is law throughout:
dark Examination ground, Libre Caslon Display for the Cachet shell, Charter for
reading, oxblood #cf5b6b reserved for flags, no green ever, near-zero motion.

## Shipped (commit 6e48c63e6)

1. **Verify is the filled primary.** The lectern's Verify button was a
   transparent outline (read as tertiary) at the exact moment the demo asks for
   commitment. Now paper-filled with ink text at rest when enabled, per the
   2026-06-17 re-tone contract; outline register moved to the disabled state.
   A quiet mono cmd-return chord chip sits beside it.
2. **The specimen affordance.** Cold lectern shows "Or examine a specimen draft
   with planted defects": one click fills the sheet with a litigator-shaped
   specimen (verbatim Brown quote + real cite, altered $360M figure, fabricated
   Vandelay cite). Never auto-runs the check; disappears once any draft exists.
   Kills the blank-canvas-plus-textbox AI-wrapper cold open; the demo starts
   itself in one click.
3. **The failure register.** A failed check was a bare oxblood whisper floating
   in a void ("Backend offline"). Now a structured ruling: mono uppercase
   "THE CHECK DID NOT FINISH", the cause in reading serif, and a verb-led
   "Run the check again" recovery (withheld when there is no draft or a re-run
   is already in flight). role=alert kept.
4. **Sheet presence.** Faint inset top light + deeper shadow so the writing
   surface reads as a lit sheet on the desk rather than a void.
5. **Toolchain:** dev-only `optimizeDeps.esbuildOptions.target: "esnext"` in
   vite.config.ts — the esbuild 0.28.1 security pin had broken Vite 6's dev
   prebundle (500s on every dep), so nobody could run the dev server. Shipped
   build target unchanged (safari17).

Verified: typecheck, lint, build:macos, 855/855 vitest incl. bundle budgets,
live dev at 1280 + 1920 (lectern cold/filled/error states), verifyScope motion
guard holds (no new keyframes).

NOT visually QA'd this pass (needs backend or the no-backend brief-fixture
shim): the populated verdict surface — WorkspaceMargin, carousel, drawer,
certification exhibit. The changes do not touch their layout.

## The remaining roadmap, ranked by demo conversion value

1. **The verdict reveal (the money moment).** When the stream settles, the
   ruling should land like a stamped judgment: the summary line composed as a
   headline in the display face, statements beneath in strict reading order,
   oxblood only where a flag earned it. Today the summary is typographically
   equal to everything around it. One evening of hierarchy work, zero motion
   needed; the stillness IS the drama. Craft-gated.
2. **The streaming procession.** "Checking citations · 2 of 5" is honest but
   generic. Elevate to the examination register: a mono uppercase docket line
   (EXAMINATION IN PROGRESS · CITATION 2 OF 5) with the per-card Checking
   states it already has. Copy + one CSS class.
3. **Specimen → record pairing.** The specimen draft currently verifies against
   nothing (no record attached), so most statements will could-not-check. The
   full one-click demo wants a paired specimen record (the demo corpus) loaded
   with it, so flags + a supported card land together. Needs a small backend
   affordance or a bundled demo doc id; decide with the validation-demo hat on.
4. **Drawer + exhibit polish pass** (F1/F2 in the Forge queue): matched source
   clause beside a flagged figure in the drawer; visual QA of the token
   highlight at 1440/1920. Already specced in the queue as [REVIEW].
5. **Reopened-brief continuity.** Opening from the Shelf re-hydrates instantly;
   the moment deserves the same composed landing as a fresh verdict (today it
   pops with no context line). Small.
6. **Command palette depth.** cmd-K exists with verify/seal/export verbs; add
   attach-record, open-shelf, load-specimen so the whole demo is drivable
   keyboard-only. Small, very Linear.

## Decisions taken without asking (reversible, flagged)

- Specimen copy says "with planted defects" plainly: honesty-first framing,
  consistent with the refusal brand. Reword freely.
- The fabricated cite uses an obviously fictional caption (Vandelay Industries
  v. Kramer) so no real case is implied. Swap for the demo corpus's canonical
  fabricated cite if one exists.
