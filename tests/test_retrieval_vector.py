import hashlib
import math
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import db
from services.retrieval.backfill import backfill_missing_embeddings
from services.retrieval.embeddings import FastembedEmbedder
from services.retrieval.vector import index_chunk, search_vector, vector_table_exists

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_SOURCE = REPO_ROOT / "migrations"


def _vector_runtime_supported() -> bool:
    return db.sqlite_vec_runtime_supported()


class MockEmbedder:
    dim = 384

    def _vector(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values = [((digest[index % len(digest)] / 255.0) * 2.0) - 1.0 for index in range(self.dim)]
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return [value / norm for value in values]

    def embed_passages(self, texts):
        return [self._vector(text) for text in texts]

    def embed_query(self, text):
        return self._vector(text)


@unittest.skipUnless(_vector_runtime_supported(), "sqlite-vec runtime support is unavailable")
class RetrievalVectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_paths = (
            db.BASE_DIR,
            db.DATA_DIR,
            db.UPLOAD_DIR,
            db.DB_PATH,
            db.SCHEMA_PATH,
        )

    def tearDown(self) -> None:
        db.configure_paths(
            base_dir=self.original_paths[0],
            data_dir=self.original_paths[1],
            upload_dir=self.original_paths[2],
            db_path=self.original_paths[3],
            schema_path=self.original_paths[4],
        )

    def _configure_temp_runtime(self, root: Path) -> None:
        data_dir = root / "data"
        upload_dir = data_dir / "uploads"
        data_dir.mkdir(parents=True, exist_ok=True)
        upload_dir.mkdir(parents=True, exist_ok=True)
        (root / "schema.sql").write_text("-- historical reference only\n", encoding="utf-8")
        shutil.copytree(MIGRATIONS_SOURCE, root / "migrations", dirs_exist_ok=True)
        db.configure_paths(
            base_dir=root,
            data_dir=data_dir,
            upload_dir=upload_dir,
            db_path=data_dir / "test.db",
            schema_path=root / "schema.sql",
        )

    def _insert_document(self, conn, doc_id: str, subject_name: str) -> None:
        conn.execute(
            """
            INSERT INTO documents (id, filename, file_type, subject_name, status)
            VALUES (?, ?, 'txt', ?, 'ready')
            """,
            (doc_id, f"{doc_id}.txt", subject_name),
        )

    def _insert_chunk(
        self, conn, chunk_id: str, doc_id: str, content: str, section: str = "Core"
    ) -> int:
        cursor = conn.execute(
            """
            INSERT INTO chunks (id, doc_id, content, section, chunk_index, token_count)
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (chunk_id, doc_id, content, section, len(content.split())),
        )
        return int(cursor.lastrowid)

    def test_migration_applies_and_chunks_vec_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._configure_temp_runtime(root)
            with db.get_db() as conn:
                db.apply_migrations(conn)
                tables = {
                    row["name"]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }

        self.assertIn("chunks_vec", tables)

    def test_index_chunk_and_search_vector(self) -> None:
        embedder = MockEmbedder()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._configure_temp_runtime(root)
            with db.get_db() as conn:
                db.apply_migrations(conn)
                self._insert_document(conn, "doc-a", "Biology")
                rowid = self._insert_chunk(
                    conn, "chunk-a", "doc-a", "Cell division depends on spindle fibers."
                )
                index_chunk(
                    conn, rowid, embedder.embed_query("cell division depends on spindle fibers")
                )
                conn.commit()
                hits = search_vector(
                    conn, "cell division depends on spindle fibers", embedder=embedder
                )

        self.assertEqual(["chunk-a"], [hit.chunk_id for hit in hits])

    def test_three_chunks_return_nearest_first(self) -> None:
        embedder = MockEmbedder()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._configure_temp_runtime(root)
            with db.get_db() as conn:
                db.apply_migrations(conn)
                self._insert_document(conn, "doc-a", "Biology")
                rows = [
                    ("chunk-a", "doc-a", "Cell division depends on spindle fibers."),
                    ("chunk-b", "doc-a", "Photosynthesis stores light energy in sugars."),
                    ("chunk-c", "doc-a", "Beta measures market risk in a portfolio."),
                ]
                for chunk_id, doc_id, content in rows:
                    rowid = self._insert_chunk(conn, chunk_id, doc_id, content)
                    index_chunk(conn, rowid, embedder.embed_query(content))
                conn.commit()
                hits = search_vector(
                    conn, "Cell division depends on spindle fibers.", embedder=embedder
                )

        self.assertEqual("chunk-a", hits[0].chunk_id)

    def test_doc_ids_and_subject_filters_work(self) -> None:
        embedder = MockEmbedder()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._configure_temp_runtime(root)
            with db.get_db() as conn:
                db.apply_migrations(conn)
                self._insert_document(conn, "doc-a", "Biology")
                self._insert_document(conn, "doc-b", "Finance")
                rowid_a = self._insert_chunk(
                    conn, "chunk-a", "doc-a", "Cell division drives growth."
                )
                rowid_b = self._insert_chunk(
                    conn, "chunk-b", "doc-b", "Cell division is a phrase used in this finance joke."
                )
                index_chunk(conn, rowid_a, embedder.embed_query("Cell division drives growth."))
                index_chunk(
                    conn,
                    rowid_b,
                    embedder.embed_query("Cell division is a phrase used in this finance joke."),
                )
                conn.commit()
                doc_hits = search_vector(
                    conn, "Cell division drives growth.", embedder=embedder, doc_ids=["doc-a"]
                )
                subject_hits = search_vector(
                    conn, "Cell division drives growth.", embedder=embedder, subject_name="Biology"
                )

        self.assertEqual(["chunk-a"], [hit.chunk_id for hit in doc_hits])
        self.assertEqual(["chunk-a"], [hit.chunk_id for hit in subject_hits])

    def test_empty_query_returns_empty_list(self) -> None:
        embedder = MockEmbedder()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._configure_temp_runtime(root)
            with db.get_db() as conn:
                db.apply_migrations(conn)
                self.assertTrue(vector_table_exists(conn))
                hits = search_vector(conn, "   ", embedder=embedder)

        self.assertEqual([], hits)

    def test_operational_error_is_logged_not_silent(self) -> None:
        embedder = MockEmbedder()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._configure_temp_runtime(root)
            with db.get_db() as conn:
                db.apply_migrations(conn)
                self._insert_document(conn, "doc-a", "Biology")
                self._insert_chunk(conn, "chunk-a", "doc-a", "Cell division drives growth.")
                conn.execute("DROP TABLE chunks_vec")
                conn.execute("CREATE TABLE chunks_vec (chunk_id INTEGER, embedding BLOB)")
                conn.commit()
                with self.assertLogs("einstein.retrieval.vector", level="WARNING") as captured:
                    hits = search_vector(conn, "Cell division", embedder=embedder)

        self.assertEqual([], hits)
        self.assertTrue(any("vector_search_failed" in line for line in captured.output))

    def test_backfill_indexes_missing_rows_and_clears_flag(self) -> None:
        embedder = MockEmbedder()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._configure_temp_runtime(root)
            with db.get_db() as conn:
                db.apply_migrations(conn)
                self._insert_document(conn, "doc-a", "Biology")
                self._insert_chunk(conn, "chunk-a", "doc-a", "Cell division drives growth.")
                self._insert_chunk(conn, "chunk-b", "doc-a", "Mitosis separates chromosomes.")
                conn.commit()
                result = backfill_missing_embeddings(conn, embedder=embedder, batch_size=2)
                total = conn.execute("SELECT COUNT(*) AS total FROM chunks_vec").fetchone()["total"]
                flag = conn.execute(
                    "SELECT value FROM app_settings WHERE key = 'chunks_vec_backfill_pending'"
                ).fetchone()["value"]

        self.assertTrue(result["completed"])
        self.assertEqual(2, total)
        self.assertEqual("0", str(flag))

    def test_backfill_can_resume_after_partial_run(self) -> None:
        embedder = MockEmbedder()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._configure_temp_runtime(root)
            with db.get_db() as conn:
                db.apply_migrations(conn)
                self._insert_document(conn, "doc-a", "Biology")
                for index in range(5):
                    self._insert_chunk(
                        conn, f"chunk-{index}", "doc-a", f"Cell division fact {index}"
                    )
                conn.commit()
                partial = backfill_missing_embeddings(
                    conn, embedder=embedder, batch_size=2, max_batches=1
                )
                partial_total = conn.execute("SELECT COUNT(*) AS total FROM chunks_vec").fetchone()[
                    "total"
                ]
                partial_flag = conn.execute(
                    "SELECT value FROM app_settings WHERE key = 'chunks_vec_backfill_pending'"
                ).fetchone()["value"]
                resumed = backfill_missing_embeddings(conn, embedder=embedder, batch_size=2)
                final_total = conn.execute("SELECT COUNT(*) AS total FROM chunks_vec").fetchone()[
                    "total"
                ]
                final_flag = conn.execute(
                    "SELECT value FROM app_settings WHERE key = 'chunks_vec_backfill_pending'"
                ).fetchone()["value"]

        self.assertFalse(partial["completed"])
        self.assertEqual(2, partial_total)
        self.assertEqual("1", str(partial_flag))
        self.assertTrue(resumed["completed"])
        self.assertEqual(5, final_total)
        self.assertEqual("0", str(final_flag))

    @unittest.skipUnless(os.getenv("RUN_HEAVY_TESTS") == "1", "heavy vector test disabled")
    def test_real_fastembed_query_returns_biology_chunk_first(self) -> None:
        embedder = FastembedEmbedder()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._configure_temp_runtime(root)
            with db.get_db() as conn:
                db.apply_migrations(conn)
                self._insert_document(conn, "bio", "Biology")
                self._insert_document(conn, "finance", "Finance")
                chunks = [
                    ("chunk-bio", "bio", "Cell division includes mitosis and meiosis in biology."),
                    ("chunk-bio-2", "bio", "Chromosomes package DNA for division."),
                    ("chunk-fin-1", "finance", "Beta measures market risk."),
                    ("chunk-fin-2", "finance", "Discounted cash flow estimates intrinsic value."),
                    (
                        "chunk-fin-3",
                        "finance",
                        "The efficient market hypothesis discusses information.",
                    ),
                ]
                for chunk_id, doc_id, content in chunks:
                    self._insert_chunk(conn, chunk_id, doc_id, content)
                conn.commit()
                backfill_missing_embeddings(conn, embedder=embedder, batch_size=5)
                hits = search_vector(conn, "cell division", embedder=embedder, limit=3)

        self.assertEqual("chunk-bio", hits[0].chunk_id)


if __name__ == "__main__":
    unittest.main()
