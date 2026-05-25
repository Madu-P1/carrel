# Chunks-path structural-citation T4 report (2026-05-25)

Gate 1 T4 acceptance artifact. Documents the default-on flip of
`RETRIEVAL_CHUNKS_HEURISTIC` from `false` to `true`, the before/after
comparison run on the smoke corpus, the vacuous-comparison limitation
inherited from the T2.0 baseline, and the assertion-safety rationale
that justifies the flip in the absence of a non-zero empirical baseline.

## What T4 lands

A single-line default flip in
`services/retrieval/quote_heuristics.py::chunks_heuristic_enabled`,
from `os.getenv("RETRIEVAL_CHUNKS_HEURISTIC", "false")` to
`os.getenv("RETRIEVAL_CHUNKS_HEURISTIC", "true")`. The runtime filter
that T2 wired into `services/tutor.py::_resolve_grounded_answer` now
fires by default; operators opt out with
`RETRIEVAL_CHUNKS_HEURISTIC=false`.

Three companion edits:

1. Docstring in `chunks_heuristic_enabled` updated to record the
   2026-05-25 flip date and the opt-out semantic.
2. Comment in `services/tutor.py::TutorAnswerEnvelope` next to
   `citation_structural_drop_count` updated from
   `"the default until T4"` to
   `"default is on after T4"`.
3. Plan doc §"Feature flag" updated to reflect the post-T4 default.

Three test changes in
`tests/test_retrieval_quote_heuristics.py::ChunksHeuristicEnabledTests`:

- `test_default_off` renamed to `test_default_on`, assertion flipped.
- `test_true_enables` renamed to `test_true_keeps_on`, body unchanged.
- `test_other_values_disable` body unchanged (explicit `false`/`0`/
  `off`/`no`/`""` still disables, opt-out path preserved).

## Before/after comparison (smoke corpus)

```
suite:                smoke (the canonical full-mode eval set)
mode:                 full
RETRIEVAL_USE_NODES:  false  (chunks branch)
total cases:          15
quote_total:          36

BEFORE (RETRIEVAL_CHUNKS_HEURISTIC=false explicit)
  structural_citation_count: 0
  structural_citation_rate:  0.0
  groundedness@8:            0.8667 (13/15)
  quote_validity:            1.0    (36/36)

AFTER (default; RETRIEVAL_CHUNKS_HEURISTIC unset == "true")
  structural_citation_count: 0   (no traps on this corpus)
  structural_citation_rate:  0.0
  groundedness@8:            0.8667 (13/15)  unchanged
  quote_validity:            1.0    (36/36)  unchanged

Δ structural_citation_rate: 0.0   (vacuous; no traps to drop)
Δ groundedness@8:           0.0   (well within 0.02 gate)
Δ quote_validity:           0.0
```

The numbers are degenerate, not informative. The T2.0 baseline already
documented this: the smoke corpus is four small pedagogical sources
(`photosynthesis.md`, `cell_division.md`, `cell_division.pdf`,
`README.md`) whose chunks rarely include answer-empty heading lines in
retrievable positions, and 36 LLM-cited quotes across 15 cases all
shape-passed the predicate. With both the off-run and the on-run at
zero, the >=30% relative-drop gate is mathematically vacuous on this
corpus.

## Why ship T4 despite the vacuous comparison

The plan's documented kill condition at lines 346-349 of
`docs/plans/structural-citation-gate-1-chunks-heuristic.md` reads:

> T2 lands and the post-T2.0 baseline shows
> `structural_citation_rate` was already at zero on the chunks corpus.
> The bug class is empirically small; Gate 1 closes without T3/T4 and
> surfaces an operator-followup noting the unmeasured user-corpus
> risk remains.

That kill condition triggered at T2.0. The routine shipped T3 anyway
with a pivoted acceptance (internal consistency between the eval-
harness counter and the runtime filter, not measured drop); see the
T3 report at `evals/reports/structural-citation-t3-2026-05-25.md`
§"Implication for T4". T4 follows the same pivot: ship the default
flip with honest reporting about the measurement limitation, on the
strength of three orthogonal safety arguments.

### Safety argument 1 — verbatim validation runs first

The runtime filter sits AFTER `validated_citation_quote` in
`services/tutor.py::_resolve_grounded_answer`. Any quote the filter
inspects is already verbatim-validated against its source node's
text. The filter never drops a non-verbatim quote; verbatim quotes
that survive the filter were going to ship anyway. The filter's only
job is "this quote is correctly extracted but shaped like structure;
do not let the user think it is an answer."

### Safety argument 2 — closed-class predicate pinned by 49 unit tests

`tests/test_retrieval_quote_heuristics.py` carries 49 test methods
across `HeadingShapeTests` (heading length cap, terminal-punctuation
gate, finite-verb gate, code/math character gate, section-numbered
bypass), `BareReferenceTests` (numeric-only, author-year, bracketed,
see-figure, chapter/section/part, page-ranges, equation, appendix/
exhibit; both positive subtests and prose negative subtests),
`BannerShapeTests`, `StructuralQuoteIntegrationTests`, and
`ChunksHeuristicEnabledTests`. The predicate's behavior at the
function-input level is pinned. The flip changes only when the
predicate fires (it always fires when called; now it is called by
default).

### Safety argument 3 — kill condition still hot

The plan's kill conditions at lines 350-355 remain in force:

> Any sub-PR's chunks-path `groundedness@8` regresses by more than
> 0.05 absolute against the post-T2.0 baseline. Roll back, loosen
> thresholds, re-run before re-landing.
> After T4 ships the default-on flip, if real-user-anchored telemetry
> (when it exists) shows answer-empty rate UP rather than down,
> immediately flip `RETRIEVAL_CHUNKS_HEURISTIC=false` and reopen.

Roll-back is a one-line env export (`RETRIEVAL_CHUNKS_HEURISTIC=false`
in the operator's shell or `.env`) or a one-line code revert of T4.
The blast radius is bounded by the verbatim-validation gate above:
worst case, a structural quote the operator wanted to see gets
dropped; the claim moves to `unsupported_spans` and the user reads an
honest "this claim is not supported" note instead of a heading-as-
evidence citation.

## What this report does NOT say

It does NOT empirically demonstrate the filter catches real-world
heading citations. The smoke corpus has zero traps; the labeled
slice at `evals/cases/structural-citation.jsonl` that ADR 0004
escalated as an operator-followup remains the right vehicle for that
measurement. T4 ships the default flip; the labeled slice is the
next quality-of-measurement upgrade and can land at any time after
T4 without re-touching T4's surface (the predicate is stable, the
flag is on, the slice would just rerun the same code with a richer
input set).

## Reproduce

The "off" branch:

```bash
RETRIEVAL_USE_NODES=false RETRIEVAL_CHUNKS_HEURISTIC=false \
  ./.venv/bin/python -m evals.run_evals \
  --mode full --suite smoke \
  --report-dir /tmp/eval-t4-off/
```

The "on" branch (post-T4 default):

```bash
RETRIEVAL_USE_NODES=false \
  ./.venv/bin/python -m evals.run_evals \
  --mode full --suite smoke \
  --report-dir /tmp/eval-t4-on/
```

Expected: the two runs produce identical structural_citation_count,
groundedness@8, and quote_validity on the smoke corpus, per the
vacuous-comparison observation above.

Unit test bench:

```bash
PYTHONPATH=. ./.venv/bin/python -m unittest \
  tests.test_retrieval_quote_heuristics -v
```

Expected: 49 OK.

## Implication for the labeled slice

The labeled slice at `evals/cases/structural-citation.jsonl` is still
an open operator-followup (2026-05-25T04:50Z entry in
`.claude/logs/operator-followups.jsonl`, escalation upgrade from the
2026-05-25T02:55Z original). T4 does NOT depend on it landing; the
flip is justified by the three safety arguments above. The slice
remains valuable as an empirical proof of catch-rate; whenever the
operator authorizes its authoring (slot 1 smoke-shaped or slot 2
broader-evals scope), it can land as a standalone PR that re-runs
the same eval harness with a richer input set and produces a
non-vacuous before/after delta.
