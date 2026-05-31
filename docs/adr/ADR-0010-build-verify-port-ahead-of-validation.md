# ADR-0010: Build the Verify Port Ahead of the Validation Gate

- Status: Accepted
- Date: 2026-05-29
- Amends: [ADR-0008](ADR-0008-v2-pivot-validation-first-sequencing.md) (sequencing only; does not change its strategy, thesis, or exit conditions)
- References: [`docs/plans/cachet-verify-port-2026-05-29.md`](../plans/cachet-verify-port-2026-05-29.md) (the build contract), `prototypes/cachet-shell.html` (the design), PR #88 (T64 answer-quality fail-loud, the hard blocker ADR-0008 named, now done), [ADR-0009](ADR-0009-fail-loud-on-high-stakes-flows.md)

## Context

ADR-0008 sequenced V2 validation-first: run the T66 30-day test on the existing build, "build nothing new," keep the polish queue paused. The reasoning was an asymmetric downside: a litigator who watches a hollow-answer demo concludes the category is not real, and that false negative is hard to recover from.

Two things changed since 2026-05-26:

1. **The hard blocker is closed.** ADR-0008's "build nothing new" rested on one concrete risk: the generator produced header-only / hollow answers (T64). T64 shipped (PR #88: fail-loud provider gate on high-stakes flows, [ADR-0009](ADR-0009-fail-loud-on-high-stakes-flows.md)). The verify engine no longer silently degrades to a weak provider; it surfaces `ok=False`. The specific failure ADR-0008 protected against is fixed.
2. **An interactive design (`/atelier`) + architecture review (`/plan-eng-review`) pass produced a locked, decision-complete build plan** for the full verify surface ("warm chambers around a cold record"), grounded in the real engine, with the prototype's three engine-honesty gaps (fake per-cite labor, draft-quote-verbatim, claim-span alignment) converted into real, test-gated PRs.

The operator decided, 2026-05-29, to build the full verify port now via the `/carrel-build` autonomous routine rather than wait behind the T66 gate.

## Decision

Sequence the verify-port build (queue tasks T69-T75, contract in the build plan) ahead of the T66 validation test. The autonomous loop builds the port; T65/T66/T67 (the validation test and post-test design) remain operator-led and unchanged.

The intent is that **T66 validates the ported surface**, not the current scaffold: the port becomes the demo vehicle, so the test measures demand for the real product. This is sequencing, not a strategy change. ADR-0008's thesis (independent verification layer, litigation wedge) and its three-branch decision rule (COMMIT_B / FALLBACK_A / KILL) stand.

## Why this is defensible, and where the risk remains

- **The original objection is gone.** ADR-0008's asymmetric-downside argument was "a litigator watches a hollow-answer demo and concludes the category is not real." T64 removed hollow answers. Building the surface now does not reintroduce that risk.
- **The residual ADR-0008 risk is real and accepted.** If T66 returns KILL, the verify-port build is wasted effort. The operator accepts this. The mitigation: the port is small, additive, test-gated PRs on a reused engine, not a rewrite, so the sunk cost is bounded, and a stronger demo surface raises the odds T66 returns a true signal rather than a false negative.
- **This is not an ADR-0008 exit.** None of ADR-0008's formal exit conditions fired (T66 has not run). This is a deliberate operator override of the sequencing, recorded so the autonomous loop and future sessions see one consistent authority instead of a contradiction between the build plan and ADR-0008's pause.

## Open question for the operator

Confirm the intended sequencing: **port-then-validate** (T69-T75 land, then T66 demos the ported surface, the assumption baked into this ADR and the queue) versus **port-in-parallel** (build proceeds but T66 runs on whatever is current when sessions are scheduled). The queue assumes port-then-validate: the loop builds T69-T75, then halts and surfaces for operator-led T65.

## Non-goals

- Changing ADR-0008's strategy, thesis, or decision rule.
- Making T65/T66/T67 autonomous. They stay operator-led.
- Lifting build-only scope. The port is build-only (no outreach, drafts only).
- Auto-trusting the rater on craft or security. Per the build plan, the craft PRs (cert, Margin) and the security PR (Keychain) surface for human review even at a rater 100; a code rubric cannot rate taste or prove a key never leaks.
