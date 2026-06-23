# 0008 — Unattended engine red-team is discovery-only; fixes are human-gated

Date: 2026-06-24
Status: Accepted
Slug: engine-redteam-vs-polish (debate at `.forge/debates/engine-redteam-vs-polish/decision.md`)

## Context

The Council was asked to pick the highest-value Cachet build target for an unattended
overnight Forge run: (a) deterministic engine hardening via an adversarial red-team loop,
(b) demo/frontend polish, or (c) Gate 2 semantic entailment for clean prose. Three seats
(Harvey, Vulcan, Bellwether) wanted (a)'s strategic output: a test-locked adversarial
failure ledger that a regulated buyer's security review can consume. The adversary proved
that pursuing (a) by pointing an unattended loop at the engine's truth-surface files
reproduces the exact class of failure the Forge contract was written to prevent.

Two repo facts decided it. First, `.claude/forge.contract.yaml` already gates every truth
surface (`anchors.py`, `sentences.py`, `contract_verify.py`, `deterministic_envelope.py`,
`case_verification.py`, `local_caselaw.py`) under `human_gates.security`, with the explicit
reason that in-repo fixtures provably miss real-slide regressions (the 2026-06-14
mln/adjudicator case). Second, the unattended driver ships on the held-out gate alone and
no held-out set is staged in this worktree, so an autonomous engine FIX could not legitimately
ship regardless. The known failure direction (a loop laundering a false green into
could-not-check to pass a held-out test, invisibly) is the same move ADR-0013's "figures are
never affirmed" stance exists to prevent.

## Decision

Split adversarial red-team work into two halves with different ship authority, permanently:

1. DISCOVERY (read-only, may run unattended). The generator synthesizes (claim, source-clause)
   pairs, runs them through the existing deterministic path, and logs every result to a
   confession ledger. It mutates NO engine code and imports the engine without monkeypatching
   behavior. It flags both false GREEN and false could-not-check (the laundering direction) as
   defect classes. This is the defensible, buyer-legible artifact.

2. FIX (human-gated, never autonomous). Each crack becomes a proposed fix plus its proposed
   held-out regression test, queued as a REVIEW task and at most drafted on the branch. It
   lands only after a human read. Every fix routes through could-not-check, never a new green
   criterion or a widened literal-match rule. Any change touching a truth surface is REVIEW by
   contract.

Polish (b) is not the primary target while the polish threshold is already cleared; the one
exception is rendering the supported/accepted count beside the refusal (acceptance made
visible), which is product substance. Gate 2 semantic entailment (c) is barred as an
unattended target because non-deterministic model output cannot be locked by a deterministic
ship gate; it returns only behind a reviewed eval harness with a labeled set and a defensible
threshold.

## Consequences

- The moat gets hardened in the safe order: find cracks autonomously, fix them under human
  eyes. The adversarial artifact (the ledger) is produced tonight with no risk to the truth
  surface.
- An unattended night can ship only behavior-preserving AUTO work (E1/S1/S2) as drafts plus the
  discovery ledger; engine corrections accumulate as a morning review queue, not merged diffs.
- Promoting the FIX half to autonomous requires a staged operator-owned held-out engine suite
  AND a frozen held-out set the loop cannot edit. Until both exist, fixes stay REVIEW.
- The constitution's "never widen a green to earn coverage / honesty over coverage" rule is
  enforced structurally, not by trust: the unattended loop has no code path that can turn
  could-not-check or disagreement into green.
