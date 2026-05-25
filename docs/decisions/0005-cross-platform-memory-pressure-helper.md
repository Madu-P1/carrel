# 0005 — Cross-platform memory-pressure helper: defer standalone helper, write consumer-design plan first

**Status:** Accepted
**Date:** 2026-05-25
**Deciders:** /carrel-build autonomous loop (proponent + adversary + synthesizer fresh-context spawns); fleet slot 2.
**Supersedes:** none (initial entry for this concern).
**Superseded by:** none.

## Context

The 2026-05-14 ingestion-robustness eng review surfaced a backlog row at `TODOS.md` named `cross-platform-memory-pressure-fallback.md`. The row's premise: a `MemoryPressure.is_safe_to_start_worker()` helper exists in the tree calling `vm_stat` + `sysctl vm.swapusage`, and it needs a psutil-based fallback for the future Linux port. The row was "wrapped exactly so this fallback is a 1-day swap."

Fleet slot 2 picked up this row on 2026-05-25 with the brief at `.claude/fleet/TODOS.fleet-2.md`. Slot 2's T1 was to locate the helper, write the cross-platform plan, and run the proponent/adversary/synthesizer routine. T2/T3/T4 were the sub-PR decomposition (extract, add psutil dispatcher, CI matrix).

**Premise correction.** A 2026-05-25 code search proved the helper does not exist anywhere outside `.venv/`. No `memory_pressure.py`, no `MemoryPressure` symbol, no `vm_stat` shellout, no `psutil` import in application code. The 2026-05-14 eng-review item was forward-looking; it anticipated a B+C-lite adaptive-concurrency redesign that never landed in the form the eng review imagined.

The plan author (this loop) drafted `docs/plans/cross-platform-memory-pressure-fallback.md` with the premise correction up front and reframed the work as net-new creation of the helper, no consumers wired, three sub-PRs as planned. The plan went to debate per the slot brief mandate.

## Options considered

- **Option A:** Build the helper as the reframed plan describes — public API `is_safe_to_start_worker(*, min_free_mb=512, max_swap_used_pct=75.0) -> tuple[bool, MemorySnapshot]` with `_macos_memory_snapshot()` + `_psutil_memory_snapshot()` + dispatcher. Zero consumers wired. Three sub-PRs (T2 helper, T3 dispatcher, T4 ubuntu CI matrix).

- **Option B:** Defer slot 2 entirely; surface the premise correction to operator; re-task the slot to a sibling backlog item (`afm-ingestion-compatibility.md` or `sqlite-write-lock-during-ingestion.md` — both also from the same eng review).

- **Option C:** Write `docs/plans/adaptive-ingestion-concurrency.md` first as the consumer-design plan; derive the memory-helper API from at least one concrete consumer's needs (`services/jobs.py:23` request-scoped pool OR `script/reingest_all.py:163` batch pool); land helper + first consumer as one coherent pair under that new plan's sub-PR decomposition.

## Decision

**Option C, with Option B as acceptable fallback if operator prefers to re-task the slot.**

## Reasoning

Proponent + adversary transcripts archived at `/tmp/proponent-transcript.md` and `/tmp/adversary-transcript.md` (the fleet routine's session-local debate scratch). Synthesizer ruled in favor of the adversary with HIGH confidence.

The crux: **can a public API be designed correctly without a real caller in hand?** The proponent said yes because the eng review's "capture cross-platform shape before the first caller anchors macOS-only" framing makes the helper a captured architectural decision, not speculative generality. The adversary said no, with one decisive concrete point: the two real worker pools (`services/jobs.py:23` FastAPI request-scoped fixed-2 ThreadPoolExecutor, and `script/reingest_all.py:163` batch ThreadPoolExecutor with `--concurrency` flag) have materially different needs. The first wants a non-blocking async check; the second wants a `recommended_worker_count(*, max_workers)` companion (the plan's own §9 open question #3 admits this). A binary `is_safe_to_start_worker` predicate guessed without a caller will be the wrong shape for at least one of them.

The adversary's point survives all proponent rebuttals:

- "Capture now or it calcifies" assumes there is an existing macOS-only artifact for future callers to couple to. With no helper and no callers today, nothing calcifies. The eng-review item's risk only re-emerges if a first consumer ships with `subprocess.run(["vm_stat"])` inline — and no such PR is in flight.
- "Three bounded sub-PRs, ~550 LoC total, zero behavior change" is honest but does not address the API-shape problem. A well-tested implementation of the wrong API shape is still the wrong API shape.
- "Acceptance criterion is `no existing test regresses`" is tautological for a callerless utility (the rater rubric flags this; criterion D / E penalize speculative scaffolding with self-patching tests).

Option C preserves the cross-platform intent the operator approved on 2026-05-14 while letting consumer design lead the helper API. It does not lose Linux-portability — Linux-portability is lost only when a consumer ships first with inline shellouts, which is not happening.

Option C is preferred over Option B because the operator clearly wants this surface eventually (the eng-review item is sincere). Halting outright without a forward path costs context. Writing the consumer plan first preserves momentum on the right thing.

## Consequences

1. **Stop sub-PR decomposition T2/T3/T4 of the current slot brief.** Do not create `services/ingestion/memory_pressure.py` until the consumer-design plan lands and runs its own debate routine.

2. **Mark `docs/plans/cross-platform-memory-pressure-fallback.md` as SUPERSEDED** with a header banner pointing at this ADR. The plan content stays — it remains useful as raw material for the consumer-design plan (the §2 macOS shellout semantics, §3 psutil gaps, §4 dispatch shape are all directly reusable).

3. **Rewrite `.claude/fleet/TODOS.fleet-2.md`** so T1's deliverable is the new combined plan `docs/plans/adaptive-ingestion-concurrency.md`, and T2/T3/T4 are re-specified by that plan after its own debate.

4. **Operator follow-up.** Append a line to `.claude/logs/operator-followups.jsonl` so the operator sees the slot pivoted via synthesizer verdict, not silently rewrote scope.

5. **No code changes ship from this T1 turn.** The deliverables are: this ADR, the SUPERSEDED banner on the plan, the rewritten slot brief, the operator follow-up entry. T1 is then complete and the slot proceeds to drafting the new combined plan.

6. **The new combined plan must name at least one concrete consumer** (the synthesizer's decisive concern). Acceptable first consumers: (a) `script/reingest_all.py` batch loop with a derived `recommended_worker_count` API, or (b) `services/jobs.py` request-scoped pool with a derived async-safe check. The new plan picks one and derives the API from there.

## References

- Plan being superseded: `docs/plans/cross-platform-memory-pressure-fallback.md`
- Slot brief: `.claude/fleet/TODOS.fleet-2.md`
- Source backlog row: `TODOS.md` (main branch version, "Active backlog (from … ingestion-robustness eng review, approved 2026-05-14)")
- Worker pools considered: `services/jobs.py:23`, `script/reingest_all.py:163`
- Adjacent eng-review issue: `docs/issues/2026-05-14-sqlite-write-lock-during-ingestion.md`
- Debate transcripts: `/tmp/proponent-transcript.md`, `/tmp/adversary-transcript.md` (session-local scratch; archived inline into this ADR's body if those paths roll over).

## Verdict summary

VERDICT: C
RATIONALE: Helper API is guessed without a real caller; plan's own §9 admits the binary-predicate vs worker-count shape is unresolved; consumer design must precede helper design.
NEXT_ACTION: Write `docs/plans/adaptive-ingestion-concurrency.md` next (slot 2 T1 re-tasked), naming at least one concrete consumer, then re-run the debate routine on that plan.
