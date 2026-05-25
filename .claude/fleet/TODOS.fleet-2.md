# Slot 2 — adaptive ingestion concurrency (re-tasked 2026-05-25)

**History.** Original brief was "cross-platform memory-pressure fallback" — a 1-day swap of an existing macOS-only `MemoryPressure.is_safe_to_start_worker()` helper to add a psutil-based fallback for Linux. T1 grep proved the helper does not exist anywhere outside `.venv/`; the 2026-05-14 eng-review item was forward-looking. The debate routine (proponent/adversary/synthesizer, fresh-context spawns) ruled Option C with HIGH confidence: write the consumer-design plan first, then derive the helper API from concrete consumers. Verdict + reasoning: `docs/decisions/0005-cross-platform-memory-pressure-helper.md`. Original plan preserved (SUPERSEDED banner) at `docs/plans/cross-platform-memory-pressure-fallback.md`.

**Owns subtree:** `services/ingestion/memory_pressure.py` (new file, but only after consumer design), `services/jobs.py` (one of the two consumer-pool candidates), `script/reingest_all.py` (the other consumer-pool candidate), associated tests, one CI matrix tweak.

**Stays out of:** `services/retrieval/`, `services/tutor.py`, `evals/`, `ai/`. Unchanged from the original brief.

**Source:** the synthesizer verdict in `docs/decisions/0005-cross-platform-memory-pressure-helper.md`. The 2026-05-14 eng-review intent (cross-platform-aware adaptive concurrency for the ingestion path) is preserved; the path to it now leads through consumer design first.

## Tasks

- [x] T1: Write `docs/plans/cross-platform-memory-pressure-fallback.md`, run proponent/adversary/synthesizer routine, persist ADR `0005`. Verdict: SUPERSEDED, pivot to consumer-design-first per ADR 0005. **Status:** done — PR #69 (squashed onto main 2026-05-25).

- [x] T1-redux: Write `docs/plans/adaptive-ingestion-concurrency.md` covering consumer-pool analysis, derived helper API, sub-PR decomposition. Run proponent/adversary/synthesizer routine. **Status:** done 2026-05-25 — plan written, debate ran, **verdict: Position A (reingest_all-first, count-primary public API) with MEDIUM confidence, 5 mandatory plan adjustments applied** (see `docs/decisions/0007-adaptive-ingestion-first-consumer.md`). PR pending on branch `slot-2/adaptive-ingestion-concurrency-plan`.

- [x] T2-redux: Sub-PR 1 — `services/ingestion/memory_pressure.py` (helper module per plan §3.1 / ADR 0007 Consequence 1), `script/reingest_all.py` wiring (sentinel default; explicit operator value overrides), 24 tests at `tests/test_memory_pressure.py` (7 above the planned 17, covering end-to-end macOS happy path + module-import-without-psutil + env-override precedence), `psutil>=5.9,<7.0` in `requirements-dev.txt`, canonical verify chain extended to include the new module. **Status:** done 2026-05-25 — bundled with T3-redux into PR #80, squash commit `a73180d8`, rated 90/100 (structural pre-merge ceiling on em-dash in commit `0109a985` body; closed at squash via clean `--body-file` per prior-auditor counter-proposal at `.claude/logs/audits/rejected/ebeb5a1f6e5e34b5.json`, matching the T04 precedent in project-root `AUTONOMOUS_WORK_PLAN.md`). **Slot-coupling per ADR 0007:** satisfied — T3-redux landed in the same squash.

- [x] T3-redux: Sub-PR 2 — landed 2026-05-25 in squash commit `a73180d8` on main (bundled into PR #80 alongside T2-redux per ADR 0007 slot-coupling constraint). `CARREL_MEMORY_HEADROOM_MB` and `CARREL_MEMORY_MAX_SWAP_PCT` env overrides live with explicit-arg > env > static-default precedence. Opt-in `tests/integration/test_memory_pressure_macos.py` gated on `sys.platform=='darwin'` AND `CARREL_RUN_MEMORY_PRESSURE_INTEGRATION=1`. Empirics note at `docs/notes/2026-05-25-memory-pressure-empirics.md` carries row 1 (M3 dev machine, cell_division.pdf, recommended=1 under 92.9% swap pressure, peak_RSS_per_worker=446 MB, per-worker delta=367 MB) in the mandatory `(snapshot, recommended_count, peak_RSS_per_worker)` format. 1480-page-PDF row and multi-worker row surfaced as operator follow-ups (worktree isolation blocks the live-DB pass from slot-2 routine). Kill condition NOT triggered: row 1's per-worker delta (367 MB) sits inside the 512 MB threshold's safety margin, not >2x outside.

- [x] T4-redux: Sub-PR 3 — `ubuntu-latest` GitHub Actions matrix entry running `tests/test_memory_pressure.py` with `CARREL_FORCE_PSUTIL_MEMORY=1`. **Status:** done 2026-05-25 — branch `slot-2/ubuntu-ci-matrix` off main `a73180d8`. Adds blocking `memory-pressure-ubuntu` job to `.github/workflows/ci.yml` (job-level `env: CARREL_FORCE_PSUTIL_MEMORY: "1"` forces psutil dispatcher branch). README §Verify-chain gains a one-line note about the new matrix entry. macOS-latest `swift-build` job unchanged. psutil stays in `requirements-dev.txt` only (not runtime requirements.txt) per plan §5 T4 guard.

## Independence assertion

Unchanged: if a sub-PR finds itself needing to edit `services/retrieval/`, `services/tutor.py`, `evals/`, or anything under `ai/`, STOP. Document the collision in `.claude/fleet/collisions.md` (create if missing) and halt this slot for operator review.

## Note on consumer pool candidates

If the operator prefers to re-task the slot away from this work entirely (Option B from ADR 0005), the slot-2-compatible alternatives surfaced in the eng review are:
- `afm-ingestion-compatibility.md` — needs AFM lane work to be in flight to make sense; AFM made optional in PR #66 so partially blocked.
- `sqlite-write-lock-during-ingestion` (fix #3 only: bounded chunk-insert transactions in `services/ingestion/orchestrator.py` or `services/jobs.py`). Fix #1 and #2 from that issue touch `services/tutor.py` and are OUT of slot 2's stays-out-of subtree.

Operator triggers the re-task by editing this file's T1-redux to point at one of the above.
