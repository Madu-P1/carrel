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
        fallback produces only a couple of chunks, threshold is 3. We must
        refuse with error='weak_coverage' instead of asking the LLM to
        synthesize from thin evidence — that's the hallucination surface."""
        with main.get_db() as conn:
            self._insert_document(conn, "doc-a", "bio-a.txt", "Biology")
            # Only 2 chunks in the doc, both tangential to the question.
            self._insert_chunk(conn, "chunk-1", "doc-a", "Ion channels.")
            self._insert_chunk(conn, "chunk-2", "doc-a", "Membrane potential.")
            conn.commit()
            router = StubRouter()
            # Hybrid search misses; scope fallback returns the 2 chunks.
            with mock.patch("services.tutor.search_hybrid", return_value=[]):
                with mock.patch.dict(os.environ, {"GROUNDED_TUTOR": "on"}, clear=False):
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
        """Counter-case: scope fallback produces enough chunks (>= threshold).
        Claude still runs because there's real material to synthesize from."""
        with main.get_db() as conn:
            self._insert_document(conn, "doc-a", "bio-a.txt", "Biology")
            # 4 chunks >= _WEAK_COVERAGE_MIN_CONTEXTS (default 3).
            for i in range(4):
                self._insert_chunk(
                    conn,
                    f"chunk-{i}",
                    "doc-a",
                    f"Sentence {i} about cellular respiration.",
                )
            conn.commit()
            router = StubRouter(
                result=self._tool_result({"summary": "ok", "claims": [], "unsupported_spans": []})
            )
            with mock.patch("services.tutor.search_hybrid", return_value=[]):
                with mock.patch.dict(os.environ, {"GROUNDED_TUTOR": "on"}, clear=False):
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
        self.assertEqual("chunk-1", response["citations"][0]["chunk_id"])
        self.assertEqual("doc-a", response["citations"][0]["document_id"])
        self.assertEqual("Mitosis separates duplicated chromosomes.", response["claims"][0]["text"])
        self.assertIn("unsupported_spans", response)
        self.assertIn("scaffolds", response)
        self.assertIn("scaffold_steps", response)
        self.assertIn("citation_drop_count", response)
        self.assertIn("citation_repair_count", response)
        self.assertEqual("claude-sonnet-4-6", response["model"])


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


if __name__ == "__main__":
    unittest.main()
