# Chunks-path structural-citation baseline (2026-05-25)

Gate 1 T2.0 acceptance artifact. Establishes the chunks-path
baseline measurement of `structural_citation_rate` against which the
T4 default-on flip's >=30% relative-drop gate will be evaluated.

## Result

```
suite:                smoke (the canonical full-mode eval set)
mode:                 full
RETRIEVAL_USE_NODES:  false  (chunks branch)
total cases:          15
quote_total:          36
structural_citation_count: 0
structural_citation_rate:  0.0
groundedness@8:       0.8667 (13/15)
quote_validity:       1.0    (36/36)
citation_precision:   0.7333
citation_recall:      0.8
latency_p50_ms:       4243.91
latency_p95_ms:       7280.68
model:                claude-sonnet-4-6
ran:                  2026-05-25T02:48:14Z (UTC)
report json:          (tee'd from /tmp/eval-baseline-t2.0/, not committed)
```

Verify metric source:
`evals/run_evals.py:481-485` (the new T2.0 instrumentation site) ran
on every one of the 36 cited quotes the smoke corpus produced. Zero
matched the structural-shape predicate in
`services/retrieval/quote_heuristics.py::is_structural_quote`.

## What this baseline says

The instrumentation works. The shape detector fires on the right
inputs (39 unit tests pin its behavior). On the current smoke
corpus, no LLM-cited quote shape-matched a heading, bare reference,
or banner.

## What this baseline does NOT say

It does NOT say the chunks path is free of structural-citation bugs
in production. The smoke corpus is four small pedagogical sources
(`photosynthesis.md`, `cell_division.md`, `cell_division.pdf`,
`README.md`) whose chunks rarely include answer-empty heading lines
in retrievable positions. Real-user libraries with multi-chapter
PDFs (textbooks, papers) carry many more heading-adjacent body
chunks, which is the case Gate 1 is designed to fix.

## Implication for T4's acceptance gate

The slot-1 TODOS T4 acceptance says
"`structural_citation_rate` drops >=30% from the post-T2.0 baseline".
With baseline = 0.0, that gate is unmeasurable on the smoke corpus.
Two paths forward (the operator picks):

1. **Land the labeled `evals/cases/structural-citation.jsonl` slice
   (operator-followup from ADR 0004) before T4.** The slice would
   include 20-30 hand-built traps that the LLM is likely to fall
   into, producing a non-zero baseline. T4's drop gate then
   measures the actual improvement.
2. **Re-anchor T4 to absolute structural_citation_count instead of
   a relative drop.** Acceptance becomes "with the runtime filter
   on, structural_citation_count on a labeled trap suite drops to 0
   or near-zero," which is a stronger claim but requires the same
   labeled slice.

Either way, the labeled slice goes from a quality-of-measurement
bonus to a hard precondition for T4. The slot-1 charter
(`fleet/slot-1` branch, `TODOS.md` "Tasks" section) should reflect
this upgrade against the T4 entry before T4 starts; the slice was
previously framed as `blocking: no` at the T1 plan stage in
ADR 0004 (`docs/decisions/0004-gate-1-chunks-path-structural-citation-heuristic.md`),
explicitly noted as a quality bonus rather than a hard precondition.
This baseline reframes it.

## Implication for T2 (the runtime filter, next PR)

T2's acceptance pivots from "the rate drops" to "the rate IS the
measurement-side count, applied at the resolve layer too, with the
same single source of truth." Concretely: T2's acceptance text
should say "with `RETRIEVAL_CHUNKS_HEURISTIC=true`, no cited quote
that the eval harness would now count as structural reaches the
final answer's citation list" rather than measuring against the
T2.0 baseline (which is 0).

T2 lands as planned. Its acceptance just refocuses on internal
consistency between the eval-harness counter and the runtime filter,
not on a baseline-drop measurement.

## Per-case structural detail

(Per-case structural_citation_count was zero across all 15 cases;
nothing to enumerate. The full run's JSON / markdown reports were
emitted to a local temp directory and are not committed; rerun via
the command below to regenerate.)

## Reproduce

```bash
RETRIEVAL_USE_NODES=false ./.venv/bin/python -m evals.run_evals \
  --mode full --suite smoke --report-dir /tmp/eval-baseline-t2.0/
```

Expected output mirrors the Result block above. Re-run will produce
a fresh `<UTC-ts>.json` and `<UTC-ts>.md` in the report dir.
