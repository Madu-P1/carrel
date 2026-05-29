# Plan: T65 — Cachet V2 validation test prep (the 30-day test)

- **Date:** 2026-05-29
- **Status:** STARTED (this plan is the mandated first artifact). Operator-led.
- **Deps:** T64 (answer-quality fail-loud gate) shipped; verify-as-hero slice 1 built + rated 100/SHIP (branch `claude/upbeat-darwin-9d524f`). The slice is the surface under test.
- **Frame:** ADR-0008 validation-first. T65 prepares the test; T66 runs it; T67 (Stage 2/3 design) is conditional on T66's verdict.
- **HARD GUARD: zero new product code in T65.** If a deliverable surfaces a code need, it becomes its own task. The test must not become a cover for more building.

## The decision this test exists to make

T66 ends with one binding verdict, written to `docs/validation/30-day-test-2026-05-26/closeout.md`:
- **COMMIT_B** — the verification thesis earns real trust from real liability-bearing professionals; proceed to Stage 2 (tax attorneys first per the discovery).
- **FALLBACK_A** — signal is narrow or profession-specific (e.g., only one cohort bites); narrow the wedge before committing more.
- **KILL** — the refusal/verification does not change behavior; write the postmortem, re-point the engine.

The rule (Deliverable 4) is set BEFORE sessions and is binding. Resist re-reading a no-signal result as a maybe-signal result.

## Deliverable 1: the seeded memo(s) [I can draft this; founder picks the matter]

An AI-drafted legal memo (two: one civil, one criminal, to span practice areas) sourced from a **public-domain matter** so the artifact is freely shareable. Each carries **8-12 cited cases** with a known, planted error distribution:
- ~70% real and accurately characterized (the validator must NOT false-flag these),
- ~20% real but holding-mismatched (must surface as `proposition_unsupported`),
- ~10% fabricated / non-existent (must surface as `citation_not_found`).

This is the ground-truth artifact: because we plant the errors, we can measure (a) the validator's catch rate and false-positive rate, and (b) in T66, the litigator's reaction to each verdict.

**Acceptance:** run each memo end-to-end through the current validator (`/api/verify`). It must catch every fabrication and every holding mismatch, and not false-flag the accurate cites. Any seeded error that slips through is itself a T64/engine signal: iterate the memo, and if the miss is an engine gap, file a separate engine task (do not patch code under T65).

**First run recorded (2026-05-29):** a throttled diagnostic validated the mechanism — holding-match caught the Lochner mismatch (`holding_match=False`) with correct reasoning when the provider was on, and the planted 404 (Delgado) was caught. It also corrected the ground truth: civil #10 (571 U.S. 312) is a **phantom** (real cite → *Fernandez v. California* / confabulated name), not a 404, so the civil memo's planted classes are 7 accurate / 2 holding-mismatch / 1 phantom (the pure-404 class lives in the criminal memo); and criminal #9 (Gideon, 372 U.S. 335) returns `300 ambiguous` deterministically, so it is reclassified `could_not_check` and flagged for a cite swap. Full per-cite catch-rate / false-positive census is **pending T66** because the free CourtListener tier (5/min) cannot pace a complete two-memo run. Full record and findings: `../validation/30-day-test-2026-05-26/catch-test-results-2026-05-29.md` (relative to repo root: `docs/validation/30-day-test-2026-05-26/catch-test-results-2026-05-29.md`). Two product-improvement candidates surfaced (fail-loud on holding-unavailable; explicit name-mismatch flagging) — filed as engine tasks, not patched here.

## Deliverable 2: recruiting [founder-led; I draft screening criteria + framing]

- **Primary wedge:** 15-20 litigators who file AI-assisted briefs and personally carry the Rule 11 / malpractice exposure.
- **Cross-professional probes** (per `docs/notes/2026-05-29-cachet-cross-professional-discovery.md`, to test whether the SPINE generalizes, not just the litigation engine):
  - **Tax attorneys (2-3)** — the cleanest Stage-2 wedge (same corpus shape; "still good law" becomes "is this code section superseded"; 26 USC 7216 makes local-first load-bearing).
  - **A solo or small-firm auditor (1-2)** — recruited specifically to document the numeric-reconciliation gap with a real human (the discovery's biggest "engine doesn't generalize for free" finding).
  - **An investigative journalist (1)** — cheap to recruit, hardest on the verbatim-vs-altered-vs-absent distinction.
- **4-6 non-lawyers** (per the design doc) as a control on legibility.
- **Exclude** (per the discovery): CISOs / regulatory affairs / hospital clinicians — procurement-gated or Stage-3 product; a 30-day self-serve test mis-measures them.
- Recruiting is the operator's job. I draft the screening criteria and the session framing; the founder does outreach (no automated outreach under build-only scope).

## Deliverable 3: watch-session protocol [DRAFTED 2026-05-29]

**Full operator playbook:** `../validation/30-day-test-2026-05-26/supervised-session-protocol.md` — pre-session checklist (keys + provider-on + rate-limit awareness), neutral framing, the session arc, the five moments to watch (with the refusal as the central "gem" test), non-leading probes, the per-session capture template, and how each session's one-line verdict rolls into the Deliverable 4 rule. Scoped to the **supervised pilot** (litigator uses Carrel on the operator's machine) since standalone distribution is unbuilt. The bullets below are the summary it expands.

- **What they touch:** the verify-as-hero surface (this slice) + the seeded memo, on the founder's machine or a packaged build.
- **What to observe (capture verbatim):** Does the loud refusal earn trust or read as the tool dodging? Do they act on the flags? Does one-click-to-source land them where they need? Do they reach for the certification export, and would it satisfy a judge's standing order / their carrier? Would they pay, and in what shape? What is their unprompted "the gem" reaction?
- **Anti-leading:** discover their workflow and pain before showing the product; do not pitch.
- **Notes:** anonymized, under `docs/validation/30-day-test-2026-05-26/sessions/<date>-<participant-id>.md` — no participant names, no firm names, no client names.

## Deliverable 4: the binding decision rule [founder sets thresholds; I draft a candidate]

Write the exact COMMIT_B / FALLBACK_A / KILL thresholds BEFORE the first session. Candidate shape (founder tunes the numbers):
- **COMMIT_B** if a clear majority of litigators say they would run real, live briefs through it before filing AND the refusal/one-click-to-source measurably changed how they checked the seeded memo.
- **FALLBACK_A** if the strong signal is concentrated in one cohort (e.g., tax bites, litigators shrug).
- **KILL** if the verification does not change behavior across cohorts.

## Links
- Surface under test: this branch (verify-as-hero slice 1); discovery: `docs/notes/2026-05-29-cachet-cross-professional-discovery.md`; sequencing: `docs/adr/ADR-0008-v2-pivot-validation-first-sequencing.md`; the slice plan: `docs/plans/cachet-verify-hero-2026-05-29.md`.
