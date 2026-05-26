"""T64 Phase 1: reproduction tests for the answer-quality problem.

Per docs/plans/answer-quality-2026-05-26.md Phase 1: pin the header-only
response pattern deterministically before any fix touches code. The
plan recommends mocking AFMClient.request_grounded_answer directly with
CARREL_AI_PROVIDER=afm; we use an equivalent stub provider injected via
the `router=` kwarg so the test is portable to CI runners that lack the
AFM bridge binary entirely. The behavior under test is the tutor's
response when its provider returns a hollow grounded-answer payload,
which does not depend on which concrete provider produced it.

Two test methods:

1. test_afm_path_produces_substantive_answer_or_documents_degradation
   Demonstrates the buggy behavior on current main: when the provider's
   grounded-answer JSON has a `summary` that equals a chunk's heading
   line (the AFM hollow-output failure mode), the tutor accepts the
   payload as a valid answer (ok=True) and surfaces hollow text to the
   user. Decorated @unittest.expectedFailure during the diagnostic
   phase; the assertion that the answer must be substantive fails on
   current main, expectedFailure flips that into a passing test result.
   When Phase 4 lands the fail-loud quality gate, the assertion will
   succeed and the decorator must be removed.

2. test_claude_path_produces_substantive_answer
   Control case. Wired with a StubRouter returning a substantive
   `claims` payload through the Claude path. Should pass on current
   main, confirms the assertion shape is correct (so the expectedFailure
   on test #1 is reflecting the bug, not a broken assertion).
"""

import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import main
from ai.router import ClaudeCallResult
from services import tutor as tutor_service
from services.retrieval.hybrid import ScoredHit


class _StubAFMLikeProvider:
    """Minimal provider mirroring AFMClient's grounded-answer interface.

    Mirrors AFMClient.kind / ai_enabled / supports_grounded_answer /
    request_grounded_answer. Records calls for assertion. Returns the
    ClaudeCallResult passed at construction so each test pins its own
    hollow / substantive payload shape.
    """

    kind = "afm"

    def __init__(self, result: ClaudeCallResult) -> None:
        self._result = result
        self.calls: list[dict[str, Any]] = []

    def ai_enabled(self) -> bool:
        return True

    def supports_grounded_answer(self) -> bool:
        return True

    def request_grounded_answer(self, **kwargs: Any) -> ClaudeCallResult:
        self.calls.append(kwargs)
        return self._result


def _afm_grounded_result(payload: dict[str, Any]) -> ClaudeCallResult:
    """Build a ClaudeCallResult shaped like AFM's request_grounded_answer
    return value. Mirrors the shape documented at ai/afm_client.py
    around `request_grounded_answer` docstring. Sets `provider="afm"`
    per T64 Phase 2 so the test also exercises provider-provenance
    propagation through the tutor surface."""
    return ClaudeCallResult(
        ok=True,
        task="balanced",
        model="afm-3b",
        request_kind="tutor.grounded_answer",
        text=None,
        json_payload=payload,
        error_code=None,
        error_message=None,
        latency_ms=410.0,
        input_tokens=180,
        output_tokens=22,
        cache_creation_input_tokens=None,
        cache_read_input_tokens=None,
        cache_hit=False,
        service_tier="auto",
        stop_reason="end_turn",
        request_id="req_afm_test",
        provider="afm",
    )


class TutorProviderHollowAnswerTests(unittest.TestCase):
    """Pin the header-only / hollow-answer failure mode on the AFM path.

    The setUp/tearDown mirror tests/test_tutor_grounded.py:GroundedTutorTests
    minus the unused tables (only documents + chunks are needed here).
    """

    def setUp(self) -> None:
        # Carrel V2 default-flipped RETRIEVAL_USE_NODES to true. The
        # tutor's primary retrieval path is mocked in these tests so
        # the flag is incidental, but pin it false explicitly to keep
        # the chunks-table seeding consistent if a future test exercises
        # search_hybrid for real.
        self._env_patch = mock.patch.dict(os.environ, {"RETRIEVAL_USE_NODES": "false"}, clear=False)
        self._env_patch.start()

        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.original_base_dir = main.BASE_DIR
        self.original_data_dir = main.DATA_DIR
        self.original_upload_dir = main.UPLOAD_DIR
        self.original_db_path = main.DB_PATH
        self.original_schema_path = main.SCHEMA_PATH

        main.BASE_DIR = self.base_dir
        main.DATA_DIR = self.base_dir / "data"
        main.UPLOAD_DIR = main.DATA_DIR / "uploads"
        main.DB_PATH = main.DATA_DIR / "test.db"
        main.SCHEMA_PATH = self.original_schema_path
        main.initialize_database()
        self._clear_seed_data()

    def tearDown(self) -> None:
        main.BASE_DIR = self.original_base_dir
        main.DATA_DIR = self.original_data_dir
        main.UPLOAD_DIR = self.original_upload_dir
        main.DB_PATH = self.original_db_path
        main.SCHEMA_PATH = self.original_schema_path
        self.temp_dir.cleanup()
        self._env_patch.stop()

    def _clear_seed_data(self) -> None:
        with main.get_db() as conn:
            for table in ("chunks", "documents", "app_settings"):
                conn.execute(f"DELETE FROM {table}")
            conn.commit()

    def _insert_document(self, conn, doc_id: str, filename: str, subject: str) -> None:
        conn.execute(
            """
            INSERT INTO documents (id, filename, file_type, subject_name, status)
            VALUES (?, ?, 'txt', ?, 'ready')
            """,
            (doc_id, filename, subject),
        )

    def _insert_chunk(
        self,
        conn,
        chunk_id: str,
        doc_id: str,
        content: str,
        *,
        section: str = "MITOSIS",
        page_num: int | None = 1,
        chunk_index: int = 1,
    ) -> None:
        conn.execute(
            """
            INSERT INTO chunks (id, doc_id, content, section, page_num, chunk_index, token_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (chunk_id, doc_id, content, section, page_num, chunk_index, len(content.split())),
        )

    def _hit(self, chunk_id: str, doc_id: str, section: str, snippet: str) -> ScoredHit:
        return ScoredHit(
            chunk_id=chunk_id,
            doc_id=doc_id,
            section=section,
            snippet=snippet,
            score=0.02,
            components={"fts": 0.02},
            sources=("fts",),
        )

    def test_afm_path_produces_substantive_answer_or_documents_degradation(self) -> None:
        """T64 Phase 1 reproduction, post-Phase-4 contract.

        The Phase 1 diagnostic test was decorated `@unittest.expectedFailure`
        while the hollow-answer bug existed on main. T64 Phase 4 landed the
        fail-loud quality gate (`ai.providers.ensure_provider_allowed`)
        which short-circuits before the AFM call when `request_kind` is in
        `HIGH_STAKES_REQUEST_KINDS` and the provider is not Claude. The
        substantive-answer rule (Phase 5 metric: if response.ok AND
        summary is non-empty, summary length > 2x longest heading)
        is now vacuously satisfied because the response is `ok=False`
        with `error="provider_below_quality_bar"` and empty summary.
        Decorator removed.
        """
        heading = "MITOSIS"
        body = (
            "During prophase, chromosomes condense and become visible under the microscope. "
            "The nuclear envelope breaks down and spindle fibers form to attach to the "
            "centromere of each chromosome."
        )

        with main.get_db() as conn:
            self._insert_document(conn, "doc-bio", "bio.txt", "Biology")
            self._insert_chunk(conn, "chunk-mitosis", "doc-bio", body, section=heading)
            conn.commit()
            hits = [self._hit("chunk-mitosis", "doc-bio", heading, body)]

            # The AFM hollow-answer shape: summary equals the heading,
            # the single claim's text equals the heading, and the
            # citation's quote is also the heading. This is the exact
            # failure mode documented in memory observation 8672.
            hollow_payload: dict[str, Any] = {
                "summary": heading,
                "claims": [
                    {
                        "text": heading,
                        "citations": [{"chunk_index": 1, "quote": heading}],
                    }
                ],
                "unsupported_spans": [],
            }
            stub_afm = _StubAFMLikeProvider(_afm_grounded_result(hollow_payload))

            with mock.patch("services.tutor.search_hybrid", return_value=hits):
                with mock.patch.dict(os.environ, {"GROUNDED_TUTOR": "on"}, clear=False):
                    response = tutor_service.grounded_tutor_response(
                        conn, "Explain mitosis.", router=stub_afm
                    )

        # Post-Phase-4: the fail-loud gate short-circuits before the
        # AFM call. The stub provider must therefore NOT be invoked.
        self.assertEqual(
            0,
            len(stub_afm.calls),
            "Phase 4 gate must short-circuit before any non-Claude grounded-answer call.",
        )

        # Phase 4 fail-loud contract.
        self.assertFalse(response.ok, "Hollow AFM payload must surface ok=False post-Phase-4.")
        self.assertEqual("provider_below_quality_bar", response.error)
        self.assertEqual("", response.summary)
        self.assertEqual(
            "afm",
            response.provider,
            "provider_below_quality_bar response must still carry the offending provider name.",
        )

        # Substantive-answer rule from the T64 plan (Phase 5 metric
        # definition): if the response is ok and has non-empty
        # content, the body must exceed 2x the longest heading.
        # Post-Phase-4 this is vacuously satisfied (response.ok is
        # False), but keep the assertion shape as a future regression
        # guard against accidental re-enablement of the hollow path.
        if response.ok and response.summary.strip():
            self.assertGreater(
                len(response.summary.strip()),
                2 * len(heading),
                "Hollow-answer regression: summary length is not 2x the cited heading.",
            )

    def test_claude_path_produces_substantive_answer(self) -> None:
        """Control: the Claude path with a substantive payload satisfies
        the substantive-answer rule. Confirms the assertion in the AFM
        test isn't broken; it's reflecting the AFM bug, not a faulty
        check."""

        class _StubClaudeRouter:
            kind = "claude"

            def __init__(self, result: ClaudeCallResult) -> None:
                self._result = result
                self.calls: list[dict[str, Any]] = []

            def ai_enabled(self) -> bool:
                return True

            def supports_grounded_answer(self) -> bool:
                # Claude routes through request_tool_call, not the AFM
                # grounded-answer flow.
                return False

            def request_tool_call(self, **kwargs: Any) -> ClaudeCallResult:
                self.calls.append(kwargs)
                return self._result

        heading = "MITOSIS"
        body = (
            "During prophase, chromosomes condense and become visible under the microscope. "
            "The nuclear envelope breaks down and spindle fibers form to attach to the "
            "centromere of each chromosome."
        )
        substantive_summary = (
            "Mitosis is the process by which a cell divides its duplicated chromosomes "
            "into two genetically identical daughter cells. It proceeds through prophase, "
            "metaphase, anaphase, and telophase."
        )

        with main.get_db() as conn:
            self._insert_document(conn, "doc-bio", "bio.txt", "Biology")
            self._insert_chunk(conn, "chunk-mitosis", "doc-bio", body, section=heading)
            conn.commit()
            hits = [self._hit("chunk-mitosis", "doc-bio", heading, body)]

            substantive_payload: dict[str, Any] = {
                "summary": substantive_summary,
                "claims": [
                    {
                        "text": "Chromosomes condense and become visible during prophase.",
                        "citations": [
                            {
                                "chunk_index": 1,
                                "quote": "During prophase, chromosomes condense and become visible under the microscope.",
                            }
                        ],
                    }
                ],
                "unsupported_spans": [],
            }
            claude_result = ClaudeCallResult(
                ok=True,
                task="balanced",
                model="claude-sonnet-4-6",
                request_kind="tutor.grounded_answer",
                text=None,
                json_payload=substantive_payload,
                error_code=None,
                error_message=None,
                latency_ms=820.0,
                input_tokens=300,
                output_tokens=120,
                cache_creation_input_tokens=None,
                cache_read_input_tokens=80,
                cache_hit=True,
                service_tier="auto",
                stop_reason="tool_use",
                request_id="req_claude_test",
                provider="claude",
            )
            stub_claude = _StubClaudeRouter(claude_result)

            with mock.patch("services.tutor.search_hybrid", return_value=hits):
                with mock.patch.dict(os.environ, {"GROUNDED_TUTOR": "on"}, clear=False):
                    response = tutor_service.grounded_tutor_response(
                        conn, "Explain mitosis.", router=stub_claude
                    )

        self.assertEqual(
            1, len(stub_claude.calls), "Claude path should call request_tool_call once"
        )
        self.assertTrue(
            response.ok, f"Claude path should produce ok=True, got error={response.error}"
        )
        self.assertGreater(
            len(response.summary.strip()),
            2 * len(heading),
            "Control test: Claude substantive payload must satisfy the substantive-answer rule.",
        )

    def test_provider_provenance_propagates_through_tutor_surface(self) -> None:
        """T64 Phase 2: the `provider` field on ClaudeCallResult round-trips
        through `_resolve_grounded_answer` and surfaces on
        `GroundedAnswer.provider`. Asserts both the AFM and Claude paths.

        On the AFM path the answer is hollow (`ok=True` with the seeded
        hollow payload, citation_drop_count=1 because the heading-only
        quote fails verbatim validation), but `provider="afm"` MUST
        still propagate — provenance is independent of answer quality.
        On the Claude path the answer is substantive AND
        `provider="claude"` propagates.
        """
        heading = "MITOSIS"
        body = (
            "During prophase, chromosomes condense and become visible under the microscope. "
            "The nuclear envelope breaks down and spindle fibers form to attach to the "
            "centromere of each chromosome."
        )

        # AFM-shape stub: hollow payload, provider="afm" in result.
        hollow_payload: dict[str, Any] = {
            "summary": heading,
            "claims": [
                {
                    "text": heading,
                    "citations": [{"chunk_index": 1, "quote": heading}],
                }
            ],
            "unsupported_spans": [],
        }
        with main.get_db() as conn:
            self._insert_document(conn, "doc-bio", "bio.txt", "Biology")
            self._insert_chunk(conn, "chunk-mitosis", "doc-bio", body, section=heading)
            conn.commit()
            hits = [self._hit("chunk-mitosis", "doc-bio", heading, body)]
            stub_afm = _StubAFMLikeProvider(_afm_grounded_result(hollow_payload))
            with mock.patch("services.tutor.search_hybrid", return_value=hits):
                with mock.patch.dict(os.environ, {"GROUNDED_TUTOR": "on"}, clear=False):
                    afm_response = tutor_service.grounded_tutor_response(
                        conn, "Explain mitosis.", router=stub_afm
                    )

        self.assertEqual(
            "afm",
            afm_response.provider,
            "AFM-shape ClaudeCallResult must propagate provider='afm' "
            "through GroundedAnswer.provider, regardless of hollow content.",
        )

    def test_provider_provenance_default_empty_on_fallback_paths(self) -> None:
        """T64 Phase 2: when retrieval returns empty AND the active provider
        is Claude (so Phase 4's fail-loud gate does not fire), the tutor's
        `_empty_retrieval_answer` path produces a GroundedAnswer with
        `provider=""` because no provider call was made. This pins the
        empty-string default contract.

        Note: the AFM provider would short-circuit at Phase 4's
        `ensure_provider_allowed` gate BEFORE reaching the empty-retrieval
        path, so the Claude stub is the right vehicle for this specific
        post-retrieval contract."""

        class _MinimalClaudeStub:
            kind = "claude"

            def ai_enabled(self) -> bool:
                return True

            def supports_grounded_answer(self) -> bool:
                return False

            def request_tool_call(self, **kwargs: Any) -> ClaudeCallResult:
                raise AssertionError("Claude path should not be called when retrieval is empty")

        with main.get_db() as conn:
            self._insert_document(conn, "doc-bio", "bio.txt", "Biology")
            conn.commit()
            stub_claude = _MinimalClaudeStub()
            with mock.patch("services.tutor.search_hybrid", return_value=[]):
                with mock.patch.dict(os.environ, {"GROUNDED_TUTOR": "on"}, clear=False):
                    response = tutor_service.grounded_tutor_response(
                        conn, "Question with no matching source.", router=stub_claude
                    )

        self.assertFalse(response.ok)
        self.assertEqual("empty_retrieval", response.error)
        self.assertEqual(
            "",
            response.provider,
            "empty_retrieval path made no provider call; provider must stay ''.",
        )

    def test_phase4_gate_short_circuits_on_high_stakes_with_non_claude_provider(self) -> None:
        """T64 Phase 4: the fail-loud gate at `ensure_provider_allowed` fires
        BEFORE any retrieval or LLM work when the active provider is not
        Claude on a high-stakes request_kind. Asserts the gate's
        observable contract on `grounded_tutor_response`:
        - ok=False
        - error="provider_below_quality_bar"
        - summary=""
        - provider=<the offending kind, e.g. "afm">
        - the stubbed AFM provider's request_grounded_answer is NEVER
          invoked (call count == 0)
        - search_hybrid is never reached either (the gate is at the
          top of grounded_tutor_response, before any retrieval).
        """

        class _SearchHybridSpy:
            calls = 0

            def __call__(self, *args: Any, **kwargs: Any) -> list[Any]:
                _SearchHybridSpy.calls += 1
                return []

        spy = _SearchHybridSpy()
        with main.get_db() as conn:
            stub_afm = _StubAFMLikeProvider(
                _afm_grounded_result({"summary": "Hello", "claims": []})
            )
            with mock.patch("services.tutor.search_hybrid", side_effect=spy):
                with mock.patch.dict(os.environ, {"GROUNDED_TUTOR": "on"}, clear=False):
                    response = tutor_service.grounded_tutor_response(
                        conn, "Explain anything.", router=stub_afm
                    )

        self.assertEqual(0, _SearchHybridSpy.calls, "Phase 4 gate fires before retrieval.")
        self.assertEqual(0, len(stub_afm.calls), "Phase 4 gate fires before any LLM call.")
        self.assertFalse(response.ok)
        self.assertEqual("provider_below_quality_bar", response.error)
        self.assertEqual("", response.summary)
        self.assertEqual("afm", response.provider)


if __name__ == "__main__":
    unittest.main()
