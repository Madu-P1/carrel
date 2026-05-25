# Slot 1 — Gate 1: structural-citation chunks-path heuristic

**Owns subtree:** `services/retrieval/` (chunks path), citation-resolve hooks in `services/tutor.py`, `tests/test_retrieval_*`, `tests/test_tutor_grounded*`.

**Stays out of:** anything under `services/ingestion/`, anything under `evals/` that isn't a smoke harness, `ai/afm_*`, Swift sidecars. Slot 2 owns ingestion.

**Source:** TODOS.md → "Active backlog (from structural-citation gate, Gate 0 shipped 2026-05-22)" → Gate 1 row. Plan doc does not exist yet — first task is to write it.

## Tasks

- [x] T1: Plan doc + ADR 0004. **Done — PR #70, squash-merged on `main`.**

- [x] T2.0: Eval-harness instrumentation (sub-PR inserted between T1 and T2 after ADR 0004 quote-granularity pivot). Counts structural shapes at the chunks-branch citation-resolve site without changing runtime behavior. **Done — PR #71, squash commit `8d14c119` on `main`, 2026-05-25. Baseline at `evals/reports/structural-citation-baseline-2026-05-25.md` (0 / 36 on smoke corpus; kill condition triggered).**

- [x] T2: Runtime heading + bare-reference filter at `services/tutor.py::_resolve_grounded_answer`, behind `RETRIEVAL_CHUNKS_HEURISTIC=true`. **Done — bundled with T3 in PR #77 cherry-pick (closed PRs #74 + #75), squash commit `0fa06b32` on `main`, 2026-05-25.**

- [x] T3: Banner-shape tightening + 4 new bare-reference patterns + section-numbered length-cap bypass. **Done — bundled with T2 in PR #77, squash commit `0fa06b32` on `main`, 2026-05-25. Report at `evals/reports/structural-citation-t3-2026-05-25.md`.**

- [x] T4: Flip `RETRIEVAL_CHUNKS_HEURISTIC` default to `true`. Report at `evals/reports/compare-chunks-heuristic-2026-05-25.md`. **Done — PR pending on `slot1/gate-1-t4-default-on-flip`. Vacuous smoke-corpus comparison; shipped on three safety arguments per the T4 report. The labeled `evals/cases/structural-citation.jsonl` slice remains an open operator-followup and is not a T4 precondition.**

## Status — Gate 1 closed 2026-05-25

All four sub-tasks shipped on `main`. The plan's kill condition triggered at T2.0 (smoke-corpus structural_citation_rate = 0); the routine shipped T3 and T4 with pivoted acceptances per the three reports above. Gate 2 (semantic entailment via Selene Mini) is the next gate; it sits behind both Gate 0 and Gate 1 and is owned by a separate plan, not by slot 1.

## Independence assertion

If a sub-PR finds itself needing to edit `services/ingestion/`, `services/extraction/`, or any `evals/` runner code, STOP. That's slot 2's land or it's net-new coordination work. Document the collision in `.claude/fleet/collisions.md` (create if missing) and halt this slot for operator review.

Smoke-shaped additions under `evals/cases/` and report files under `evals/reports/` remain in slot 1 scope (per the T2.0 amendment precedent at `.claude/logs/operator-followups.jsonl` 2026-05-25T02:55:01Z).
