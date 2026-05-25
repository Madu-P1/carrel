# Slot 2 — adaptive ingestion concurrency (re-tasked 2026-05-25)

**History.** Original brief was "cross-platform memory-pressure fallback" — a 1-day swap of an existing macOS-only `MemoryPressure.is_safe_to_start_worker()` helper to add a psutil-based fallback for Linux. T1 grep proved the helper does not exist anywhere outside `.venv/`; the 2026-05-14 eng-review item was forward-looking. The debate routine (proponent/adversary/synthesizer, fresh-context spawns) ruled Option C with HIGH confidence: write the consumer-design plan first, then derive the helper API from concrete consumers. Verdict + reasoning: `docs/decisions/0005-cross-platform-memory-pressure-helper.md`. Original plan preserved (SUPERSEDED banner) at `docs/plans/cross-platform-memory-pressure-fallback.md`.

**Owns subtree:** `services/ingestion/memory_pressure.py` (new file, but only after consumer design), `services/jobs.py` (one of the two consumer-pool candidates), `script/reingest_all.py` (the other consumer-pool candidate), associated tests, one CI matrix tweak.

**Stays out of:** `services/retrieval/`, `services/tutor.py`, `evals/`, `ai/`. Unchanged from the original brief.

**Source:** the synthesizer verdict in `docs/decisions/0005-cross-platform-memory-pressure-helper.md`. The 2026-05-14 eng-review intent (cross-platform-aware adaptive concurrency for the ingestion path) is preserved; the path to it now leads through consumer design first.

## Tasks

- [x] T1: Write `docs/plans/cross-platform-memory-pressure-fallback.md`, run proponent/adversary/synthesizer routine, persist ADR `0005`. Verdict: SUPERSEDED, pivot to consumer-design-first per ADR 0005. **Status:** done — commit + PR TBD on `docs/memory-pressure-fallback-plan` branch.

- [ ] T1-redux: Write `docs/plans/adaptive-ingestion-concurrency.md` covering: (a) the two consumer pools (`services/jobs.py:23` request-scoped fixed-2 `ThreadPoolExecutor`; `script/reingest_all.py:163` batch `ThreadPoolExecutor` with `--concurrency` flag), (b) which one becomes the FIRST consumer of the memory-pressure helper and why, (c) the derived helper API shape — binary predicate vs `recommended_worker_count` companion vs async-safe non-blocking check — chosen from the first consumer's actual needs, (d) sub-PR decomposition for helper + first consumer landing as one coherent pair, (e) keep cross-platform support (macOS shellouts + psutil fallback + ubuntu CI matrix) per the original plan's §2-§5 (reused as raw material). Run the proponent/adversary/synthesizer routine on the new plan.

- [ ] T2-redux: Sub-PR 1 per the new plan — typically the helper module with API derived from the chosen consumer. Specific shape to be set by the new plan.

- [ ] T3-redux: Sub-PR 2 per the new plan — typically the first consumer wired through the helper.

- [ ] T4-redux: Sub-PR 3 per the new plan — typically the ubuntu CI matrix entry (reused unchanged from the original brief).

## Independence assertion

Unchanged: if a sub-PR finds itself needing to edit `services/retrieval/`, `services/tutor.py`, `evals/`, or anything under `ai/`, STOP. Document the collision in `.claude/fleet/collisions.md` (create if missing) and halt this slot for operator review.

## Note on consumer pool candidates

If the operator prefers to re-task the slot away from this work entirely (Option B from ADR 0005), the slot-2-compatible alternatives surfaced in the eng review are:
- `afm-ingestion-compatibility.md` — needs AFM lane work to be in flight to make sense; AFM made optional in PR #66 so partially blocked.
- `sqlite-write-lock-during-ingestion` (fix #3 only: bounded chunk-insert transactions in `services/ingestion/orchestrator.py` or `services/jobs.py`). Fix #1 and #2 from that issue touch `services/tutor.py` and are OUT of slot 2's stays-out-of subtree.

Operator triggers the re-task by editing this file's T1-redux to point at one of the above.
