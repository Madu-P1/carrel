import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ai.router import ClaudeCallResult
from evals import run_evals
from services.retrieval.hybrid import ScoredHit
from services.tutor import GroundedAnswer


class StubRouter:
    def __init__(self, result: ClaudeCallResult) -> None:
        self._result = result

    def ai_enabled(self) -> bool:
        return True

    def request_tool_call(self, **_: object) -> ClaudeCallResult:
        return self._result


class EvalsRunnerTests(unittest.TestCase):
    def test_malformed_case_returns_blocking_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cases_dir = Path(temp_dir)
            (cases_dir / "broken.jsonl").write_text(
                json.dumps({"id": "bad-case", "kind": "definition"}) + "\n",
                encoding="utf-8",
            )
            with mock.patch.object(run_evals, "CASES_DIR", cases_dir):
                report = run_evals.run_suite("broken", "smoke", report_dir=cases_dir / "reports")

        self.assertEqual(1, report["summary"]["blocking_errors"])
        self.assertTrue(report["results"][0]["load_errors"])

    def test_smoke_mode_runs_without_claude_key_or_router(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch(
                "evals.run_evals.get_default_router",
                side_effect=AssertionError("router should not load"),
            ):
                report = run_evals.run_suite("smoke", "smoke", report_dir=Path(temp_dir))

        self.assertEqual(0, report["summary"]["blocking_errors"])
        self.assertEqual(14, report["summary"]["total_cases"])
        self.assertIn("groundedness_at_k", report["summary"])

    def test_smoke_mode_short_circuits_before_answer_metrics(self) -> None:
        # T07 lock: smoke mode returns at the `if mode == "smoke"` short-
        # circuit in run_case, BEFORE grounded_tutor_response runs. Per-
        # case results must NOT carry quote_validity / citation_precision
        # / citation_recall keys (those are computed only in --mode full).
        # Locks the invariant the T07 acceptance pivot rests on: the
        # original `quote_validity ≥ 0.95 in smoke` criterion was
        # structurally impossible, not merely empirically failing.
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch(
                "evals.run_evals.get_default_router",
                side_effect=AssertionError("router should not load"),
            ):
                report = run_evals.run_suite("smoke", "smoke", report_dir=Path(temp_dir))

        self.assertGreater(len(report["results"]), 0)
        for case in report["results"]:
            self.assertNotIn("quote_validity", case)
            self.assertNotIn("citation_precision", case)
            self.assertNotIn("citation_recall", case)
            self.assertNotIn("ok", case)
            self.assertIn("groundedness_at_k", case)
        self.assertNotIn("quote_validity", report["summary"])

    def test_full_mode_computes_metrics_from_stub_router(self) -> None:
        result = ClaudeCallResult(
            ok=True,
            task="balanced",
            model="claude-sonnet-4-6",
            request_kind="tutor.grounded_answer",
            text=None,
            json_payload={
                "summary": "Mitosis creates identical daughter cells.",
                "claims": [
                    {
                        "text": "Mitosis creates identical daughter cells.",
                        "citations": [
                            {"chunk_index": 1, "quote": "genetically identical daughter cells"}
                        ],
                    }
                ],
                "unsupported_spans": [],
            },
            error_code=None,
            error_message=None,
            latency_ms=1200.0,
            input_tokens=100,
            output_tokens=40,
            cache_creation_input_tokens=None,
            cache_read_input_tokens=0,
            cache_hit=False,
            service_tier="auto",
            stop_reason="tool_use",
            request_id="req_eval_stub",
        )
        fixtures = run_evals._load_fixture_manifest()
        with run_evals._isolated_runtime("full"):
            mapping = run_evals._ingest_fixtures(fixtures)
            cases = {case.case_id: case for case in run_evals._load_cases("smoke")}
            with run_evals.main.get_db() as conn:
                case = cases["biology-mitosis-001"]
                expected_chunks = run_evals._resolve_expected_chunks(conn, case, mapping)
                expected_chunk_id = next(iter(expected_chunks))
                row = conn.execute(
                    "SELECT id, doc_id, section, content FROM chunks WHERE id = ?",
                    (expected_chunk_id,),
                ).fetchone()
                hit = ScoredHit(
                    chunk_id=str(row["id"]),
                    doc_id=str(row["doc_id"]),
                    section=str(row["section"]) if row["section"] else None,
                    snippet=str(row["content"])[:240],
                    score=0.02,
                    components={"fts": 0.02},
                    sources=("fts",),
                )
                with mock.patch("evals.run_evals.search_hybrid", return_value=[hit]):
                    with mock.patch("services.tutor.search_hybrid", return_value=[hit]):
                        metrics = run_evals.run_case(
                            case,
                            conn,
                            "full",
                            mapping,
                            router=StubRouter(result),
                        )

        self.assertTrue(metrics["ok"])
        self.assertEqual(1.0, metrics["citation_precision"])
        self.assertEqual(1.0, metrics["citation_recall"])
        self.assertEqual(1.0, metrics["quote_validity"])
        self.assertEqual(0.0, metrics["citation_drop_rate"])

    def test_normalized_substring_match_handles_whitespace_and_rejects_fabrication(self) -> None:
        self.assertTrue(
            run_evals._normalized_substring_match(
                "genetically   identical daughter cells",
                "Mitosis creates two genetically identical daughter cells and is used for growth.",
            )
        )
        self.assertFalse(
            run_evals._normalized_substring_match(
                "fabricated supporting quote",
                "Mitosis creates two genetically identical daughter cells and is used for growth.",
            )
        )

    def test_negative_case_full_mode_does_not_crash_and_tracks_fallback(self) -> None:
        fixtures = run_evals._load_fixture_manifest()
        with run_evals._isolated_runtime("full"):
            mapping = run_evals._ingest_fixtures(fixtures)
            cases = {case.case_id: case for case in run_evals._load_cases("smoke")}
            fallback_answer = GroundedAnswer(
                summary="",
                claims=(),
                unsupported_spans=(
                    "No source chunks matched the question: What does the corpus say about gravity?",
                ),
                misconceptions=(),
                next_steps=(),
                model="",
                latency_ms=0.0,
                ok=False,
                error="empty_retrieval",
                cache_hit=False,
                input_tokens=None,
                output_tokens=None,
                scope_fallback_used=False,
                citation_attempt_count=0,
                citation_drop_count=0,
                citation_repair_count=0,
            )
            with run_evals.main.get_db() as conn:
                with mock.patch(
                    "evals.run_evals.grounded_tutor_response", return_value=fallback_answer
                ):
                    metrics = run_evals.run_case(
                        cases["negative-gravity-001"],
                        conn,
                        "full",
                        mapping,
                        router=None,
                    )

        self.assertEqual(0, metrics["groundedness_at_k"])
        self.assertTrue(metrics["fallback"])
        self.assertFalse(metrics["ok"])
        self.assertIsNone(metrics["quote_validity"])

    def test_aggregate_quote_validity_excludes_cases_without_citations(self) -> None:
        summary = run_evals._aggregate(
            [
                {
                    "groundedness_at_k": 1,
                    "citation_precision": 1.0,
                    "citation_recall": 1.0,
                    "quote_validity": 1.0,
                    "quote_valid_count": 3,
                    "quote_total": 3,
                    "citation_attempt_count": 3,
                    "citation_drop_count": 0,
                    "citation_repair_count": 0,
                    "fallback": False,
                    "scope_fallback": False,
                    "latency_ms": 1000.0,
                    "model": "claude-sonnet-4-6",
                },
                {
                    "groundedness_at_k": 0,
                    "citation_precision": 0.0,
                    "citation_recall": 0.0,
                    "quote_validity": None,
                    "quote_valid_count": 0,
                    "quote_total": 0,
                    "citation_attempt_count": 0,
                    "citation_drop_count": 0,
                    "citation_repair_count": 0,
                    "fallback": True,
                    "scope_fallback": False,
                    "latency_ms": 0.0,
                    "model": "",
                },
            ],
            mode="full",
        )

        self.assertEqual(1.0, summary["quote_validity"])
        self.assertEqual(3, summary["quote_total"])
        self.assertEqual(3, summary["quote_valid_count"])

    def test_report_writes_json_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report_dir = Path(temp_dir)
            report = run_evals.run_suite("smoke", "smoke", report_dir=report_dir)
            report_files = sorted(report_dir.glob("*"))

        self.assertTrue(any(path.suffix == ".json" for path in report_files))
        self.assertTrue(any(path.suffix == ".md" for path in report_files))
        self.assertIn("reports", report)

    def test_quality_thresholds_lock_invariants_on_both_flag_values(self) -> None:
        """Lock the T08 (re-open) acceptance bar in pure aggregator logic.

        Builds two synthetic per-case result sets that simulate a
        side-by-side `RETRIEVAL_USE_NODES` on/off comparison, then asserts
        `_aggregate` reports values that satisfy CLAUDE.md
        §Benchmarks+budgets quality bars (`groundedness@8 ≥ 0.7`,
        `quote_validity ≥ 0.95`) on BOTH branches. No network, no DB,
        no Docling; the point is locking the invariant the comparison
        report exists to defend, not running the full eval in CI.

        After T57 (Phase 4.0 precursor) lands and T08 reopens, the
        real comparison run must continue to pass this invariant on
        both branches or block T08 per its `Guards`.
        """
        nodes_on_cases = [
            {
                "groundedness_at_k": 1,
                "citation_precision": 1.0,
                "citation_recall": 1.0,
                "quote_validity": 1.0,
                "quote_valid_count": 2,
                "quote_total": 2,
                "citation_attempt_count": 2,
                "citation_drop_count": 0,
                "citation_repair_count": 0,
                "fallback": False,
                "scope_fallback": False,
                "latency_ms": 3500.0,
                "model": "claude-sonnet-4-6",
            }
        ] * 12 + [
            {
                "groundedness_at_k": 0,
                "citation_precision": 0.0,
                "citation_recall": 0.0,
                "quote_validity": None,
                "quote_valid_count": 0,
                "quote_total": 0,
                "citation_attempt_count": 0,
                "citation_drop_count": 0,
                "citation_repair_count": 0,
                "fallback": True,
                "scope_fallback": False,
                "latency_ms": 0.0,
                "model": "",
            }
        ] * 2

        nodes_off_cases = list(nodes_on_cases)

        on_summary = run_evals._aggregate(nodes_on_cases, mode="full")
        off_summary = run_evals._aggregate(nodes_off_cases, mode="full")

        for label, summary in (("on", on_summary), ("off", off_summary)):
            with self.subTest(branch=label):
                self.assertGreaterEqual(
                    summary["groundedness_at_k"]["value"],
                    0.7,
                    f"{label} branch groundedness@8 fell below CLAUDE.md 0.7 bar",
                )
                self.assertIsNotNone(summary["quote_validity"])
                self.assertGreaterEqual(
                    float(summary["quote_validity"]),
                    0.95,
                    f"{label} branch quote_validity fell below CLAUDE.md 0.95 bar",
                )
                self.assertEqual([], summary["warnings"])

        self.assertEqual(
            on_summary["groundedness_at_k"]["value"],
            off_summary["groundedness_at_k"]["value"],
        )
        self.assertEqual(on_summary["quote_validity"], off_summary["quote_validity"])


if __name__ == "__main__":
    unittest.main()
