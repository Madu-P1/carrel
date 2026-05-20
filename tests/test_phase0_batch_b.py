import json
import tempfile
import unittest
from pathlib import Path

from benchmarks.phase0 import compare_to_baseline
from evals.run_evals import run_suite


class Phase0BatchBTests(unittest.TestCase):
    def test_benchmark_compare_reports_regression_without_failing_when_allowed(self) -> None:
        baseline = {
            "startup": {"health_p50_ms": 100.0, "health_p95_ms": 120.0},
            "ingestion": {"latency_ms": 1000.0, "throughput_mb_per_s": 1.0},
            "retrieval": {"p50_ms": 20.0, "p95_ms": 30.0},
        }
        current = {
            "startup": {"health_p50_ms": 140.0, "health_p95_ms": 150.0},
            "ingestion": {"latency_ms": 1400.0, "throughput_mb_per_s": 0.7},
            "retrieval": {"p50_ms": 28.0, "p95_ms": 40.0},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            baseline_path = root / "baseline.json"
            current_path = root / "current.json"
            baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
            current_path.write_text(json.dumps(current), encoding="utf-8")

            regressed = compare_to_baseline(
                current_path,
                baseline_path,
                tolerance=0.25,
                fail_on_regression=False,
            )

        self.assertTrue(regressed)

    def test_benchmark_compare_can_fail_on_regression(self) -> None:
        baseline = {
            "startup": {"health_p50_ms": 100.0, "health_p95_ms": 100.0},
            "ingestion": {"latency_ms": 1000.0, "throughput_mb_per_s": 1.0},
            "retrieval": {"p50_ms": 20.0, "p95_ms": 20.0},
        }
        current = {
            "startup": {"health_p50_ms": 200.0, "health_p95_ms": 200.0},
            "ingestion": {"latency_ms": 2000.0, "throughput_mb_per_s": 0.4},
            "retrieval": {"p50_ms": 45.0, "p95_ms": 45.0},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            baseline_path = root / "baseline.json"
            current_path = root / "current.json"
            baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
            current_path.write_text(json.dumps(current), encoding="utf-8")

            with self.assertRaises(SystemExit):
                compare_to_baseline(
                    current_path,
                    baseline_path,
                    tolerance=0.25,
                    fail_on_regression=True,
                )

    def test_smoke_eval_suite_passes(self) -> None:
        report = run_suite("smoke", "smoke")
        # T58 added biology-mitosis-pdf-001 to exercise the Docling
        # typed-node ingest path; smoke suite is now 15 cases (was 14).
        self.assertEqual(15, report["summary"]["total_cases"])
        self.assertEqual(0, report["summary"]["blocking_errors"])


if __name__ == "__main__":
    unittest.main()
