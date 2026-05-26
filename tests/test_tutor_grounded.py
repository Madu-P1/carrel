import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import main
from ai.router import ClaudeCallResult
from api_models import TutorQueryRequest
from routes.tutor import tutor_query
from services import tutor as tutor_service
from services.retrieval.hybrid import ScoredHit


class StubRouter:
    def __init__(self, result: ClaudeCallResult | None = None, *, enabled: bool = True) -> None:
        self._result = result
        self._enabled = enabled
        self.calls: list[dict[str, object]] = []

    def ai_enabled(self) -> bool:
        return self._enabled

    def request_tool_call(self, **kwargs):
        self.calls.append(kwargs)
        if self._result is None:
            raise AssertionError("request_tool_call should not have been invoked")
        return self._result


class GroundedTutorTests(unittest.TestCase):
    def setUp(self) -> None:
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
        self.clear_seed_data()

    def tearDown(self) -> None:
        main.BASE_DIR = self.original_base_dir
        main.DATA_DIR = self.original_data_dir
        main.UPLOAD_DIR = self.original_upload_dir
        main.DB_PATH = self.original_db_path
        main.SCHEMA_PATH = self.original_schema_path
        self.temp_dir.cleanup()

    def clear_seed_data(self) -> None:
        with main.get_db() as conn:
            for table in [
                "concept_edges",
                "questions",
                "srs_cards",
                "dialogue_sessions",
                "notes",
                "study_events",
                "tutor_exchange_evidence",
                "tutor_exchanges",
                "evidence_references",
                "concepts",
                "chunks",
                "documents",
                "app_settings",
            ]:
                conn.execute(f"DELETE FROM {table}")
            if conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'chunks_vec'"
            ).fetchone():
                conn.execute("DELETE FROM chunks_vec")
            if conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'chunks_fts'"
            ).fetchone():
                conn.execute("DELETE FROM chunks_fts")
            conn.commit()

    def _insert_document(self, conn, doc_id: str, filename: str, subject_name: str) -> None:
        conn.execute(
            """
            INSERT INTO documents (id, filename, file_type, subject_name, status)
            VALUES (?, ?, 'txt', ?, 'ready')
            """,
            (doc_id, filename, subject_name),
        )

    def _insert_chunk(
        self,
        conn,
        chunk_id: str,
        doc_id: str,
        content: str,
        *,
        section: str = "Core",
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

    def _insert_node(
        self,
        conn,
        doc_id: str,
        verbatim_text: str,
        *,
        heading_path: str = "Core",
        page: int | None = 1,
        char_start: int = 0,
        char_end: int | None = None,
        reading_order: int = 1,
        node_type: str = "body",
    ) -> int:
        cursor = conn.execute(
            """
            INSERT INTO nodes (
                doc_id, node_type, heading_path, page, char_start, char_end,
                verbatim_text, reading_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc_id,
                node_type,
                heading_path,
                page,
                char_start,
                char_end if char_end is not None else char_start + len(verbatim_text),
                verbatim_text,
                reading_order,
            ),
        )
        return int(cursor.lastrowid)

    def _insert_concept(self, conn, concept_id: str, doc_id: str, name: str) -> None:
        conn.execute(
            """
            INSERT INTO concepts (id, doc_id, name, description, mastery, source_chunks)
            VALUES (?, ?, ?, ?, 0.2, '[]')
            """,
            (concept_id, doc_id, name, name),
        )

    def _hit(
        self, chunk_id: str, doc_id: str, section: str, snippet: str, score: float = 0.02
    ) -> ScoredHit:
        return ScoredHit(
            chunk_id=chunk_id,
            doc_id=doc_id,
            section=section,
            snippet=snippet,
            score=score,
            components={"fts": score},
            sources=("fts",),
        )

    def _tool_result(
        self, payload: dict[str, object], *, ok: bool = True, error_code: str | None = None
    ) -> ClaudeCallResult:
        return ClaudeCallResult(
            ok=ok,
            task="balanced",
            model="claude-sonnet-4-6",
            request_kind="tutor.grounded_answer",
            text=None,
            json_payload=payload if ok else None,
            error_code=error_code,
            error_message=error_code,
            latency_ms=321.0,
            input_tokens=200,
            output_tokens=80,
            cache_creation_input_tokens=None,
            cache_read_input_tokens=50,
            cache_hit=True,
            service_tier="auto",
            stop_reason="tool_use",
            request_id="req_tutor_test",
        )

    def test_happy_path_resolves_claims_and_citations(self) -> None:
        with main.get_db() as conn:
            self._insert_document(conn, "doc-a", "bio-a.txt", "Biology")
            self._insert_document(conn, "doc-b", "bio-b.txt", "Biology")
            self._insert_chunk(
                conn,
                "chunk-1",
                "doc-a",
                "Mitosis separates duplicated chromosomes.",
                section="Mitosis",
                page_num=2,
            )
            self._insert_chunk(
                conn,
                "chunk-2",
                "doc-b",
                "Meiosis reduces chromosome number.",
                section="Meiosis",
                page_num=4,
            )
            conn.commit()
            hits = [
                self._hit(
                    "chunk-1", "doc-a", "Mitosis", "Mitosis separates duplicated chromosomes."
                ),
                self._hit("chunk-2", "doc-b", "Meiosis", "Meiosis reduces chromosome number."),
            ]
            router = StubRouter(
                self._tool_result(
                    {
                        "summary": "Mitosis and meiosis differ in chromosome handling and cell outcome.",
                        "claims": [
                            {
                                "text": "Mitosis separates duplicated chromosomes.",
                                "citations": [
                                    {
                                        "chunk_index": 1,
                                        "quote": "Mitosis separates duplicated chromosomes.",
                                    }
                                ],
                            },
                            {
                                "text": "Meiosis reduces chromosome number.",
                                "citations": [
                                    {
                                        "chunk_index": 2,
                                        "quote": "Meiosis reduces chromosome number.",
                                    }
                                ],
                            },
                        ],
                        "unsupported_spans": [],
                    }
                )
            )
            with mock.patch("services.tutor.search_hybrid", return_value=hits):
                with mock.patch.dict(os.environ, {"GROUNDED_TUTOR": "on"}, clear=False):
                    response = tutor_service.grounded_tutor_response(
                        conn,
                        "Why are mitosis and meiosis different?",
                        doc_ids=["doc-a", "doc-b"],
                        concept_name="Cell Division",
                        learner_confidence=30,
                        router=router,
                    )

        self.assertTrue(response.ok)
        self.assertEqual(2, len(response.claims))
        self.assertEqual("chunk-1", response.claims[0].citations[0].node_id)
        self.assertEqual("chunk-2", response.claims[1].citations[0].node_id)
        self.assertTrue(response.summary.startswith("Mitosis and meiosis differ"))

    def test_citation_index_out_of_range_moves_claim_to_unsupported(self) -> None:
        with main.get_db() as conn:
            self._insert_document(conn, "doc-a", "bio-a.txt", "Biology")
            self._insert_chunk(
                conn,
                "chunk-1",
                "doc-a",
                "Mitosis separates duplicated chromosomes.",
                section="Mitosis",
            )
            conn.commit()
            hits = [
                self._hit(
                    "chunk-1", "doc-a", "Mitosis", "Mitosis separates duplicated chromosomes."
                )
            ]
            router = StubRouter(
                self._tool_result(
                    {
                        "summary": "Mitosis separates duplicated chromosomes.",
                        "claims": [
                            {
                                "text": "This unsupported claim should move out of claims.",
                                "citations": [{"chunk_index": 99, "quote": "No support."}],
                            }
                        ],
                        "unsupported_spans": [],
                    }
                )
            )
            with mock.patch("services.tutor.search_hybrid", return_value=hits):
                with mock.patch.dict(os.environ, {"GROUNDED_TUTOR": "on"}, clear=False):
                    response = tutor_service.grounded_tutor_response(
                        conn, "What happens in mitosis?", router=router
                    )

        self.assertTrue(response.ok)
        self.assertEqual(0, len(response.claims))
        self.assertIn(
            "This unsupported claim should move out of claims.", response.unsupported_spans
        )

    def test_mixed_valid_and_invalid_citations_keep_supported_claim(self) -> None:
        with main.get_db() as conn:
            self._insert_document(conn, "doc-a", "bio-a.txt", "Biology")
            self._insert_chunk(
                conn,
                "chunk-1",
                "doc-a",
                "Mitosis separates duplicated chromosomes.",
                section="Mitosis",
            )
            conn.commit()
            hits = [
                self._hit(
                    "chunk-1", "doc-a", "Mitosis", "Mitosis separates duplicated chromosomes."
                )
            ]
            router = StubRouter(
                self._tool_result(
                    {
                        "summary": "Mitosis separates duplicated chromosomes.",
                        "claims": [
                            {
                                "text": "Mitosis separates duplicated chromosomes.",
                                "citations": [
                                    {
                                        "chunk_index": 1,
                                        "quote": "Mitosis separates duplicated chromosomes.",
                                    },
                                    {"chunk_index": 99, "quote": "Bad citation."},
                                ],
                            }
                        ],
                        "unsupported_spans": [],
                    }
                )
            )
            with mock.patch("services.tutor.search_hybrid", return_value=hits):
                with mock.patch.dict(os.environ, {"GROUNDED_TUTOR": "on"}, clear=False):
                    response = tutor_service.grounded_tutor_response(
                        conn, "Explain mitosis.", router=router
                    )

        self.assertEqual(1, len(response.claims))
        self.assertEqual(1, len(response.claims[0].citations))
        self.assertEqual("chunk-1", response.claims[0].citations[0].node_id)

    def test_quote_validation_replaces_model_quote_with_actual_source_span(self) -> None:
        with main.get_db() as conn:
            self._insert_document(conn, "doc-a", "bio-a.txt", "Biology")
            self._insert_chunk(
                conn,
                "chunk-1",
                "doc-a",
                "Mitosis creates “genetically identical” daughter cells during growth.",
                section="Mitosis",
            )
            conn.commit()
            hits = [
                self._hit(
                    "chunk-1",
                    "doc-a",
                    "Mitosis",
                    "Mitosis creates genetically identical daughter cells during growth.",
                )
            ]
            router = StubRouter(
                self._tool_result(
                    {
                        "summary": "Mitosis creates genetically identical daughter cells.",
                        "claims": [
                            {
                                "text": "Mitosis creates genetically identical daughter cells.",
                                "citations": [
                                    {
                                        "chunk_index": 1,
                                        "quote": 'Mitosis creates "genetically identical" daughter cells during growth.',
                                    }
                                ],
                            }
                        ],
                        "unsupported_spans": [],
                    }
                )
            )
            with mock.patch("services.tutor.search_hybrid", return_value=hits):
                with mock.patch.dict(os.environ, {"GROUNDED_TUTOR": "on"}, clear=False):
                    response = tutor_service.grounded_tutor_response(
                        conn, "Explain mitosis.", router=router
                    )

        self.assertTrue(response.ok)
        self.assertEqual(
            "Mitosis creates “genetically identical” daughter cells during growth.",
            response.claims[0].citations[0].quote,
        )
        self.assertEqual(1, response.citation_repair_count)
        self.assertEqual(0, response.citation_drop_count)

    def test_unverifiable_quote_drops_citation_and_demotes_claim(self) -> None:
        with main.get_db() as conn:
            self._insert_document(conn, "doc-a", "bio-a.txt", "Biology")
            self._insert_chunk(
                conn,
                "chunk-1",
                "doc-a",
                "Mitosis separates duplicated chromosomes.",
                section="Mitosis",
            )
            conn.commit()
            hits = [
                self._hit(
                    "chunk-1", "doc-a", "Mitosis", "Mitosis separates duplicated chromosomes."
                )
            ]
            router = StubRouter(
                self._tool_result(
                    {
                        "summary": "Mitosis creates daughter cells.",
                        "claims": [
                            {
                                "text": "Mitosis creates daughter cells through a different mechanism.",
                                "citations": [
                                    {
                                        "chunk_index": 1,
                                        "quote": "Mitosis produces two identical cells for tissue repair.",
                                    }
                                ],
                            }
                        ],
                        "unsupported_spans": [],
                    }
                )
            )
            with mock.patch("services.tutor.search_hybrid", return_value=hits):
                with mock.patch.dict(os.environ, {"GROUNDED_TUTOR": "on"}, clear=False):
                    response = tutor_service.grounded_tutor_response(
                        conn, "Explain mitosis.", router=router
                    )

        self.assertTrue(response.ok)
        self.assertEqual(0, len(response.claims))
        self.assertIn(
            "Mitosis creates daughter cells through a different mechanism.",
            response.unsupported_spans,
        )
        self.assertEqual(1, response.citation_drop_count)
        self.assertEqual(0, response.citation_repair_count)

    def test_claude_failure_returns_visible_passages_only_fallback(self) -> None:
        with main.get_db() as conn:
            self._insert_document(conn, "doc-a", "bio-a.txt", "Biology")
            self._insert_chunk(
                conn,
                "chunk-1",
                "doc-a",
                "Mitosis separates duplicated chromosomes.",
                section="Mitosis",
            )
            conn.commit()
            hits = [
                self._hit(
                    "chunk-1", "doc-a", "Mitosis", "Mitosis separates duplicated chromosomes."
                )
            ]
            router = StubRouter(self._tool_result({}, ok=False, error_code="claude_call_failed"))
            with mock.patch("services.tutor.search_hybrid", return_value=hits):
                with mock.patch.dict(os.environ, {"GROUNDED_TUTOR": "on"}, clear=False):
                    response = tutor_service.grounded_tutor_response(
                        conn, "Explain mitosis.", router=router
                    )

        self.assertFalse(response.ok)
        self.assertEqual("claude_call_failed", response.error)
        self.assertEqual("", response.summary)
        self.assertEqual(1, len(response.claims))
        self.assertEqual("chunk-1", response.claims[0].citations[0].node_id)

    def test_grounded_tutor_off_skips_claude_and_returns_fallback(self) -> None:
        with main.get_db() as conn:
            self._insert_document(conn, "doc-a", "bio-a.txt", "Biology")
            self._insert_chunk(
                conn, "chunk-1", "doc-a", "Mitosis separates duplicated chromosomes."
            )
            conn.commit()
            hits = [
                self._hit("chunk-1", "doc-a", "Core", "Mitosis separates duplicated chromosomes.")
            ]
            router = StubRouter()
            with mock.patch("services.tutor.search_hybrid", return_value=hits):
                with mock.patch.dict(os.environ, {"GROUNDED_TUTOR": "off"}, clear=False):
                    response = tutor_service.grounded_tutor_response(
                        conn, "Explain mitosis.", router=router
                    )

        self.assertFalse(response.ok)
        self.assertEqual("grounded_tutor_disabled", response.error)
        self.assertEqual([], router.calls)

    def test_grounded_tutor_auto_without_ai_returns_fallback(self) -> None:
        with main.get_db() as conn:
            self._insert_document(conn, "doc-a", "bio-a.txt", "Biology")
            self._insert_chunk(
                conn, "chunk-1", "doc-a", "Mitosis separates duplicated chromosomes."
            )
            conn.commit()
            hits = [
                self._hit("chunk-1", "doc-a", "Core", "Mitosis separates duplicated chromosomes.")
            ]
            router = StubRouter(enabled=False)
            with mock.patch("services.tutor.search_hybrid", return_value=hits):
                with mock.patch.dict(os.environ, {"GROUNDED_TUTOR": "auto"}, clear=False):
                    response = tutor_service.grounded_tutor_response(
                        conn, "Explain mitosis.", router=router
                    )

        self.assertFalse(response.ok)
        self.assertEqual([], router.calls)
        self.assertIn(response.error, {"grounded_tutor_unavailable", "grounded_tutor_disabled"})

    def test_pro_tutor_fails_closed_on_null_provider(self) -> None:
        """T09 fail-closed regression: when `select_provider()` returns
        NullProvider via the production env-driven path, `grounded_tutor_response`
        must surface `ok=False` with the canonical Null-provider error code
        and emit no LLM-synthesized summary — no silent fallback to a
        heuristic answer (CLAUDE.md "no silent fallbacks").

        This complements `test_grounded_tutor_auto_without_ai_returns_fallback`
        (which injects a disabled StubRouter directly) by exercising the
        `select_provider` → `get_default_provider` → `grounded_tutor_response`
        integration end-to-end with `CARREL_AI_PROVIDER=off`. The cached
        provider singleton is dropped via `reset_default_provider()` so
        the off-override actually takes effect.

        Acceptance text in AUTONOMOUS_WORK_PLAN.md originally said
        `error="ai_synthesis_unavailable", citations=[]`; the actual code
        emits `error="grounded_tutor_unavailable"` (mode=auto with
        `ai_enabled=False`) and populates passages-only claims via
        `_passages_only_fallback`. The test asserts the real fail-closed
        contract; the acceptance text was updated to match on the T09
        in_progress commit and the discrepancy surfaced to
        operator-followups.
        """
        from ai.providers import (
            NullProvider,
            get_default_provider,
            reset_default_provider,
            select_provider,
        )

        with main.get_db() as conn:
            self._insert_document(conn, "doc-a", "bio-a.txt", "Biology")
            self._insert_chunk(
                conn, "chunk-1", "doc-a", "Mitosis separates duplicated chromosomes."
            )
            conn.commit()
            hits = [
                self._hit("chunk-1", "doc-a", "Core", "Mitosis separates duplicated chromosomes.")
            ]

            reset_default_provider()
            try:
                with mock.patch.dict(
                    os.environ,
                    {"CARREL_AI_PROVIDER": "off", "GROUNDED_TUTOR": "auto"},
                    clear=False,
                ):
                    self.assertIsInstance(select_provider(), NullProvider)
                    self.assertIsInstance(get_default_provider(), NullProvider)

                    with mock.patch("services.tutor.search_hybrid", return_value=hits):
                        response = tutor_service.grounded_tutor_response(conn, "Explain mitosis.")
            finally:
                reset_default_provider()

        self.assertFalse(response.ok)
        self.assertEqual("grounded_tutor_unavailable", response.error)
        self.assertEqual("", response.summary)
        self.assertEqual("", response.model)
        self.assertEqual(0, response.citation_attempt_count)
        self.assertEqual(0, response.citation_drop_count)
        self.assertEqual(0, response.citation_repair_count)

    def test_empty_retrieval_returns_empty_answer_without_claude_call(self) -> None:
        with main.get_db() as conn:
            router = StubRouter()
            with mock.patch("services.tutor.search_hybrid", return_value=[]):
                with mock.patch.dict(os.environ, {"GROUNDED_TUTOR": "on"}, clear=False):
                    response = tutor_service.grounded_tutor_response(
                        conn, "Question with no matching source.", router=router
                    )

        self.assertFalse(response.ok)
        self.assertEqual("empty_retrieval", response.error)
        self.assertEqual([], router.calls)

    def test_weak_coverage_refuses_when_scope_fallback_and_few_contexts(self) -> None:
        """Grounded-only refusal: query retrieval returns empty, scope
        fallback produces only a couple of nodes, threshold is 3. We must
        refuse with error='weak_coverage' instead of asking the LLM to
        synthesize from thin evidence — that's the hallucination surface."""
        with main.get_db() as conn:
            self._insert_document(conn, "doc-a", "bio-a.txt", "Biology")
            # Only 2 nodes in the doc, both tangential to the question.
            # T03: fallback queries FROM nodes, not FROM chunks.
            self._insert_node(conn, "doc-a", "Ion channels.", reading_order=1)
            self._insert_node(conn, "doc-a", "Membrane potential.", reading_order=2)
            conn.commit()
            router = StubRouter()
            # Hybrid search misses; scope fallback returns the 2 chunks.
            with mock.patch("services.tutor.search_hybrid", return_value=[]):
                with mock.patch.dict(
                    os.environ,
                    {"GROUNDED_TUTOR": "on", "RETRIEVAL_USE_NODES": "true"},
                    clear=False,
                ):
                    response = tutor_service.grounded_tutor_response(
                        conn,
                        "Explain photosynthesis light reactions.",
                        doc_ids=["doc-a"],
                        router=router,
                    )

        self.assertFalse(response.ok)
        self.assertEqual("weak_coverage", response.error)
        # No Claude call happened — the refusal fires before the LLM.
        self.assertEqual([], router.calls)
        # The passages we did find are still exposed so the UI can show them.
        self.assertGreater(len(response.claims), 0)

    def test_scope_fallback_with_enough_contexts_still_calls_claude(self) -> None:
        """Counter-case: scope fallback produces enough nodes (>= threshold).
        Claude still runs because there's real material to synthesize from."""
        with main.get_db() as conn:
            self._insert_document(conn, "doc-a", "bio-a.txt", "Biology")
            # 4 nodes >= _WEAK_COVERAGE_MIN_CONTEXTS (default 3).
            # T03: fallback queries FROM nodes, not FROM chunks.
            for i in range(4):
                self._insert_node(
                    conn,
                    "doc-a",
                    f"Sentence {i} about cellular respiration.",
                    reading_order=i + 1,
                )
            conn.commit()
            router = StubRouter(
                result=self._tool_result({"summary": "ok", "claims": [], "unsupported_spans": []})
            )
            with mock.patch("services.tutor.search_hybrid", return_value=[]):
                with mock.patch.dict(
                    os.environ,
                    {"GROUNDED_TUTOR": "on", "RETRIEVAL_USE_NODES": "true"},
                    clear=False,
                ):
                    tutor_service.grounded_tutor_response(
                        conn,
                        "Explain cellular respiration.",
                        doc_ids=["doc-a"],
                        router=router,
                    )

        # The router WAS called — we didn't short-circuit to refusal.
        self.assertEqual(1, len(router.calls))

    def test_subject_name_and_doc_ids_propagate_to_hybrid_retrieval(self) -> None:
        with main.get_db() as conn:
            router = StubRouter()
            with mock.patch("services.tutor.search_hybrid", return_value=[]) as search_mock:
                with mock.patch.dict(os.environ, {"GROUNDED_TUTOR": "off"}, clear=False):
                    tutor_service.grounded_tutor_response(
                        conn,
                        "Explain mitosis.",
                        doc_ids=["doc-a"],
                        subject_name="Biology",
                        router=router,
                    )

        self.assertEqual(["doc-a"], search_mock.call_args.kwargs["doc_ids"])
        self.assertEqual("Biology", search_mock.call_args.kwargs["subject_name"])

    def test_misconceptions_and_scaffolds_are_populated_on_grounded_answer(self) -> None:
        with main.get_db() as conn:
            self._insert_document(conn, "doc-a", "bio-a.txt", "Biology")
            self._insert_chunk(
                conn,
                "chunk-1",
                "doc-a",
                "Mitosis separates duplicated chromosomes.",
                section="Mitosis",
            )
            conn.commit()
            hits = [
                self._hit(
                    "chunk-1", "doc-a", "Mitosis", "Mitosis separates duplicated chromosomes."
                )
            ]
            router = StubRouter(
                self._tool_result(
                    {
                        "summary": "Mitosis separates duplicated chromosomes.",
                        "claims": [
                            {
                                "text": "Mitosis separates duplicated chromosomes.",
                                "citations": [
                                    {
                                        "chunk_index": 1,
                                        "quote": "Mitosis separates duplicated chromosomes.",
                                    }
                                ],
                            }
                        ],
                        "unsupported_spans": [],
                    }
                )
            )
            with mock.patch("services.tutor.search_hybrid", return_value=hits):
                with mock.patch.dict(os.environ, {"GROUNDED_TUTOR": "on"}, clear=False):
                    response = tutor_service.grounded_tutor_response(
                        conn,
                        "Is mitosis always the same as meiosis?",
                        learner_confidence=20,
                        concept_name="Cell Division",
                        router=router,
                    )

        self.assertTrue(response.misconceptions)
        self.assertTrue(response.next_steps)

    def test_route_envelope_preserves_legacy_fields_and_adds_grounded_shape(self) -> None:
        with main.get_db() as conn:
            self._insert_document(conn, "doc-a", "bio-a.txt", "Biology")
            self._insert_chunk(
                conn,
                "chunk-1",
                "doc-a",
                "Mitosis separates duplicated chromosomes.",
                section="Mitosis",
                page_num=3,
            )
            self._insert_concept(conn, "concept-a", "doc-a", "Cell Division")
            conn.commit()

        hits = [
            self._hit("chunk-1", "doc-a", "Mitosis", "Mitosis separates duplicated chromosomes.")
        ]
        router = StubRouter(
            self._tool_result(
                {
                    "summary": "Mitosis separates duplicated chromosomes.",
                    "claims": [
                        {
                            "text": "Mitosis separates duplicated chromosomes.",
                            "citations": [
                                {
                                    "chunk_index": 1,
                                    "quote": "Mitosis separates duplicated chromosomes.",
                                }
                            ],
                        }
                    ],
                    "unsupported_spans": [],
                }
            )
        )

        with mock.patch("services.tutor.search_hybrid", return_value=hits):
            # Tutor now pulls its provider from ai.providers.get_default_provider.
            # The stub router satisfies AIProvider structurally, so substitution works.
            with mock.patch("services.tutor.get_default_provider", return_value=router):
                with mock.patch.dict(os.environ, {"GROUNDED_TUTOR": "on"}, clear=False):
                    response = tutor_query(
                        TutorQueryRequest(
                            question="What happens in mitosis?",
                            doc_id="doc-a",
                            concept_id="concept-a",
                            subject_name="Biology",
                            confidence=35,
                        )
                    )

        self.assertEqual("Mitosis separates duplicated chromosomes.", response["answer"])
        self.assertTrue(response["grounded"])
        self.assertEqual("chunk-1", response["citations"][0]["node_id"])
        self.assertEqual("doc-a", response["citations"][0]["document_id"])
        self.assertEqual("Mitosis separates duplicated chromosomes.", response["claims"][0]["text"])
        self.assertIn("unsupported_spans", response)
        self.assertIn("scaffolds", response)
        self.assertIn("scaffold_steps", response)
        self.assertIn("citation_drop_count", response)
        self.assertIn("citation_repair_count", response)
        self.assertEqual("claude-sonnet-4-6", response["model"])

    def test_structural_quote_passes_through_when_heuristic_flag_off(self) -> None:
        """Gate 1 (T2) regression-preservation: with RETRIEVAL_CHUNKS_HEURISTIC
        off (the default until T4), a heading-shape cited quote survives
        the new filter and reaches the answer's claims unchanged."""
        with main.get_db() as conn:
            self._insert_document(conn, "doc-h", "headings.txt", "Biology")
            chunk_content = (
                "Chapter 3: Mitosis Overview\n"
                "Mitosis separates duplicated chromosomes into two identical cells."
            )
            self._insert_chunk(
                conn,
                "chunk-heading",
                "doc-h",
                chunk_content,
                section="Mitosis",
                page_num=2,
            )
            conn.commit()
            hits = [self._hit("chunk-heading", "doc-h", "Mitosis", chunk_content)]
            router = StubRouter(
                self._tool_result(
                    {
                        "summary": "Mitosis overview.",
                        "claims": [
                            {
                                "text": "Mitosis is the focus of this section.",
                                "citations": [
                                    {
                                        "chunk_index": 1,
                                        # Heading-shape: is_heading_shape fires.
                                        "quote": "Chapter 3: Mitosis Overview",
                                    }
                                ],
                            }
                        ],
                        "unsupported_spans": [],
                    }
                )
            )
            with mock.patch("services.tutor.search_hybrid", return_value=hits):
                with mock.patch.dict(
                    os.environ,
                    {"GROUNDED_TUTOR": "on", "RETRIEVAL_CHUNKS_HEURISTIC": "false"},
                    clear=False,
                ):
                    response = tutor_service.grounded_tutor_response(
                        conn,
                        "What does chapter 3 say about mitosis?",
                        doc_ids=["doc-h"],
                        router=router,
                    )

        self.assertTrue(response.ok)
        # Flag off: structural quote keeps its citation.
        self.assertEqual(1, len(response.claims))
        self.assertEqual(1, len(response.claims[0].citations))
        self.assertEqual("Chapter 3: Mitosis Overview", response.claims[0].citations[0].quote)
        self.assertEqual(0, response.citation_structural_drop_count)
        self.assertEqual((), response.unsupported_spans)

    def test_structural_quote_dropped_when_heuristic_flag_on(self) -> None:
        """Gate 1 (T2) primary case: with RETRIEVAL_CHUNKS_HEURISTIC on,
        a heading-shape cited quote is dropped post-validation, the
        structural-drop counter increments, the orphaned claim moves to
        unsupported_spans, and citation_drop_count does NOT double-count
        the structural drop."""
        with main.get_db() as conn:
            self._insert_document(conn, "doc-h", "headings.txt", "Biology")
            chunk_content = (
                "Chapter 3: Mitosis Overview\n"
                "Mitosis separates duplicated chromosomes into two identical cells."
            )
            self._insert_chunk(
                conn,
                "chunk-heading",
                "doc-h",
                chunk_content,
                section="Mitosis",
                page_num=2,
            )
            conn.commit()
            hits = [self._hit("chunk-heading", "doc-h", "Mitosis", chunk_content)]
            router = StubRouter(
                self._tool_result(
                    {
                        "summary": "Mitosis overview.",
                        "claims": [
                            {
                                "text": "Mitosis is the focus of this section.",
                                "citations": [
                                    {
                                        "chunk_index": 1,
                                        "quote": "Chapter 3: Mitosis Overview",
                                    }
                                ],
                            }
                        ],
                        "unsupported_spans": [],
                    }
                )
            )
            with mock.patch("services.tutor.search_hybrid", return_value=hits):
                with mock.patch.dict(
                    os.environ,
                    {"GROUNDED_TUTOR": "on", "RETRIEVAL_CHUNKS_HEURISTIC": "true"},
                    clear=False,
                ):
                    response = tutor_service.grounded_tutor_response(
                        conn,
                        "What does chapter 3 say about mitosis?",
                        doc_ids=["doc-h"],
                        router=router,
                    )

        self.assertTrue(response.ok)
        self.assertEqual(0, len(response.claims))
        self.assertEqual(1, response.citation_structural_drop_count)
        # No double-count with the existing drop counter.
        self.assertEqual(0, response.citation_drop_count)
        # Orphaned claim text demoted to unsupported_spans, same path the
        # existing "if citations:" check uses for every claim whose
        # citations all fail upstream validation.
        self.assertIn(
            "Mitosis is the focus of this section.",
            response.unsupported_spans,
        )

    def test_mixed_structural_and_prose_keeps_prose_citation(self) -> None:
        """Gate 1 (T2): with the flag on, a claim with both a structural
        and a prose citation keeps the prose one. Only the structural
        citation is dropped; the claim survives because the surviving
        citation grounds it."""
        with main.get_db() as conn:
            self._insert_document(conn, "doc-h", "headings.txt", "Biology")
            chunk_content = (
                "Chapter 3: Mitosis Overview\n"
                "Mitosis separates duplicated chromosomes into two identical cells."
            )
            self._insert_chunk(
                conn,
                "chunk-heading",
                "doc-h",
                chunk_content,
                section="Mitosis",
                page_num=2,
            )
            conn.commit()
            hits = [self._hit("chunk-heading", "doc-h", "Mitosis", chunk_content)]
            router = StubRouter(
                self._tool_result(
                    {
                        "summary": "Mitosis overview.",
                        "claims": [
                            {
                                "text": "Mitosis separates duplicated chromosomes.",
                                "citations": [
                                    {
                                        # Structural — gets dropped.
                                        "chunk_index": 1,
                                        "quote": "Chapter 3: Mitosis Overview",
                                    },
                                    {
                                        # Prose substring of the same chunk — survives.
                                        "chunk_index": 1,
                                        "quote": "Mitosis separates duplicated chromosomes into two identical cells.",
                                    },
                                ],
                            }
                        ],
                        "unsupported_spans": [],
                    }
                )
            )
            with mock.patch("services.tutor.search_hybrid", return_value=hits):
                with mock.patch.dict(
                    os.environ,
                    {"GROUNDED_TUTOR": "on", "RETRIEVAL_CHUNKS_HEURISTIC": "true"},
                    clear=False,
                ):
                    response = tutor_service.grounded_tutor_response(
                        conn,
                        "What does mitosis do?",
                        doc_ids=["doc-h"],
                        router=router,
                    )

        self.assertTrue(response.ok)
        self.assertEqual(1, len(response.claims))
        self.assertEqual(1, len(response.claims[0].citations))
        # The surviving citation is the prose one.
        self.assertEqual(
            "Mitosis separates duplicated chromosomes into two identical cells.",
            response.claims[0].citations[0].quote,
        )
        self.assertEqual(1, response.citation_structural_drop_count)
        self.assertEqual(0, response.citation_drop_count)
        self.assertEqual((), response.unsupported_spans)


class TutorPrimaryRetrievalDispatchTests(unittest.TestCase):
    """T57 — verify `tutor_primary_retrieval` dispatches on
    `retrieval_use_nodes_enabled()`.

    Flag off (default): route through `search_hybrid` (legacy chunks-based
    hybrid). Flag on: route through `search_typed_hybrid` (typed-node FTS
    + vector). Both branches feed `_hydrate_node_context`, which already
    dispatches on hit shape, so the dispatch is the single hook the
    `RETRIEVAL_USE_NODES` flag controls at the primary retrieval site.

    This unit test locks the integration the T08 first-pass run surfaced
    as missing (see `evals/reports/compare-nodes-2026-05-19.md` and the
    T57 entry in `AUTONOMOUS_WORK_PLAN.md`). Without this dispatch the
    flag had zero observable effect at the primary retrieval call sites.
    """

    def setUp(self) -> None:
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

    def tearDown(self) -> None:
        main.BASE_DIR = self.original_base_dir
        main.DATA_DIR = self.original_data_dir
        main.UPLOAD_DIR = self.original_upload_dir
        main.DB_PATH = self.original_db_path
        main.SCHEMA_PATH = self.original_schema_path
        self.temp_dir.cleanup()

    def test_flag_off_routes_to_search_hybrid(self) -> None:
        chunks_sentinel = [
            ScoredHit(
                chunk_id="ck-1",
                doc_id="doc-a",
                section="Core",
                snippet="chunks branch",
                score=0.42,
                components={"fts": 0.42},
                sources=("fts",),
            )
        ]
        with main.get_db() as conn:
            with mock.patch.dict(os.environ, {"RETRIEVAL_USE_NODES": "false"}, clear=False):
                with (
                    mock.patch(
                        "services.tutor.search_hybrid", return_value=chunks_sentinel
                    ) as chunks_mock,
                    mock.patch(
                        "services.tutor.search_typed_hybrid", return_value=["nodes-sentinel"]
                    ) as nodes_mock,
                ):
                    hits = tutor_service.tutor_primary_retrieval(
                        conn,
                        "Explain mitosis.",
                        doc_ids=None,
                        subject_name="Biology",
                        limit=8,
                    )

        self.assertIs(chunks_sentinel, hits)
        self.assertEqual(1, chunks_mock.call_count)
        self.assertEqual(0, nodes_mock.call_count)
        kwargs = chunks_mock.call_args.kwargs
        self.assertEqual("Biology", kwargs["subject_name"])
        self.assertIsNone(kwargs["doc_ids"])
        self.assertEqual(8, kwargs["limit"])

    def test_flag_on_routes_to_search_typed_hybrid(self) -> None:
        nodes_sentinel = [
            tutor_service.RetrievedNode(
                node_id=7,
                doc_id="doc-a",
                node_type="body",
                heading_path="Core",
                page=1,
                char_start=0,
                char_end=42,
                verbatim_text="nodes branch",
                snippet="nodes branch",
                score=0.42,
                components={"fts": 0.42},
                sources=("fts",),
            )
        ]
        with main.get_db() as conn:
            with mock.patch.dict(os.environ, {"RETRIEVAL_USE_NODES": "true"}, clear=False):
                with (
                    mock.patch(
                        "services.tutor.search_hybrid", return_value=["chunks-sentinel"]
                    ) as chunks_mock,
                    mock.patch(
                        "services.tutor.search_typed_hybrid", return_value=nodes_sentinel
                    ) as nodes_mock,
                ):
                    hits = tutor_service.tutor_primary_retrieval(
                        conn,
                        "Explain mitosis.",
                        doc_ids=["doc-a"],
                        subject_name=None,
                        limit=8,
                    )

        self.assertIs(nodes_sentinel, hits)
        self.assertEqual(0, chunks_mock.call_count)
        self.assertEqual(1, nodes_mock.call_count)
        kwargs = nodes_mock.call_args.kwargs
        self.assertIsNone(kwargs["subject_name"])
        self.assertEqual(["doc-a"], kwargs["doc_ids"])
        self.assertEqual(8, kwargs["limit"])

    def test_grounded_tutor_response_uses_dispatcher(self) -> None:
        """End-to-end: `grounded_tutor_response` exercises the dispatcher
        on the primary retrieval call site (services/tutor.py:1273)."""
        with main.get_db() as conn:
            conn.execute(
                "INSERT INTO documents (id, filename, file_type, subject_name, status)"
                " VALUES (?, ?, 'txt', ?, 'ready')",
                ("doc-a", "bio.txt", "Biology"),
            )
            conn.commit()
            with mock.patch.dict(
                os.environ,
                {"RETRIEVAL_USE_NODES": "true", "GROUNDED_TUTOR": "off"},
                clear=False,
            ):
                with (
                    mock.patch("services.tutor.search_hybrid", return_value=[]) as chunks_mock,
                    mock.patch("services.tutor.search_typed_hybrid", return_value=[]) as nodes_mock,
                ):
                    tutor_service.grounded_tutor_response(
                        conn, "Explain mitosis.", router=StubRouter(enabled=False)
                    )

        # With the flag on, dispatcher MUST hit the typed-hybrid path
        # at the primary retrieval site, not the legacy chunks hybrid.
        self.assertEqual(0, chunks_mock.call_count)
        self.assertEqual(1, nodes_mock.call_count)


class HydrateNodeContextDispatchTests(unittest.TestCase):
    """T02 — verify `_hydrate_node_context` dispatches on hit shape.

    `RetrievedNode` (typed-node retrieval) routes to `_hydrate_from_nodes`,
    which fetches only the document filename and reuses RetrievedNode's
    verbatim_text/heading_path/page directly. `ScoredHit` (legacy chunks
    retrieval) routes to `_hydrate_from_chunks`, which does the existing
    `FROM chunks JOIN documents` lookup. Phase 4 flips the caller dispatch.
    """

    def setUp(self) -> None:
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

    def tearDown(self) -> None:
        main.BASE_DIR = self.original_base_dir
        main.DATA_DIR = self.original_data_dir
        main.UPLOAD_DIR = self.original_upload_dir
        main.DB_PATH = self.original_db_path
        main.SCHEMA_PATH = self.original_schema_path
        self.temp_dir.cleanup()

    def test_retrieved_node_hits_dispatch_to_nodes_path(self) -> None:
        from services.retrieval.typed_hybrid import RetrievedNode

        with main.get_db() as conn:
            conn.execute("DELETE FROM documents")
            conn.execute(
                """
                INSERT INTO documents (id, filename, file_type, subject_name, status)
                VALUES (?, ?, 'txt', ?, 'ready')
                """,
                ("doc-nodes-1", "biology.md", "Biology"),
            )
            hit = RetrievedNode(
                node_id=42,
                doc_id="doc-nodes-1",
                node_type="body",
                heading_path="Cell division",
                page=3,
                char_start=0,
                char_end=80,
                verbatim_text="Mitosis creates two genetically identical daughter cells.",
                snippet="Mitosis creates two daughter cells.",
                score=0.91,
            )
            contexts = tutor_service._hydrate_node_context([hit], conn)

        self.assertEqual(len(contexts), 1)
        ctx = contexts[0]
        # node_id flows through as the real int from nodes.id; this is
        # the post-T02 invariant the chunks path can't satisfy yet.
        self.assertEqual(ctx.node_id, 42)
        self.assertEqual(ctx.doc_id, "doc-nodes-1")
        self.assertEqual(ctx.document_name, "biology.md")
        self.assertEqual(ctx.section, "Cell division")
        self.assertEqual(ctx.page_num, 3)
        self.assertIn("Mitosis", ctx.verbatim_text)
        self.assertAlmostEqual(ctx.score, 0.91)

    def test_heading_nodes_are_filtered_from_citation_context(self) -> None:
        """Gate 0 — a heading is a section label, not answer content, and
        must never reach the model as citable context even when it
        outranks the body node scoped under it."""
        from services.retrieval.typed_hybrid import RetrievedNode

        with main.get_db() as conn:
            conn.execute("DELETE FROM documents")
            conn.execute(
                """
                INSERT INTO documents (id, filename, file_type, subject_name, status)
                VALUES (?, ?, 'txt', ?, 'ready')
                """,
                ("doc-nodes-h", "biology.md", "Biology"),
            )
            heading = RetrievedNode(
                node_id=7,
                doc_id="doc-nodes-h",
                node_type="heading",
                heading_path="Cell division",
                page=1,
                char_start=0,
                char_end=13,
                verbatim_text="Cell division",
                snippet="Cell division",
                score=0.99,
            )
            body = RetrievedNode(
                node_id=8,
                doc_id="doc-nodes-h",
                node_type="body",
                heading_path="Cell division",
                page=1,
                char_start=14,
                char_end=72,
                verbatim_text="Mitosis creates two genetically identical daughter cells.",
                snippet="Mitosis creates two daughter cells.",
                score=0.40,
            )
            contexts = tutor_service._hydrate_node_context([heading, body], conn)

        # The heading ranked highest yet is dropped; only the body node —
        # the one that can actually ground a claim — survives.
        self.assertEqual([c.node_id for c in contexts], [8])
        self.assertEqual(contexts[0].node_type, "body")

    def test_scored_hit_dispatch_to_chunks_path(self) -> None:
        with main.get_db() as conn:
            conn.execute("DELETE FROM chunks")
            conn.execute("DELETE FROM documents")
            conn.execute(
                """
                INSERT INTO documents (id, filename, file_type, subject_name, status)
                VALUES (?, ?, 'txt', ?, 'ready')
                """,
                ("doc-chunks-1", "biology.md", "Biology"),
            )
            conn.execute(
                """
                INSERT INTO chunks (id, doc_id, content, section, page_num, chunk_index, token_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "chunk-legacy-1",
                    "doc-chunks-1",
                    "Mitochondria are organelles.",
                    "Cells",
                    1,
                    1,
                    4,
                ),
            )
            hit = ScoredHit(
                chunk_id="chunk-legacy-1",
                doc_id="doc-chunks-1",
                section="Cells",
                snippet="Mitochondria are organelles.",
                score=0.42,
                components={"fts": 0.42},
                sources=("fts",),
            )
            contexts = tutor_service._hydrate_node_context([hit], conn)

        self.assertEqual(len(contexts), 1)
        ctx = contexts[0]
        # T01 transitional: chunk_id str UUID flows through node_id on
        # the chunks branch until Phase 4 flips the caller dispatch.
        self.assertEqual(ctx.node_id, "chunk-legacy-1")
        self.assertEqual(ctx.doc_id, "doc-chunks-1")
        self.assertEqual(ctx.document_name, "biology.md")
        self.assertEqual(ctx.section, "Cells")
        self.assertEqual(ctx.page_num, 1)
        self.assertIn("Mitochondria", ctx.verbatim_text)

    def test_empty_hits_returns_empty(self) -> None:
        with main.get_db() as conn:
            self.assertEqual(tutor_service._hydrate_node_context([], conn), [])

    def test_nodes_branch_strips_extraction_artifacts_from_verbatim_text(self) -> None:
        from services.retrieval.typed_hybrid import RetrievedNode

        with main.get_db() as conn:
            conn.execute("DELETE FROM documents")
            conn.execute(
                """
                INSERT INTO documents (id, filename, file_type, subject_name, status)
                VALUES (?, ?, 'txt', ?, 'ready')
                """,
                ("doc-artifact-1", "math.md", "Math"),
            )
            # PUA U+E001 and empty-parens are the canonical PDF extraction
            # artifacts that `strip_extraction_artifacts` removes.
            hit = RetrievedNode(
                node_id=99,
                doc_id="doc-artifact-1",
                node_type="body",
                heading_path="Equations",
                page=1,
                char_start=0,
                char_end=40,
                verbatim_text="Euler's identity: e(i pi) + 1 = 0 ()",
                snippet="Euler's identity: e(i pi) + 1 = 0 ()",
                score=0.5,
            )
            contexts = tutor_service._hydrate_node_context([hit], conn)

        self.assertEqual(len(contexts), 1)
        ctx = contexts[0]
        self.assertNotIn("", ctx.verbatim_text)
        self.assertNotIn("()", ctx.verbatim_text)
        self.assertNotIn("", ctx.snippet)

    def test_nodes_branch_warns_and_falls_back_on_orphaned_node(self) -> None:
        from services.retrieval.typed_hybrid import RetrievedNode

        with main.get_db() as conn:
            conn.execute("DELETE FROM documents")
            hit = RetrievedNode(
                node_id=77,
                doc_id="doc-missing",
                node_type="body",
                heading_path="Stub",
                page=None,
                char_start=0,
                char_end=10,
                verbatim_text="Orphaned text.",
                snippet="Orphaned text.",
                score=0.1,
            )
            with mock.patch.object(tutor_service, "log_event") as logged:
                contexts = tutor_service._hydrate_node_context([hit], conn)

        self.assertEqual(len(contexts), 1)
        self.assertEqual(contexts[0].document_name, "Source")
        self.assertTrue(
            any(call.args[2] == "tutor_hydrate_orphaned_node" for call in logged.call_args_list),
            "expected tutor_hydrate_orphaned_node log_event for orphaned RetrievedNode",
        )


class FallbackContextsFromScopeTests(unittest.TestCase):
    """T03 — verify `_fallback_contexts_from_scope` reads `FROM nodes`.

    Three scope-fallback paths exercise the same node-keyed query:
      1. concept_id → translate `concepts.source_chunks` UUIDs to nodes
         by joining (doc_id, page_num) since `chunks` has no char_start.
      2. doc_ids → SELECT FROM nodes WHERE doc_id IN (...).
      3. subject_name → SELECT FROM nodes JOIN documents ON subject_name.

    Guard against silent fallback to chunks: when nodes are empty but
    chunks still exist for the same doc, the result is empty list.
    """

    def setUp(self) -> None:
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

        # T03 fallback dispatch reads RETRIEVAL_USE_NODES; this class
        # exercises the nodes path exclusively, so enable the flag for
        # the duration of the test.
        self._env_patch = mock.patch.dict(os.environ, {"RETRIEVAL_USE_NODES": "true"}, clear=False)
        self._env_patch.start()

    def tearDown(self) -> None:
        self._env_patch.stop()
        main.BASE_DIR = self.original_base_dir
        main.DATA_DIR = self.original_data_dir
        main.UPLOAD_DIR = self.original_upload_dir
        main.DB_PATH = self.original_db_path
        main.SCHEMA_PATH = self.original_schema_path
        self.temp_dir.cleanup()

    @staticmethod
    def _insert_document(conn, doc_id: str, filename: str, subject_name: str) -> None:
        conn.execute(
            """
            INSERT INTO documents (id, filename, file_type, subject_name, status)
            VALUES (?, ?, 'txt', ?, 'ready')
            """,
            (doc_id, filename, subject_name),
        )

    @staticmethod
    def _insert_node(
        conn,
        doc_id: str,
        verbatim_text: str,
        *,
        heading_path: str = "Core",
        page: int | None = 1,
        char_start: int = 0,
        reading_order: int = 1,
    ) -> int:
        cursor = conn.execute(
            """
            INSERT INTO nodes (
                doc_id, node_type, heading_path, page, char_start, char_end,
                verbatim_text, reading_order
            ) VALUES (?, 'body', ?, ?, ?, ?, ?, ?)
            """,
            (
                doc_id,
                heading_path,
                page,
                char_start,
                char_start + len(verbatim_text),
                verbatim_text,
                reading_order,
            ),
        )
        return int(cursor.lastrowid)

    @staticmethod
    def _insert_chunk(
        conn,
        chunk_id: str,
        doc_id: str,
        content: str,
        *,
        section: str = "Core",
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

    def test_doc_scope_returns_node_keyed_contexts(self) -> None:
        with main.get_db() as conn:
            self._insert_document(conn, "doc-a", "bio.md", "Biology")
            node_id = self._insert_node(
                conn, "doc-a", "Mitochondria are the powerhouse of the cell."
            )
            conn.commit()
            contexts = tutor_service._fallback_contexts_from_scope(
                conn,
                doc_ids=["doc-a"],
                subject_name=None,
                concept_id=None,
                limit=8,
            )

        self.assertEqual(len(contexts), 1)
        ctx = contexts[0]
        # The post-T03 invariant: node_id is the real integer nodes.id,
        # not the legacy chunks str-UUID the helper returned before.
        self.assertEqual(ctx.node_id, node_id)
        self.assertIsInstance(ctx.node_id, int)
        self.assertEqual(ctx.doc_id, "doc-a")
        self.assertEqual(ctx.document_name, "bio.md")
        self.assertIn("Mitochondria", ctx.verbatim_text)

    def test_subject_scope_returns_node_keyed_contexts(self) -> None:
        with main.get_db() as conn:
            self._insert_document(conn, "doc-a", "bio.md", "Biology")
            self._insert_document(conn, "doc-b", "chem.md", "Chemistry")
            self._insert_node(conn, "doc-a", "Photosynthesis converts light energy.")
            self._insert_node(conn, "doc-b", "Atoms bond covalently.")
            conn.commit()
            contexts = tutor_service._fallback_contexts_from_scope(
                conn,
                doc_ids=None,
                subject_name="Biology",
                concept_id=None,
                limit=8,
            )

        self.assertEqual(len(contexts), 1)
        self.assertEqual(contexts[0].doc_id, "doc-a")
        self.assertIn("Photosynthesis", contexts[0].verbatim_text)

    def test_concept_scope_translates_source_chunks_to_nodes_via_doc_page(self) -> None:
        with main.get_db() as conn:
            self._insert_document(conn, "doc-a", "bio.md", "Biology")
            # A legacy chunk pinned to (doc-a, page 2) lives in source_chunks.
            self._insert_chunk(conn, "chunk-1", "doc-a", "Krebs cycle.", page_num=2)
            # The node we expect translation to find shares (doc_id, page).
            node_id = self._insert_node(
                conn,
                "doc-a",
                "The Krebs cycle oxidizes acetyl-CoA in mitochondria.",
                page=2,
                reading_order=5,
            )
            # A noise node on a different page must NOT be returned.
            self._insert_node(
                conn,
                "doc-a",
                "Glycolysis happens in the cytoplasm.",
                page=1,
                reading_order=1,
            )
            conn.execute(
                """
                INSERT INTO concepts (id, doc_id, name, description, mastery, source_chunks)
                VALUES (?, ?, ?, ?, 0.2, ?)
                """,
                (
                    "concept-krebs",
                    "doc-a",
                    "Krebs cycle",
                    "Krebs cycle",
                    '["chunk-1"]',
                ),
            )
            conn.commit()
            contexts = tutor_service._fallback_contexts_from_scope(
                conn,
                doc_ids=None,
                subject_name=None,
                concept_id="concept-krebs",
                limit=8,
            )

        node_ids = [ctx.node_id for ctx in contexts]
        self.assertIn(node_id, node_ids)
        self.assertNotIn(
            "Glycolysis",
            " ".join(ctx.verbatim_text for ctx in contexts),
            "noise node on a different page must not leak into the result",
        )

    def test_fallback_returns_empty_when_only_chunks_present_no_nodes(self) -> None:
        """Regression guard for CLAUDE.md "no silent fallbacks" rule.

        Chunks rows exist for the doc, but the nodes table has no rows.
        The fallback must NOT silently widen to chunks; it must return
        empty so the caller can surface ok=False / weak_coverage.
        """
        with main.get_db() as conn:
            self._insert_document(conn, "doc-a", "bio.md", "Biology")
            self._insert_chunk(conn, "chunk-only", "doc-a", "Only chunk content.")
            conn.commit()
            doc_contexts = tutor_service._fallback_contexts_from_scope(
                conn,
                doc_ids=["doc-a"],
                subject_name=None,
                concept_id=None,
                limit=8,
            )
            subject_contexts = tutor_service._fallback_contexts_from_scope(
                conn,
                doc_ids=None,
                subject_name="Biology",
                concept_id=None,
                limit=8,
            )

        self.assertEqual(doc_contexts, [])
        self.assertEqual(subject_contexts, [])

    def test_concept_fallback_returns_empty_when_translation_fails(self) -> None:
        """If `concepts.source_chunks` resolves to (doc_id, page) tuples
        that no node row shares, translation has failed — return empty
        rather than widening to all nodes in the doc."""
        with main.get_db() as conn:
            self._insert_document(conn, "doc-a", "bio.md", "Biology")
            self._insert_chunk(conn, "chunk-page-2", "doc-a", "Stuff on page 2.", page_num=2)
            # Node lives on page 99 — translation must miss.
            self._insert_node(
                conn,
                "doc-a",
                "Far away node on a different page.",
                page=99,
                reading_order=1,
            )
            conn.execute(
                """
                INSERT INTO concepts (id, doc_id, name, description, mastery, source_chunks)
                VALUES (?, ?, ?, ?, 0.2, ?)
                """,
                (
                    "concept-x",
                    "doc-a",
                    "Concept X",
                    "Concept X",
                    '["chunk-page-2"]',
                ),
            )
            conn.commit()
            contexts = tutor_service._fallback_contexts_from_scope(
                conn,
                doc_ids=None,
                subject_name=None,
                concept_id="concept-x",
                limit=8,
            )

        self.assertEqual(contexts, [])


class HydrateCitedContextsTests(unittest.TestCase):
    """T04 — verify `_hydrate_cited_contexts` dispatches on the same
    RETRIEVAL_USE_NODES flag the rest of the tutor stack does.

    Two paths:
      1. flag on → SELECT FROM nodes WHERE id IN, RetrievedNode hits,
         HydratedNodeContext with int node_id and verbatim_text from
         nodes.verbatim_text.
      2. flag off → SELECT FROM chunks WHERE id IN, ScoredHit hits,
         HydratedNodeContext built via `_hydrate_from_chunks`.

    Guard: empty cited_ids returns []; cited_ids that find no rows
    return [] (no silent fallback between the two paths).
    """

    def setUp(self) -> None:
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

    def tearDown(self) -> None:
        main.BASE_DIR = self.original_base_dir
        main.DATA_DIR = self.original_data_dir
        main.UPLOAD_DIR = self.original_upload_dir
        main.DB_PATH = self.original_db_path
        main.SCHEMA_PATH = self.original_schema_path
        self.temp_dir.cleanup()

    @staticmethod
    def _insert_document(conn, doc_id: str, filename: str) -> None:
        conn.execute(
            """
            INSERT INTO documents (id, filename, file_type, subject_name, status)
            VALUES (?, ?, 'txt', 'Biology', 'ready')
            """,
            (doc_id, filename),
        )

    @staticmethod
    def _insert_chunk(conn, chunk_id: str, doc_id: str, content: str) -> None:
        conn.execute(
            """
            INSERT INTO chunks (id, doc_id, content, section, page_num, chunk_index, token_count)
            VALUES (?, ?, ?, 'Core', 1, 1, ?)
            """,
            (chunk_id, doc_id, content, len(content.split())),
        )

    @staticmethod
    def _insert_node(conn, doc_id: str, verbatim_text: str, *, page: int = 1) -> int:
        cursor = conn.execute(
            """
            INSERT INTO nodes (
                doc_id, node_type, heading_path, page, char_start, char_end,
                verbatim_text, reading_order
            ) VALUES (?, 'body', 'Core', ?, 0, ?, ?, 1)
            """,
            (doc_id, page, len(verbatim_text), verbatim_text),
        )
        return int(cursor.lastrowid)

    def test_returns_empty_for_empty_cited_ids(self) -> None:
        with main.get_db() as conn:
            self.assertEqual(tutor_service._hydrate_cited_contexts(conn, []), [])

    def test_nodes_path_resolves_int_node_ids_to_hydrated_contexts(self) -> None:
        with mock.patch.dict(os.environ, {"RETRIEVAL_USE_NODES": "true"}, clear=False):
            with main.get_db() as conn:
                self._insert_document(conn, "doc-a", "bio.txt")
                node_id = self._insert_node(
                    conn,
                    "doc-a",
                    "Mitosis separates duplicated chromosomes.",
                )
                conn.commit()
                contexts = tutor_service._hydrate_cited_contexts(conn, [node_id])

        self.assertEqual(1, len(contexts))
        ctx = contexts[0]
        self.assertEqual(node_id, ctx.node_id)
        self.assertEqual("doc-a", ctx.doc_id)
        self.assertEqual("bio.txt", ctx.document_name)
        self.assertEqual("Mitosis separates duplicated chromosomes.", ctx.verbatim_text)

    def test_chunks_path_resolves_uuid_chunk_ids_to_hydrated_contexts(self) -> None:
        # RETRIEVAL_USE_NODES default is false; rely on it.
        with main.get_db() as conn:
            self._insert_document(conn, "doc-a", "bio.txt")
            self._insert_chunk(conn, "chunk-a", "doc-a", "Meiosis halves chromosome number.")
            conn.commit()
            contexts = tutor_service._hydrate_cited_contexts(conn, ["chunk-a"])

        self.assertEqual(1, len(contexts))
        ctx = contexts[0]
        # chunks-path keeps the TEXT UUID under the T01 transitional contract.
        self.assertEqual("chunk-a", ctx.node_id)
        self.assertEqual("doc-a", ctx.doc_id)
        self.assertEqual("bio.txt", ctx.document_name)
        self.assertIn("Meiosis", ctx.verbatim_text)

    def test_nodes_path_returns_empty_when_no_node_rows_resolve(self) -> None:
        # Flag on, but cited ids reference no existing node rows.
        # No silent fallback to chunks — return empty.
        with mock.patch.dict(os.environ, {"RETRIEVAL_USE_NODES": "true"}, clear=False):
            with main.get_db() as conn:
                self._insert_document(conn, "doc-a", "bio.txt")
                # A chunk exists for doc-a but the flag-on path must
                # not silently degrade to it.
                self._insert_chunk(conn, "chunk-orphan", "doc-a", "Orphan text.")
                conn.commit()
                contexts = tutor_service._hydrate_cited_contexts(conn, [9999])

        self.assertEqual([], contexts)

    def test_chunks_path_returns_empty_when_no_chunk_rows_resolve(self) -> None:
        with main.get_db() as conn:
            self._insert_document(conn, "doc-a", "bio.txt")
            conn.commit()
            contexts = tutor_service._hydrate_cited_contexts(conn, ["chunk-missing"])

        self.assertEqual([], contexts)


class CitationNodeTypeGateTests(unittest.TestCase):
    """Carrel V2: every Citation must carry its source node_type so a
    verification surface can tell prose from structural cites, and
    _resolve_grounded_answer must refuse to ground a claim on a
    structural context as a backstop to _drop_non_citable_contexts."""

    def _result(self, payload: dict[str, object]) -> ClaudeCallResult:
        return ClaudeCallResult(
            ok=True,
            task="balanced",
            model="claude-sonnet-4-6",
            request_kind="tutor.grounded_answer",
            text=None,
            json_payload=payload,
            error_code=None,
            error_message=None,
            latency_ms=10.0,
            input_tokens=10,
            output_tokens=10,
            cache_creation_input_tokens=None,
            cache_read_input_tokens=None,
            cache_hit=False,
            service_tier="auto",
            stop_reason="tool_use",
            request_id="req_node_type_gate",
        )

    def _ctx(self, *, node_type: str, text: str) -> tutor_service.HydratedNodeContext:
        return tutor_service.HydratedNodeContext(
            node_id=1,
            doc_id="doc-1",
            document_name="Source.pdf",
            section="Intro",
            page_num=1,
            verbatim_text=text,
            snippet=text,
            score=0.5,
            node_type=node_type,
        )

    def test_body_citation_carries_node_type_through(self) -> None:
        ctx = self._ctx(node_type="body", text="Mitosis separates chromosomes.")
        payload = {
            "summary": "Mitosis fact.",
            "claims": [
                {
                    "text": "Mitosis separates chromosomes.",
                    "citations": [{"chunk_index": 1, "quote": "Mitosis separates chromosomes."}],
                }
            ],
            "unsupported_spans": [],
        }
        answer = tutor_service._resolve_grounded_answer(
            self._result(payload),
            [ctx],
            question="What does mitosis do?",
            concept_name=None,
            learner_confidence=None,
            scope_fallback_used=False,
        )
        self.assertEqual(1, len(answer.claims))
        self.assertEqual(1, len(answer.claims[0].citations))
        self.assertEqual("body", answer.claims[0].citations[0].node_type)
        self.assertEqual(0, answer.citation_non_prose_drop_count)

    def test_heading_context_is_dropped_at_validation_time(self) -> None:
        """Backstop path. If a heading/header/footer context somehow
        reaches _resolve_grounded_answer (e.g. a future caller skips
        _drop_non_citable_contexts), the cite must be dropped, the new
        counter must increment, and the claim must demote to
        unsupported_spans without inflating the verbatim-quote drop
        counter."""
        ctx = self._ctx(
            node_type="heading",
            text="Chapter 3: Mitosis Overview",
        )
        payload = {
            "summary": "Mitosis is the focus.",
            "claims": [
                {
                    "text": "Mitosis is the focus of this section.",
                    "citations": [{"chunk_index": 1, "quote": "Chapter 3: Mitosis Overview"}],
                }
            ],
            "unsupported_spans": [],
        }
        answer = tutor_service._resolve_grounded_answer(
            self._result(payload),
            [ctx],
            question="What is chapter 3 about?",
            concept_name=None,
            learner_confidence=None,
            scope_fallback_used=False,
        )
        self.assertEqual(0, len(answer.claims))
        self.assertEqual(1, answer.citation_non_prose_drop_count)
        self.assertEqual(0, answer.citation_drop_count)
        self.assertEqual(0, answer.citation_structural_drop_count)
        self.assertIn(
            "Mitosis is the focus of this section.",
            answer.unsupported_spans,
        )

    def test_mixed_body_and_heading_keeps_body_citation(self) -> None:
        body = self._ctx(node_type="body", text="Mitosis separates chromosomes.")
        heading = tutor_service.HydratedNodeContext(
            node_id=2,
            doc_id="doc-1",
            document_name="Source.pdf",
            section="Intro",
            page_num=1,
            verbatim_text="Chapter 3: Mitosis Overview",
            snippet="Chapter 3: Mitosis Overview",
            score=0.4,
            node_type="heading",
        )
        payload = {
            "summary": "Mitosis fact.",
            "claims": [
                {
                    "text": "Mitosis separates chromosomes.",
                    "citations": [
                        {"chunk_index": 2, "quote": "Chapter 3: Mitosis Overview"},
                        {"chunk_index": 1, "quote": "Mitosis separates chromosomes."},
                    ],
                }
            ],
            "unsupported_spans": [],
        }
        answer = tutor_service._resolve_grounded_answer(
            self._result(payload),
            [body, heading],
            question="What does mitosis do?",
            concept_name=None,
            learner_confidence=None,
            scope_fallback_used=False,
        )
        self.assertEqual(1, len(answer.claims))
        self.assertEqual(1, len(answer.claims[0].citations))
        self.assertEqual("body", answer.claims[0].citations[0].node_type)
        self.assertEqual(
            "Mitosis separates chromosomes.",
            answer.claims[0].citations[0].quote,
        )
        self.assertEqual(1, answer.citation_non_prose_drop_count)
        self.assertEqual((), answer.unsupported_spans)


if __name__ == "__main__":
    unittest.main()
