"""Cross-platform memory-pressure helper for ingestion pool sizing.

Public surface:

- ``recommended_worker_count(*, max_workers, ...) -> tuple[int, MemorySnapshot]``
  is the primary API. Callers that need to size a worker pool ask "given my
  cap of M workers, how many should I actually start?" once at pool
  construction. The returned count is in ``[1, max_workers]``.

- ``is_safe_to_start_worker(...) -> tuple[bool, MemorySnapshot]`` is a 10-line
  binary wrapper for callers that have already decided to submit one unit of
  work and only need a yes/no answer.

The dispatcher routes to a macOS ``vm_stat`` + ``sysctl vm.swapusage`` path on
Darwin and a ``psutil`` path elsewhere. ``CARREL_FORCE_PSUTIL_MEMORY=1`` forces
the psutil path on Darwin for CI parity. ``psutil`` is imported inside the
function so module import does not require it on production macOS, where the
shellout path is the only one ever executed.

See ``docs/plans/adaptive-ingestion-concurrency.md`` §3 and
``docs/decisions/0007-adaptive-ingestion-first-consumer.md``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import TypedDict


class MemorySnapshot(TypedDict, total=False):
    platform: str
    available_mb: float
    free_mb: float
    total_mb: float
    swap_used_mb: float
    swap_total_mb: float
    swap_used_pct: float
    compressor_mb: float
    page_size_bytes: int
    recommended: int
    error: str


_DEFAULT_MIN_FREE_MB_PER_WORKER = 512
_DEFAULT_MAX_SWAP_USED_PCT = 75.0


def _parse_vm_stat(text: str) -> dict[str, float | int]:
    """Parse the output of ``vm_stat`` into a dict of page counts.

    Returns at least ``page_size_bytes`` and the page counters used by the
    snapshot path (``free``, ``inactive``, ``speculative``, ``purgeable``,
    ``compressor``). Values are integers; ``page_size_bytes`` is the page
    size in bytes (commonly 4096 on x86_64 and 16384 on Apple Silicon).

    Raises ``ValueError`` on malformed output (missing page size or no
    page counters).
    """
    page_size: int | None = None
    pages: dict[str, int] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if "page size of" in line.lower():
            for token in line.split():
                if token.isdigit():
                    page_size = int(token)
                    break
            continue
        if ":" not in line:
            continue
        label, _, value = line.partition(":")
        value = value.strip().rstrip(".")
        if not value.isdigit():
            continue
        label_lower = label.lower()
        if "pages free" in label_lower:
            pages["free"] = int(value)
        elif "pages inactive" in label_lower:
            pages["inactive"] = int(value)
        elif "pages speculative" in label_lower:
            pages["speculative"] = int(value)
        elif "pages purgeable" in label_lower:
            pages["purgeable"] = int(value)
        elif "compressor pages used" in label_lower:
            pages["compressor"] = int(value)
    if page_size is None:
        raise ValueError("vm_stat output missing page size header")
    if not pages:
        raise ValueError("vm_stat output contained no recognized page counters")
    return {"page_size_bytes": page_size, **pages}


def _parse_sysctl_swapusage(text: str) -> dict[str, float]:
    """Parse ``sysctl vm.swapusage`` into ``{total_mb, used_mb, used_pct}``.

    Expected shape: ``vm.swapusage: total = 4096.00M  used = 1024.00M  free = 3072.00M  (encrypted)``.
    A total of zero yields ``used_pct = 0.0`` (no divide-by-zero); the
    Mac may have swap disabled, which is a real configuration.

    Raises ``ValueError`` if total or used cannot be read.
    """
    total_mb: float | None = None
    used_mb: float | None = None
    body = text.strip()
    if "vm.swapusage" in body:
        _, _, body = body.partition(":")
    body = body.strip()
    tokens = body.split()
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token == "=" and i >= 1 and i + 1 < len(tokens):
            key = tokens[i - 1].rstrip(":")
            raw_value = tokens[i + 1]
            try:
                mb = float(raw_value.rstrip("M").rstrip(","))
            except ValueError:
                i += 1
                continue
            if key == "total":
                total_mb = mb
            elif key == "used":
                used_mb = mb
        i += 1
    if total_mb is None or used_mb is None:
        raise ValueError("sysctl vm.swapusage output missing total or used")
    if total_mb <= 0:
        used_pct = 0.0
    else:
        used_pct = (used_mb / total_mb) * 100.0
    return {"total_mb": total_mb, "used_mb": used_mb, "used_pct": used_pct}


def _macos_memory_snapshot() -> MemorySnapshot:
    """Build a snapshot from ``vm_stat`` and ``sysctl vm.swapusage``."""
    snapshot: MemorySnapshot = {"platform": "darwin"}
    try:
        vm_stat_raw = subprocess.check_output(
            ["vm_stat"], stderr=subprocess.DEVNULL, text=True, timeout=5
        )
    except (OSError, subprocess.SubprocessError) as exc:
        snapshot["error"] = f"vm_stat failed: {type(exc).__name__}: {exc}"
        return snapshot
    try:
        vm_stat_fields = _parse_vm_stat(vm_stat_raw)
    except ValueError as exc:
        snapshot["error"] = f"vm_stat parse failed: {exc}"
        return snapshot

    page_size = int(vm_stat_fields["page_size_bytes"])
    snapshot["page_size_bytes"] = page_size

    free_pages = int(vm_stat_fields.get("free", 0))
    inactive_pages = int(vm_stat_fields.get("inactive", 0))
    speculative_pages = int(vm_stat_fields.get("speculative", 0))
    purgeable_pages = int(vm_stat_fields.get("purgeable", 0))
    compressor_pages = int(vm_stat_fields.get("compressor", 0))

    bytes_per_mb = 1024 * 1024
    free_mb = (free_pages * page_size) / bytes_per_mb
    available_mb = (
        (free_pages + inactive_pages + speculative_pages + purgeable_pages) * page_size
    ) / bytes_per_mb
    compressor_mb = (compressor_pages * page_size) / bytes_per_mb

    snapshot["free_mb"] = free_mb
    snapshot["available_mb"] = available_mb
    snapshot["compressor_mb"] = compressor_mb

    try:
        sysctl_raw = subprocess.check_output(
            ["sysctl", "vm.swapusage"], stderr=subprocess.DEVNULL, text=True, timeout=5
        )
    except (OSError, subprocess.SubprocessError) as exc:
        snapshot["error"] = f"sysctl vm.swapusage failed: {type(exc).__name__}: {exc}"
        return snapshot
    try:
        swap_fields = _parse_sysctl_swapusage(sysctl_raw)
    except ValueError as exc:
        snapshot["error"] = f"sysctl vm.swapusage parse failed: {exc}"
        return snapshot

    snapshot["swap_total_mb"] = swap_fields["total_mb"]
    snapshot["swap_used_mb"] = swap_fields["used_mb"]
    snapshot["swap_used_pct"] = swap_fields["used_pct"]
    return snapshot


def _psutil_memory_snapshot() -> MemorySnapshot:
    """Build a snapshot via ``psutil``. Dev-only path on macOS.

    Imports ``psutil`` inside the function so production macOS does not
    require it as a runtime dependency. Linux callers and the
    ``CARREL_FORCE_PSUTIL_MEMORY=1`` debugging path do require it; see
    ``requirements-dev.txt``.
    """
    snapshot: MemorySnapshot = {"platform": sys.platform}
    try:
        import psutil
    except ImportError as exc:
        snapshot["error"] = f"psutil import failed: {exc}"
        return snapshot

    try:
        vm = psutil.virtual_memory()
        swap = psutil.swap_memory()
    except Exception as exc:
        snapshot["error"] = f"psutil read failed: {type(exc).__name__}: {exc}"
        return snapshot

    bytes_per_mb = 1024 * 1024
    snapshot["total_mb"] = vm.total / bytes_per_mb
    snapshot["available_mb"] = vm.available / bytes_per_mb
    snapshot["free_mb"] = vm.free / bytes_per_mb
    snapshot["swap_total_mb"] = swap.total / bytes_per_mb
    snapshot["swap_used_mb"] = swap.used / bytes_per_mb
    snapshot["swap_used_pct"] = 0.0 if swap.total <= 0 else (swap.used / swap.total) * 100.0
    return snapshot


def _snapshot() -> MemorySnapshot:
    """Pick the platform-appropriate snapshot collector.

    ``CARREL_FORCE_PSUTIL_MEMORY=1`` forces the psutil path regardless of
    platform, for CI parity and operator debugging.
    """
    if os.environ.get("CARREL_FORCE_PSUTIL_MEMORY") == "1":
        return _psutil_memory_snapshot()
    if sys.platform == "darwin":
        return _macos_memory_snapshot()
    return _psutil_memory_snapshot()


def recommended_worker_count(
    *,
    max_workers: int,
    min_free_mb_per_worker: int = _DEFAULT_MIN_FREE_MB_PER_WORKER,
    max_swap_used_pct: float = _DEFAULT_MAX_SWAP_USED_PCT,
) -> tuple[int, MemorySnapshot]:
    """Recommend a worker-pool size given the live memory snapshot.

    Returns ``(count, snapshot)`` with ``count`` in ``[1, max_workers]``.
    The count math is::

        count = max(1, min(max_workers, available_mb // min_free_mb_per_worker))

    Conservative on swap pressure (``swap_used_pct > max_swap_used_pct``
    drops the count to 1 regardless of memory headroom) and on snapshot
    error (count is 1, never zero — the caller has work to do and the
    helper is advisory). The returned count is also written back into
    the snapshot's ``recommended`` field for telemetry.
    """
    if max_workers < 1:
        raise ValueError("max_workers must be at least 1")

    snapshot = _snapshot()

    if snapshot.get("error"):
        snapshot["recommended"] = 1
        return 1, snapshot

    swap_used_pct = float(snapshot.get("swap_used_pct", 0.0))
    if swap_used_pct > max_swap_used_pct:
        snapshot["recommended"] = 1
        return 1, snapshot

    available_mb = float(snapshot.get("available_mb", 0.0))
    if min_free_mb_per_worker <= 0:
        raise ValueError("min_free_mb_per_worker must be positive")

    headroom_count = int(available_mb // min_free_mb_per_worker)
    count = max(1, min(max_workers, headroom_count))
    snapshot["recommended"] = count
    return count, snapshot


def is_safe_to_start_worker(
    *,
    min_free_mb: int = _DEFAULT_MIN_FREE_MB_PER_WORKER,
    max_swap_used_pct: float = _DEFAULT_MAX_SWAP_USED_PCT,
) -> tuple[bool, MemorySnapshot]:
    """Binary helper for callers that already plan to submit one unit of work.

    Returns ``(safe, snapshot)``. ``safe`` is True iff the host has at
    least ``min_free_mb`` MB available and swap usage is at or below
    ``max_swap_used_pct``. On snapshot error the predicate yields True —
    the helper is advisory, not a veto, and the caller has work to do.

    This function shares the underlying snapshot + thresholds with
    ``recommended_worker_count`` but does NOT simply wrap it. The
    count API applies a floor of 1 (advisory pool sizing), which would
    make ``count >= 1`` always True and the wrapper useless. The
    binary API applies a floor of 0 (real veto for the future
    ``services/jobs.py`` consumer per ADR 0007 Consequence 7). See
    ``docs/plans/adaptive-ingestion-concurrency.md`` §3.2.
    """
    snapshot = _snapshot()
    if snapshot.get("error"):
        snapshot["recommended"] = 1
        return True, snapshot
    swap_used_pct = float(snapshot.get("swap_used_pct", 0.0))
    if swap_used_pct > max_swap_used_pct:
        snapshot["recommended"] = 0
        return False, snapshot
    available_mb = float(snapshot.get("available_mb", 0.0))
    if available_mb >= min_free_mb:
        snapshot["recommended"] = 1
        return True, snapshot
    snapshot["recommended"] = 0
    return False, snapshot
