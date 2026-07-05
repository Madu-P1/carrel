"""HTTP-level tests for POST /api/verify/extract-draft (routes/verify.py).

This endpoint lets a user upload a DOCUMENT as the draft under verification
(not just paste text). It reuses the proven ingestion extraction path but must
honor the honesty law for extracted drafts (docs/plans/
cachet-draft-upload-and-long-docs-2026-07-05.md, §1):

  Cachet verifies exactly the extracted text, shows exactly the extracted
  text, and names BOTH artifacts (the raw-file sha256 and the extracted-text
  sha256) plus the extractor identity. It never verifies bytes the user
  cannot see, and an unreadable/empty document REFUSES explicitly.

The load-bearing safety tests here are the honesty gates, written before the
endpoint:

  1. Self-verification trap: a draft must NEVER enter the retrieval corpus.
     A draft that became a source could verify against itself — a structural
     false green. So extract-draft persists nothing: no `documents` row, no
     stored file, no doc_id.
  2. Empty/failed extraction refuses explicitly (never a silent empty draft).
  3. Both hashes are returned and correct (raw bytes + extracted text).
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

import db
import main
from services.local_api_security import HEADER_NAME, get_local_api_token

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_SOURCE = REPO_ROOT / "migrations"


def _document_count() -> int:
    with db.get_db() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM documents").fetchone()
    return int(row["n"] if row is not None else 0)


class ExtractDraftRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_paths = (
            db.BASE_DIR,
            db.DATA_DIR,
            db.UPLOAD_DIR,
            db.DB_PATH,
            db.SCHEMA_PATH,
        )
        self._temp = tempfile.TemporaryDirectory()
        root = Path(self._temp.name)
        data_dir = root / "data"
        self._upload_dir = data_dir / "uploads"
        self._upload_dir.mkdir(parents=True, exist_ok=True)
        (root / "schema.sql").write_text("-- test\n", encoding="utf-8")
        shutil.copytree(MIGRATIONS_SOURCE, root / "migrations", dirs_exist_ok=True)
        db.configure_paths(
            base_dir=root,
            data_dir=data_dir,
            upload_dir=self._upload_dir,
            db_path=data_dir / "test.db",
            schema_path=root / "schema.sql",
        )
        with db.get_db() as conn:
            db.apply_migrations(conn)

        from fastapi.testclient import TestClient

        self.client = TestClient(main.app, headers={HEADER_NAME: get_local_api_token()})

    def tearDown(self) -> None:
        db.configure_paths(
            base_dir=self._original_paths[0],
            data_dir=self._original_paths[1],
            upload_dir=self._original_paths[2],
            db_path=self._original_paths[3],
            schema_path=self._original_paths[4],
        )
        self._temp.cleanup()

    def _post(self, filename: str, content: bytes):
        return self.client.post(
            "/api/verify/extract-draft",
            files={"file": (filename, content, "application/octet-stream")},
        )

    # --- the honesty gates (the ship authority for D1) ---

    def test_a_readable_document_returns_both_hashes_and_the_extracted_text(self) -> None:
        body = b"The term is two years from the effective date. The fee is $500."
        response = self._post("draft.txt", body)
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        # The read-back IS the extracted text; the user sees exactly what was checked.
        self.assertIn("two years", data["draft_text"])
        self.assertIn("$500", data["draft_text"])
        # The certificate needs BOTH artifacts named.
        self.assertEqual(data["draft_file_sha256"], hashlib.sha256(body).hexdigest())
        self.assertEqual(
            data["draft_sha256"],
            hashlib.sha256(data["draft_text"].encode("utf-8")).hexdigest(),
        )
        # The extractor is named (honesty: OCR vs embedded text is a different
        # trust statement), and the counts are honest positives.
        self.assertTrue(data["extractor"])
        self.assertGreaterEqual(data["sentences"], 2)
        self.assertGreater(data["chars"], 0)

    def test_extract_draft_never_enters_the_retrieval_corpus(self) -> None:
        # THE structural false-green guard: a draft that became a source could
        # verify against itself. extract-draft must persist nothing.
        self.assertEqual(_document_count(), 0)
        response = self._post("draft.md", b"# Heading\n\nThe cap is one million dollars.")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(_document_count(), 0, "extract-draft must not create a document row")
        self.assertNotIn("doc_id", response.json())
        self.assertNotIn("id", response.json())

    def test_extract_draft_leaves_no_stored_file_behind(self) -> None:
        before = {p.name for p in self._upload_dir.iterdir()}
        response = self._post("draft.txt", b"A single checkable sentence about $500.")
        self.assertEqual(response.status_code, 200, response.text)
        after = {p.name for p in self._upload_dir.iterdir()}
        self.assertEqual(before, after, "extract-draft must not leave bytes in the upload store")

    def test_empty_document_refuses_explicitly_never_a_silent_empty_draft(self) -> None:
        response = self._post("blank.txt", b"   \n  \t ")
        self.assertGreaterEqual(response.status_code, 400)
        self.assertLess(response.status_code, 500)
        # A concrete, honest reason — not a silent 200 with an empty draft.
        self.assertNotEqual(response.status_code, 200)
        # The self-verification trap must hold on the REFUSAL path too (a
        # save-before-validate leak is likeliest here): nothing persisted.
        self.assertEqual(_document_count(), 0, "a refused document must not create a row")
        self.assertEqual(
            list(self._upload_dir.iterdir()), [], "a refused document must leave no file"
        )

    def test_unsupported_file_type_is_refused(self) -> None:
        response = self._post("draft.exe", b"not a document")
        self.assertEqual(response.status_code, 400, response.text)
        # Zero-persistence holds on the reject path too.
        self.assertEqual(_document_count(), 0)
        self.assertEqual(list(self._upload_dir.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
