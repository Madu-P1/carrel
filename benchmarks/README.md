# Benchmarks

The benchmark harnesses are source-controlled here. Generated outputs belong in `data/benchmarks/`.

## Commands

- Run the Phase 0 baseline harness:
  - `python -m benchmarks.phase0`
- Compare the current run to the checked-in baseline and fail on regressions:
  - `python -m benchmarks.phase0 --compare data/benchmarks/baseline.json --tolerance 0.25 --fail-on-regression`

## Output Policy

- `data/benchmarks/baseline.json` is the checked-in reference snapshot.
- All other generated benchmark JSON is ignored by Git.
- When a benchmark candidate baseline still shows more than `50%` drift on a verification rerun, keep the existing baseline and track the regression instead of rebaselining immediately.

## Metrics

- `startup.health_p50_ms`
- `startup.health_p95_ms`
- `ingestion.latency_ms`
- `ingestion.throughput_mb_per_s`
- `retrieval.p50_ms`
- `retrieval.p95_ms`

The current harness runs against an isolated temporary database so it does not mutate a developer's real library.
