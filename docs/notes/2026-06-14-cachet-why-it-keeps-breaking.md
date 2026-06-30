# Cachet: why it keeps hitting issues — a brief for a senior dev

Written 2026-06-14 to get outside advice. Honest, evidence-first. The ask at the
bottom is specific.

## What Cachet is (30 seconds)

A local-first, deterministic (no-LLM) verifier. You give it an AI-written summary
claim and a source document; it must say `present` / `contradiction` /
`could-not-verify` — and its whole product promise is **never a false green**
(never bless an altered/wrong claim as supported) and **never a false accusation**
(never flag a correct one). When unsure, it refuses ("could not verify"). The
engine is regex anchor-extraction (money, %, magnitude, date, duration, governing
law, polarity, citations) + a per-clause comparator + a cross-clause adjudicator.

## The symptom the founder experiences

Almost every working session surfaces a new "Cachet is broken" moment: empty
results, a missed alteration, a false flag, a correct statement reading "could not
verify." It *feels* like a system that never stabilizes.

## The reframe: three different problems wear the same costume

The single most useful thing for an advisor to know is that "Cachet keeps
breaking" is really **three unrelated problems**, and only one of them is an
engine-correctness problem.

### 1. True edge-bugs — normal, and well-handled

Every real document is a new test case. Recent examples: a European decimal
"1,2 billion" misparsed as 12 billion; bare/EUR magnitudes ("20 billion") not
extracted at all because the money regex required a `$`. These are real bugs, but
they are the *expected* drip of edge-discovery for a verification engine, and the
team handles them well: test-first fix, ~298 engine tests, and an adversarial
"red-team" battery that on its last run (2026-06-13) **held 15/15 attacks across 8
families with zero false-greens and zero false-accusations.** So the engine's
*runtime safety* — the disqualifying-failure surface — is actually sound. This is
NOT the reason it feels broken.

### 2. The semantic ceiling — not a bug, a wall

The deterministic approach has hit a problem it cannot solve without understanding
*meaning*. Example that recurs: a slide says "PBT 16%" and elsewhere "profitability
exceeding 10%." A correct claim "PBT 16%" reads "could not verify," because the
engine compares 16% against the unrelated 10% — it is **metric-blind**. It cannot
tell "different metric" (PBT vs profitability) from "an amendment" (§4 says 50%,
§9 says 40% for the same thing). It conservatively **refuses** — which is correct
and safe, but reads as noise on figure-dense documents.

This session I tried to fix exactly this ("if the claim is verbatim in one clause,
trust it"). It passed 6 new tests — and then the engine's *own* held-out
integration test failed it, because that "verbatim-trust" is the precise
"present-wins masks an amended-contract conflict" behavior the team had already
ruled out as their worst failure class. **There is no safe *deterministic* fix
here.** Telling "different metric" from "amendment" is semantic work.

### 3. A leaky dev / validation / ops loop — the real amplifier

This is what actually makes it *feel* perpetually broken, and it is the most
fixable:

- **Stale builds.** The live demo froze on old in-memory code (uvicorn loads once
  at boot); it returned *nothing* for *every* input while the on-disk engine was
  fine. The founder saw "totally broken" when the engine worked. No reload, no
  "is this current?" check.
- **Branch / worktree sprawl: 70 active worktrees, 35 cachet-ish branches.** Fixes
  land in one worktree and never reach the demo; "I fixed this, why is it still
  broken" because the fix is on a branch the running demo isn't built from. History
  shows repeated "stale branch reverts newer work" and "did not reproduce on
  current code."
- **CI exists but isn't enforced.** `ci.yml` runs ruff + the engine unittest
  suites on every push/PR, but `main` is pushed to **directly, bypassing the 4
  required status checks** (admin override). So the gate is there and ignored.
- **Validation is reactive eyeballing.** Bugs are found by the founder pasting a
  real document and looking at the result, one at a time. The systematic adversary
  battery (which is clean) is run sporadically by hand, not in CI.

## The evidence (numbers)

- Engine core: ~3,800 LOC across `anchors.py`, `contract_verify.py`,
  `deterministic_envelope.py`, `verify.py`. 21 compiled regex detectors.
- 45 commits touched the engine since 2026-05-20. The commit log reads like a
  whack-a-mole stream: "X can no longer false-green," "can no longer be accused,"
  "can no longer pass unexamined." High churn on a subtle core.
- 298 engine test functions; adversary battery 15/15 clean (zero false-greens).
- 70 git worktrees, 35 cachet branches.
- `ci.yml` present and comprehensive; main pushed directly, bypassing it.

## The honest root cause (my read, for you to challenge)

It is **not** that the engine is unsafe — the adversary results say it holds. It
is two things:

1. **Evolvability, not correctness.** The core is *safe at runtime* but *hard to
   change safely*: a subtle cross-clause adjudicator + 21 detectors + delicate
   refuse/bless rules mean every extension risks a regression (a careful pass this
   week introduced a false-green that only a held-out test caught). Ousterhout's
   point: the cost is in modification. The churn is the tell.
2. **A leaky loop around a hard problem.** An intrinsically semantic problem is
   being approached with accreting deterministic heuristics, while the dev/ops loop
   (stale builds, branch sprawl, bypassed CI, manual validation) lets fixes miss
   the demo and lets new edges be discovered one-at-a-time by the founder.

## What I'd ask a senior dev (the actual questions)

1. **Substrate.** Is "regex anchors + cross-clause adjudicator" the right
   foundation for "verify NL claims vs NL sources with a zero-false-green
   guarantee," or is the team hardening a design that's fundamentally
   under-powered for the semantic cases? When do you add a small local model vs add
   another deterministic rule?
2. **The T0/T1 line.** The recurring wall is *metric identity* (is this 16% the
   same quantity as that 10%?) and *amendment vs different-metric*. Both are
   semantic. Is the "deterministic T0 now, model T1 later" split right, or should a
   narrow model already be load-bearing for topicality?
3. **Over-refusal.** Is "could not verify" on a correct-but-figure-dense statement
   an acceptable product behavior (honest, never wrong) or a thing that must be
   solved — and if it must, is that strictly a model problem?
4. **Evolvability.** How would you make this engine *safe to extend*? Is the
   adjudicator carrying too many coupled rules; should the comparison logic be
   restructured (deeper modules, fewer interacting gates) so a change can't
   regress a far-away case?
5. **The loop.** How do you stop the stale-build / branch-sprawl / bypassed-CI
   leakage so a fix reliably reaches the demo, and make adversarial coverage
   continuous (in CI) instead of a founder eyeballing real docs?

## One-line summary for the advisor

"Our deterministic verifier is *safe* (red-team clean) but *hard to evolve* and has
hit a *semantic ceiling*; meanwhile a leaky dev/ops loop makes good code look
broken. Tell us where to invest: the architecture, the model line, or the loop."
