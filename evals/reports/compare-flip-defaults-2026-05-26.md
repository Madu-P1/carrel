# Default-flip comparison (ADR-0006) — 2026-05-26

Side-by-side full-mode smoke eval for the V2 default flip:
`INGEST_USE_DOCLING` and `RETRIEVAL_USE_NODES` both move from
default `false` to default `true`. ADR-0006 quality gate requires
the nodes path (new default) to preserve the CLAUDE.md thresholds:

- `groundedness@8 >= 0.7`
- `quote_validity >= 0.95`

| Metric | Nodes (new default) | Chunks (legacy opt-out) |
|---|---|---|
| groundedness@8 | 13/15 (86.7%) | 13/15 (86.7%) |
| quote_validity | 38/38 (1.00) | 32/32 (1.00) |
| structural_citation_rate | 0/38 (0.00) | 0/32 (0.00) |
| citation_precision | 0.70 | 0.77 |
| citation_recall | 0.80 | 0.80 |
| citation_drop_rate | 0/38 (0.0%) | 0/32 (0.0%) |
| citation_repair_rate | 2/38 (5.3%) | 2/32 (6.2%) |
| p50 latency | 5.1s | 4.7s |
| p95 latency | 6.5s | 7.7s |

## Quality gate

Both thresholds clear on the new default path:

- groundedness@8 = 0.867 >= 0.7 (pass)
- quote_validity = 1.00 >= 0.95 (pass)

## Worst-case shape

Same two cases miss on both paths:

- `negative-gravity-001` — intentional negative; corpus does not
  cover gravity, the model correctly refuses. groundedness=0 is
  the expected outcome, not a failure.
- `negative-blackholes-001` — same shape as above.

## Observations

- Nodes path produces denser citation grounding (38 cites vs 32 on
  the same 15 cases) because typed-node retrieval surfaces
  list_item and body nodes separately where the chunks path
  would collapse them into one paragraph-bucket chunk.
- Precision is 7 points lower on nodes (0.70 vs 0.77) and recall
  is identical (0.80). Net groundedness@8 is unchanged. The extra
  cites are bounded prose nodes from the same expected docs, not
  cross-doc fabrication.
- Repair rate is comparable (5.3% nodes, 6.2% chunks). The
  validator is doing the same work on both paths.
- Structural-citation rate stays at zero on both paths — Gate 0
  (`_drop_non_citable_contexts`) keeps heading/header/footer out
  of the candidate pool, and Gate 1 (`is_structural_quote` on the
  chunks path, default-on after T4) keeps heading-shape quotes
  out of resolved citations.

## Reproduce

```bash
# Nodes path (new default)
./.venv/bin/python -m evals.run_evals \
  --mode full --suite smoke --report-dir /tmp/eval-nodes/

# Chunks path (legacy opt-out)
RETRIEVAL_USE_NODES=false INGEST_USE_DOCLING=false \
  ./.venv/bin/python -m evals.run_evals \
  --mode full --suite smoke --report-dir /tmp/eval-chunks/
```

## Verdict

Default flip is safe. Both quality thresholds clear. Nodes path
delivers the structural typing required by the Carrel V2
verification surface (Citation.node_type populates with real
values; chip badges render Table / Figure / Eq / Note / etc.)
without trading off groundedness or quote validity.
