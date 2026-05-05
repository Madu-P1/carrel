from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient
from openpyxl import Workbook

import main
import services.jobs as jobs_service
from services.extraction.detector import FileTypeDetector
from services.local_api_security import HEADER_NAME, get_local_api_token


class UploadSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.original_base_dir = main.BASE_DIR
        self.original_data_dir = main.DATA_DIR
        self.original_upload_dir = main.UPLOAD_DIR
        self.original_db_path = main.DB_PATH
        self.original_schema_path = main.SCHEMA_PATH
        self.original_job_upload_dir = jobs_service.JOB_UPLOAD_DIR

        main.BASE_DIR = self.base_dir
        main.DATA_DIR = self.base_dir / "data"
        main.UPLOAD_DIR = main.DATA_DIR / "uploads"
        main.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        main.DB_PATH = main.DATA_DIR / "test.db"
        main.SCHEMA_PATH = self.original_schema_path
        jobs_service.JOB_UPLOAD_DIR = main.DATA_DIR / "job-uploads"
        main.initialize_database()
        self.client = TestClient(main.app, headers={HEADER_NAME: get_local_api_token()})

    def tearDown(self) -> None:
        main.BASE_DIR = self.original_base_dir
        main.DATA_DIR = self.original_data_dir
        main.UPLOAD_DIR = self.original_upload_dir
        main.DB_PATH = self.original_db_path
        main.SCHEMA_PATH = self.original_schema_path
        jobs_service.JOB_UPLOAD_DIR = self.original_job_upload_dir
        self.temp_dir.cleanup()

    def _upload(self, filename: str, data: bytes):
        return self.client.post(
            "/api/documents/upload",
            files={"file": (filename, io.BytesIO(data), "application/octet-stream")},
            data={"subject_name": "Security"},
        )

    def test_unsupported_extension_rejected_before_disk_write(self) -> None:
        response = self._upload("payload.exe", b"MZ fake binary")

        self.assertEqual(response.status_code, 400)
        self.assertEqual([], list(main.UPLOAD_DIR.iterdir()))

    def test_oversized_upload_returns_413_and_removes_partial_file(self) -> None:
        with mock.patch("services.uploads.MAX_UPLOAD_BYTES", 8):
            response = self._upload("large.txt", b"0123456789abcdef")

        self.assertEqual(response.status_code, 413)
        self.assertEqual([], list(main.UPLOAD_DIR.iterdir()))

    def test_extraction_failure_removes_written_file(self) -> None:
        response = self._upload("blank.txt", b" \n\t ")

        self.assertEqual(response.status_code, 422)
        self.assertEqual([], list(main.UPLOAD_DIR.iterdir()))

    def test_detector_reads_only_bounded_header(self) -> None:
        path = self.base_dir / "sample.pdf"
        path.write_bytes(b"%PDF" + b"x" * 1024)

        with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("unbounded read")):
            detected_suffix, detected_mime = FileTypeDetector.detect(path)

        self.assertEqual(".pdf", detected_suffix)
        self.assertEqual("application/pdf", detected_mime)

    def test_library_subject_create_keeps_empty_folder_visible(self) -> None:
        response = self.client.post(
            "/api/library/subjects",
            json={"subject_name": "Finance"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual("Finance", response.json()["subject"]["subject_name"])

        subjects = self.client.get("/api/library/subjects").json()["subjects"]
        finance = next(subject for subject in subjects if subject["subject_name"] == "Finance")
        self.assertEqual(0, finance["source_count"])

    def test_jobs_import_accepts_csv_and_xlsx_extensions(self) -> None:
        with mock.patch("services.jobs.submit_job") as submit_job:
            csv_response = self.client.post(
                "/api/jobs/import",
                files={"file": ("milan_reviews.csv", io.BytesIO(b"review,score\nGreat pasta,5\n"), "text/csv")},
                data={"subject_name": "Marketing"},
            )
            xlsx_response = self.client.post(
                "/api/jobs/import",
                files={
                    "file": (
                        "reviews.xlsx",
                        io.BytesIO(self._xlsx_bytes()),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                },
                data={"subject_name": "Finance"},
            )

        self.assertEqual(csv_response.status_code, 200)
        self.assertEqual(xlsx_response.status_code, 200)
        self.assertEqual("Marketing", csv_response.json()["job"]["subject_name"])
        self.assertEqual("Finance", xlsx_response.json()["job"]["subject_name"])
        self.assertEqual(2, submit_job.call_count)

    def test_document_upload_ingests_csv_and_xlsx(self) -> None:
        csv_response = self.client.post(
            "/api/documents/upload",
            files={"file": ("milan_reviews.csv", io.BytesIO(b"review,score\nGreat pasta,5\n"), "text/csv")},
            data={"subject_name": "Marketing"},
        )
        xlsx_response = self.client.post(
            "/api/documents/upload",
            files={
                "file": (
                    "finance_reviews.xlsx",
                    io.BytesIO(self._xlsx_bytes()),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
            data={"subject_name": "Finance"},
        )

        self.assertEqual(csv_response.status_code, 200)
        self.assertEqual(xlsx_response.status_code, 200)
        self.assertEqual("csv", csv_response.json()["file_type"])
        self.assertEqual("xlsx", xlsx_response.json()["file_type"])
        self.assertEqual("Marketing", csv_response.json()["subject_name"])
        self.assertEqual("Finance", xlsx_response.json()["subject_name"])

    def _xlsx_bytes(self) -> bytes:
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "Reviews"
        worksheet.append(["review", "score"])
        worksheet.append(["Great pasta", 5])
        buffer = io.BytesIO()
        workbook.save(buffer)
        return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
