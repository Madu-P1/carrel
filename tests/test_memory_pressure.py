"""Tests for services.ingestion.memory_pressure (T2-redux per ADR 0007)."""

from __future__ import annotations

import os
import subprocess
import sys
import types
import unittest
from unittest import mock

from services.ingestion import memory_pressure

VM_STAT_NORMAL = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                              45000.
Pages active:                            120000.
Pages inactive:                          80000.
Pages speculative:                       5000.
Pages throttled:                              0.
Pages wired down:                        60000.
Pages purgeable:                         2000.
"Translation faults":                  9876543.
Pages copy-on-write:                     12345.
Pages zero filled:                       54321.
Pages reactivated:                        6789.
Compressor pages used:                   30000.
"""

VM_STAT_MISSING_PAGE_SIZE = """Mach Virtual Memory Statistics:
Pages free:                              45000.
Pages inactive:                          80000.
"""

SYSCTL_NORMAL = "vm.swapusage: total = 4096.00M  used = 1024.00M  free = 3072.00M  (encrypted)\n"
SYSCTL_ZERO_TOTAL = "vm.swapusage: total = 0.00M  used = 0.00M  free = 0.00M  (encrypted)\n"
SYSCTL_MALFORMED = "vm.swapusage: not what we expected\n"


class ParserTests(unittest.TestCase):
    def test_parse_vm_stat_normal(self):
        fields = memory_pressure._parse_vm_stat(VM_STAT_NORMAL)
        self.assertEqual(fields["page_size_bytes"], 16384)
        self.assertEqual(fields["free"], 45000)
        self.assertEqual(fields["inactive"], 80000)
        self.assertEqual(fields["speculative"], 5000)
        self.assertEqual(fields["purgeable"], 2000)
        self.assertEqual(fields["compressor"], 30000)

    def test_parse_vm_stat_missing_page_size_raises(self):
        with self.assertRaises(ValueError):
            memory_pressure._parse_vm_stat(VM_STAT_MISSING_PAGE_SIZE)

    def test_parse_sysctl_swapusage_normal(self):
        fields = memory_pressure._parse_sysctl_swapusage(SYSCTL_NORMAL)
        self.assertAlmostEqual(fields["total_mb"], 4096.0)
        self.assertAlmostEqual(fields["used_mb"], 1024.0)
        self.assertAlmostEqual(fields["used_pct"], 25.0)

    def test_parse_sysctl_swapusage_zero_total_no_divide_by_zero(self):
        fields = memory_pressure._parse_sysctl_swapusage(SYSCTL_ZERO_TOTAL)
        self.assertEqual(fields["total_mb"], 0.0)
        self.assertEqual(fields["used_mb"], 0.0)
        self.assertEqual(fields["used_pct"], 0.0)

    def test_parse_sysctl_swapusage_malformed_raises(self):
        with self.assertRaises(ValueError):
            memory_pressure._parse_sysctl_swapusage(SYSCTL_MALFORMED)


def _stub_psutil_module(
    *,
    total_bytes: int = 16 * 1024 * 1024 * 1024,
    available_bytes: int = 8 * 1024 * 1024 * 1024,
    free_bytes: int = 4 * 1024 * 1024 * 1024,
    swap_total_bytes: int = 4 * 1024 * 1024 * 1024,
    swap_used_bytes: int = 1 * 1024 * 1024 * 1024,
) -> types.SimpleNamespace:
    """Return a SimpleNamespace mimicking the psutil module surface we use."""
    vm = types.SimpleNamespace(total=total_bytes, available=available_bytes, free=free_bytes)
    swap = types.SimpleNamespace(total=swap_total_bytes, used=swap_used_bytes)
    return types.SimpleNamespace(
        virtual_memory=lambda: vm,
        swap_memory=lambda: swap,
    )


class PsutilSnapshotTests(unittest.TestCase):
    def test_psutil_snapshot_normal(self):
        stub = _stub_psutil_module()
        with mock.patch.dict(sys.modules, {"psutil": stub}):
            snap = memory_pressure._psutil_memory_snapshot()
        self.assertNotIn("error", snap)
        self.assertAlmostEqual(snap["total_mb"], 16384.0)
        self.assertAlmostEqual(snap["available_mb"], 8192.0)
        self.assertAlmostEqual(snap["swap_total_mb"], 4096.0)
        self.assertAlmostEqual(snap["swap_used_mb"], 1024.0)
        self.assertAlmostEqual(snap["swap_used_pct"], 25.0)

    def test_psutil_snapshot_zero_swap(self):
        stub = _stub_psutil_module(swap_total_bytes=0, swap_used_bytes=0)
        with mock.patch.dict(sys.modules, {"psutil": stub}):
            snap = memory_pressure._psutil_memory_snapshot()
        self.assertEqual(snap["swap_total_mb"], 0.0)
        self.assertEqual(snap["swap_used_pct"], 0.0)

    def test_psutil_snapshot_import_error(self):
        # Remove psutil from sys.modules AND block the import.
        original_psutil = sys.modules.pop("psutil", None)
        try:
            real_import = (
                __builtins__["__import__"]
                if isinstance(__builtins__, dict)
                else __builtins__.__import__
            )

            def _blocking_import(name, *args, **kwargs):
                if name == "psutil":
                    raise ImportError("psutil is not installed (synthetic)")
                return real_import(name, *args, **kwargs)

            with mock.patch("builtins.__import__", side_effect=_blocking_import):
                snap = memory_pressure._psutil_memory_snapshot()
            self.assertIn("error", snap)
            self.assertIn("psutil import failed", snap["error"])
        finally:
            if original_psutil is not None:
                sys.modules["psutil"] = original_psutil


class DispatcherTests(unittest.TestCase):
    def test_dispatcher_picks_macos_path_on_darwin(self):
        env_without_force = {
            k: v for k, v in os.environ.items() if k != "CARREL_FORCE_PSUTIL_MEMORY"
        }
        with (
            mock.patch.object(memory_pressure.sys, "platform", "darwin"),
            mock.patch.dict(os.environ, env_without_force, clear=True),
            mock.patch.object(
                memory_pressure, "_macos_memory_snapshot", return_value={"platform": "darwin-stub"}
            ) as mac_stub,
            mock.patch.object(
                memory_pressure, "_psutil_memory_snapshot", return_value={"platform": "psutil-stub"}
            ) as psutil_stub,
        ):
            snap = memory_pressure._snapshot()
        mac_stub.assert_called_once()
        psutil_stub.assert_not_called()
        self.assertEqual(snap["platform"], "darwin-stub")

    def test_dispatcher_picks_psutil_path_on_linux(self):
        env_without_force = {
            k: v for k, v in os.environ.items() if k != "CARREL_FORCE_PSUTIL_MEMORY"
        }
        with (
            mock.patch.object(memory_pressure.sys, "platform", "linux"),
            mock.patch.dict(os.environ, env_without_force, clear=True),
            mock.patch.object(
                memory_pressure, "_macos_memory_snapshot", return_value={"platform": "darwin-stub"}
            ) as mac_stub,
            mock.patch.object(
                memory_pressure, "_psutil_memory_snapshot", return_value={"platform": "psutil-stub"}
            ) as psutil_stub,
        ):
            snap = memory_pressure._snapshot()
        mac_stub.assert_not_called()
        psutil_stub.assert_called_once()
        self.assertEqual(snap["platform"], "psutil-stub")

    def test_dispatcher_force_psutil_overrides_darwin(self):
        with (
            mock.patch.object(memory_pressure.sys, "platform", "darwin"),
            mock.patch.dict(os.environ, {"CARREL_FORCE_PSUTIL_MEMORY": "1"}),
            mock.patch.object(
                memory_pressure, "_macos_memory_snapshot", return_value={"platform": "darwin-stub"}
            ) as mac_stub,
            mock.patch.object(
                memory_pressure, "_psutil_memory_snapshot", return_value={"platform": "psutil-stub"}
            ) as psutil_stub,
        ):
            snap = memory_pressure._snapshot()
        mac_stub.assert_not_called()
        psutil_stub.assert_called_once()
        self.assertEqual(snap["platform"], "psutil-stub")


class MacosSnapshotTests(unittest.TestCase):
    """End-to-end macOS snapshot via subprocess mocks. Verifies the parser
    plumbing ties to the shellout output the helper actually consumes."""

    def test_macos_snapshot_happy_path(self):
        def fake_check_output(cmd, **_kwargs):
            if cmd[0] == "vm_stat":
                return VM_STAT_NORMAL
            if cmd[:2] == ["sysctl", "vm.swapusage"]:
                return SYSCTL_NORMAL
            raise AssertionError(f"unexpected subprocess: {cmd!r}")

        with mock.patch.object(subprocess, "check_output", side_effect=fake_check_output):
            snap = memory_pressure._macos_memory_snapshot()
        self.assertEqual(snap["platform"], "darwin")
        self.assertEqual(snap["page_size_bytes"], 16384)
        # (45000 + 80000 + 5000 + 2000) pages * 16384 bytes / 1MB = 2062.5 MB
        self.assertAlmostEqual(snap["available_mb"], 2062.5)
        self.assertAlmostEqual(snap["free_mb"], 703.125)
        self.assertAlmostEqual(snap["compressor_mb"], 468.75)
        self.assertAlmostEqual(snap["swap_used_pct"], 25.0)

    def test_macos_snapshot_vm_stat_subprocess_error(self):
        def fake_check_output(cmd, **_kwargs):
            raise FileNotFoundError("vm_stat: no such binary")

        with mock.patch.object(subprocess, "check_output", side_effect=fake_check_output):
            snap = memory_pressure._macos_memory_snapshot()
        self.assertIn("error", snap)
        self.assertIn("vm_stat", snap["error"])


class RecommendedWorkerCountTests(unittest.TestCase):
    def _patch_snapshot(self, snapshot):
        return mock.patch.object(memory_pressure, "_snapshot", return_value=snapshot)

    def test_plenty_of_memory_returns_max(self):
        with self._patch_snapshot(
            {"platform": "darwin", "available_mb": 8000.0, "swap_used_pct": 10.0}
        ):
            count, snap = memory_pressure.recommended_worker_count(max_workers=4)
        self.assertEqual(count, 4)
        self.assertEqual(snap["recommended"], 4)

    def test_below_min_free_returns_one(self):
        with self._patch_snapshot(
            {"platform": "darwin", "available_mb": 100.0, "swap_used_pct": 10.0}
        ):
            count, snap = memory_pressure.recommended_worker_count(max_workers=4)
        self.assertEqual(count, 1)
        self.assertEqual(snap["recommended"], 1)

    def test_swap_pressure_returns_one(self):
        with self._patch_snapshot(
            {"platform": "darwin", "available_mb": 8000.0, "swap_used_pct": 90.0}
        ):
            count, snap = memory_pressure.recommended_worker_count(max_workers=4)
        self.assertEqual(count, 1)
        self.assertEqual(snap["recommended"], 1)

    def test_snapshot_error_returns_one(self):
        with self._patch_snapshot({"platform": "darwin", "error": "vm_stat parse failed: ..."}):
            count, snap = memory_pressure.recommended_worker_count(max_workers=4)
        self.assertEqual(count, 1)
        self.assertEqual(snap["recommended"], 1)

    def test_exact_boundary_matches_max_workers(self):
        # max_workers=4, min_free_mb_per_worker=512, available_mb=2048 → exactly 4.
        with self._patch_snapshot(
            {"platform": "darwin", "available_mb": 2048.0, "swap_used_pct": 0.0}
        ):
            count, snap = memory_pressure.recommended_worker_count(
                max_workers=4, min_free_mb_per_worker=512
            )
        self.assertEqual(count, 4)
        self.assertEqual(snap["recommended"], 4)


class IsSafeToStartWorkerTests(unittest.TestCase):
    def _patch_snapshot(self, snapshot):
        return mock.patch.object(memory_pressure, "_snapshot", return_value=snapshot)

    def test_wrapper_consistent_with_predicate(self):
        # Plenty of memory: safe is True, count >= 1.
        with self._patch_snapshot(
            {"platform": "darwin", "available_mb": 4000.0, "swap_used_pct": 5.0}
        ):
            safe, snap = memory_pressure.is_safe_to_start_worker()
        self.assertTrue(safe)
        self.assertEqual(snap["recommended"], 1)

        # Below headroom: binary returns False even though count API would return 1.
        with self._patch_snapshot(
            {"platform": "darwin", "available_mb": 100.0, "swap_used_pct": 5.0}
        ):
            safe, snap = memory_pressure.is_safe_to_start_worker()
        self.assertFalse(safe)
        self.assertEqual(snap["recommended"], 0)

        # Swap pressure: binary returns False.
        with self._patch_snapshot(
            {"platform": "darwin", "available_mb": 4000.0, "swap_used_pct": 90.0}
        ):
            safe, snap = memory_pressure.is_safe_to_start_worker()
        self.assertFalse(safe)
        self.assertEqual(snap["recommended"], 0)


class ModuleImportTests(unittest.TestCase):
    """The module's top-level import must succeed without psutil installed.

    Production macOS never executes the psutil path; the dispatcher routes
    to _macos_memory_snapshot first. Importing the module on a vanilla
    install (no requirements-dev.txt) must therefore not raise.
    """

    def test_module_imports_without_psutil(self):
        original_psutil = sys.modules.pop("psutil", None)
        # Drop the cached module so re-import would re-load it.
        sys.modules.pop("services.ingestion.memory_pressure", None)
        try:
            real_import = (
                __builtins__["__import__"]
                if isinstance(__builtins__, dict)
                else __builtins__.__import__
            )

            def _blocking_import(name, *args, **kwargs):
                if name == "psutil" or name.startswith("psutil."):
                    raise ImportError("psutil is not installed (synthetic)")
                return real_import(name, *args, **kwargs)

            with mock.patch("builtins.__import__", side_effect=_blocking_import):
                # The module-level import block must NOT mention psutil at the top.
                import importlib

                imported = importlib.import_module("services.ingestion.memory_pressure")
            self.assertTrue(hasattr(imported, "recommended_worker_count"))
            self.assertTrue(hasattr(imported, "is_safe_to_start_worker"))
        finally:
            if original_psutil is not None:
                sys.modules["psutil"] = original_psutil


if __name__ == "__main__":
    unittest.main()
