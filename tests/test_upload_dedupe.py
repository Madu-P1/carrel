"""Upload dedupe tests.

Contract:
  - Uploading the same file bytes twice returns 409 on the second attempt.
  - Uploading the same manual text twice returns 409 on the second attempt.
  - Deleting the first upload lets the second attempt succeed (not blocked
    by the prior canonical row).
  - Different files of the same name with different bytes are NOT treated
    as duplicates (hash is content-based, not filename-based).
  - The 409 body carries enough detail for the UI to render "already in
    library as X" without a second round trip.
"""

from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import main


_TEXT_BYTES = (
    b"Capital markets are venues where buyers and sellers trade financial "
    b"instruments such as stocks and bonds. The primary market handles new "
    b"issuances while the secondary market trades existing securities. "
    b"Market efficiency concerns how quickly information is reflected in "
    b"prices across these venues. Arbitrage exists when identical assets "
    b"trade at different prices.\n"
)


class UploadDedupeBase(unittest.TestCase):
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
        main.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        main.DB_PATH = main.DATA_DIR / "test.db"
        main.SCHEMA_PATH = self.original_schema_path
        main.initialize_database()
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        main.BASE_DIR = self.original_base_dir
        main.DATA_DIR = self.original_data_dir
        main.UPLOAD_DIR = self.original_upload_dir
        main.DB_PATH = self.original_db_path
        main.SCHEMA_PATH = self.original_schema_path
        self.temp_dir.cleanup()

    def _upload_text(self, title: str, content: str, subject: str = "General"):
        return self.client.post(
            "/api/documents/text",
            json={"title": title, "content": content, "subject_name": subject},
        )

    def _upload_file(self, filename: str, data: bytes, subject: str = "General"):
        return self.client.post(
            "/api/documents/upload",
            files={"file": (filename, io.BytesIO(data), "application/octet-stream")},
            data={"subject_name": subject},
        )


class ManualTextDedupeTests(UploadDedupeBase):
    def test_identical_text_second_upload_returns_409(self) -> None:
        body = "Capital markets let buyers and sellers trade financial instruments."
        first = self._upload_text("Notes", body)
        self.assertEqual(first.status_code, 200, first.text)

        second = self._upload_text("Notes copy", body)
        self.assertEqual(second.status_code, 409, second.text)

        detail = second.json()["detail"]
        self.assertEqual(detail["code"], "duplicate_source")
        self.assertEqual(detail["existing_doc_id"], first.json()["doc_id"])
        self.assertIn("already", detail["message"].lower())

    def test_whitespace_only_difference_is_still_a_duplicate(self) -> None:
        first = self._upload_text("Notes", "Mitosis creates two identical daughter cells.")
        self.assertEqual(first.status_code, 200)

        # Extra trailing whitespace and stray blank lines should still hash
        # to the same canonical source because clean_learning_text normalises
        # them before hashing.
        second = self._upload_text(
            "Notes v2",
            "Mitosis creates two identical daughter cells.   \n\n\n",
        )
        self.assertEqual(second.status_code, 409)

    def test_different_text_is_accepted_even_with_same_title(self) -> None:
        first = self._upload_text("Notes", "Content A about mitosis.")
        self.assertEqual(first.status_code, 200)

        second = self._upload_text("Notes", "Content B about capital markets.")
        self.assertEqual(second.status_code, 200)
        self.assertNotEqual(first.json()["doc_id"], second.json()["doc_id"])


class FileUploadDedupeTests(UploadDedupeBase):
    def test_identical_bytes_second_upload_returns_409(self) -> None:
        first = self._upload_file("a.txt", _TEXT_BYTES)
        self.assertEqual(first.status_code, 200, first.text)

        second = self._upload_file("a-copy.txt", _TEXT_BYTES)
        self.assertEqual(second.status_code, 409)
        detail = second.json()["detail"]
        self.assertEqual(detail["code"], "duplicate_source")
        self.assertEqual(detail["existing_doc_id"], first.json()["doc_id"])

    def test_same_filename_different_bytes_accepted(self) -> None:
        first = self._upload_file("lecture.txt", _TEXT_BYTES)
        self.assertEqual(first.status_code, 200)

        mutated = _TEXT_BYTES + b"\nAn extra paragraph with different content.\n"
        second = self._upload_file("lecture.txt", mutated)
        self.assertEqual(second.status_code, 200)
        self.assertNotEqual(first.json()["doc_id"], second.json()["doc_id"])

    def test_delete_then_reupload_is_allowed(self) -> None:
        first = self._upload_file("a.txt", _TEXT_BYTES)
        doc_id = first.json()["doc_id"]

        dup = self._upload_file("a.txt", _TEXT_BYTES)
        self.assertEqual(dup.status_code, 409)

        deleted = self.client.delete(f"/api/documents/{doc_id}")
        self.assertEqual(deleted.status_code, 200)

        # Clean slate: the canonical was removed, so re-ingesting the same
        # bytes should succeed and create a fresh row.
        reuploaded = self._upload_file("a.txt", _TEXT_BYTES)
        self.assertEqual(reuploaded.status_code, 200)
        self.assertNotEqual(reuploaded.json()["doc_id"], doc_id)


class DuplicateCleanupTests(UploadDedupeBase):
    """The Library dedupe gate stops NEW duplicates, but existing rows from
    before the gate landed still need a cleanup path. These tests exercise
    `/api/library/duplicates` + `/api/library/duplicates/cleanup`."""

    def _force_insert_duplicate(self, filename: str, data: bytes, subject: str = "General") -> str:
        """Bypass the 409 gate to simulate a legacy duplicate row. Uses the
        orchestrator directly so we land in the same schema state users with
        pre-gate data already have."""
        import uuid as _uuid

        from services import extraction_pipeline
        from services.ingestion import ingest_document_record

        stored_name = f"{_uuid.uuid4()}.txt"
        path = main.UPLOAD_DIR / stored_name
        path.write_bytes(data)
        asset = extraction_pipeline.extract_asset(path)
        with main.get_db() as conn:
            result = ingest_document_record(
                conn=conn,
                filename=filename,
                file_type=asset.detected_type,
                extracted_text=str(asset.cleaned_text or asset.raw_text),
                page_count=asset.quality.metrics.get("page_count"),
                storage_name=stored_name,
                subject_name=subject,
                asset=asset,
            )
        return str(result["doc_id"])

    def test_preview_returns_empty_when_no_duplicates(self) -> None:
        first = self._upload_file("only.txt", _TEXT_BYTES)
        self.assertEqual(first.status_code, 200)
        response = self.client.get("/api/library/duplicates")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total_groups"], 0)
        self.assertEqual(body["total_duplicates"], 0)
        self.assertEqual(body["groups"], [])

    def test_preview_surfaces_existing_duplicate_cluster(self) -> None:
        first = self._upload_file("a.txt", _TEXT_BYTES)
        self.assertEqual(first.status_code, 200)
        canonical_id = first.json()["doc_id"]
        # Force two legacy dupes with the same bytes. Bypass the gate so we
        # land a realistic cluster.
        dup_a = self._force_insert_duplicate("a-copy-1.txt", _TEXT_BYTES)
        dup_b = self._force_insert_duplicate("a-copy-2.txt", _TEXT_BYTES)

        response = self.client.get("/api/library/duplicates")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total_groups"], 1)
        self.assertEqual(body["total_duplicates"], 2)

        group = body["groups"][0]
        self.assertEqual(group["canonical"]["id"], canonical_id)
        duplicate_ids = [d["id"] for d in group["duplicates"]]
        self.assertIn(dup_a, duplicate_ids)
        self.assertIn(dup_b, duplicate_ids)

    def test_cleanup_dry_run_does_not_mutate(self) -> None:
        first = self._upload_file("a.txt", _TEXT_BYTES)
        canonical_id = first.json()["doc_id"]
        self._force_insert_duplicate("a-copy-1.txt", _TEXT_BYTES)
        self._force_insert_duplicate("a-copy-2.txt", _TEXT_BYTES)

        response = self.client.post(
            "/api/library/duplicates/cleanup",
            params={"dry_run": "true"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["dry_run"])
        self.assertEqual(body["would_delete"], 2)
        self.assertEqual(body["groups"], 1)

        # Nothing actually deleted — preview should still show the cluster.
        preview = self.client.get("/api/library/duplicates").json()
        self.assertEqual(preview["total_duplicates"], 2)
        remaining = self.client.get("/api/documents").json()
        self.assertEqual(len([d for d in remaining if d["id"] == canonical_id]), 1)

    def test_cleanup_removes_non_canonical_rows(self) -> None:
        first = self._upload_file("a.txt", _TEXT_BYTES)
        canonical_id = first.json()["doc_id"]
        dup_a = self._force_insert_duplicate("a-copy-1.txt", _TEXT_BYTES)
        dup_b = self._force_insert_duplicate("a-copy-2.txt", _TEXT_BYTES)

        response = self.client.post("/api/library/duplicates/cleanup")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["dry_run"])
        self.assertEqual(body["groups"], 1)
        self.assertEqual(body["deleted"], 2)

        remaining = {d["id"] for d in self.client.get("/api/documents").json()}
        self.assertIn(canonical_id, remaining)
        self.assertNotIn(dup_a, remaining)
        self.assertNotIn(dup_b, remaining)

        # Preview is empty after a successful cleanup.
        preview = self.client.get("/api/library/duplicates").json()
        self.assertEqual(preview["total_duplicates"], 0)

    def test_cleanup_with_no_duplicates_is_noop(self) -> None:
        first = self._upload_file("only.txt", _TEXT_BYTES)
        self.assertEqual(first.status_code, 200)
        response = self.client.post("/api/library/duplicates/cleanup")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["groups"], 0)
        self.assertEqual(body["deleted"], 0)


if __name__ == "__main__":
    unittest.main()
