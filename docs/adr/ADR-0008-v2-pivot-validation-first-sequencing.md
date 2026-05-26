# ADR-0008: Validation-First Sequencing for the V2 Pivot

- Status: Accepted
- Date: 2026-05-26
- Supersedes: the 2026-05-26 "V2 polish push" operator override in
  `AUTONOMOUS_WORK_PLAN.md` (which authorized the autonomous loop to
  ship T59-T63 polish without first running the validation gate the
  V2 design doc itself prescribed).
- References: `/Users/madu/.gstack/projects/Codex/madu-main-design-20260522-015141.md`
  (V2 design doc, APPROVED 2026-05-22),
  [ADR-0006](ADR-0006-typed-node-defaults-on.md) (typed-node defaults
  on, the structural prerequisite for V2 verification),
  PR #82 (V2 Stage 1 backend + UI scaffold, commit `57188d81`).

## Context

The 2026-05-22 office-hours session repositioned Carrel from a study
tutor to an **independent AI verification layer for high-stakes AI
output**, with litigation pre-flight as the wedge. The design doc
approved Approach B (app first, then verify API) and named one
central unvalidated risk:

> Whether liability-bearing professionals feel verification as a
> distinct, must-have, separately-paid need rather than "my AI
> already cites." This is the central unknown the 30-day test
> targets.

It then set an explicit assignment:

> Run the 30-day test. Build nothing. Take an AI-drafted legal memo,
> seed it with real citations and a few subtly wrong ones, and run
> it through Carrel's existing validator so it catches the bad ones.
> That is the demo. Then do 15-20 watch sessions with litigators and
> 4-6 with a non-lawyer liability-bearer. Stay silent, watch.

Between 2026-05-22 and 2026-05-26 the engineering response was
inverted: V2 Stage 1 backend + UI scaffold shipped (PR #82, 7
commits): typed-node defaults flipped on (closing the prior T12),
`Citation.node_type` + non-prose drop gate, CourtListener
case-existence verifier, holding-match verifier, `/api/verify`
route, `VerifyView` UX scaffold. A polish queue (T59-T63) was then
opened for the autonomous loop to consume unattended.

This put Carrel in a position where:

1. The validation gate the founder set has not started.
2. The autonomous loop is set up to ship more verification surface.
3. The verification surface depends on the answering surface being
   substantive, and the answering surface has a known regression:
   the generator produces header-only / title-only answers in a
   non-trivial fraction of cases (memory observation 8672,
   2026-05-22, flagged as the prerequisite issue before any other
   pipeline improvement can deliver value).

A litigator watch session on the current build risks the worst
possible signal: the founder demos a verification layer that
correctly verifies a hollow generator answer, and the litigator
concludes the category is not real. The validation test would then
return a false negative against the strongest version of the
product.

## Decision

Reshape the queue around the design doc's own sequencing:

1. **Pause the V2 polish queue (T59-T63).** They are correctly
   scoped and high-confidence, but they harden a surface that will
   be demoed under conditions the answer-quality bug poisons. Hold
   until after the validation gate.
2. **Promote the answer-quality investigation to a blocker-level
   task (T64).** Generator outputs that surface as headers / titles
   instead of substantive answers are a Stage-1 demo killer. Investigate,
   reproduce, fix, regression-test before any litigator watch session.
3. **Open the 30-day validation test as structured work (T65 prep
   + T66 run).** The doc's assignment becomes the next two operator-
   led tasks. Build nothing new; use the existing validator. Costs
   roughly zero in build effort, a few hundred dollars in recruiting,
   30 days of founder calendar time.
4. **Queue Stage 2/3 design work behind the test outcome (T67).**
   The validation test has three decision branches per the doc, and
   only one of them leads to Approach B execution. Designing for the
   wrong branch wastes weeks.
5. **Retire T12 from the queue.** It shipped as part of PR #82
   commit `fbd745d4`. The status flip on this file is overdue.
6. **Defer (do not kill) T13-T58.** The chunks-to-nodes migration
   has real value but is no longer the critical path. A separate
   sweep will assign each task an explicit kill / keep / defer
   verdict in a follow-up; until then they remain `pending` but
   blocked behind the validation outcome by the new override block.

## Why This Path

- **The founder set the gate.** ADR drift between "what we said we'd
  do" and "what we shipped" is the kind of small, accumulating error
  that ends companies. Honoring the design doc is the simplest
  correction.
- **The counter-argument is real but loses.** "T59-T63 are small,
  let them run, then validate" is seductive because the loop is set
  up and the tasks are scoped. It loses because the validation test
  is not gated on V2 polish landing; it is gated on the generator
  producing substantive answers and on the verifier catching seeded
  errors. Polish does neither. The polish queue can run after the
  test if the test green-lights Approach B; if the test red-lights
  it, the polish was wasted anyway.
- **A failing 30-day test is a hard outcome to recover from.** If
  litigators watch hollow-answer demos and shrug, the founder cannot
  re-run the same test in 60 days with a better build. The
  recruiting well is poisoned, the message ("I showed you something
  that wasn't ready") sticks. The asymmetric downside justifies a
  4-6 week delay on the polish queue.
- **Local-first does not change the calculus.** The verification
  thesis is structural. The structural moat is intact whether T59-
  T63 ship this week or next month. There is no time-decay on the
  category window that punishes a 30-day investigation pause.

## Exit Conditions (When To Set Override `=off`)

1. **Validation test green-lights Approach B.** Litigators AND at
   least one other liability-bearing profession lean in and ask to
   pay. Polish queue resumes; Stage 2/3 design work starts (T67).
2. **Validation test green-lights Approach A only.** Lawyers bite,
   non-lawyers shrug. Polish queue resumes (the vertical app is the
   product); Stage 2/3 design is scoped down to "good vertical app
   with one customer profile" rather than horizontal verification
   platform.
3. **Validation test red-lights the category.** Universal shrugs.
   Decommit from V2. Revert to the pre-pivot Carrel tutor surface,
   re-evaluate. Polish queue is killed (not just paused).
4. **Answer-quality investigation surfaces a structural problem
   (T64 blocked).** If the generator quality is bounded by something
   we cannot fix in <2 weeks (model limit, retrieval ceiling,
   product-shape mismatch), surface to operator before continuing
   the test prep; the test premise might shift.

## Non-Goals

- **Killing the polish queue.** T59-T63 stay `pending` with explicit
  pause-reason notes. They resume on exit condition (1) or (2).
- **Killing the chunks-to-nodes migration (T13-T58).** Deferred for
  separate triage; do not delete tasks here.
- **Rewriting the V2 design doc.** It stands. This ADR is about
  sequencing, not strategy.
- **Removing the autonomous loop.** It stays armed. The override
  just re-points it at the right queue when it next fires
  (post-validation).

## Updates To `AUTONOMOUS_WORK_PLAN.md`

- T12 status flipped to `done` (PR #82 commit `fbd745d4`).
- The new validation-first override block (dated 2026-05-26) is
  inserted ABOVE the prior V2 polish push block. The prior block
  stays for the historical record but is marked SUPERSEDED.
- T59-T63 stay `pending` with new `**Pause:**` lines pointing to
  this ADR.
- New tasks T64 (answer-quality investigation), T65 (validation
  test prep), T66 (validation test run), T67 (Stage 2/3 design,
  conditional on T66 outcome) appended to the queue.
- T13-T58 remain `pending` with no individual changes; the
  override defers them.

## Open Questions

- **T64 (answer-quality) plan ownership.** The investigation needs a
  proper `docs/plans/answer-quality-2026-05-26.md` produced by
  `make-plan` with documentation discovery, since the root cause is
  not yet known. Done before T64 work starts.
- **T65 (validation test prep) plan ownership.** Same applies, and
  needs `docs/plans/validation-test-prep-2026-05-26.md`. Includes
  memo seeding protocol, litigator recruiting script, watch session
  guide, decision-rule operationalization, observation rubric.
- **Non-lawyer second-vertical selection.** Doc lists analyst /
  auditor / clinician / consultant. T65 must pick one before
  recruiting opens.
- **HANDOFF.md + CLAUDE.md V2 framing.** Updated in this commit
  pass so new sessions load the V2 lens. Tutor framing kept in the
  exit-scenario sections so the legacy surface is still legible.
  V2 is a repositioning, not a deletion.
