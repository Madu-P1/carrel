"""Tests for the Manage Cards surface.

Covers `services.study.list_cards`, `list_subjects`, `delete_card`, and
`bulk_delete_cards`, plus the FastAPI routes wired on top. Data fixtures
reuse the ingestion pipeline so we exercise real SQL joins (srs_cards →
concepts → documents) rather than handcrafted rows.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import main
from routes.study import bulk_delete_cards, delete_card, list_cards, list_subjects
from services import study as study_service
from services.ingestion import ingest_document_record
from services.local_api_security import HEADER_NAME, get_local_api_token

_SAMPLE_FINANCE = (
    "Capital markets are venues where buyers and sellers trade financial "
    "instruments. The primary market issues new securities; the secondary "
    "market trades existing ones. Market efficiency concerns how quickly "
    "information is reflected in prices. Arbitrage exists when identical "
    "assets trade at different prices across markets."
)

_SAMPLE_BIOLOGY = (
    "Mitosis is the process by which a eukaryotic cell divides into two "
    "genetically identical daughter cells. Checkpoints pause progression "
    "when DNA damage is detected. The cell cycle includes interphase and "
    "the mitotic phase with prophase, metaphase, anaphase, and telophase."
)


class ManageCardsServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.original_base_dir = main.BASE_DIR
        self.original_data_dir = main.DATA_DIR
        self.original_upload_dir = main.UPLOAD_DIR
        self.original_db_path = main.DB_PATH
        self.original_schema_path = main.SCHEMA_PATH

        # PR 0a: this suite's fixture is "ingest two documents and expect
        # cards to exist". Auto-card creation on upload is now off by
        # default; opt the suite into the legacy behaviour so the
        # ingestion-seeded join queries still have rows to filter.
        self._original_auto_card_draft = os.environ.get("CARREL_AUTO_CARD_DRAFT")
        os.environ["CARREL_AUTO_CARD_DRAFT"] = "true"

        main.BASE_DIR = self.base_dir
        main.DATA_DIR = self.base_dir / "data"
        main.UPLOAD_DIR = main.DATA_DIR / "uploads"
        main.DB_PATH = main.DATA_DIR / "test.db"
        main.SCHEMA_PATH = self.original_schema_path
        main.initialize_database()
        self._seed_library()

    def tearDown(self) -> None:
        main.BASE_DIR = self.original_base_dir
        main.DATA_DIR = self.original_data_dir
        main.UPLOAD_DIR = self.original_upload_dir
        main.DB_PATH = self.original_db_path
        main.SCHEMA_PATH = self.original_schema_path
        if self._original_auto_card_draft is None:
            os.environ.pop("CARREL_AUTO_CARD_DRAFT", None)
        else:
            os.environ["CARREL_AUTO_CARD_DRAFT"] = self._original_auto_card_draft
        self.temp_dir.cleanup()

    def _seed_library(self) -> None:
        """Ingest two documents across two subjects so filter tests have
        something to discriminate against."""
        with main.get_db() as conn:
            ingest_document_record(
                conn=conn,
                filename="finance-01.txt",
                file_type="txt",
                extracted_text=_SAMPLE_FINANCE,
                page_count=None,
                subject_name="Finance",
            )
            ingest_document_record(
                conn=conn,
                filename="biology-01.txt",
                file_type="txt",
                extracted_text=_SAMPLE_BIOLOGY,
                page_count=None,
                subject_name="Biology",
            )

    def _total_cards(self) -> int:
        with main.get_db() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM srs_cards").fetchone()
        return int(row["n"])

    def test_list_cards_paginates_and_returns_total(self) -> None:
        expected_total = self._total_cards()
        self.assertGreater(
            expected_total,
            0,
            "Ingestion should have produced at least one SRS card for the seed docs.",
        )

        with main.get_db() as conn:
            page = study_service.list_cards(conn, limit=1, offset=0)

        self.assertEqual(page["total"], expected_total)
        self.assertEqual(len(page["cards"]), 1)
        self.assertEqual(page["limit"], 1)
        card = page["cards"][0]
        # Sanity — joined fields are present and populated.
        self.assertIn(card["subject_name"], {"Finance", "Biology"})
        self.assertTrue(card["document_name"])
        self.assertTrue(card["concept"])
        self.assertTrue(card["front"])
        self.assertTrue(card["back"])

    def test_list_cards_filter_by_subject(self) -> None:
        with main.get_db() as conn:
            finance_page = study_service.list_cards(conn, subject="Finance", limit=100)
            biology_page = study_service.list_cards(conn, subject="Biology", limit=100)

        self.assertGreater(finance_page["total"], 0)
        self.assertGreater(biology_page["total"], 0)
        for card in finance_page["cards"]:
            self.assertEqual(card["subject_name"], "Finance")
        for card in biology_page["cards"]:
            self.assertEqual(card["subject_name"], "Biology")
        self.assertEqual(
            finance_page["total"] + biology_page["total"],
            self._total_cards(),
        )

    def test_list_cards_filter_by_search(self) -> None:
        with main.get_db() as conn:
            all_page = study_service.list_cards(conn, limit=500)
            needle_page = study_service.list_cards(conn, search="mitosis", limit=500)

        self.assertLessEqual(needle_page["total"], all_page["total"])
        for card in needle_page["cards"]:
            combined = f"{card['front']} {card['back']}".lower()
            self.assertIn("mitosis", combined)

    def test_list_subjects_counts_match_card_totals(self) -> None:
        with main.get_db() as conn:
            subjects = study_service.list_subjects(conn)
            total_cards = sum(s["card_count"] for s in subjects)
        self.assertEqual(total_cards, self._total_cards())
        names = {s["subject_name"] for s in subjects}
        self.assertIn("Finance", names)
        self.assertIn("Biology", names)

    def test_delete_card_removes_row(self) -> None:
        with main.get_db() as conn:
            page = study_service.list_cards(conn, limit=1)
        card_id = page["cards"][0]["id"]
        start_total = self._total_cards()

        with main.get_db() as conn:
            deleted = study_service.delete_card(conn, card_id)
            conn.commit()
        self.assertTrue(deleted)
        self.assertEqual(self._total_cards(), start_total - 1)

        # Second call returns False — already gone.
        with main.get_db() as conn:
            deleted_again = study_service.delete_card(conn, card_id)
            conn.commit()
        self.assertFalse(deleted_again)

    def test_bulk_delete_cards_removes_many(self) -> None:
        with main.get_db() as conn:
            page = study_service.list_cards(conn, limit=5)
        ids = [card["id"] for card in page["cards"]]
        self.assertGreaterEqual(len(ids), 2)
        start_total = self._total_cards()

        with main.get_db() as conn:
            count = study_service.bulk_delete_cards(conn, ids)
            conn.commit()
        self.assertEqual(count, len(ids))
        self.assertEqual(self._total_cards(), start_total - len(ids))


class ManageCardsRouteTests(unittest.TestCase):
    """End-to-end via the FastAPI router, ensuring the HTTP contract is
    stable (status codes, JSON shape, path encoding)."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.original_base_dir = main.BASE_DIR
        self.original_data_dir = main.DATA_DIR
        self.original_upload_dir = main.UPLOAD_DIR
        self.original_db_path = main.DB_PATH
        self.original_schema_path = main.SCHEMA_PATH

        # PR 0a: Manage Cards routes assume cards exist after ingest;
        # opt this suite into the legacy auto-card behaviour.
        self._original_auto_card_draft = os.environ.get("CARREL_AUTO_CARD_DRAFT")
        os.environ["CARREL_AUTO_CARD_DRAFT"] = "true"

        main.BASE_DIR = self.base_dir
        main.DATA_DIR = self.base_dir / "data"
        main.UPLOAD_DIR = main.DATA_DIR / "uploads"
        main.DB_PATH = main.DATA_DIR / "test.db"
        main.SCHEMA_PATH = self.original_schema_path
        main.initialize_database()
        with main.get_db() as conn:
            ingest_document_record(
                conn=conn,
                filename="seed.txt",
                file_type="txt",
                extracted_text=_SAMPLE_FINANCE,
                page_count=None,
                subject_name="Finance",
            )
        self.client = TestClient(main.app, headers={HEADER_NAME: get_local_api_token()})

    def tearDown(self) -> None:
        main.BASE_DIR = self.original_base_dir
        main.DATA_DIR = self.original_data_dir
        main.UPLOAD_DIR = self.original_upload_dir
        main.DB_PATH = self.original_db_path
        main.SCHEMA_PATH = self.original_schema_path
        if self._original_auto_card_draft is None:
            os.environ.pop("CARREL_AUTO_CARD_DRAFT", None)
        else:
            os.environ["CARREL_AUTO_CARD_DRAFT"] = self._original_auto_card_draft
        self.temp_dir.cleanup()

    def test_list_endpoint_returns_cards_and_total(self) -> None:
        response = self.client.get("/api/srs/cards", params={"limit": 5})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("cards", body)
        self.assertIn("total", body)
        self.assertGreaterEqual(body["total"], 1)

    def test_subjects_endpoint(self) -> None:
        response = self.client.get("/api/srs/subjects")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("subjects", body)
        self.assertTrue(body["subjects"])

    def test_delete_unknown_card_returns_404(self) -> None:
        response = self.client.delete("/api/srs/cards/does-not-exist")
        self.assertEqual(response.status_code, 404)

    def test_delete_existing_card_returns_deleted_count(self) -> None:
        list_response = self.client.get("/api/srs/cards", params={"limit": 1})
        card_id = list_response.json()["cards"][0]["id"]
        response = self.client.delete(f"/api/srs/cards/{card_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"deleted": 1})

    def test_bulk_delete_returns_actual_row_count(self) -> None:
        list_response = self.client.get("/api/srs/cards", params={"limit": 3})
        ids = [card["id"] for card in list_response.json()["cards"]]
        response = self.client.post(
            "/api/srs/cards/bulk-delete",
            json={"ids": ids},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["deleted"], len(ids))

        # Posting the same ids again is a noop, not a 404.
        repeat = self.client.post(
            "/api/srs/cards/bulk-delete",
            json={"ids": ids},
        )
        self.assertEqual(repeat.status_code, 200)
        self.assertEqual(repeat.json()["deleted"], 0)

    # Sanity: the imported route callables exist. Keeps this module honest
    # against accidental renames.
    def test_route_callables_are_present(self) -> None:
        self.assertTrue(callable(list_cards))
        self.assertTrue(callable(list_subjects))
        self.assertTrue(callable(delete_card))
        self.assertTrue(callable(bulk_delete_cards))

    def test_create_card_returns_new_card_and_it_shows_up_in_list(self) -> None:
        response = self.client.post(
            "/api/srs/cards",
            json={"front": "What is liquidity?", "back": "Ease of converting an asset to cash."},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertIn("card", body)
        new_card = body["card"]
        self.assertEqual(new_card["front"], "What is liquidity?")
        self.assertEqual(new_card["back"], "Ease of converting an asset to cash.")
        self.assertEqual(new_card["card_type"], "custom")
        self.assertEqual(new_card["state"], "new")
        # Orphan card (no concept) — null concept + document fields.
        self.assertIsNone(new_card["concept_id"])
        self.assertIsNone(new_card["document_id"])
        # Fetched back via list_cards (which uses LEFT JOIN now).
        listed = self.client.get("/api/srs/cards").json()
        ids = {c["id"] for c in listed["cards"]}
        self.assertIn(new_card["id"], ids)

    def test_create_card_rejects_empty_fields(self) -> None:
        response = self.client.post(
            "/api/srs/cards",
            json={"front": "", "back": "something"},
        )
        self.assertEqual(response.status_code, 422)

        response = self.client.post(
            "/api/srs/cards",
            json={"front": "   ", "back": "something"},
        )
        # Non-empty pre-trim but empty post-trim — caught by the service layer.
        self.assertEqual(response.status_code, 400)

    def test_create_card_with_invalid_concept_id_returns_400(self) -> None:
        response = self.client.post(
            "/api/srs/cards",
            json={
                "front": "q",
                "back": "a",
                "concept_id": "not-a-real-concept-id",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_create_card_with_invalid_doc_id_returns_400(self) -> None:
        response = self.client.post(
            "/api/srs/cards",
            json={
                "front": "q",
                "back": "a",
                "doc_id": "not-a-real-doc-id",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_create_card_with_doc_id_links_to_the_document(self) -> None:
        # A card made from the Reader carries a direct doc_id even though
        # it has no concept. The read queries COALESCE s.doc_id with the
        # concept-derived doc_id, so document_id / document_name /
        # subject_name all resolve from the direct linkage.
        with main.get_db() as conn:
            doc = conn.execute("SELECT id FROM documents WHERE filename = 'seed.txt'").fetchone()
        doc_id = doc["id"]

        response = self.client.post(
            "/api/srs/cards",
            json={
                "front": "What is arbitrage?",
                "back": "Identical assets trading at different prices.",
                "doc_id": doc_id,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        new_card = response.json()["card"]
        self.assertIsNone(new_card["concept_id"])
        self.assertEqual(new_card["document_id"], doc_id)
        self.assertEqual(new_card["document_name"], "seed.txt")
        self.assertEqual(new_card["subject_name"], "Finance")

        # The linkage survives the list_cards round-trip + doc_id filter.
        listed = self.client.get("/api/srs/cards", params={"doc_id": doc_id}).json()
        ids = {c["id"] for c in listed["cards"]}
        self.assertIn(new_card["id"], ids)

    def test_ai_draft_happy_path_returns_cleaned_cards(self) -> None:
        """The route routes through the AI provider and returns cleaned cards.
        We mock the provider to avoid a real network call and the flakiness
        of a live LLM. Focus is on plumbing + response shape + filters.
        """
        from unittest import mock as _mock

        from ai.router import ClaudeCallResult

        fake_result = ClaudeCallResult(
            ok=True,
            task="fast",
            model="claude-haiku-4-5",
            request_kind="srs.ai_draft",
            text=None,
            json_payload={
                "cards": [
                    {
                        "front": "What is NPV?",
                        "back": "Present value of future cash flows minus the initial investment.",
                    },
                    {
                        "front": "Why does NPV matter?",
                        "back": "It tells you whether a project creates or destroys shareholder value.",
                    },
                    {"front": "", "back": "This one gets dropped (empty front)"},
                    {"front": "Orphan front only"},  # malformed — dropped
                    {"front": "Long" + "x" * 5000, "back": "a"},  # oversize — dropped
                ]
            },
            error_code=None,
            error_message=None,
            latency_ms=1200.0,
            input_tokens=120,
            output_tokens=300,
            cache_creation_input_tokens=None,
            cache_read_input_tokens=None,
            cache_hit=False,
            service_tier=None,
            stop_reason="tool_use",
            request_id="req-1",
        )

        class FakeProvider:
            def ai_enabled(self) -> bool:
                return True

            def model_for_task(self, task):  # pragma: no cover
                del task
                return "fake"

            def request_tool_call(self, **_) -> ClaudeCallResult:
                return fake_result

            def request_text(self, **_):  # pragma: no cover
                raise AssertionError("unused")

            def request_json(self, **_):  # pragma: no cover
                raise AssertionError("unused")

        with _mock.patch("routes.study.get_default_provider", return_value=FakeProvider()):
            response = self.client.post(
                "/api/srs/cards/ai-draft",
                json={"topic": "Net present value", "count": 3},
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(len(body["cards"]), 2)  # only the two well-formed items survive
        self.assertEqual(body["cards"][0]["front"], "What is NPV?")

    def test_ai_draft_when_provider_disabled_reports_ai_disabled(self) -> None:
        from unittest import mock as _mock

        class DisabledProvider:
            def ai_enabled(self) -> bool:
                return False

            def model_for_task(self, task):  # pragma: no cover
                del task
                return "none"

            def request_tool_call(self, **_):  # pragma: no cover
                raise AssertionError("should not be called when disabled")

            def request_text(self, **_):  # pragma: no cover
                raise AssertionError("unused")

            def request_json(self, **_):  # pragma: no cover
                raise AssertionError("unused")

        with _mock.patch("routes.study.get_default_provider", return_value=DisabledProvider()):
            response = self.client.post(
                "/api/srs/cards/ai-draft",
                json={"topic": "Bonds"},
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ai_disabled")
        self.assertEqual(body["cards"], [])

    def test_ai_draft_rejects_empty_topic(self) -> None:
        response = self.client.post("/api/srs/cards/ai-draft", json={"topic": ""})
        self.assertEqual(response.status_code, 422)

    def test_review_orphan_card_succeeds(self) -> None:
        """Regression guard: user-authored cards have concept_id=NULL. The
        /api/srs/review handler used to INNER JOIN concepts, which returned
        no row for orphans and raised 404 on every rating attempt. Rating
        an orphan card must return the same shape as rating a linked card.
        """
        # Create an orphan card via the user-create endpoint.
        created = self.client.post(
            "/api/srs/cards",
            json={"front": "What is LIFO?", "back": "Last in, first out."},
        ).json()["card"]
        self.assertIsNone(created["concept_id"])

        # Rate it "good" — this previously 404'd.
        response = self.client.post(
            "/api/srs/review",
            json={"card_id": created["id"], "rating": "good"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        # The response shape is stable: next_due_date + interval + ease.
        self.assertIn("next_due_date", body)
        self.assertIn("interval", body)
        self.assertIn("ease", body)

    def test_review_unknown_card_still_returns_404(self) -> None:
        response = self.client.post(
            "/api/srs/review",
            json={"card_id": "does-not-exist", "rating": "good"},
        )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
