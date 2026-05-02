import tempfile
import time
import unittest
from pathlib import Path

import db
from services import evidence_resolution, onboarding

REPO_ROOT = Path(__file__).resolve().parent.parent


class PublicBetaLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_paths = (
            db.BASE_DIR,
            db.DATA_DIR,
            db.UPLOAD_DIR,
            db.DB_PATH,
            db.SCHEMA_PATH,
        )
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        data_dir = root / "data"
        upload_dir = data_dir / "uploads"
        data_dir.mkdir(parents=True)
        upload_dir.mkdir()
        db.configure_paths(
            base_dir=root,
            data_dir=data_dir,
            upload_dir=upload_dir,
            db_path=data_dir / "test.db",
            schema_path=REPO_ROOT / "schema.sql",
        )
        with db.get_db() as conn:
            db.apply_migrations(conn)

    def tearDown(self) -> None:
        db.configure_paths(
            base_dir=self.original_paths[0],
            data_dir=self.original_paths[1],
            upload_dir=self.original_paths[2],
            db_path=self.original_paths[3],
            schema_path=self.original_paths[4],
        )
        self.temp_dir.cleanup()

    def test_onboarding_seed_is_idempotent(self) -> None:
        with db.get_db() as conn:
            first = onboarding.seed_demo_library(conn)
            second = onboarding.seed_demo_library(conn)
            total = conn.execute("SELECT COUNT(*) AS total FROM documents").fetchone()["total"]
            rows = conn.execute(
                "SELECT filename, file_type, storage_name, page_count FROM documents ORDER BY filename"
            ).fetchall()

        self.assertTrue(first["seeded"])
        self.assertFalse(second["seeded"])
        self.assertEqual(3, total)
        self.assertTrue(all(row["file_type"] == "pdf" for row in rows))
        self.assertTrue(all(row["storage_name"] for row in rows))
        self.assertTrue(all((db.UPLOAD_DIR / row["storage_name"]).exists() for row in rows))
        self.assertTrue(all(int(row["page_count"] or 0) >= 1 for row in rows))

    def test_evidence_resolver_returns_chunk_level_location(self) -> None:
        with db.get_db() as conn:
            seeded = onboarding.seed_demo_library(conn)
            doc_id = seeded["documents"][0]["doc_id"]
            chunk_id = conn.execute(
                "SELECT id FROM chunks WHERE doc_id = ? ORDER BY chunk_index ASC LIMIT 1",
                (doc_id,),
            ).fetchone()["id"]
            resolved = evidence_resolution.resolve_evidence(conn, document_id=doc_id, chunk_id=chunk_id)

        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertEqual("chunk", resolved["location_kind"])
        self.assertEqual(doc_id, resolved["document_id"])
        self.assertEqual(chunk_id, resolved["chunk_id"])

    def test_job_import_reaches_ready_and_records_events(self) -> None:
        from services import jobs

        source = Path(self.temp_dir.name) / "job-source.txt"
        source.write_text("Yield rises when bond prices fall. Duration estimates price sensitivity.", encoding="utf-8")
        job = jobs.enqueue_import(source_path=source, filename="job-source.txt", subject_name="Finance")

        deadline = time.time() + 10
        latest = job
        while time.time() < deadline:
            maybe = jobs.get_job(job["id"])
            if maybe:
                latest = maybe
            if latest["status"] == "ready":
                break
            time.sleep(0.1)

        events = jobs.list_events()
        self.assertEqual("ready", latest["status"])
        self.assertTrue(latest["document_id"])
        self.assertTrue(any(event["event_type"] == "job_ready" for event in events))


if __name__ == "__main__":
    unittest.main()
