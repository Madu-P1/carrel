# ADR 0001: AFM Pass 1 Ship Strategy

**Date:** 2026-05-12
**Status:** Accepted (with operator override on action item 2)
**Routine:** Carrel autonomous build, dry run #1
**Decision driver:** chimbrooks@gmail.com via `docs/plans/afm-decision-brief-2026-05-11.md`

## Operator override (2026-05-12)

After this debate completed, the operator set a build-only scope on the autonomous routine: **no DMs, no outreach approved**. Action item 2 below (send the three study-group recruitment DMs) is therefore **DEFERRED to operator manual handling**, not executed by the routine. Action items 1, 3, 4, 5 (archive runbook, update TODOS.md, set kill criterion, park Phase 4.5) remain in scope for the autonomous implementer agent because they are build-side artifacts.

The implementer-agent action plan below reflects this override.

## Context

A solo founder building Carrel, a pre-launch local-first AI study workspace for macOS, faced a 3 to 4 hour fork in the road:

1. **Ship AFM Pass 1 honestly with the citation gap documented on a PR.** 30 minutes.
2. **Push Phase 4.5 today** to implement provider-specific schema handling in `services/tutor.py` so AFM actually produces user-visible citations. 3 to 4 hours.
3. **Park AFM, run the 3-study-group customer dev test** the founder had drafted but not sent.

The proposal under debate by the autonomous routine was option 1. The Proponent agent built the case for, the Adversary built the case against, the Synthesizer picked the winner, and the Independent Auditor signed off with caveats.

## Decision

**Winner: Adversary. Option 3 is strictly dominant.**

The Synthesizer returned HIGH confidence. The Auditor approved with five non-blocking follow-ups and one blocking caveat (the runbook must be archived in place, not deleted).

## Action plan (audited, build-only scope applied)

**For the autonomous routine to execute (build-side only):**

1. Skip the AFM runbook ceremony. The AFM Pass 1 commits `d867af74` and `9611e2bf` are already on the current branch, with 15 follow-on commits built on top of them. There is nothing to commit.
2. Update `TODOS.md` with a pointer to the citation gap at `services/tutor.py:30-90` and `:705-755` (using the brief's line ranges, not the synthesizer's), plus the kill criterion: *"If 3-study-group test returns weak signal on citations as the wedge by 2026-06-11, archive Phase 4.5 entirely."*
3. Move `docs/plans/afm-runbook-2026-05-10.md` to `docs/plans/parked/` with a README explaining the kill-criterion gate. Do NOT delete the runbook: Phases 5 to 9 contain load-bearing implementation detail.
4. Phase 4.5 stays parked until customer signal arrives.

**Deferred to operator manual handling (out of routine scope as of 2026-05-12):**

- Send the three study-group recruitment DMs. The operator handles outreach. If and when the routine surfaces a candidate moment, it will log to `.claude/logs/operator-followups.jsonl` for the operator to read and act on.
- Set the Claude API budget cap on the cohort accounts. This depends on the operator deciding to run the cohort test.

## Why this matters

The Adversary surfaced an empirical fact that the Proponent's argument depended on but had not verified: the AFM Pass 1 commits were already merged. The Proponent's "30 minutes to ship Pass 1" was 30 minutes to perform a runbook ceremony for work that had already shipped. The Synthesizer trusted the git fact over the runbook's framing. The Auditor independently re-verified and caught a second-order risk (ambiguity in "replace the runbook" that could have triggered a `rm` of load-bearing context).

This is the canonical case for the adversarial routine: a single-agent pass would likely have followed the runbook's framing without checking git state, executed option 1, and shipped a brand-negative PR for work that did not need shipping.

## Confidence

HIGH (Synthesizer), APPROVED (Auditor).

## Proponent transcript

```
# Proponent: Ship Pass 1 honestly on its own branch with the citation gap documented as a known limitation, then immediately pivot.

## Why this is right

Codebase fit: the seam is already cut, the work just needs to be committed.

The runbook at docs/plans/afm-runbook-2026-05-10.md:25-89 lists the exact eight files to stage on a clean branch, with a hand-written commit message ready to paste. The stash command at lines 33 to 41 names the seven flashcard-related files that need to be separated. Nothing in step 1 is speculative: it is shell commands the founder can paste in fifteen minutes.

The provider abstraction is already clean. ai/afm_client.py:1-13 documents AFMClient as implementing the AIProvider Protocol so callers do not know which backend is wired. The schema mismatch lives entirely in services/tutor.py:32-91 (the system prompt and tool definition) and services/tutor.py:700-736 (the _flatten_claim_citations and _serialize_claims consumers that expect nested Claim objects). That isolation is the proof: AFM is plugged in correctly at the wire layer. The Ask flow gap is a separable defect, not an architectural defect. Shipping Pass 1 does not bake the limitation into the design; it just exposes the interface where Phase 4.5 will land.

Test coverage is already in place. tests/test_afm_client.py is 26.9KB of unit tests; the runbook commit message at line 76 cites 20 tests for the AFMClient itself, 47 passing in 0.011s overall. The PR will not land with broken tests because the tests do not exercise the schema gap; they exercise the bridge contract, which works.

Strategic alignment: AFM is on disk in the right form, ready to power the moat the moment the schema lands.

The validated moat is privacy plus verbatim citations plus deadlines. AFM is the privacy pillar of the free tier: zero data leaves the device, the model ships with macOS, Carrel is macOS-only so this is uniquely available to Carrel. Shipping Pass 1 means the next time the founder opens this question, the foundation is in main, reviewable, and reachable from a feature flag. Reverting to the customer-dev path does not delete AFM; it parks it in a known-good state. Pushing Phase 4.5 today delays customer dev by three to four hours and ships a feature with no validated demand behind it. Option 1 preserves both.

Time and risk profile: thirty minutes for an outcome that buys back hours of uncertainty.

Three to four hours on Phase 4.5 (option 2) gambles that the right answer to the schema gap is option C in the brief (two-tier tool schema), and that the founder can implement it cleanly in a single pre-customer-dev session. The brief itself says "I lean toward C. A and B both have abstraction smells." A leaning is not a decision. Spending half a day implementing the wrong abstraction is the worst outcome here, because any reversal costs a second half-day. Option 1 forecloses zero options: the AFM branch sits on main, the customer-dev test can run on Claude as the free tier (the brief even calculates the cost at trivial), and Phase 4.5 can land later with the benefit of three-study-group signal informing whether nested citations even matter to those users.

The risk of option 1 is small and bounded. The PR description (runbook lines 513-553) is already drafted and honest: "Carrel free tier is now functional on Apple's on-device 3B model" with a test plan that calls out the AFM-Claude-Ollama fallback. The only edit needed is a one-paragraph "Known limitation" note saying the grounded-answer flow currently produces empty citations on AFM and will be addressed in a follow-up commit.

Second-order upside: the work becomes shareable and the founder gets out of the engineering loop.

Once Pass 1 is on main, the founder can talk about AFM publicly. "Carrel's free tier runs on the LLM Apple ships with your Mac" becomes a true statement on the README. The marketing surface lights up before the schema bug is fixed because the marketing claim is about the architecture, not the depth of one flow. That is genuinely valuable: it lets the founder send the recruitment DMs (option 3) with the AFM story already in the product page. Without option 1, the AFM work is invisible to anyone outside this machine, and the recruitment story has to either omit it or promise it.

A second second-order benefit: shipping the work prevents bit-rot. The brief notes Pass 1 is on feat/flashcards-focus-2026-05-09, intermingled with unrelated flashcard work. Every day that branch stays alive, the merge surface drifts further from main. Thirty minutes today is one to three hours of rebase work in a week.

## Strongest concession

The honest counter is this: option 1 ships infrastructure that does not yet light up the product, and the founder has been here before. Six months in, the temptation to keep adding mechanics is exactly the pattern that delays customer dev indefinitely. Someone could read option 1 as "more building disguised as discipline." If the AFM branch sits on main for six weeks with no Phase 4.5 follow-up, option 1 will look like a rationalization for avoiding the harder question.

But the dismantle is this: option 1 is the cheapest path to honestly being done with AFM tonight. Option 2 is three to four more hours of building. Option 3 deletes the work entirely from public view. Only option 1 closes the loop in thirty minutes and leaves the founder free to send the recruitment DMs the same evening. The risk that Phase 4.5 never lands is real, but that risk is identical under all three options, because Phase 4.5 depends on customer signal anyway. Option 1 buys the right to defer Phase 4.5 indefinitely without erasing the foundation.

## What I would ship first

1. Execute runbook step 1 verbatim (15 min): git stash, branch off main, stage the eight AFM files, commit with the prepared message, push, restore flashcard branch.
2. Open the PR with one added paragraph (10 min): prepend a "Known limitation: grounded-answer flow returns empty citations on AFM; see services/tutor.py:32-91 and :700-736 for the schema gap. Tracked as Phase 4.5 on docs/plans/afm-integration-2026-05-10.md." Mark the PR as ready, not draft, because Pass 1 is genuinely complete on its own terms.
3. Send the three recruitment DMs (5 min): the founder has them drafted. With Pass 1 shipped, the engineering side is closed for the night and the next decision (Phase 4.5 versus more customer dev) waits on real signal from the three study groups.
```

## Adversary transcript

```
# Adversary: why the proposal is wrong

## The strongest counter

Option 1 is not the safe middle path. It is the worst of the three options on offer, and the founder's own decision brief at docs/plans/afm-decision-brief-2026-05-11.md:184 admits it: "I suspect the right answer is option (3), and I want someone to either confirm that or argue convincingly that the free tier needs to be functional before the customer test gives meaningful signal." Option 1 confirms neither. It pretends to be a compromise while delivering zero of what each pole was optimizing for. Option 3 is strictly dominant.

Concrete failure mode 1: option 1 is engineering theatre, not a free tier. The brief at line 59 documents the actual state: "citation_attempt_count=0 means the LLM call succeeded, my retrieval found 8 relevant chunks, but the model produced zero structured citations. Carrel's UI is built around citation chip flight... with zero citations, there's nothing to flight, and the answer card renders blank or shows 'couldn't synthesize.'" Shipping Pass 1 with this gap documented produces a free tier that fails at the one thing Carrel's validated wedge depends on: verbatim citations. The founder confirmed at brief line 27 that "privacy + verbatim citations + deadline planning" are the three pillars. Option 1 ships the free tier minus the citation pillar. Worse, it ships it under a PR title that says "Apple Foundation Models grounded-answer provider." That public artifact is a commitment device.

Concrete failure mode 2: the AFM Pass 1 commits already exist on main. Verify: git log --all --oneline --grep="AFM" returns d867af74 feat(ai): Apple Foundation Models grounded-answer provider with chunk... and 9611e2bf fix(ai): harden AFM grounded-answer path + chunk cleanup. The runbook at docs/plans/afm-runbook-2026-05-10.md:27 describes a workflow ("You're currently on feat/flashcards-focus-2026-05-09...") that does not match the current branch feat/audit-pr-p3-provider-singleton-invalidation. The premise of option 1, "separate AFM from flashcard work and open a PR," is built on a stale snapshot. AFM has already been merged. The 30 minutes of option 1 work is largely complete or moot. Spending another 30 minutes on bookkeeping for code that is already on main is the definition of motion without progress.

Concrete failure mode 3: tutor.py already shows the gap is real and unsolved by tweaks. The codebase at services/tutor.py:64-71 already has a separate _AFM_GROUNDED_TUTOR_SYSTEM prompt and at line 75 a _AFM_MAX_CHUNKS=4 discipline knob. These were added precisely because someone already tried to make the existing schema work for AFM. They didn't fix the structured-output gap. The brief at line 89-94 documents three structural deltas (submit_grounded_answer wrapper key, answer vs summary, flat supported_spans vs nested claims[].citations[]) that a system-prompt change cannot reach. Option 1's "documented limitation" is documenting a problem that the codebase has already attempted to paper over and failed. Each future contributor reading the PR will assume someone has it in hand. No one does.

Second-order cost: option 1 freezes the architectural choice. The brief at line 104-110 names three architectural paths (A: branch in tutor.py, B: normalize in AFMClient, C: two-tier schema). The founder leans toward C. Shipping a PR that says "AFM works but doesn't produce citations" inscribes the failure mode into the public commit history before C ships. When C does ship (Phase 4.5), the changelog will need a "now actually works" entry, which is the worst kind of release note. It signals to the only audience that matters in a pre-launch product (the founder's future self and a possible first round of investors) that the team ships broken things and documents them rather than finishing them.

Strategic erosion: brand damage compounds at zero-user scale. At pre-launch with zero users, every public artifact is high-signal. A first-impression PR titled "AFM provider with known citation gap" is read by anyone evaluating the project later (a future hire, an investor, an acquirer, the founder's own confidence). The cost of shipping a half-finished thing scales inversely with audience size. With one user, broken features compound brand decay maximally. The brief at line 142 names "taste-driven craft is a moat" as a constraint; option 1 spends moat for nothing.

The dominant alternative is option 3. AFM commits are on main. The free tier currently runs on Claude (per brief line 132, "I could test demand TODAY with Claude as the free-tier backend"). The 18 study-group seats times 50 questions per month at Sonnet's API price is a negligible monthly bill, well under 30 dollars. The 30-day customer test produces signal that no engineering can produce. The marginal value of option 1's 30 minutes against option 3's 30 minutes of sending three DMs is not close. One produces zero new information; the other produces the single highest-EV data point available in the next 30 days.

## What the proponent will say to this

The proponent will argue that option 1 is cheap insurance: 30 minutes locks in the architectural state, lets the founder stop context-switching on AFM, and clears the working tree for either option 2 or option 3. They will say "free optionality" and "low downside." They will frame the PR as a checkpoint, not a release, and argue that the citation gap is honestly disclosed so no one is misled.

## Why that rebuttal still fails

Because the working tree clearing has already happened in main (d867af74 and 9611e2bf are merged), the option 1 work isn't a checkpoint, it's a redundant ceremony. And "honestly disclosed" is the wrong frame: the disclosure is not about audience honesty, it is about closing the founder's open psychological loop. A 30-day customer test closes that loop with real information; a documented-gap PR closes it with theatre. Option 3 dominates on every axis option 1 was supposed to win on.

## What I would do instead

1. Send the three study-group recruitment DMs in the next 60 minutes. Use Claude Sonnet as the free-tier backend for the test cohort; absorb the maybe-30-dollars-per-month API spend as a customer development line item, not engineering.
2. Park Phase 4.5 behind a kill criterion: if the 3-study-group test surfaces "free tier cost is a blocker to adoption" within 30 days, schedule Phase 4.5 then with real evidence. If the test surfaces "students don't even want this," AFM Phase 4.5 was waste avoided.
3. Delete or archive docs/plans/afm-runbook-2026-05-10.md and replace it with a one-line entry in TODOS.md: "AFM Phase 4.5 deferred pending 3-study-group test results." Reduces future-Claude confusion about an already-merged feature.
```

## Synthesizer verdict

```
# Synthesizer Verdict: Ship AFM Pass 1 honestly on its own branch with the citation gap documented, then pivot.

## What is actually being decided

Should the founder spend 30 minutes performing a runbook-driven branch-and-PR ceremony for AFM Pass 1 before sending the customer dev DMs, or should the founder skip that ceremony entirely and go straight to the DMs because the underlying work is already merged?

## The crux

The proposal's load-bearing premise is that the runbook describes uncommitted work that needs a branch-stage-commit-push sequence to "close the loop" tonight. The adversary verified, and I re-verified via git log, that the AFM Pass 1 commits (d867af74, 9611e2bf) and four subsequent hardening commits already exist on the current branch. The runbook's opening fiction (the founder is on feat/flashcards-focus-2026-05-09 with an unstaged AFM diff) no longer matches reality. The proponent's "30 minutes to ship" is 30 minutes to perform a ceremony for work that has already shipped to the branch.

The second crux is the proposal's strategic claim: opening a PR with a "known limitation" note converts the AFM work into a marketing asset. The adversary's counter is that publishing a public artifact whose headline reads "AFM provider with citation gap" at pre-launch with zero users is brand-negative, not brand-positive. The validated moat is privacy plus citations. A PR that admits the citation half is broken inscribes the failure mode into the only artifact future evaluators will read.

## Verdict

WINNER: ADVERSARY

## Reasoning

The proponent's case rests on a factually wrong premise about the working tree state. The runbook the proponent cites describes a stash-and-stage workflow for files that are no longer unstaged because the commits already landed. The 30-minute estimate collapses to either zero minutes (nothing to do) or to a different, smaller task (cherry-pick or rebase, not stage-and-commit). The "shareable marketing surface" benefit is real in principle, but the artifact the proponent wants to ship is a PR titled with a known-gap caveat, which is the worst kind of public commit-history entry for a pre-launch product whose entire wedge depends on the very feature that doesn't yet work.

I grant the proponent's points that are non-decisive. The provider abstraction is clean, the 47 tests pass, the seam at services/tutor.py:32-91 is genuinely isolated, and bit-rot prevention is a real concern in general. None of these survive the git fact, because the commits that prevent bit-rot are already on the branch.

I reject the proponent's strongest survivable claim: that option 1 "forecloses zero options." A public PR with a documented citation gap is not zero-cost. It commits the project to an explanation in any future deck, README, or hiring conversation. The reversibility test cuts the other way: not opening a PR is more reversible than opening one with a caveat in the title.

The adversary's case maps directly onto the Carrel constraints. Solo founder. Pre-launch with zero users. Six months in. Self-funded with 9 to 12 months of runway. Customer dev signal is the only input that is currently load-bearing on the next architectural decision. The brief itself, at line 184, says the founder suspects option 3 is right. The adversary takes the founder's stated suspicion seriously and the proponent does not.

The triviality short-circuit applies on the inverse: the proponent's path is small (30 minutes) but the action is also moot (work is merged). Pick the path that produces signal, not the path that produces ceremony.

## Action plan

1. Skip the runbook ceremony entirely. The AFM Pass 1 commits are already on the branch. Verify the merge state with git log --all --oneline --grep=AFM and confirm Pass 1 + hardening commits are present (they are: d867af74, 9611e2bf, plus four follow-ups).
2. Send the three study-group recruitment DMs in the next 60 minutes. Use Claude Sonnet as the free-tier backend for the cohort. Phase 4.5 stays parked until customer signal arrives.
3. Replace the AFM runbook with a one-line entry in TODOS.md pointing at services/tutor.py:32-91 and :700-736 as the citation-gap location, and a kill criterion: "If 3-study-group test returns weak signal on citations as the wedge, archive Phase 4.5 entirely."

## Confidence

HIGH. The decision turns on a verifiable git fact that collapses the proponent's central premise, and the resulting answer (option 3) is the one the founder already suspected was right.
```

## Auditor sign-off

See [.claude/logs/audits/approved/dryrun-afm-strategy.json](../../.claude/logs/audits/approved/dryrun-afm-strategy.json) for the full JSON. Summary:

- **Verdict:** APPROVED
- **Correctness bar:** PASS
- **Trust bar:** PASS
- **Destructive bar:** PASS with CAVEAT. The synthesizer's action item 3 ("replace the AFM runbook") is ambiguous between archive and delete. Approval is conditional on archive in place. If read as delete, this crosses the destructive bar and requires re-audit.
- **Follow-ups (non-blocking):**
  1. Clarify "replace" wording in action item 3 to mean archive plus pointer, not deletion.
  2. Pin the kill criterion to the explicit date 2026-06-11.
  3. Use the decision brief's line ranges (`:30-90` and `:705-755`), not the synthesizer's (`:32-91` and `:700-736`), since the brief is the founder-authored source of truth.
  4. Set a Claude API budget cap on the cohort test accounts before sending DMs.
  5. Move the runbook to `docs/plans/parked/` with a kill-criterion README so future sessions do not accidentally resume it.

## What the autonomous routine demonstrated end-to-end

1. **Independent reasoning.** The Adversary, spawned in a fresh context with no memory of the Proponent's output, independently verified git state and surfaced the load-bearing fact that the Proponent had not checked.
2. **Bias-free synthesis.** The Synthesizer, spawned cold, picked the side whose load-bearing claim survived empirical verification. No prior conversation could have biased it toward either pole.
3. **Catch-the-cliff auditing.** The Auditor, also cold, caught a destructive-action risk in the Synthesizer's action plan that no upstream agent had flagged (the ambiguity in "replace the runbook" between archive and delete).
4. **Persisted artifact.** This ADR plus the JSON audit verdict at `.claude/logs/audits/approved/dryrun-afm-strategy.json` form an immutable record that future sessions can read without re-running the debate.

## Where to go from here

- Implementer-agent action plan, with the auditor's caveats applied:
  - Action 1: archive `docs/plans/afm-runbook-2026-05-10.md` to `docs/plans/parked/afm-runbook-2026-05-10.md` with a kill-criterion README at `docs/plans/parked/README.md`.
  - Action 2: update `TODOS.md` with the citation-gap pointer at `services/tutor.py:30-90` and `:705-755` plus the dated kill criterion.
  - Action 3: send the three study-group recruitment DMs. Confirm Claude API budget cap is set before sending.
- Halt condition: if the founder wants to revisit Phase 4.5 before 2026-06-11, halt the autonomous routine and re-debate.
