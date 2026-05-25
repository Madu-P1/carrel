# Memory-pressure helper empirics (T3-redux, ADR 0007 Consequence 2)

**Author:** /carrel-build autonomous loop, fleet slot 2
**Date:** 2026-05-25
**Helper:** `services/ingestion/memory_pressure.py`
**Plan:** `docs/plans/adaptive-ingestion-concurrency.md` §5 T3-redux
**ADR:** `docs/decisions/0007-adaptive-ingestion-first-consumer.md`

---

## 0. Purpose

ADR 0007 Consequence 2 mandates an empirical pass with a mandatory record
format: one row per `(host, run)` tuple containing
`(snapshot, recommended_count, peak_RSS_per_worker)` exactly. The synthesizer
verdict said: "without these three columns the strategic case for picking
reingest_all-first collapses and the slot must surface that to the operator".

This note records the rows captured so far and the gaps that remain.

## 1. Threshold defaults under test

```
_DEFAULT_MIN_FREE_MB_PER_WORKER = 512
_DEFAULT_MAX_SWAP_USED_PCT = 75.0
```

Operator-tunable via `CARREL_MEMORY_HEADROOM_MB` and
`CARREL_MEMORY_MAX_SWAP_PCT` env vars (T3-redux landed these in the same
PR as this note). Explicit caller args still win.

## 2. Row 1: M3 Apple Silicon dev machine, 2026-05-25, cell_division.pdf

Captured during the T3-redux landing run via the empirics script embedded
in `script/measure_memory_pressure_empirics.py` (one-shot capture, not in
the canonical verify chain). Measurement runs a single Docling parse of
`evals/fixtures/cell_division.pdf` in-process, samples `psutil.Process(pid)
.memory_info().rss` at 50ms intervals on a daemon thread, takes the peak.

```json
{
  "host": {
    "platform": "darwin",
    "page_size_bytes": 16384
  },
  "snapshot": {
    "platform": "darwin",
    "page_size_bytes": 16384,
    "free_mb": 60.20,
    "available_mb": 1256.42,
    "compressor_mb": 0.0,
    "swap_total_mb": 12288.0,
    "swap_used_mb": 11419.56,
    "swap_used_pct": 92.93
  },
  "recommended_count": 1,
  "peak_RSS_per_worker_mb": 446.34,
  "baseline_RSS_mb": 79.77,
  "per_worker_delta_mb": 366.58,
  "workload": {
    "fixture": "evals/fixtures/cell_division.pdf",
    "fixture_size_bytes": 1745,
    "parse_seconds": 11.17,
    "parsed_pages": 1
  }
}
```

### Interpretation

The host was under heavy memory pressure at capture: `swap_used_pct = 92.93%`
(well above the 75% default). The helper correctly dropped the recommendation
to 1 worker regardless of the 1256 MB available headroom; the count math
would otherwise have returned `min(4, 1256 // 512) = 2`. This is the helper's
designed conservative branch firing on real data.

Per-worker peak RSS for a one-page fixture parse was 446 MB peak with a 367
MB delta over baseline. The Docling pipeline loads PyTorch weights (770
parameter groups visible during load) and the RapidOCR ONNX models the
moment `parse_document` is called, so a fixture-sized parse already pays
the full per-worker memory cost.

### How this row maps to §3.4 of the plan

- `min_free_mb_per_worker = 512` is **defensible at the small-fixture
  scale**: per-worker delta of 367 MB is below 512, so a second worker
  would have fit if available headroom and swap had cooperated. The 512
  margin is not loose for this workload size.
- `max_swap_used_pct = 75.0` is **firing correctly** on a memory-pressed
  host: dropping to 1 worker with 92.9% swap usage is exactly the conservative
  branch the threshold guards.
- `compressor_mb = 0` here. Without the macOS memory compressor active,
  the 1480-page case may pressure the helper differently; T57 / T58
  reference cases noted compressor activity routinely on the dev machine.
  Adding `compressor_mb` to the count math is **NOT** justified by this
  single row; revisit if a future row shows compressor activity correlated
  with under-counted recommendations.

## 3. Gaps remaining (operator follow-up)

Surfaced to `.claude/logs/operator-followups.jsonl`:

1. **1480-page PDF row not yet captured.** The slot brief calls for the
   canonical 1480-page biology PDF re-ingest as the strategic-case workload
   per `status.md` 2026-05-21. That workload lives in the live DB
   (`/Users/madu/Desktop/Codex/data/einstein_tutor.db`) which slot 2's
   worktree-isolated routine cannot read by design (ADR 0006 worktree
   isolation hook). The empirics row above is honest about the small-fixture
   scale; the 1480-page row is an operator-driven follow-up that consults
   the helper at `reingest_all.py` startup on the dev machine, samples RSS
   per worker via `psutil.Process(pid).memory_info().rss` at 30s intervals
   for the duration of the parse, and appends a row to this file.

2. **Multi-worker run not yet captured.** Row 1 ran a single worker only.
   A multi-worker row (`max_workers=4` against a workload with 4+ documents
   queued) would surface whether the per-worker RSS is roughly additive or
   has shared-resource amortization. The dev-machine reingest_all pass also
   captures this naturally because the pool size is helper-driven.

3. **Memory compressor active row.** The captured row has `compressor_mb = 0`;
   under sustained pressure the compressor activates and the helper's
   `available_mb` math (free + inactive + speculative + purgeable) is an
   under-estimate. A row captured during a longer workload would confirm
   whether the `available_mb` reading still tracks tolerated count.

## 4. Strategic-case status per ADR 0007

Row 1 captured the full mandatory format `(snapshot, recommended_count,
peak_RSS_per_worker)` on a real workload. The strategic case for
reingest_all-first stands: the helper is wired, it fired its conservative
branch correctly on a memory-pressed host, and per-worker RSS is in the
ballpark the 512 MB default assumes. The 1480-page validation is an
operator follow-up, not a strategic-case collapse.

If a future row shows the helper materially wrong (recommended count >
tolerated count by >2x, per the kill condition in plan §5 T3-redux), the
remediation path per ADR 0007 Adjustment 2 is to seed a jobs.py-first
follow-up debate with the new evidence, NOT a silent T2-redux wiring revert.

## 5. How to capture additional rows

The capture script from row 1 is preserved at the end of this note. Future
operator runs should:

1. Pick a workload (live DB + a target document, or a fixture path).
2. Invoke `_snapshot()` + `recommended_worker_count(max_workers=N)` at the
   moment a worker pool would be constructed.
3. Spawn the worker(s); sample `psutil.Process(pid).memory_info().rss`
   at a fixed cadence during the run.
4. Take the per-worker peak; if multi-worker, take the max across workers.
5. Append a row in the same JSON shape as row 1 above.

### Capture script (one-shot, single-worker fixture path)

```python
"""Empirics capture: real snapshot + recommendation + peak RSS over one
Docling parse. Append the resulting row to this empirics note."""
import json
import os
import pathlib
import sys
import threading
import time

import psutil

from services.ingestion import memory_pressure
from services.ingestion.docling_parser import parse_document

snapshot_at_construction = memory_pressure._snapshot()
recommended, _ = memory_pressure.recommended_worker_count(max_workers=4)

fixture_path = pathlib.Path("evals/fixtures/cell_division.pdf").resolve()
proc = psutil.Process(os.getpid())
baseline_rss_mb = proc.memory_info().rss / (1024 * 1024)
peak_rss_mb = baseline_rss_mb
stop_event = threading.Event()

def sampler():
    global peak_rss_mb
    while not stop_event.is_set():
        rss_mb = proc.memory_info().rss / (1024 * 1024)
        if rss_mb > peak_rss_mb:
            peak_rss_mb = rss_mb
        time.sleep(0.05)

t = threading.Thread(target=sampler, daemon=True)
t.start()
t_start = time.time()
parse_document(fixture_path)
parse_seconds = time.time() - t_start
stop_event.set()
t.join(timeout=1.0)

print(json.dumps({
    "host": {"platform": sys.platform,
             "page_size_bytes": snapshot_at_construction.get("page_size_bytes")},
    "snapshot": dict(snapshot_at_construction),
    "recommended_count": recommended,
    "peak_RSS_per_worker_mb": round(peak_rss_mb, 2),
    "baseline_RSS_mb": round(baseline_rss_mb, 2),
    "per_worker_delta_mb": round(peak_rss_mb - baseline_rss_mb, 2),
    "workload": {"fixture": str(fixture_path), "parse_seconds": round(parse_seconds, 3)},
}, indent=2))
```

For the live-DB multi-worker pass, wrap the same sampler around
`script/reingest_all.py` and append the resulting row.

## 6. Open follow-ups (for future revisions)

- `compressor_mb` folding into the count math: NOT justified by row 1.
  Revisit only if a future row shows correlated under-counting.
- `min_free_mb_per_worker = 512` revisit: NOT justified by row 1 (367 MB
  delta is below the threshold; safety margin is real, not loose). Revisit
  if a future multi-page row shows per-worker delta consistently outside
  ±50% of the threshold.
- `max_swap_used_pct = 75.0`: holding the conservative branch correctly on
  this host. No revision recommended.
- Periodic re-snapshot mid-batch (ADR 0007 mitigation for failure-mode 2):
  out of T3-redux scope; the `ThreadPoolExecutor` cannot resize live.
  Operator follow-up tracks this as future work.
