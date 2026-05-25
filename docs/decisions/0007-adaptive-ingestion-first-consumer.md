# 0007 — Adaptive ingestion concurrency: pick `script/reingest_all.py` as the FIRST consumer of the memory-pressure helper, with count-primary public API

**Status:** Accepted
**Date:** 2026-05-25
**Deciders:** /carrel-build autonomous loop (proponent + adversary + synthesizer fresh-context spawns); fleet slot 2.
**Supersedes:** none (downstream from ADR 0005).
**Superseded by:** none.

## Context

ADR 0005 ruled (HIGH confidence) that the memory-pressure helper's public
API cannot be designed correctly without a real caller in hand, and that
slot 2's T1 should be rewritten to a consumer-design-first plan. That plan
landed at `docs/plans/adaptive-ingestion-concurrency.md` on 2026-05-25.
The plan named two real candidates from Consequence 6 of ADR 0005:

- **(a)** `script/reingest_all.py` batch loop, deriving a
  `recommended_worker_count` API (count semantics, fires once at pool
  construction).
- **(b)** `services/jobs.py` request-scoped pool, deriving an async-safe
  binary check (binary semantics, fires per submission).

The plan's §2.3 (proponent seed) recommended (a) with count-primary; §2.4
(adversary seed) recommended (b) with binary-primary or a third "test
fixture consumer" option. The plan went to debate.

## Options considered

- **Position A** (proponent): reingest_all-first, count-primary public API
  (`recommended_worker_count(*, max_workers, ...) -> tuple[int, MemorySnapshot]`),
  binary `is_safe_to_start_worker` shipped as a 10-line wrapper. Helper +
  first consumer ship together in T2-redux. T3-redux runs a 1480-page-PDF
  empirical pass.

- **Position B** (adversary): jobs.py-first, binary-primary public API
  (`is_safe_to_submit_now() -> bool`). Wiring lands behind
  `CARREL_JOBS_MEMORY_GATING=1` env, defaulting OFF. reingest_all wiring
  deferred until T3-redux empirics exist.

- **Third option** (adversary alternative): land the helper with no real
  consumer; satisfy ADR 0005's "at least one concrete consumer" with a
  20-line in-tree test fixture; defer both real consumers.

## Decision

**Position A wins, MEDIUM confidence, with five mandatory adjustments
applied to the plan before T2-redux begins.**

## Reasoning

Proponent + adversary transcripts archived at `/tmp/proponent-reingest-first.md`
and `/tmp/adversary-jobs-first.md` (session-local scratch). Synthesizer
verdict archived at `/tmp/synthesizer-verdict.md`. The verdict engaged six
specific tensions:

1. **Operator-knob critique** (adversary failure mode 1): `--concurrency`
   already exists, so auto-tune-on-omitted-flag is syntactic sugar. The
   synthesizer judged this critique landed but did not decide the case —
   today's actual failure mode is "operator forgets, runs default 4, dev
   machine thrashes, observation lands in status.md a week later".
   Auto-tune converts an undocumented foot-gun into a measured default
   while preserving operator override.

2. **One-shot snapshot wrong for 2-hour batches** (adversary failure mode 2):
   technically correct and the proponent does not directly rebut it.
   `ThreadPoolExecutor` cannot resize, the helper fires once, a host
   drifting into pressure mid-run gets no help. But this argues against
   pretending Position A is a full solution, not against picking it.
   Mitigation: operator-followup recording periodic-resize as future work.

3. **"Binary dressed up"** (adversary failure mode 3): real hit on the
   "strict superset" rhetoric. `count(max_workers=1) >= 1` is the binary
   question with a ceremonial `max_workers=1` attached. The synthesizer
   demanded the plan drop the "strict superset" framing. Count→binary is
   still a 10-line wrapper; binary→count requires a public-surface
   refactor. Reversibility favors A.

4. **Rollback leaves callerless helper** (adversary failure mode 4):
   cleanest direct hit on ADR 0005's governing language. If T3-redux
   empirics force a T2-redux wiring revert, the helper is callerless —
   exactly the speculative-scaffolding outcome ADR 0005 rejected. This
   is why confidence is MEDIUM not HIGH. Mitigation: T3-redux ships in
   the same slot as T2-redux; >2x miss seeds a jobs.py-first follow-up
   debate, not a silent revert.

5. **Third option's merit**: the 20-line test-fixture consumer is clever
   but dodges the question. ADR 0005 Consequence 6 enumerates only two
   acceptable first consumers by name; a fixture is not one of them.
   Accepting would relitigate the prior HIGH-confidence verdict. The
   third option also produces no empirical dataset, so the next round
   gets the same guessed thresholds. Rejected.

6. **Strategic moat point**: the adversary's "Carrel's moat is user-felt
   quality" paragraph reads rhetorically strong but the evidence cuts
   the other way. The 1480-page-PDF thrash documented in status.md
   2026-05-21 is reingest_all, not jobs.py. Proponent point 5 wins this
   exchange.

The empirical-validation surface is the deciding factor. Only the count
API can produce per-host `(snapshot, recommended_count, peak_RSS_per_worker)`
records, and that dataset is what makes the deferred jobs.py debate next
round answerable with data instead of guessed thresholds.

## Consequences

1. **T2-redux scope.** Create `services/ingestion/memory_pressure.py`
   with `recommended_worker_count` as the primary public API and
   `is_safe_to_start_worker` as a 10-line binary wrapper. Wire
   `script/reingest_all.py` to consult the helper when `--concurrency`
   is omitted; explicit operator value overrides. ~17 tests.
   Helper + first consumer ship together in one PR.

2. **T3-redux scope.** Run a 1480-page-PDF empirical pass on the dev
   machine. Mandatory record format: one row per `(host, run)` tuple
   containing `(snapshot, recommended_count, peak_RSS_per_worker)`. Add
   `CARREL_MEMORY_HEADROOM_MB` and `CARREL_MEMORY_MAX_SWAP_PCT` env
   overrides. Write the empirics note at
   `docs/notes/2026-05-XX-memory-pressure-empirics.md`. Land an
   integration test at `tests/integration/test_memory_pressure_macos.py`
   (opt-in only via `CARREL_RUN_MEMORY_PRESSURE_INTEGRATION=1`).
   **T3-redux must ship within the same slot as T2-redux** to close
   the rollback gap; if it cannot fit the runway, do not start T2-redux.

3. **T3-redux kill condition tightened.** A >2x miss between recommended
   count and tolerated count does NOT trigger a silent revert. It seeds
   a jobs.py-first follow-up debate with the empirics dataset as new
   evidence and surfaces to operator.

4. **T4-redux scope.** Ubuntu CI matrix entry; runs
   `tests/test_memory_pressure.py` with `CARREL_FORCE_PSUTIL_MEMORY=1`.

5. **Plan adjustments applied.** `docs/plans/adaptive-ingestion-concurrency.md`
   updated in-place to (a) drop "strict superset" rhetoric from §3.2,
   (b) add the slot-coupling constraint to T3-redux, (c) tighten the
   T3-redux kill condition, (d) make the empirics note's row format
   mandatory.

6. **Operator follow-ups appended** to `.claude/logs/operator-followups.jsonl`:
   (a) periodic-resize / mid-run-snapshot as future work; (b)
   `request-scoped-ingestion-backpressure.md` future plan pointer.

7. **`services/jobs.py` is explicitly deferred** to its own plan with
   its own debate. See `docs/plans/adaptive-ingestion-concurrency.md` §7
   for the four open admission-control design questions that the future
   plan must answer.

8. **No code changes ship from this T1-redux turn.** Deliverables: this
   ADR, the plan-with-five-adjustments, the operator follow-ups, the
   slot-brief status flip. T2-redux begins on a new branch off `main`
   after the plan-only PR lands.

## References

- Plan governed by this verdict: `docs/plans/adaptive-ingestion-concurrency.md`
- Upstream ADR: `docs/decisions/0005-cross-platform-memory-pressure-helper.md`
- Slot brief: `.claude/fleet/TODOS.fleet-2.md`
- Worker pools considered: `services/jobs.py:23`, `script/reingest_all.py:163`
- Adjacent deferred plan: `docs/plans/request-scoped-ingestion-backpressure.md` (not yet written; see plan §7)
- Debate transcripts: `/tmp/proponent-reingest-first.md`, `/tmp/adversary-jobs-first.md`, `/tmp/synthesizer-verdict.md`

## Verdict summary

VERDICT: A (proponent — reingest_all-first, count-primary)
CONFIDENCE: MEDIUM
NEXT_ACTION: Open plan-only PR carrying the plan-with-adjustments + this ADR + operator-followups. T2-redux begins after PR lands as the slot's next branch off `main`.
