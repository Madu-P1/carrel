# Adaptive ingestion concurrency

**Plan date:** 2026-05-25
**Author:** /carrel-build autonomous loop, fleet slot 2
**Slot brief:** `.claude/fleet/TODOS.fleet-2.md` (T1-redux)
**Successor to:** `docs/plans/cross-platform-memory-pressure-fallback.md` (SUPERSEDED 2026-05-25, see `docs/decisions/0005-cross-platform-memory-pressure-helper.md`)

---

## 0. Why this plan exists (succession from ADR 0005)

ADR 0005 closed slot 2's first T1 with a SUPERSEDED verdict. The synthesizer's
crux was that the memory-pressure helper's public API cannot be designed
correctly without a real caller in hand. Two concrete worker pools exist in
the tree today and they have materially different needs (§2 below). Picking
ONE first consumer and deriving the helper API from that consumer's actual
shape is the path that ADR 0005 mandated.

This plan picks the first consumer, derives the helper API from it, and
decomposes the work into three sub-PRs. The §2-§5 raw material from the
SUPERSEDED plan (macOS shellouts, psutil semantic gaps, dispatcher, ubuntu
CI matrix) is reused unchanged — it was always correct; the synthesizer only
ruled on the API-shape question, not the cross-platform mechanics.

The proponent/adversary/synthesizer routine will run on THIS plan before T2-redux
opens. The recommendation in §2.3 is the proponent's seed; §2.4 is the adversary
seed; the synthesizer either ratifies or overrides. Verdict will land as ADR
`0007-adaptive-ingestion-first-consumer.md` (ADR 0006 is the worktree-isolation
hook, already shipped).

---

## 1. Scope and non-goals

### What this plan covers

- **Consumer-pool analysis.** Read the two real worker pools that exist today
  (`services/jobs.py:23` request-scoped fixed-2 `ThreadPoolExecutor`,
  `script/reingest_all.py:163` batch `ThreadPoolExecutor` with `--concurrency`).
  Pick ONE as the first consumer and explain why.
- **Helper API derivation.** From the chosen consumer's actual usage shape,
  pick the helper's public API: binary predicate vs `recommended_worker_count`
  vs async-safe non-blocking. Default this plan: a count-returning helper
  (`recommended_worker_count`), with a trivially-derived binary wrapper kept
  for future callers that genuinely need a yes/no answer.
- **Sub-PR decomposition.** Three sub-PRs (T2-redux helper+consumer pair,
  T3-redux hardening, T4-redux ubuntu CI matrix). The helper does NOT ship
  alone; it ships with its first consumer wired, satisfying ADR 0005's
  "callerless utility" objection.
- **Cross-platform support.** macOS `vm_stat` + `sysctl vm.swapusage`
  shellouts AND a psutil fallback for Linux/Windows AND an `ubuntu-latest`
  CI matrix entry. Raw material from `docs/plans/cross-platform-memory-pressure-fallback.md`
  §2-§5 reused.

### What this plan does NOT cover (non-goals)

- **`services/jobs.py` wiring.** The request-scoped FastAPI pool has a
  materially different shape (fire-and-forget submit from a request thread,
  no latency budget, end-user UX surface). Wiring it correctly requires
  designing the admission-control surface (reject/defer/queue/throttle).
  That's its own plan — `docs/plans/request-scoped-ingestion-backpressure.md`
  — and explicitly out of slot 2. See §7 for the deferred-design note.
- **Adaptive per-document concurrency inside a Docling parse.** Docling's own
  worker count (`docling_parser.parse_document` is single-process) is not
  adjustable from here.
- **iOS / iPadOS port.** The platform-dispatch shape supports adding
  `darwin-mobile` later but the iOS path is not in this slot.
- **SQLite write-lock contention.** Separate issue
  (`docs/issues/2026-05-14-sqlite-write-lock-during-ingestion.md`); the
  memory helper is a different lever.
- **Auto-tuning the memory-headroom-per-worker threshold from telemetry.**
  Threshold is a constant (`min_free_mb_per_worker = 512`) in this slot.
  Telemetry-driven tuning is a future revision.

---

## 2. Consumer-pool analysis

### 2.1 `services/jobs.py:23` — request-scoped FastAPI pool

```python
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="carrel-job")

def submit_job(job_id: str) -> None:
    with _LOCK:
        if job_id in _SUBMITTED:
            return
        _SUBMITTED.add(job_id)
    _EXECUTOR.submit(_run_import_job, job_id)
```

**Characteristics:**
- Module-level executor; fixed `max_workers=2` since module import.
- `submit_job` called from a FastAPI request thread (`enqueue_import` at
  `services/jobs.py:154`); MUST be non-blocking. Memory check inside this
  call path adds latency to every upload.
- Worker spawn cadence: driven by user uploads. Bursty.
- Failure mode of "memory unsafe": today, the executor queues the task
  (`ThreadPoolExecutor` blocks no one; over-subscription is silent). A
  memory-aware variant would have to choose between (a) reject the upload
  (bad UX, user just dragged a file), (b) defer to a SQLite-backed queue
  and drain at safe pressure (complex coordination), (c) submit anyway and
  throttle inside the worker (defeats the helper).
- The fixed `max_workers=2` is probably already safe enough on a 16 GB Mac;
  the actual UX pain is rare, not constant.

**Why the API shape matters here:** the natural shape is async-safe
`is_safe_to_submit_now() -> bool` called per-upload, returning fast. But
this is exactly the binary form ADR 0005's synthesizer warned about —
the wrong shape for the OTHER consumer.

### 2.2 `script/reingest_all.py:163` — batch backfill pool

```python
with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
    futures = [pool.submit(_parse_one, doc_id, filename, path) for doc_id, filename, path in todo]
    for future in futures:
        doc_id, filename, nodes, parse_error = future.result()
        ...
```

**Characteristics:**
- One-shot CLI invocation. `--concurrency N` is the operator knob (default 4).
- Constructs the pool once with a fixed `max_workers`; submits ALL futures
  upfront; iterates `future.result()` synchronously.
- Operator-launched; latency tolerance is huge (script runs for hours;
  a 1480-page biology PDF re-ingest is the canonical workload — `status.md`
  2026-05-21 notes this regularly drives the dev machine to ~60-100 MB free).
- Failure mode of "memory unsafe at startup": reduce the pool size and
  proceed. Operator sees a one-line log entry. Zero UX cost.
- This is exactly where the eng-review item from 2026-05-14 was pointing
  ("when ingestion + AFM both want memory on a 16 GB Mac"). The 1480-page
  case is the concrete incident.

**Why the API shape matters here:** the natural shape is
`recommended_worker_count(*, max_workers=4) -> int` called ONCE at pool
construction. The script defaults `--concurrency` to the recommended count;
explicit `--concurrency N` overrides (operator wisdom beats heuristics).

### 2.3 Decision (proponent seed): `script/reingest_all.py` is the first consumer

**Rationale:**

1. **Highest-impact target for the memory-pressure signal.** The 1480-page
   PDF re-ingest case is where memory exhaustion has been empirically
   observed. The jobs.py path's 2-worker cap is rarely the cause of
   page-fault storms — re-ingest's 4-worker default is.

2. **Operator-controlled cadence; zero end-user UX risk.** Reducing pool
   size from 4 to 1 on a constrained host is a benign decision. Rejecting
   a user's upload is not. Start with the consumer where conservatism is
   cheap.

3. **The `--concurrency` flag is already the right knob.** Wiring
   `recommended_worker_count(max_workers=args.concurrency)` is a ~5-line
   change. The explicit flag stays as an override. Helper failure modes
   degrade gracefully (worst case: same behavior as today).

4. **Helper-API shape: count semantics is strictly more general than binary.**
   `recommended_worker_count` derives a binary check trivially
   (`safe = count >= 1`); the reverse does not. Picking the count form keeps
   future jobs.py wiring (or any third consumer) an option.

5. **Empirical signal for §9 open questions.** The original plan's open
   questions about `compressor_mb` belonging in the predicate, and about
   whether the `min_free_mb` default of 512 is correct, can be ANSWERED by
   running the helper through a real `reingest_all.py` pass on a 1480-page
   PDF and comparing the recommended count against what the host actually
   tolerated. This makes T3-redux a measurement pass.

6. **Slot independence holds cleanly.** `script/reingest_all.py` is squarely
   in the slot's "owns subtree" list. `services/jobs.py` is also in scope,
   but its wiring's design surface is bigger than slot 2's mandate.

### 2.4 Counter-argument (adversary seed): pick `services/jobs.py` first

**Steelman:**

1. **Higher user-visible impact.** A user uploading on a memory-constrained
   machine hits thrash today. Memory-aware admission control prevents UX
   degradation. Re-ingest is operator-only, so users never feel the
   re-ingest path improving.

2. **The async-safe shape is the strict subset of what the helper API needs
   to support eventually.** If we design for count semantics and reingest_all
   only, jobs.py wiring later will require either (a) an API addition
   (binary wrapper), or (b) a refactor. Better to design both shapes upfront.

3. **The `--concurrency` operator knob already exists.** Operators can
   tune reingest_all manually today. The helper adds little value there
   beyond "auto-tune"; the empirical pain is in jobs.py where there is no
   operator knob to begin with.

4. **The synthesizer's verdict (ADR 0005) said "at least one concrete
   consumer", not "pick the easiest one".** jobs.py is harder but it's
   what the eng-review item actually had in mind in 2026-05-14 ("adaptive
   concurrency" is plural workers per request burst, not a one-shot
   backfill).

**Why the proponent still wins (preliminary, pending debate):**

- The async-safe shape's "submit / reject / defer" decision is its own
  architectural call. Resolving it here would more than double this plan's
  scope. The "reject" branch alone is a UX design problem (toast? error
  page? auto-retry?). The "defer" branch is a queue + drain design.
  Neither is in the slot's stays-out-of subtree, but both are out of the
  slot's reasonable iteration budget.
- The count form already supports jobs.py later. Binary `safe = count >= 1`
  is a one-liner wrapper.
- The 2026-05-14 eng-review item's underlying concern ("ingestion + AFM
  thrash on a 16 GB Mac") is empirically a re-ingest problem, not an
  upload problem. The 1480-page PDF case IS what the eng review had in
  mind even if the words pointed at jobs.py.
- Conservatism-bias for the first ship: ship the helper with a low-stakes
  consumer first, measure on a real workload, then take the lessons into
  the higher-stakes consumer.

### 2.5 The synthesizer's task

Read both seeds. Either ratify §2.3 (proponent wins) and proceed with the
sub-PR decomposition in §5, OR flip to §2.4 (adversary wins) and rewrite
§5 to start with jobs.py. The synthesizer MAY also demand a third option;
the most likely third option is "land the helper with NO consumer this
slot, defer consumer selection until both pools' callsite-design plans
are written". That would be a return to ADR 0005's rejected Option A and
the synthesizer's prior verdict applies; the third option is therefore
unlikely.

---

## 3. Derived helper API

### 3.1 The shape

```python
# services/ingestion/memory_pressure.py

def recommended_worker_count(
    *,
    max_workers: int,
    min_free_mb_per_worker: int = 512,
    max_swap_used_pct: float = 75.0,
) -> tuple[int, MemorySnapshot]:
    """Return (count, snapshot). Count in [1, max_workers].

    count = max(1, min(max_workers, available_mb // min_free_mb_per_worker))
    Conservative on swap pressure: if swap_used_pct > max_swap_used_pct,
    count drops to 1 regardless of memory headroom. Conservative on snapshot
    error: count is 1 (never zero — the caller has work to do, the helper
    is advisory).
    """

def is_safe_to_start_worker(
    *,
    min_free_mb: int = 512,
    max_swap_used_pct: float = 75.0,
) -> tuple[bool, MemorySnapshot]:
    """Thin wrapper for binary callers. safe = recommended_worker_count(max_workers=1) >= 1
    with min_free_mb_per_worker=min_free_mb. Kept for future jobs.py-shaped consumers."""
```

### 3.2 Why count primary, with binary as a 10-line wrapper

Honest framing per the ADR 0007 synthesizer's adjustment 4: count is the
right shape for the first consumer (reingest_all); binary is the right
shape for the next consumer (jobs.py); we ship both because the wrapper
is 10 lines. The earlier draft claimed count semantics is a "strict
superset" of binary. That claim does not survive scrutiny — the count
API forces every caller to declare a `max_workers` value even when there
is no sizing decision to make. `is_safe_to_start_worker = recommended_worker_count(max_workers=1) >= 1`
is technically a one-line derivation, but it asks "can the host handle one
more worker assuming we wanted one", which is the binary question with a
ceremonial `max_workers=1` attached.

The reason to ship count primary anyway:

| Concern | Binary primary | Count primary |
|---|---|---|
| reingest_all (the first consumer) | Forces per-future polling inside worker threads with a yield-on-unsafe loop the helper does not provide | Right shape — called once at pool construction with the script's existing `--concurrency` cap |
| jobs.py (future consumer) | Right shape — called per submit | Wrapper `safe = count(max_workers=1) >= 1` is functional but ceremonial |
| Reversibility | binary→count requires a public-surface refactor (must add a second function or break the signature) | count→binary is a 10-line wrapper shipped in the same module |
| Empirical-validation surface | Cannot produce per-host `(snapshot, recommended_count, peak_RSS)` records | Produces the dataset that lets the next debate (jobs.py wiring) be answered with data, not guesses |

Ship the count form as primary; keep the binary form as a one-liner wrapper.
Total LoC delta vs original SUPERSEDED §1: ~10 lines.

### 3.3 Snapshot TypedDict (reused from SUPERSEDED §1)

```python
class MemorySnapshot(TypedDict, total=False):
    platform: str             # "darwin" | "linux" | "win32" | ...
    available_mb: float       # OS's idea of memory available for a new allocation
    free_mb: float            # strictly unallocated
    total_mb: float
    swap_used_mb: float
    swap_total_mb: float
    swap_used_pct: float
    compressor_mb: float      # macOS only
    page_size_bytes: int      # macOS only (snapshot debug aid)
    recommended: int          # NEW: the count the helper returned (debug aid)
    error: str                # populated iff snapshot collection failed
```

The `recommended` field is new vs the SUPERSEDED plan. It lets the caller
log "host had X MB available, helper recommended N workers" without
recomputing the math. Telemetry leverage.

### 3.4 Threshold rationale (reused from SUPERSEDED §1, refined)

- **`min_free_mb_per_worker = 512`.** Smallest defensible default; one
  Docling parse worker on a 1480-page PDF was observed at ~400 MB resident
  in the status.md 2026-05-21 entry. 512 MB gives a small safety margin
  and rounds to a clean number. Operator-tunable.
- **`max_swap_used_pct = 75.0`.** Above this the OS is actively paging hot
  pages and a new worker fights for swap I/O. Hurts foreground app
  responsiveness even before it hurts the worker. Operator-tunable.
- **`count` floor of 1, not 0.** The caller has decided there is work to do.
  The helper's job is to advise on pool size, not to veto the work. A floor
  of 0 would mean the caller has to special-case "skip the whole batch",
  which surfaces a different problem (no work happens) instead of solving
  the actual problem (work happens slower). The script's pool with N=1
  STILL makes progress.

---

## 4. Cross-platform implementation

This section is the SUPERSEDED plan §2-§5 raw material, lifted unchanged.
The synthesizer's verdict on ADR 0005 did not contest these sections — the
crux was API shape, not platform mechanics.

### 4.1 macOS shellout semantics

`vm_stat` and `sysctl vm.swapusage` parsers per SUPERSEDED §2.
Fields used: `Pages free`, `Pages inactive`, `Pages speculative`, `Pages
purgeable`, `page size of N bytes` from `vm_stat`; `total` and `used` from
`sysctl vm.swapusage`.
Parsing notes (trailing periods, divide-by-zero on zero swap, malformed
output → `error` key + conservative behavior) all carry over.

### 4.2 psutil semantic gaps

Per SUPERSEDED §3. `psutil.virtual_memory().available` ≈ macOS computed
available; not bit-identical but both are "bytes for a new allocation".
`compressor_mb` is macOS-only. Page size is macOS-only on the snapshot
shape. psutil-versus-shellout semantic differences are documented but do
NOT propagate to the count math — the count math reads `available_mb`
from whichever path provided the snapshot.

### 4.3 Dispatcher

Per SUPERSEDED §4:

```python
def _snapshot() -> MemorySnapshot:
    if os.environ.get("CARREL_FORCE_PSUTIL_MEMORY") == "1":
        return _psutil_memory_snapshot()
    if sys.platform == "darwin":
        return _macos_memory_snapshot()
    return _psutil_memory_snapshot()
```

The `CARREL_FORCE_PSUTIL_MEMORY=1` env escape hatch is preserved for CI
parity and operator debugging.

---

## 5. Sub-PR decomposition

### T2-redux — Sub-PR 1: helper + first consumer (one coherent PR)

This addresses ADR 0005's core objection (no callerless utility). The helper
and its first consumer land together.

**Lands:**

- `services/ingestion/memory_pressure.py` (new file, ~200 lines):
  - `MemorySnapshot` TypedDict.
  - `_parse_vm_stat(text: str)` and `_parse_sysctl_swapusage(text: str)`
    private parsers.
  - `_macos_memory_snapshot()` (shellouts).
  - `_psutil_memory_snapshot()` (psutil path; psutil import inside the
    function so module import doesn't require psutil on macOS).
  - `_snapshot()` dispatcher with platform branch + env override.
  - `recommended_worker_count(...)` (the public API).
  - `is_safe_to_start_worker(...)` (one-liner binary wrapper).
- `script/reingest_all.py` (modifications):
  - When `--concurrency` is NOT explicitly passed, call
    `recommended_worker_count(max_workers=4)` (4 is the existing default
    cap) and use the returned count.
  - When `--concurrency N` is explicitly passed, log a one-line warning if
    the recommended count is lower than N and proceed with N anyway
    (operator override beats heuristics).
  - Log one line at startup: "host snapshot: available=X MB, swap=Y%, using
    N workers (cap=M, recommended=N)".
- `tests/test_memory_pressure.py` (new, ~250 lines):
  - macOS parser tests (vm_stat normal, vm_stat zero-swap, vm_stat
    malformed, sysctl normal, sysctl zero-total). 5 tests.
  - psutil snapshot tests (normal, zero-swap, import-error). 3 tests.
  - Dispatcher tests (darwin path, linux path, force-psutil env override).
    3 tests.
  - `recommended_worker_count` tests (above thresholds → max, below
    `min_free_mb_per_worker` → 1, above `max_swap_used_pct` → 1,
    snapshot error → 1, exact-boundary cases). 5 tests.
  - `is_safe_to_start_worker` wrapper consistency test. 1 test.
  - Total: 17 tests.
- `requirements-dev.txt`:
  - Add `psutil`. Dev-only dependency. macOS production never executes
    `_psutil_memory_snapshot()` because the dispatcher routes to
    `_macos_memory_snapshot()` first. The only production path that hits
    psutil is `CARREL_FORCE_PSUTIL_MEMORY=1`, an operator-set debugging flag.

**Acceptance:**

- All 17 tests pass on macOS CI.
- `script/reingest_all.py --dry-run` on a tree with 0 candidate docs
  still prints the host snapshot log line (proves the helper is wired
  even when no work happens).
- `ruff check` + `ruff format --check` clean.
- `grep -rn "import psutil" services/` returns ONLY
  `services/ingestion/memory_pressure.py`.
- macOS production import of `services.ingestion.memory_pressure`
  succeeds without `psutil` installed (proven by a dedicated test that
  monkey-patches `sys.modules`).
- No existing test regresses.

**Guards:**

- Do NOT modify `services/jobs.py`. That's a separate plan; in-scope
  changes would leak the helper's design into an architectural problem
  it doesn't yet have a solution for.
- Do NOT default `--concurrency` to anything other than "consult helper".
  The implicit default has always been 4; the helper just makes that
  capped-at-4 instead of fixed-at-4. Explicit operator value still wins.
- LoC budget: 250 helper, 250 tests, 30 consumer wiring, 10 CHANGELOG/doc.
  Exceed → re-debate before continuing.

### T3-redux — Sub-PR 2: hardening + empirical validation

Closes the SUPERSEDED plan's §9 open questions empirically.

**Slot-coupling constraint (ADR 0007 synthesizer adjustment 1):** T3-redux
MUST ship within the same slot as T2-redux. If the slot runway cannot
accommodate both (rate-limit, watchdog kill, operator HALT), do NOT start
T2-redux. The rollback gap that the adversary identified (failure-mode-4:
revert leaves a callerless helper) is closed by guaranteeing the empirics
land in-slot, so T2-redux's wiring is validated before the slot ends.

**Lands:**

- `tests/integration/test_memory_pressure_macos.py` (new, gated on
  `sys.platform == "darwin"` AND `CARREL_RUN_MEMORY_PRESSURE_INTEGRATION=1`):
  - Calls `recommended_worker_count(max_workers=4)` against the real OS.
  - Asserts snapshot shape (positive `total_mb`, `0 <= swap_used_pct <= 100`,
    `page_size_bytes in {4096, 16384}`).
  - Asserts `count in [1, 4]`.
  - Not run in default verify chain; operators run manually.
- `docs/notes/2026-05-XX-memory-pressure-empirics.md` (new, ~150 lines):
  - Captures a measurement pass per ADR 0007 synthesizer adjustment 5.
  - Mandatory record format: one row per `(host, run)` tuple containing
    `(snapshot, recommended_count, peak_RSS_per_worker)` exactly. The
    snapshot is the TypedDict from §3.3 captured at pool construction;
    `recommended_count` is what the helper returned; `peak_RSS_per_worker`
    is observed during the run via `psutil.Process(pid).memory_info().rss`
    sampled at 30s intervals. Without these three columns the strategic
    case for picking reingest_all-first (per ADR 0007 reasoning) collapses
    and the slot must surface that to the operator.
  - Drives: run `reingest_all.py` against a 1480-page PDF on the dev
    machine, log the helper's snapshot each minute alongside actual peak
    RSS per worker. Append rows.
  - Compares: does the helper's count match what the machine tolerated?
  - If `compressor_mb` correlated with under-counted recommendations,
    revise §3.4 to fold compressor into the count math.
  - If `min_free_mb_per_worker=512` was wrong by more than ±50%, revise
    the default (PR follow-up).
- `services/ingestion/memory_pressure.py` (refinements):
  - If the empirics note above produced a revision, apply it here.
  - Add `CARREL_MEMORY_HEADROOM_MB` env var override for
    `min_free_mb_per_worker` (lets operators tune without code changes).
  - Add `CARREL_MEMORY_MAX_SWAP_PCT` env var for `max_swap_used_pct`.
- Tests:
  - New tests for the env-var overrides (3 tests).
  - If §3.4 was revised, regression tests for the new threshold logic.

**Acceptance:**

- Integration test passes on the dev machine; documented as expected on
  fresh Macs.
- Empirics note exists with at least one real measurement run logged.
- Env-var override tests pass.
- `script/reingest_all.py` continues to work with default thresholds.
- Whatever §3.4 revision happened is documented in this PR's body and in
  the empirics note.

**Guards:**

- If the empirics show the helper is materially wrong (recommended count
  > tolerated count by >2x), do NOT silently revert T2-redux's wiring.
  Per ADR 0007 synthesizer adjustment 2: a >2x miss seeds a jobs.py-first
  follow-up debate, with the empirics dataset as the new evidence. Surface
  to operator; do not unilaterally roll back the wiring (silent revert
  would re-enter the callerless-utility state ADR 0005 rejected).
- Do NOT widen the env-var surface beyond two knobs (headroom-per-worker
  and max-swap-pct). Operator tunability is a feature, env-var-soup is not.

### T4-redux — Sub-PR 3: ubuntu CI matrix

Per SUPERSEDED §5 T4. Unchanged.

**Lands:**

- `.github/workflows/*.yml` (matrix entry):
  - `ubuntu-latest` job that installs `psutil`, sets
    `CARREL_FORCE_PSUTIL_MEMORY=1`, runs `tests/test_memory_pressure.py`.
  - Does NOT run the full backend suite (macOS-specific PDFKit/Vision
    deps via the Swift sidecar).

**Acceptance:**

- ubuntu-latest matrix job is green.
- macos-latest CI is green and unchanged.
- README or CONTRIBUTING gets a one-line note about the new matrix entry.

**Guards:**

- Do NOT widen the ubuntu matrix to the full backend suite. That's its own
  Linux-port roadmap.
- Do NOT add psutil to runtime `requirements.txt`. Stays dev-only.

---

## 6. Test strategy summary

Total ~25-30 new tests across T2-redux + T3-redux:

| Layer | Tests | Where |
|---|---|---|
| Unit — macOS parsers | 5 | `tests/test_memory_pressure.py` |
| Unit — psutil snapshot | 3 | `tests/test_memory_pressure.py` |
| Unit — dispatcher | 3 | `tests/test_memory_pressure.py` |
| Unit — `recommended_worker_count` | 5 | `tests/test_memory_pressure.py` |
| Unit — `is_safe_to_start_worker` wrapper | 1 | `tests/test_memory_pressure.py` |
| Unit — env-var overrides | 3 | `tests/test_memory_pressure.py` (T3-redux) |
| Module-import-without-psutil | 1 | `tests/test_memory_pressure.py` |
| Integration — macOS real OS | 1 | `tests/integration/test_memory_pressure_macos.py` (opt-in) |

The canonical verify chain runs in CI per `CLAUDE.md` §"Verify chain". The
new tests are added to the chain in T2-redux's PR body so the rater sees the
extension.

---

## 7. `services/jobs.py` — explicit out-of-scope with deferred design

The §2.4 adversary seed argues for jobs.py as first consumer. The §2.5
synthesizer task is to decide between §2.3 and §2.4. If §2.3 wins
(proponent), the jobs.py wiring becomes a separate plan with its own
debate. This section seeds the future plan rather than punting it.

**Future plan name:** `docs/plans/request-scoped-ingestion-backpressure.md`
(not in this slot).

**Open design questions for the future plan:**

1. **Admission control surface.** What does `submit_job` do when the helper
   reports unsafe?
   - Reject: HTTP 503 with a "host is busy, try again" toast? (UX cost)
   - Defer: write the job row in `status='queued'` but skip `_EXECUTOR.submit`,
     and poll a drain loop until safe? (queue lifecycle design)
   - Throttle: submit but pause inside `_run_import_job` until safe?
     (defeats parallel ingestion)
2. **Fixed vs adaptive pool sizing.** Can `_EXECUTOR.submit` become a
   `recommended_worker_count`-sized pool that resizes dynamically? (Python's
   `ThreadPoolExecutor` doesn't support resize; would need a custom pool.)
3. **Per-request fairness.** A burst of 10 uploads under memory pressure:
   reject 8 and accept 2? FIFO queue? Per-subject quotas?
4. **Cross-component memory accounting.** When AFM is loading a model
   (separate process, holds ~2-4 GB), the helper's `available_mb` already
   reflects that — but `min_free_mb_per_worker` was tuned for Docling-only
   workloads. Does the threshold need an AFM-aware adjustment?

The future plan picks an admission-control surface, designs the queue
lifecycle, runs its own proponent/adversary/synthesizer debate, and ships
behind a feature flag. This slot does NOT preempt those decisions.

---

## 8. Independence assertion (slot brief)

Per `.claude/fleet/TODOS.fleet-2.md`: "Stays out of `services/retrieval/`,
`services/tutor.py`, `evals/`, `ai/`."

This plan touches:

- `services/ingestion/memory_pressure.py` (new; in slot's owns-subtree).
- `script/reingest_all.py` (existing; in slot's owns-subtree).
- `tests/test_memory_pressure.py` (new).
- `tests/integration/test_memory_pressure_macos.py` (new, opt-in).
- `requirements-dev.txt` (one-line addition, T2-redux).
- `.github/workflows/*.yml` (matrix entry, T4-redux).
- `docs/notes/2026-05-XX-memory-pressure-empirics.md` (new, T3-redux).
- `docs/decisions/0007-adaptive-ingestion-first-consumer.md` (new, before T2-redux).
- `.claude/fleet/TODOS.fleet-2.md` (status flip per task).

NO retrieval, tutor, eval, or ai code is touched. Slot independence holds.

The §7 deferred jobs.py wiring is explicitly excluded; if a sub-PR finds
itself drifting into `services/jobs.py`, that's a STOP signal per the
collision protocol.

---

## 9. Acceptance (overall) and kill conditions

### Overall acceptance (after T4-redux lands)

- `services/ingestion/memory_pressure.py` exists with `recommended_worker_count`
  as the primary public API and `is_safe_to_start_worker` as a binary wrapper.
- `script/reingest_all.py` consults the helper when `--concurrency` is
  omitted; explicit `--concurrency N` overrides; one log line per run records
  the host snapshot and chosen count.
- All ~25-30 unit tests pass on macOS CI.
- Same tests (minus macOS-shellout-specific ones) pass on ubuntu-latest with
  `CARREL_FORCE_PSUTIL_MEMORY=1`.
- Integration test passes on the dev machine (opt-in only).
- `grep -rn "import psutil" services/` returns ONLY
  `services/ingestion/memory_pressure.py`.
- macOS production import succeeds without psutil installed.
- The empirics note exists with at least one real measurement entry.
- ADR 0007 records the synthesizer's verdict on the first-consumer choice.
- This plan is updated with each sub-PR's commit SHA + PR number.
- No existing test regresses on either platform.

### Kill conditions (any one fires → stop the slot, surface to operator)

- T2-redux lines of code exceed 600 across all files (sign the design grew
  beyond what the plan describes; re-debate).
- T2-redux's `reingest_all.py` wiring causes a regression in the
  canonical verify chain (`./.venv/bin/python -m unittest tests.test_evals_runner`
  or similar) — the wiring is supposed to be backward-compatible.
- T3-redux's empirics measurement shows the helper is materially wrong
  (recommended count > tolerated count by >2x). Revert T2-redux wiring,
  surface.
- The proponent/adversary/synthesizer debate on this plan reaches
  THIRD_OPTION_REQUIRED three rounds running. Halt for operator.
- Any sub-PR drifts into `services/jobs.py` or `services/tutor.py` or
  `services/retrieval/` or `evals/` or `ai/`. STOP per the slot brief
  collision protocol.

---

## 10. Verify chain (per task)

Each sub-PR runs the canonical chain at `CLAUDE.md` §"Verify chain (run
before any merge)" lines 39-49.

Notes on chain steps that aren't directly relevant:

- **`./script/build_and_run.sh --verify`**: this slot does not touch Swift
  or frontend; the build will pass for unrelated reasons or fail for
  unrelated reasons. Run it; if it fails for unrelated reasons, surface in
  PR body. Do NOT bypass.
- **`benchmarks/phase0 --fail-on-regression`**: this slot does not touch
  retrieval or AI. Run; if it fails for unrelated reasons, surface.
- **`tests/test_watchdog_kill.sh`**: irrelevant to this slot's surface;
  run anyway.
- **`swift test --package-path macos-app`**: irrelevant; run anyway.

The new `tests/test_memory_pressure.py` MUST be added to the
`./.venv/bin/python -m unittest ...` line in the canonical chain (the
chain in CLAUDE.md is explicit about which test modules run). T2-redux's
PR includes a one-line CLAUDE.md edit to add the module to the chain.

---

## 11. Operator follow-ups (record at plan ship)

Append to `.claude/logs/operator-followups.jsonl`:

1. `request-scoped-ingestion-backpressure.md` is now an identified future
   plan (§7). It is NOT in slot 2's queue; surface to operator so they
   can prioritize against other backlog items.
2. The `min_free_mb_per_worker=512` and `max_swap_used_pct=75` defaults
   are heuristics; T3-redux's empirics note is the place to revisit them
   once we have a real measurement pass.
3. Telemetry on `recommended_worker_count`'s actual recommendations is
   not in this slot's scope; if Carrel adds a telemetry pipeline later,
   this is a useful signal to capture.
