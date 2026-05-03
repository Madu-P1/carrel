from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

import main
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

        main.BASE_DIR = self.base_dir
        main.DATA_DIR = self.base_dir / "data"
        main.UPLOAD_DIR = main.DATA_DIR / "uploads"
        main.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        main.DB_PATH = main.DATA_DIR / "test.db"
        main.SCHEMA_PATH = self.original_schema_path
        main.initialize_database()
        self.client = TestClient(main.app, headers={HEADER_NAME: get_local_api_token()})

    def tearDown(self) -> None:
        main.BASE_DIR = self.original_base_dir
        main.DATA_DIR = self.original_data_dir
        main.UPLOAD_DIR = self.original_upload_dir
        main.DB_PATH = self.original_db_path
        main.SCHEMA_PATH = self.original_schema_path
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


if __name__ == "__main__":
    unittest.main()
