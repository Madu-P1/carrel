"""Opt-in macOS integration test for the memory-pressure helper.

Runs the real ``vm_stat`` + ``sysctl vm.swapusage`` shellouts against the
host kernel. Verifies the snapshot shape and the recommendation range.
Gated behind ``CARREL_RUN_MEMORY_PRESSURE_INTEGRATION=1`` so the canonical
verify chain does not depend on host-specific values.

Per ADR 0007 Consequence 2 (T3-redux). See
``docs/notes/2026-05-25-memory-pressure-empirics.md`` for the measurement
pass that drove the opt-in test format.
"""

from __future__ import annotations

import os
import sys
import unittest

from services.ingestion import memory_pressure  # noqa: E402 (test helper import)

_OPT_IN_ENV = "CARREL_RUN_MEMORY_PRESSURE_INTEGRATION"


@unittest.skipUnless(
    sys.platform == "darwin" and os.environ.get(_OPT_IN_ENV) == "1",
    f"requires darwin + {_OPT_IN_ENV}=1",
)
class MemoryPressureMacosIntegrationTests(unittest.TestCase):
    """End-to-end on the real OS. Asserts shape and ranges only; absolute
    numbers depend on the live host and are not pinned."""

    def test_real_snapshot_shape(self):
        snap = memory_pressure._snapshot()
        self.assertEqual(snap.get("platform"), "darwin")
        self.assertNotIn("error", snap, msg=f"snapshot reported error: {snap.get('error')!r}")
        self.assertIn("page_size_bytes", snap)
        self.assertIn(snap["page_size_bytes"], {4096, 16384})
        self.assertIn("available_mb", snap)
        self.assertGreater(float(snap["available_mb"]), 0.0)
        self.assertIn("free_mb", snap)
        self.assertGreaterEqual(float(snap["free_mb"]), 0.0)
        self.assertIn("swap_total_mb", snap)
        self.assertGreaterEqual(float(snap["swap_total_mb"]), 0.0)
        self.assertIn("swap_used_mb", snap)
        self.assertGreaterEqual(float(snap["swap_used_mb"]), 0.0)
        self.assertIn("swap_used_pct", snap)
        self.assertGreaterEqual(float(snap["swap_used_pct"]), 0.0)
        self.assertLessEqual(float(snap["swap_used_pct"]), 100.0)

    def test_real_recommended_worker_count_in_range(self):
        count, snap = memory_pressure.recommended_worker_count(max_workers=4)
        self.assertNotIn("error", snap, msg=f"snapshot reported error: {snap.get('error')!r}")
        self.assertGreaterEqual(count, 1)
        self.assertLessEqual(count, 4)
        self.assertEqual(snap.get("recommended"), count)

    def test_real_is_safe_to_start_worker_returns_bool(self):
        safe, snap = memory_pressure.is_safe_to_start_worker()
        self.assertIsInstance(safe, bool)
        self.assertIn(snap.get("recommended"), (0, 1))


if __name__ == "__main__":
    unittest.main()
