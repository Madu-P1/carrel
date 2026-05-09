"""Feature-flag tests for the orchestrator's typed-node ingest hook.

Verifies the three states the hook must handle without breaking the
existing chunks ingest path:

1. Flag off (default) → no rows in `nodes`.
2. Flag on but Docling absent → no rows + warning logged.
3. Flag on with Docling available → rows in `nodes` alongside `chunks`.

The third case is slow (real Docling parse). It's skipped when Docling
isn't installed.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import db
from services.ingestion import docling_parser
from services.ingestion.orchestrator import ingest_document_record

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_SOURCE = REPO_ROOT / "migrations"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class _OrchestratorTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._original = (
            db.BASE_DIR,
            db.DATA_DIR,
            db.UPLOAD_DIR,
            db.DB_PATH,
            db.SCHEMA_PATH,
        )
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        data_dir = root / "data"
        upload_dir = data_dir / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        (root / "schema.sql").write_text("-- test\n", encoding="utf-8")
        shutil.copytree(MIGRATIONS_SOURCE, root / "migrations", dirs_exist_ok=True)
        db.configure_paths(
            base_dir=root,
            data_dir=data_dir,
            upload_dir=upload_dir,
            db_path=data_dir / "test.db",
            schema_path=root / "schema.sql",
        )
        self._conn = db.get_db()
        db.apply_migrations(self._conn)
        self._upload_dir = upload_dir

    def tearDown(self) -> None:
        self._conn.close()
        self._tmp.cleanup()
        db.configure_paths(
            base_dir=self._original[0],
            data_dir=self._original[1],
            upload_dir=self._original[2],
            db_path=self._original[3],
            schema_path=self._original[4],
        )

    def _stage_pdf_fixture(self, source_name: str) -> tuple[str, str]:
        """Copy a fixture PDF into UPLOAD_DIR, return (filename, storage_name)."""
        src = FIXTURES_DIR / source_name
        storage_name = f"test-{source_name}"
        shutil.copyfile(src, self._upload_dir / storage_name)
        return source_name, storage_name

    def _count_nodes(self) -> int:
        return self._conn.execute("SELECT COUNT(*) AS n FROM nodes").fetchone()["n"]

    def _count_chunks(self) -> int:
        return self._conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]


class FlagOffSkipsTypedNodeIngestTests(_OrchestratorTestBase):
    @mock.patch.dict("os.environ", {"INGEST_USE_DOCLING": "false"}, clear=False)
    def test_flag_off_writes_chunks_but_no_nodes(self) -> None:
        ingest_document_record(
            conn=self._conn,
            filename="manual.md",
            file_type="md",
            extracted_text="A short paragraph about cells.\n\nAnother paragraph.",
            page_count=None,
        )
        self.assertEqual(self._count_nodes(), 0)
        self.assertGreater(self._count_chunks(), 0)


class FlagOnButDoclingMissingTests(_OrchestratorTestBase):
    @mock.patch.dict(
        "os.environ", {"INGEST_USE_DOCLING": "true", "INGEST_DOCLING_FORMATS": "pdf"}, clear=False
    )
    def test_flag_on_with_docling_unavailable_writes_no_nodes_and_logs_warning(self) -> None:
        # Force is_available() False even when Docling is installed in the venv,
        # so the test exercises the "absent" branch deterministically.
        with mock.patch.object(docling_parser, "is_available", return_value=False):
            with self.assertLogs(
                "einstein.ingestion.orchestrator", level=logging.WARNING
            ) as captured:
                ingest_document_record(
                    conn=self._conn,
                    filename="some.pdf",
                    file_type="pdf",
                    extracted_text="placeholder text",
                    page_count=1,
                    storage_name="placeholder.pdf",
                )
        self.assertEqual(self._count_nodes(), 0)
        self.assertTrue(
            any("docling_unavailable" in line for line in captured.output),
            f"expected docling_unavailable in {captured.output}",
        )

    @mock.patch.dict(
        "os.environ", {"INGEST_USE_DOCLING": "true", "INGEST_DOCLING_FORMATS": "pdf"}, clear=False
    )
    def test_flag_on_with_no_storage_file_writes_no_nodes_and_logs_warning(self) -> None:
        # storage_name set but file missing on disk — orchestrator should
        # log + skip, not crash.
        with self.assertLogs("einstein.ingestion.orchestrator", level=logging.WARNING) as captured:
            ingest_document_record(
                conn=self._conn,
                filename="ghost.pdf",
                file_type="pdf",
                extracted_text="placeholder",
                page_count=1,
                storage_name="never-written.pdf",
            )
        self.assertEqual(self._count_nodes(), 0)
        self.assertTrue(
            any("docling_skipped_no_file" in line for line in captured.output),
            f"expected docling_skipped_no_file in {captured.output}",
        )


@unittest.skipUnless(docling_parser.is_available(), "docling not installed")
class FlagOnWithDoclingTests(_OrchestratorTestBase):
    @mock.patch.dict(
        "os.environ", {"INGEST_USE_DOCLING": "true", "INGEST_DOCLING_FORMATS": "pdf"}, clear=False
    )
    def test_flag_on_writes_nodes_alongside_chunks(self) -> None:
        filename, storage_name = self._stage_pdf_fixture("single_column.pdf")
        ingest_document_record(
            conn=self._conn,
            filename=filename,
            file_type="pdf",
            extracted_text="Photosynthesis Overview\n\nPlants convert sunlight",
            page_count=1,
            storage_name=storage_name,
        )
        self.assertGreater(self._count_nodes(), 0)
        self.assertGreater(self._count_chunks(), 0)

    @mock.patch.dict(
        "os.environ", {"INGEST_USE_DOCLING": "true", "INGEST_DOCLING_FORMATS": "docx"}, clear=False
    )
    def test_format_allowlist_gates_pdf_when_only_docx_enabled(self) -> None:
        # Hook must not run on a PDF when the allowlist excludes pdf.
        filename, storage_name = self._stage_pdf_fixture("single_column.pdf")
        ingest_document_record(
            conn=self._conn,
            filename=filename,
            file_type="pdf",
            extracted_text="Photosynthesis Overview",
            page_count=1,
            storage_name=storage_name,
        )
        self.assertEqual(self._count_nodes(), 0)


if __name__ == "__main__":
    unittest.main()
