# Slot 1 — Gate 1: structural-citation chunks-path heuristic

**Owns subtree:** `services/retrieval/` (chunks path), citation-resolve hooks in `services/tutor.py`, `tests/test_retrieval_*`, `tests/test_tutor_grounded*`.

**Stays out of:** anything under `services/ingestion/`, anything under `evals/` that isn't a smoke harness, `ai/afm_*`, Swift sidecars. Slot 2 owns ingestion.

**Source:** TODOS.md → "Active backlog (from structural-citation gate, Gate 0 shipped 2026-05-22)" → Gate 1 row. Plan doc does not exist yet — first task is to write it.

## Tasks

- [ ] T1: Write `docs/plans/structural-citation-gate-1-chunks-heuristic.md`. Cover: (a) why the chunks path can't use `node_type` (no typed AST), (b) the three structural signals — line length, finite-verb presence, bare-reference detection — and the threshold rationale per signal, (c) where the heuristic plugs in inside the citation-resolve path, (d) eval acceptance: chunks-path `groundedness@8` must not regress vs current baseline; structural-citation false-cite rate on a labeled eval slice must drop by ≥30%. Run the proponent/adversary/synthesizer routine on the plan before the first sub-PR.

- [ ] T2: Sub-PR 1 — heading-line heuristic only. Detect chunk windows whose central line is `<` heading-length cap (configurable, default 80 chars), lacks a finite verb (POS-tag or pattern proxy), and contains no other answer-bearing line. Mark as heading; skip as citation source. Lands behind `RETRIEVAL_CHUNKS_HEURISTIC=true`. Test: new fixture chunk with a heading line, expect zero citations.

- [ ] T3: Sub-PR 2 — low-information body filter. Detect chunk windows that ARE typed `body` but consist of bare references / page numbers / fragments. Drop as citation source unless no better candidate exists in the typed path. Lands behind the same env flag.

- [ ] T4: Sub-PR 3 — flip `RETRIEVAL_CHUNKS_HEURISTIC` to default-on. Eval comparison report at `evals/reports/compare-chunks-heuristic-{before,after}.md`. Acceptance gate per T1.

## Independence assertion

If a sub-PR finds itself needing to edit `services/ingestion/`, `services/extraction/`, or any `evals/` runner code, STOP. That's slot 2's land or it's net-new coordination work. Document the collision in `.claude/fleet/collisions.md` (create if missing) and halt this slot for operator review.
