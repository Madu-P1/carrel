"""Tests for the Manage Cards surface.

Covers `services.study.list_cards`, `list_subjects`, `delete_card`, and
`bulk_delete_cards`, plus the FastAPI routes wired on top. Data fixtures
reuse the ingestion pipeline so we exercise real SQL joins (srs_cards →
concepts → documents) rather than handcrafted rows.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import main
from routes.study import bulk_delete_cards, delete_card, list_cards, list_subjects
from services import study as study_service
from services.ingestion import ingest_document_record

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
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        main.BASE_DIR = self.original_base_dir
        main.DATA_DIR = self.original_data_dir
        main.UPLOAD_DIR = self.original_upload_dir
        main.DB_PATH = self.original_db_path
        main.SCHEMA_PATH = self.original_schema_path
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


if __name__ == "__main__":
    unittest.main()
