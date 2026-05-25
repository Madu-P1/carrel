# Cross-platform memory-pressure fallback

> **SUPERSEDED 2026-05-25** by `docs/decisions/0005-cross-platform-memory-pressure-helper.md`. The proponent/adversary/synthesizer routine ruled (HIGH confidence) that the helper API cannot be designed without a real caller in hand. This plan is preserved as raw material — §2 macOS shellout semantics, §3 psutil equivalents, §4 dispatch shape are all directly reusable in the successor plan `docs/plans/adaptive-ingestion-concurrency.md` (to be written by slot 2's re-tasked T1). Do NOT implement T2/T3/T4 from this plan as-is; the new combined plan re-specifies them after its own debate.

---

**Plan date:** 2026-05-25
**Author:** /carrel-build autonomous loop, fleet slot 2
**Source row:** `TODOS.md` → "Active backlog (from ingestion-robustness eng review, approved 2026-05-14)" → `cross-platform-memory-pressure-fallback.md`
**Slot brief:** `.claude/fleet/TODOS.fleet-2.md`

---

## 0. Premise correction (read first)

The TODOS row from 2026-05-14 reads:

> When Carrel ports to Linux (no immediate plan), `MemoryPressure.is_safe_to_start_worker()` needs a psutil-based fallback for the macOS-specific `vm_stat` + `sysctl vm.swapusage` calls. **The helper is wrapped exactly so this fallback is a 1-day swap**, but capture it now or the macOS-only assumption will calcify.

**That premise is wrong.** A code search of the tree on 2026-05-25 (this plan's authoring session) found:

- No file named `memory_pressure.py` anywhere under `services/` or `ai/`.
- No symbol `MemoryPressure` anywhere outside `.venv/` (third-party libraries only).
- No call to `vm_stat` or `sysctl vm.swapusage` anywhere in application code.
- No `psutil` import anywhere in application code.

The helper does not exist. The 2026-05-14 eng review described what would be needed once an adaptive-concurrency ingestion redesign (B+C-lite) landed; that redesign never landed in the form that introduced this helper. The two real worker pools in the tree today are `services/jobs.py:23` (`_EXECUTOR = ThreadPoolExecutor(max_workers=2, ...)`, fixed at 2) and `script/reingest_all.py:163` (`ThreadPoolExecutor(max_workers=args.concurrency)`, default 4). Neither gates on memory pressure; both have static concurrency.

This plan therefore covers **net-new creation** of a `services/ingestion/memory_pressure.py` helper, designed cross-platform from day one. It does not refactor an existing macOS-only helper, because there is no such helper to refactor.

The slot brief's sub-PR decomposition is honored, with T2 reframed from "extract macOS calls into a private helper" to "create the module with a private macOS snapshot helper (no callers yet)". The slot brief's stays-out-of subtree is honored: this plan touches only `services/ingestion/` and tests.

---

## 1. Scope and non-goals

### What the helper does

`is_safe_to_start_worker(*, min_free_mb: int = 512, max_swap_used_pct: float = 75.0) -> tuple[bool, dict[str, float | str]]`

Returns a `(safe, snapshot)` tuple. `safe` is true iff the host has at least `min_free_mb` of free physical RAM AND swap utilisation is below `max_swap_used_pct`. `snapshot` is the platform-neutral memory snapshot that fed the decision, in a single shape both platforms produce (see §4).

### What the helper does NOT do (non-goals for this plan)

- It does not change anything about the existing worker pools. The two consumers (`services/jobs.py`, `script/reingest_all.py`) are NOT modified by T2-T4. Wiring them is a follow-up plan (`adaptive-ingestion-concurrency.md`, deferred).
- It does not introduce adaptive concurrency. The helper is a building block; the actual "spawn N workers if safe, M workers if pressured" loop belongs to whatever PR wires the helper.
- It does not handle the iOS/iPadOS port. The platform-dispatch shape supports adding `darwin-mobile` later, but iOS is out of scope.
- It does not address SQLite write-lock contention (separate issue, see `docs/issues/2026-05-14-sqlite-write-lock-during-ingestion.md`).

### Why land the helper without consumers

Two reasons:

1. **Capture-the-decision principle.** The eng review item was explicit that we should "capture it now or the macOS-only assumption will calcify". The reasoning applies regardless of whether the calcified assumption is in current callers or in some future PR that introduces the first caller. Landing the cross-platform-aware helper now means the first caller writes `from services.ingestion.memory_pressure import is_safe_to_start_worker` and gets Linux support for free.
2. **Independence assertion (slot brief).** Slot 2 stays out of `services/retrieval/`, `services/tutor.py`, `evals/`, `ai/`. Modifying `services/jobs.py` to gate the existing pool is in-scope, but it would be a behavior change to the live ingestion path with no eng-reviewed adaptive-concurrency design backing it. Adding the helper as a utility module is the minimal scope that satisfies the eng-review intent.

---

## 2. (a) macOS shellout semantics

The eng-review item names two shellouts. Real outputs sampled from a development machine on 2026-05-25:

### `vm_stat`

```
Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                                4210.
Pages active:                             71102.
Pages inactive:                           64798.
Pages speculative:                         5514.
Pages throttled:                              0.
Pages wired down:                        143691.
Pages purgeable:                             28.
"Translation faults":                 554007371.
Pages copy-on-write:                   20185927.
Pages zero filled:                    280034762.
Pages reactivated:                    166627096.
Pages purged:                          33076766.
File-backed pages:                        53588.
Anonymous pages:                          87826.
Pages stored in compressor:             1303810.
Pages occupied by compressor:            205131.
Decompressions:                       149809271.
Compressions:                         165490894.
Pageins:                               38315497.
Pageouts:                                554113.
Swapins:                                2981186.
Swapouts:                               3633916.
```

What we read from `vm_stat`:

| Line | Meaning | Used by helper? |
|---|---|---|
| `page size of N bytes` | Page size (16 KiB on Apple Silicon, 4 KiB on Intel). | Yes — to convert page counts to bytes. |
| `Pages free` | Physically free pages. | Yes — `free_bytes = pages_free * page_size`. |
| `Pages inactive` | Pages backing files but not in active working sets; reclaimable. | Yes — `available_bytes = (pages_free + pages_inactive + pages_speculative + pages_purgeable) * page_size`. macOS "Memory Pressure" UI counts these as available. |
| `Pages speculative` | Speculatively read-ahead pages; reclaimable. | Yes — included in available. |
| `Pages purgeable` | Purgeable user pages; reclaimable. | Yes — included in available. |
| `Pages wired down` | Kernel-resident; not reclaimable. | No (informational, in snapshot for debugging). |
| `Pages stored in compressor` / `Pages occupied by compressor` | Compressed pages; memory-pressure indicator. | No directly, but snapshot carries the ratio for debugging. |
| Everything else | Counters, not capacity. | No. |

Counters (`Translation faults`, `Pages copy-on-write`, `Pages zero filled`, `Pageins`, `Pageouts`, `Compressions`, `Decompressions`, `Swapins`, `Swapouts`, `Pages reactivated`, `Pages purged`) accumulate since boot and are not meaningful at a single snapshot. They are not used.

### `sysctl vm.swapusage`

```
vm.swapusage: total = 8192.00M  used = 7088.38M  free = 1103.62M  (encrypted)
```

What we read:

| Field | Meaning | Used by helper? |
|---|---|---|
| `total` | Total swap allocated by the OS, in megabytes. | Yes — denominator for `swap_used_pct`. |
| `used` | Bytes of swap currently in use, in megabytes. | Yes — `swap_used_pct = used / total * 100`. |
| `free` | Redundant with `total - used`. | No. |
| `(encrypted)` | macOS swap is always encrypted; informational. | No (in snapshot for debugging). |

### Parsing notes

- `vm_stat` formats every numeric field with a trailing period. Strip before parsing.
- The page-size header is `page size of N bytes` (space-separated, lowercase). Parse on the literal substring `page size of `, extract integer up to the next space.
- The `"Translation faults":` line uses double quotes around the key, unlike other lines. Robust parser splits on `:` and strips whitespace + trailing period from the value.
- `sysctl vm.swapusage` always prints megabytes with a trailing `M`; the numeric portion is float-parseable after stripping `M`.
- On a fresh boot before any swap is allocated, `vm.swapusage` may print `total = 0.00M`; the helper must handle divide-by-zero (treat as `swap_used_pct = 0.0`).

### Failure modes

- `vm_stat` rarely fails on a healthy system. Subprocess timeout: 2 seconds (vastly overprovisioned; real wall-clock is ~10 ms). Non-zero exit OR malformed output → helper returns `(False, {"error": "<reason>", "platform": "darwin"})` (conservative: pressure unknown means do not spawn).
- `sysctl` can fail in sandboxed contexts; same conservative fallback.

---

## 3. (b) psutil equivalents and semantic gaps

`psutil.virtual_memory()` returns a named tuple with the fields the helper needs:

| psutil field | Semantic | Maps to which macOS-snapshot field? |
|---|---|---|
| `total` | Total physical RAM in bytes. | Sum of all `vm_stat` page categories × page size. |
| `available` | Bytes the OS thinks are immediately available without swapping (Linux: `MemAvailable` from `/proc/meminfo`). | Closest analog to `(pages_free + pages_inactive + pages_speculative + pages_purgeable) × page_size` from `vm_stat`. |
| `free` | Strictly unallocated bytes (Linux: `MemFree` from `/proc/meminfo`). | Closest analog to `pages_free × page_size`. |
| `used`, `active`, `inactive`, `buffers`, `cached`, `shared`, `slab` | Linux-only or platform-dependent. | Not used by the helper. |
| `percent` | OS-reported memory utilization percent. | Not used (we compute our own from `total - available`). |

`psutil.swap_memory()` returns:

| psutil field | Semantic | Maps to which macOS-snapshot field? |
|---|---|---|
| `total` | Total swap (bytes). | `vm.swapusage` `total` × 1 MiB. |
| `used` | Used swap (bytes). | `vm.swapusage` `used` × 1 MiB. |
| `free` | Free swap (bytes). | `vm.swapusage` `free` × 1 MiB. |
| `percent` | Used / total × 100. | We recompute to handle `total == 0`. |
| `sin`, `sout` | Cumulative swap-in / swap-out byte counters since boot. | Not used (counters, not capacity). |

### Semantic gap 1: "available" definition differs

macOS `vm_stat` does not have an explicit `MemAvailable` line. The helper's macOS snapshot computes `available = pages_free + pages_inactive + pages_speculative + pages_purgeable`, which matches what macOS's own Activity Monitor reports as "App Memory + File Cache available". On Linux, `psutil.virtual_memory().available` uses the kernel's `MemAvailable` calculation, which considers reclaimable slab and adjusts for low-memory reserves. The two numbers are not bit-identical even on identical workloads, but both are "bytes the system can give a new allocation without swap pressure", which is the right semantic for the spawn-or-not decision.

**Resolution:** the helper's `safe` predicate is defined in terms of "the OS's idea of available memory" on each platform. We do not normalize beyond that; the threshold (`min_free_mb`, default 512 MiB) is a coarse-enough decision that a 5-10 % difference between platforms is within the operator's tolerance. Snapshot includes both `available_mb` and `free_mb` so an operator debugging a false positive can see both.

### Semantic gap 2: macOS compressor

macOS compresses pages in RAM before swapping. A machine with 0 swap used but 1 GB in the compressor is under more memory pressure than the swap counter suggests. The snapshot includes `compressor_mb` for visibility. The helper does not bake compressor pressure into `safe` because the macOS "memory pressure" semantic that the operator cares about (will spawning a worker cause beachballs?) is already captured by `available_mb` + `swap_used_pct`. Linux has no compressor analog (zswap exists but is opt-in and uncommon on dev machines).

**Resolution:** snapshot-only; not used in the `safe` predicate. A future revision may add a `min_compressor_headroom_mb` parameter if the operator finds the current predicate too optimistic on real workloads.

### Semantic gap 3: page size

Apple Silicon uses 16 KiB pages; Intel Mac uses 4 KiB; Linux is usually 4 KiB but configurable. The macOS helper reads page size from `vm_stat` header. The psutil path returns bytes directly, so page size is not in the dispatcher's API.

**Resolution:** snapshot exposes `page_size_bytes` on the macOS path; the psutil path omits it (returns `None`). Tests assert the field is omitted on Linux, present on macOS.

### Semantic gap 4: swap on a swap-less machine

A machine with no swap configured (some Linux containers, some development setups) returns `psutil.swap_memory().total == 0`. The helper treats `swap_used_pct = 0.0` in that case (no swap means no swap pressure). The same divide-by-zero guard applies to macOS where `vm.swapusage` prints `total = 0.00M` before first paging.

**Resolution:** explicit `if total == 0: pct = 0.0` in both snapshot helpers.

### Why not just use psutil everywhere

We could. Honest counter-argument: psutil is mature, cross-platform, maintained, and would let us delete the shellout parsers entirely. The reason we keep both:

- **Runtime dependency hygiene.** psutil is a C extension that has had wheel-build issues on macOS (`libffi` linkage on M1 in 2023; resolved but illustrates the pattern). Carrel's production target is macOS desktop. Keeping the macOS path shellout-based means a broken psutil wheel does not break ingestion; it only breaks the CI matrix entry.
- **Operator visibility on the production platform.** The shellout snapshot includes `compressor_mb` and `page_size_bytes`, which the psutil snapshot cannot provide. These are debugging signals operators on macOS will want when a worker is incorrectly gated.
- **Smallest cross-platform-compatible API surface.** psutil is on dev-deps. Production macOS does not import it.

If the operator decides later they want psutil-everywhere, the path is: delete the macOS snapshot helper, route the dispatcher's macOS branch to the psutil snapshot, drop psutil from dev-deps and add to runtime-deps. One-day swap. The decision is reversible.

---

## 4. (c) platform-dispatch shape

```python
# services/ingestion/memory_pressure.py

from __future__ import annotations

import os
import sys
from typing import Final, TypedDict


class MemorySnapshot(TypedDict, total=False):
    platform: str           # "darwin" | "linux" | "win32" | ...
    available_mb: float     # OS's idea of memory available for a new allocation
    free_mb: float          # strictly unallocated
    total_mb: float
    swap_used_mb: float
    swap_total_mb: float
    swap_used_pct: float
    compressor_mb: float    # macOS only
    page_size_bytes: int    # macOS only (snapshot debug aid)
    error: str              # populated iff snapshot collection failed


_FORCE_PSUTIL_ENV: Final = "CARREL_FORCE_PSUTIL_MEMORY"


def is_safe_to_start_worker(
    *,
    min_free_mb: int = 512,
    max_swap_used_pct: float = 75.0,
) -> tuple[bool, MemorySnapshot]:
    """Return (safe, snapshot). Conservative: snapshot errors mean not safe."""
    snapshot = _snapshot()
    if "error" in snapshot:
        return False, snapshot
    safe = (
        snapshot.get("available_mb", 0.0) >= float(min_free_mb)
        and snapshot.get("swap_used_pct", 100.0) <= max_swap_used_pct
    )
    return safe, snapshot


def _snapshot() -> MemorySnapshot:
    if os.environ.get(_FORCE_PSUTIL_ENV) == "1":
        return _psutil_memory_snapshot()
    if sys.platform == "darwin":
        return _macos_memory_snapshot()
    return _psutil_memory_snapshot()


def _macos_memory_snapshot() -> MemorySnapshot:
    """vm_stat + sysctl vm.swapusage. macOS only."""
    ...


def _psutil_memory_snapshot() -> MemorySnapshot:
    """psutil.virtual_memory + psutil.swap_memory. Linux + Windows + macOS fallback."""
    ...
```

Key design decisions baked into the shape:

1. **One public function.** `is_safe_to_start_worker` is the entire public API. Callers do not import private helpers.
2. **TypedDict snapshot.** Not a dataclass, not a namedtuple. TypedDict is the right shape because some fields are platform-specific (`compressor_mb`, `page_size_bytes`) and TypedDict's `total=False` cleanly expresses "may or may not be present" without `Optional[T]` noise everywhere. Callers that want the structured access pattern can wrap in their own dataclass downstream.
3. **`CARREL_FORCE_PSUTIL_MEMORY=1` escape hatch.** Forces the psutil path on macOS for CI parity and for operator-side debugging. Read once per call (not cached), so flipping the env between tests works.
4. **Conservative on snapshot failure.** If the snapshot collection itself errors (subprocess timeout, parse failure, psutil import error), return `(False, {"error": "..."})`. Pressure-unknown means do not spawn. This matches the no-silent-fallback rule (a snapshot-collection failure is visibly returned, not papered over).
5. **Module sits under `services/ingestion/`.** Slot brief specifies that subtree. The eventual consumers (`services/jobs.py`, `script/reingest_all.py`) live adjacent.
6. **No `import psutil` at module top.** The psutil import lives inside `_psutil_memory_snapshot` so importing the module on a machine without psutil does not error. The function returns `{"error": "psutil_not_available"}` if the import fails.

### Why TypedDict and not a dataclass

A dataclass forces every field to be declared, which means platform-specific fields like `compressor_mb` either get a `None` default (noisy) or a separate `darwin_only_extras: dict` field (also noisy). A TypedDict with `total=False` says "here are the field types if present" and lets callers do `snapshot.get("compressor_mb")`. Snapshot is read-mostly debug data; mutation is not a concern; class methods would be ceremony.

### Why no caching

The snapshot is cheap (~10 ms on macOS for both shellouts combined; ~1 ms with psutil). Caching introduces staleness, which defeats the purpose for an adaptive-concurrency loop that wants a fresh decision each tick. If a future caller wants to amortize calls, they cache at the caller layer.

### Why `min_free_mb` defaults to 512

This is the smallest defensible default. The status.md from 2026-05-21 noted the project's heaviest path (a 1480-page biology PDF re-ingest) routinely runs the dev machine down to ~60-100 MB free. 512 MiB is enough headroom to fit one more Docling parse worker without immediately tipping into beachball territory on a 16 GB Mac. The default is exposed as a keyword argument so callers (especially `script/reingest_all.py` on constrained machines) can pass a smaller value to allow tighter packing.

### Why `max_swap_used_pct` defaults to 75

`vm.swapusage` reading >75% is a strong signal that the OS is actively paging hot pages, which makes a new worker fight for swap I/O and hurt the foreground app's responsiveness. The number is operator-tunable but the default is chosen to leave headroom before the OS reaches genuinely-thrashing levels (~90%+).

---

## 5. (d) test strategy

### Unit tests (live alongside the module)

`tests/test_memory_pressure.py`:

1. `test_macos_snapshot_parses_vm_stat` — feeds a fixture of real `vm_stat` output (captured 2026-05-25, shown in §2) into a private parser; asserts the returned snapshot has all expected fields with reasonable values.
2. `test_macos_snapshot_parses_sysctl_swapusage` — same idea for the swap shellout.
3. `test_macos_snapshot_handles_zero_swap` — fixture with `total = 0.00M`; asserts `swap_used_pct == 0.0` (no divide-by-zero crash).
4. `test_macos_snapshot_handles_subprocess_failure` — mocks subprocess to raise; asserts `error` key populated and `safe=False`.
5. `test_macos_snapshot_handles_malformed_vm_stat` — fixture with the page-size header missing; asserts graceful `error` path.
6. `test_psutil_snapshot_uses_psutil` — patches `psutil.virtual_memory` and `psutil.swap_memory`; asserts the returned snapshot matches expected shape.
7. `test_psutil_snapshot_handles_import_error` — patches `psutil` import to raise; asserts `error` key with `psutil_not_available`.
8. `test_psutil_snapshot_handles_zero_swap` — psutil reports `swap_memory().total == 0`; asserts `swap_used_pct == 0.0`.
9. `test_dispatcher_uses_macos_on_darwin` — patches `sys.platform = "darwin"` and `CARREL_FORCE_PSUTIL_MEMORY` unset; asserts the macOS helper is called (mock).
10. `test_dispatcher_uses_psutil_on_linux` — patches `sys.platform = "linux"`; asserts psutil helper is called.
11. `test_dispatcher_force_psutil_env_overrides_darwin` — patches `sys.platform = "darwin"` AND sets `CARREL_FORCE_PSUTIL_MEMORY=1`; asserts psutil helper is called.
12. `test_is_safe_returns_true_above_thresholds` — mocks `_snapshot` to return ample free + low swap; asserts `safe=True`.
13. `test_is_safe_returns_false_below_min_free_mb` — mocks `_snapshot` with `available_mb < min_free_mb`; asserts `safe=False`.
14. `test_is_safe_returns_false_above_max_swap_pct` — mocks `_snapshot` with `swap_used_pct > max_swap_used_pct`; asserts `safe=False`.
15. `test_is_safe_returns_false_on_snapshot_error` — mocks `_snapshot` to return `{"error": "..."}`; asserts `safe=False` regardless of thresholds.

### Integration test (macOS only, opt-in)

`tests/integration/test_memory_pressure_macos.py`, gated on `sys.platform == "darwin"` and `CARREL_RUN_MEMORY_PRESSURE_INTEGRATION=1`:

- Calls `is_safe_to_start_worker()` against the real OS, asserts the snapshot has reasonable shape (positive `total_mb`, `0 <= swap_used_pct <= 100`, `page_size_bytes in {4096, 16384}`).
- Not run in the default verify chain. Operators run it manually on a fresh Mac to confirm parsing handles their machine's `vm_stat` flavour.

### CI matrix (T4 deliverable)

The existing GitHub Actions workflow runs on `macos-latest`. T4 adds an `ubuntu-latest` matrix entry that:

- Installs `psutil` (dev-deps).
- Sets `CARREL_FORCE_PSUTIL_MEMORY=1`.
- Runs only `tests/test_memory_pressure.py` (not the full backend suite, which has macOS-specific dependencies like PDFKit / Vision via the Swift sidecar). This proves the psutil path works on a real Linux runner.

If the broader ingestion suite later becomes Linux-clean, the matrix entry can be widened. For now, T4 is the narrow first step.

### Test strategy for the dispatcher's force-psutil escape hatch

The unit tests cover this with platform mocks. The CI matrix proves it on a real Linux runner. The macOS integration test does NOT exercise it (the env flag is only meaningful as a fallback signal).

---

## 6. Sub-PR decomposition (T2 / T3 / T4)

### T2 — Sub-PR 1: macOS snapshot helper

Creates `services/ingestion/memory_pressure.py` with:

- `MemorySnapshot` TypedDict.
- `_macos_memory_snapshot()` private function with full vm_stat + sysctl parsing.
- `_parse_vm_stat(text: str) -> dict[str, int]` and `_parse_sysctl_swapusage(text: str) -> dict[str, float]` private parsers (separated for testability).
- A stub `_psutil_memory_snapshot()` and `_snapshot()` dispatcher that raises `NotImplementedError` (T3 fills these in).
- A stub `is_safe_to_start_worker()` that wires through the dispatcher.

Tests: items 1-5, 9 from §5 (the macOS unit tests).

Lines: ~150 (helper) + ~100 (tests). No new dependencies. No behavior change to existing callers (there are none yet).

**Acceptance:** `pytest tests/test_memory_pressure.py -v` passes the 6 added tests. `ruff check` + `ruff format --check` clean. No other test regressions.

### T3 — Sub-PR 2: psutil snapshot + dispatcher

Adds:

- `_psutil_memory_snapshot()` with the full psutil-path body.
- `_snapshot()` dispatcher with the platform branch + `CARREL_FORCE_PSUTIL_MEMORY` escape hatch.
- `is_safe_to_start_worker()` with the threshold-comparison body.
- `psutil` to `requirements-dev.txt` (NOT `requirements.txt`; macOS production stays on shellouts).

Tests: items 6-8, 10-15 from §5 (the psutil + dispatcher + predicate tests).

Lines: ~80 (helper additions) + ~150 (tests). One new dev dep.

**Acceptance:** all 15 tests in §5 pass. dev-deps install on a fresh venv. macOS production import path (no psutil import unless dispatcher routes to it) verified by a `test_module_imports_without_psutil` test that uses `sys.modules` manipulation.

**Open question (resolve in T3 PR description, default to dev-deps):** should psutil be a runtime dependency or a dev-only dependency? Default answer: dev-only. macOS desktop production never executes `_psutil_memory_snapshot()` because the dispatcher routes to `_macos_memory_snapshot()` first. The only production path that hits psutil is `CARREL_FORCE_PSUTIL_MEMORY=1`, which is an operator-set debugging flag. If the operator wants Linux-production support someday, they edit one file (`requirements.txt`) and we're done. The decision is reversible.

### T4 — Sub-PR 3: CI matrix

Adds an `ubuntu-latest` matrix entry to the GitHub Actions workflow that runs `tests/test_memory_pressure.py` with `CARREL_FORCE_PSUTIL_MEMORY=1` and psutil installed.

Lines: ~30 (YAML diff).

**Acceptance:** the new CI matrix job is green. The macOS CI job continues to pass unchanged (because the helper has no consumers).

---

## 7. Independence assertion (slot brief)

Per `.claude/fleet/TODOS.fleet-2.md`: "If a sub-PR finds itself needing to edit `services/retrieval/`, `services/tutor.py`, `evals/`, or anything under `ai/`, STOP."

This plan touches only `services/ingestion/memory_pressure.py` (new file), `tests/test_memory_pressure.py` (new file), `tests/integration/test_memory_pressure_macos.py` (new file, opt-in only), `requirements-dev.txt` (one-line addition in T3), and `.github/workflows/*.yml` (matrix entry in T4). No retrieval, tutor, eval, or ai code is touched. Slot independence holds.

---

## 8. Acceptance (overall) and kill conditions

### Overall acceptance (after T4 lands)

- `services/ingestion/memory_pressure.py` exists with the public function `is_safe_to_start_worker(*, min_free_mb, max_swap_used_pct) -> tuple[bool, MemorySnapshot]`.
- All 15 unit tests in §5 pass on macOS CI.
- Same tests pass on ubuntu-latest with `CARREL_FORCE_PSUTIL_MEMORY=1`.
- `grep -rn "import psutil" services/` returns ONLY `services/ingestion/memory_pressure.py` (no runtime-side imports leak in).
- macOS production import of `services.ingestion.memory_pressure` succeeds without `psutil` installed (proven by the dedicated test).
- No existing test regresses on either platform.
- `docs/plans/cross-platform-memory-pressure-fallback.md` (this file) is updated to mark each sub-PR done with commit SHA + PR number.

### Kill conditions (if any fire, stop the slot and surface)

- T2 lines of code exceed 250 (sign the design grew beyond TypedDict + shellout parsers, needs re-debate).
- T3 introduces a runtime psutil dependency (must remain dev-only without explicit operator approval).
- Any sub-PR adds a memory-pressure consumer (consumer wiring is a separate plan).
- macOS shellouts behave differently on Apple Silicon vs Intel in a way the integration test surfaces; pause T3 and revise §2 before proceeding.
- psutil's Linux `MemAvailable` value diverges from the macOS-snapshot `available_mb` by more than 25% on a side-by-side dev-machine smoke (signals that the cross-platform semantic is shakier than this plan claims).

---

## 9. Open questions surfaced to operator

These are recorded as operator follow-ups but do not block the plan:

1. **Should the existing `services/jobs.py:_EXECUTOR` (fixed at 2) and `script/reingest_all.py` (default 4) start consuming `is_safe_to_start_worker` once it lands?** Out of scope for this slot. The follow-up plan `adaptive-ingestion-concurrency.md` (not yet written) would cover that wiring. Suggested timing: after T57 (typed-node ingest path) is fully stable in production. Surfaced in `.claude/logs/operator-followups.jsonl`.

2. **Does the macOS snapshot's `compressor_mb` field belong in the `safe` predicate?** Default in this plan: no, snapshot-only. If real workloads show false negatives where the helper reports `safe=True` but spawning a worker causes beachballs because the compressor is full, revise. Recorded as an operator follow-up so it gets revisited after the first consumer lands.

3. **Should the helper return enough information for a callable to also choose a worker count (not just safe/unsafe)?** Plan says no, the predicate is binary by design. A future revision can add a `recommended_worker_count(*, max_workers)` companion function that takes the snapshot and returns an integer. Out of scope for T2-T4.

---

## 10. Verify chain (per task)

T2 and T3 both run the canonical chain. T4 runs the chain plus the new ubuntu CI matrix job. The chain is at `CLAUDE.md` §"Verify chain (run before any merge)" lines 39-49.

Skipped steps with rationale:

- **`./script/build_and_run.sh --verify`**: this is a docs/utility module with no Swift, no frontend, no AI provider, no DB migration. The verify step would catch a regression unrelated to this work. Run it; if it passes, fine. If it fails for unrelated reasons, surface in PR body.
- **`benchmarks/phase0 --fail-on-regression`**: same rationale. No phase0 surface is touched.
- **`tests/test_watchdog_kill.sh`**: same rationale.
- **`swift test --package-path macos-app`**: same rationale.

Full chain still runs; the rationale is only relevant if a step regresses for unrelated reasons (operator decides whether to investigate or surface).
