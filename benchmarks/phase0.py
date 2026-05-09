from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Literal

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import main  # noqa: E402
from app_runtime import resolve_runtime_paths  # noqa: E402
from routes.workspace import health  # noqa: E402
from services import artifact_studio  # noqa: E402
from services.local_api_security import HEADER_NAME, get_local_api_token  # noqa: E402

MetricDirection = Literal["lower", "higher"]

DEFAULT_OUTPUT_NAME = "latest.json"
DEFAULT_BASELINE_PATH = ROOT_DIR / "data" / "benchmarks" / "baseline.json"
COMPARISON_RULES: dict[str, MetricDirection] = {
    "startup.health_p50_ms": "lower",
    "startup.health_p95_ms": "lower",
    "ingestion.latency_ms": "lower",
    "ingestion.throughput_mb_per_s": "higher",
    "retrieval.p50_ms": "lower",
    "retrieval.p95_ms": "lower",
}


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return round(values[0], 2)
    ordered = sorted(values)
    index = int(round((percentile / 100.0) * (len(ordered) - 1)))
    return round(ordered[index], 2)


def _time_call(fn: Any, iterations: int) -> list[float]:
    samples: list[float] = []
    for _ in range(iterations):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    return samples


@contextmanager
def _isolated_runtime() -> Iterator[None]:
    original = (
        main.BASE_DIR,
        main.DATA_DIR,
        main.UPLOAD_DIR,
        main.DB_PATH,
        main.SCHEMA_PATH,
    )
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            main.BASE_DIR = base_dir
            main.DATA_DIR = base_dir / "data"
            main.UPLOAD_DIR = main.DATA_DIR / "uploads"
            main.DB_PATH = main.DATA_DIR / "benchmark.db"
            main.SCHEMA_PATH = original[4]
            main.initialize_database()
            with main.get_db() as conn:
                conn.execute("PRAGMA foreign_keys = OFF")
                rows = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
                for row in rows:
                    table_name = str(row["name"])
                    if (
                        table_name.startswith("sqlite_")
                        or table_name == "schema_migrations"
                        or table_name.startswith("chunks_fts")
                        or table_name.startswith("chunks_vec")
                    ):
                        continue
                    conn.execute(f"DELETE FROM {table_name}")
                if any(row["name"] == "chunks_vec" for row in rows):
                    conn.execute("DELETE FROM chunks_vec")
                conn.execute("PRAGMA foreign_keys = ON")
                conn.commit()
            yield
    finally:
        (
            main.BASE_DIR,
            main.DATA_DIR,
            main.UPLOAD_DIR,
            main.DB_PATH,
            main.SCHEMA_PATH,
        ) = original


def _output_path(explicit_output: Path | None = None) -> Path:
    if explicit_output is not None:
        explicit_output.parent.mkdir(parents=True, exist_ok=True)
        return explicit_output
    runtime = resolve_runtime_paths()
    runtime.benchmark_dir.mkdir(parents=True, exist_ok=True)
    return runtime.benchmark_dir / DEFAULT_OUTPUT_NAME


def run_phase0_benchmark(output_path: Path | None = None) -> Path:
    resolved_output = _output_path(output_path)
    with _isolated_runtime():
        main.initialize_database()
        import_start = time.perf_counter()
        startup_health = health()
        import_latency_ms = round((time.perf_counter() - import_start) * 1000, 2)

        with TestClient(main.app) as client:
            health_samples = _time_call(lambda: client.get("/api/health"), iterations=15)

            upload_bytes = (
                "Cell respiration releases energy through ATP production.\n" * 14000
            ).encode("utf-8")
            upload_size_mb = round(len(upload_bytes) / (1024 * 1024), 3)
            with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as handle:
                temp_path = Path(handle.name)
                handle.write(upload_bytes)

            try:
                with temp_path.open("rb") as handle:
                    start = time.perf_counter()
                    response = client.post(
                        "/api/documents/upload",
                        headers={HEADER_NAME: get_local_api_token()},
                        data={"subject_name": "Benchmark"},
                        files={"file": ("phase0-benchmark.txt", handle, "text/plain")},
                    )
                    upload_latency_s = time.perf_counter() - start
                response.raise_for_status()
                upload_payload = response.json()

                with main.get_db() as conn:
                    retrieval_samples = _time_call(
                        lambda: artifact_studio.retrieve_grounding_chunks(
                            conn,
                            source_ids=[str(upload_payload["doc_id"])],
                            concept_ids=None,
                            query="ATP energy respiration",
                            limit=8,
                        ),
                        iterations=25,
                    )
                    diagnostics_rows = conn.execute(
                        """
                        SELECT parser_diagnostics
                        FROM documents
                        WHERE parser_diagnostics IS NOT NULL AND TRIM(parser_diagnostics) != ''
                        """
                    ).fetchall()
            finally:
                temp_path.unlink(missing_ok=True)

    ocr_pages = 0
    total_pages = 0
    for row in diagnostics_rows:
        try:
            diagnostics = json.loads(str(row["parser_diagnostics"] or "{}"))
        except json.JSONDecodeError:
            continue
        quality = diagnostics.get("quality", {})
        ocr_pages += int(quality.get("ocr_pages", 0) or 0)
        total_pages += int(quality.get("pages_processed", 0) or 0)

    benchmark = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "paths": {
            "base_dir": str(resolve_runtime_paths().base_dir),
            "db_path": str(resolve_runtime_paths().db_path),
            "output_path": str(resolved_output),
        },
        "startup": {
            "health_status": startup_health.get("status"),
            "import_health_ms": import_latency_ms,
            "health_p50_ms": _percentile(health_samples, 50),
            "health_p95_ms": _percentile(health_samples, 95),
        },
        "ingestion": {
            "uploaded_doc_id": upload_payload["doc_id"],
            "input_mb": upload_size_mb,
            "latency_ms": round(upload_latency_s * 1000, 2),
            "throughput_mb_per_s": round(upload_size_mb / max(upload_latency_s, 0.001), 3),
        },
        "retrieval": {
            "samples": len(retrieval_samples),
            "p50_ms": _percentile(retrieval_samples, 50),
            "p95_ms": _percentile(retrieval_samples, 95),
            "mean_ms": round(statistics.mean(retrieval_samples), 2),
        },
        "ocr": {
            "ocr_pages": ocr_pages,
            "total_pages": total_pages,
            "fallback_rate": round((ocr_pages / total_pages), 4) if total_pages else 0.0,
        },
        "notes": [
            "Runs against an isolated temporary runtime to avoid mutating the user's real database.",
            "UI cold/warm paint is not yet included; that will need a Playwright/WKWebView harness.",
            "This benchmark uses the current retrieval implementation, so it is a performance floor before FTS/vector work.",
        ],
    }
    resolved_output.write_text(json.dumps(benchmark, indent=2), encoding="utf-8")
    return resolved_output


def _metric_value(payload: dict[str, Any], key: str) -> float | None:
    current: Any = payload
    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    if isinstance(current, (int, float)):
        return float(current)
    return None


def compare_to_baseline(
    current_path: Path,
    baseline_path: Path,
    *,
    tolerance: float,
    fail_on_regression: bool,
) -> bool:
    current = json.loads(current_path.read_text(encoding="utf-8"))
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

    print("metric | baseline | current | delta | status")
    print("--- | ---: | ---: | ---: | ---")

    regressed = False
    for key, direction in COMPARISON_RULES.items():
        baseline_value = _metric_value(baseline, key)
        current_value = _metric_value(current, key)
        if baseline_value is None or current_value is None:
            print(f"{key} | n/a | n/a | n/a | skipped")
            continue

        if baseline_value == 0:
            delta_ratio = 0.0
        else:
            delta_ratio = (current_value - baseline_value) / baseline_value

        if direction == "lower":
            has_regressed = current_value > (baseline_value * (1.0 + tolerance))
        else:
            has_regressed = current_value < (baseline_value * (1.0 - tolerance))

        status = "regressed" if has_regressed else "ok"
        regressed = regressed or has_regressed
        print(f"{key} | {baseline_value:.2f} | {current_value:.2f} | {delta_ratio:+.2%} | {status}")

    if regressed and fail_on_regression:
        raise SystemExit(1)
    return regressed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Einstein Tutor Phase 0 benchmark harness."
    )
    parser.add_argument(
        "--output", type=Path, default=None, help="Write the current run to this JSON file."
    )
    parser.add_argument(
        "--compare",
        type=Path,
        default=None,
        help="Optional baseline JSON to compare against after the run completes.",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.25,
        help="Allowed performance drift before a metric is flagged as regressed.",
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Exit non-zero when a compared metric regresses past tolerance.",
    )
    return parser.parse_args(argv)


def main_cli(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_path = run_phase0_benchmark(args.output)
    print(output_path)
    if args.compare is not None:
        compare_to_baseline(
            output_path,
            args.compare,
            tolerance=args.tolerance,
            fail_on_regression=args.fail_on_regression,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
