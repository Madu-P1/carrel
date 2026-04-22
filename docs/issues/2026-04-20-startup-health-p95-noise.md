# Startup Health P95 Benchmark Noise

- Date: 2026-04-20
- Status: Open
- Scope: Phase 1 benchmark follow-up

## Summary

The Phase 1 route-first refactor materially improved the benchmark harness on all tracked metrics versus the checked-in baseline. A candidate rebaseline run produced:

- `startup.health_p50_ms`: `1.00`
- `startup.health_p95_ms`: `1.99`
- `ingestion.latency_ms`: `970.11`
- `ingestion.throughput_mb_per_s`: `0.78`
- `retrieval.p50_ms`: `17.83`
- `retrieval.p95_ms`: `20.33`

On an immediate verification rerun, `startup.health_p95_ms` rose to `3.82ms`, which is a `+91.96%` drift versus that candidate baseline. All other tracked metrics stayed within the benchmark tolerance and remained materially better than the current checked-in baseline.

## Why This Is Tracked

The benchmark policy for this phase is:

- rebaseline when the refactor legitimately changes performance
- keep the old baseline and track an issue when a metric regresses by more than `50%`

Because `startup.health_p95_ms` exceeded that threshold on verification, the checked-in baseline was intentionally left unchanged.

## Next Step

Stabilize the startup benchmark before rebaselining. Likely fixes:

1. Increase startup sample count and average across multiple isolated runs.
2. Add a minimum timing floor or coarser precision for sub-5ms startup measurements.
3. Separate import-time health timing from `TestClient` request timing so p95 is less sensitive to scheduler jitter.
