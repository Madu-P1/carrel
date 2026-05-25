# Slot 2 — adaptive ingestion concurrency (re-tasked 2026-05-25)

**History.** Original brief was "cross-platform memory-pressure fallback" — a 1-day swap of an existing macOS-only `MemoryPressure.is_safe_to_start_worker()` helper to add a psutil-based fallback for Linux. T1 grep proved the helper does not exist anywhere outside `.venv/`; the 2026-05-14 eng-review item was forward-looking. The debate routine (proponent/adversary/synthesizer, fresh-context spawns) ruled Option C with HIGH confidence: write the consumer-design plan first, then derive the helper API from concrete consumers. Verdict + reasoning: `docs/decisions/0005-cross-platform-memory-pressure-helper.md`. Original plan preserved (SUPERSEDED banner) at `docs/plans/cross-platform-memory-pressure-fallback.md`.

**Owns subtree:** `services/ingestion/memory_pressure.py` (new file, but only after consumer design), `services/jobs.py` (one of the two consumer-pool candidates), `script/reingest_all.py` (the other consumer-pool candidate), associated tests, one CI matrix tweak.

**Stays out of:** `services/retrieval/`, `services/tutor.py`, `evals/`, `ai/`. Unchanged from the original brief.

**Source:** the synthesizer verdict in `docs/decisions/0005-cross-platform-memory-pressure-helper.md`. The 2026-05-14 eng-review intent (cross-platform-aware adaptive concurrency for the ingestion path) is preserved; the path to it now leads through consumer design first.

## Tasks

- [x] T1: Write `docs/plans/cross-platform-memory-pressure-fallback.md`, run proponent/adversary/synthesizer routine, persist ADR `0005`. Verdict: SUPERSEDED, pivot to consumer-design-first per ADR 0005. **Status:** done — PR #69 (squashed onto main 2026-05-25).

- [x] T1-redux: Write `docs/plans/adaptive-ingestion-concurrency.md` covering consumer-pool analysis, derived helper API, sub-PR decomposition. Run proponent/adversary/synthesizer routine. **Status:** done 2026-05-25 — plan written, debate ran, **verdict: Position A (reingest_all-first, count-primary public API) with MEDIUM confidence, 5 mandatory plan adjustments applied** (see `docs/decisions/0007-adaptive-ingestion-first-consumer.md`). PR pending on branch `slot-2/adaptive-ingestion-concurrency-plan`.

- [ ] T2-redux: Sub-PR 1 — Create `services/ingestion/memory_pressure.py` (TypedDict + macOS shellout parsers + psutil dispatcher + `recommended_worker_count` primary + `is_safe_to_start_worker` 10-line wrapper). Wire `script/reingest_all.py` to consult the helper when `--concurrency` is omitted; explicit operator value overrides. ~17 tests. Add psutil to `requirements-dev.txt`. **Slot-coupling constraint per ADR 0007:** T3-redux must ship within the same slot; if runway can't accommodate both, do NOT start T2-redux.

- [ ] T3-redux: Sub-PR 2 — 1480-page-PDF empirical pass with mandatory record format `(snapshot, recommended_count, peak_RSS_per_worker)`. Add `CARREL_MEMORY_HEADROOM_MB` and `CARREL_MEMORY_MAX_SWAP_PCT` env overrides. Write empirics note. Land opt-in macOS integration test. **Kill condition per ADR 0007:** >2x miss between recommended and tolerated count seeds a jobs.py-first follow-up debate (NOT a silent revert).

- [ ] T4-redux: Sub-PR 3 — `ubuntu-latest` GitHub Actions matrix entry running `tests/test_memory_pressure.py` with `CARREL_FORCE_PSUTIL_MEMORY=1`. (Unchanged from SUPERSEDED §5 T4.)

## Independence assertion

Unchanged: if a sub-PR finds itself needing to edit `services/retrieval/`, `services/tutor.py`, `evals/`, or anything under `ai/`, STOP. Document the collision in `.claude/fleet/collisions.md` (create if missing) and halt this slot for operator review.

## Note on consumer pool candidates

If the operator prefers to re-task the slot away from this work entirely (Option B from ADR 0005), the slot-2-compatible alternatives surfaced in the eng review are:
- `afm-ingestion-compatibility.md` — needs AFM lane work to be in flight to make sense; AFM made optional in PR #66 so partially blocked.
- `sqlite-write-lock-during-ingestion` (fix #3 only: bounded chunk-insert transactions in `services/ingestion/orchestrator.py` or `services/jobs.py`). Fix #1 and #2 from that issue touch `services/tutor.py` and are OUT of slot 2's stays-out-of subtree.

Operator triggers the re-task by editing this file's T1-redux to point at one of the above.
