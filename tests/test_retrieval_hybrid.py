import math
import shutil
import tempfile
import unittest
from pathlib import Path

import db
from services.retrieval.hybrid import search_hybrid
from services.retrieval.vector import index_chunk
from tests.test_retrieval_vector import MockEmbedder

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_SOURCE = REPO_ROOT / "migrations"


class RetrievalHybridTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_paths = (
            db.BASE_DIR,
            db.DATA_DIR,
            db.UPLOAD_DIR,
            db.DB_PATH,
            db.SCHEMA_PATH,
        )
        self.embedder = MockEmbedder()

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

    def test_empty_query_returns_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._configure_temp_runtime(root)
            with db.get_db() as conn:
                db.apply_migrations(conn)
                hits = search_hybrid(conn, "   ", embedder=self.embedder)

        self.assertEqual([], hits)

    def test_hit_matching_both_rankers_ranks_higher(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._configure_temp_runtime(root)
            with db.get_db() as conn:
                db.apply_migrations(conn)
                self._insert_document(conn, "doc-a", "Biology")
                shared_rowid = self._insert_chunk(
                    conn,
                    "chunk-shared",
                    "doc-a",
                    "Cell division and mitosis organize chromosome separation.",
                )
                fts_only_rowid = self._insert_chunk(
                    conn,
                    "chunk-fts",
                    "doc-a",
                    "Cell division appears in this heading-like biology outline.",
                )
                vec_only_rowid = self._insert_chunk(
                    conn,
                    "chunk-vec",
                    "doc-a",
                    "Chromosome separation during mitosis requires spindle fibers.",
                )
                index_chunk(
                    conn,
                    shared_rowid,
                    self.embedder.embed_query("cell division mitosis chromosome separation"),
                )
                index_chunk(
                    conn,
                    fts_only_rowid,
                    self.embedder.embed_query("portfolio variance beta discount rate"),
                )
                index_chunk(
                    conn,
                    vec_only_rowid,
                    self.embedder.embed_query("cell division mitosis chromosome separation"),
                )
                conn.commit()
                hits = search_hybrid(
                    conn,
                    "cell division mitosis chromosome separation",
                    embedder=self.embedder,
                    limit=3,
                )

        self.assertEqual("chunk-shared", hits[0].chunk_id)
        self.assertEqual(("fts", "vec"), hits[0].sources)
        self.assertIn("chunk-fts", [hit.chunk_id for hit in hits])
        self.assertIn("chunk-vec", [hit.chunk_id for hit in hits])

    def test_rrf_math_matches_expected_value(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._configure_temp_runtime(root)
            with db.get_db() as conn:
                db.apply_migrations(conn)
                self._insert_document(conn, "doc-a", "Biology")
                rowid = self._insert_chunk(
                    conn, "chunk-a", "doc-a", "Cell division includes mitosis."
                )
                index_chunk(
                    conn, rowid, self.embedder.embed_query("cell division includes mitosis")
                )
                conn.commit()
                hits = search_hybrid(
                    conn,
                    "cell division includes mitosis",
                    embedder=self.embedder,
                    limit=1,
                )

        self.assertEqual(1, len(hits))
        expected = 2.0 / (60 + 1)
        self.assertTrue(math.isclose(expected, hits[0].score, rel_tol=1e-9, abs_tol=1e-9))

    def test_filters_propagate_to_both_rankers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._configure_temp_runtime(root)
            with db.get_db() as conn:
                db.apply_migrations(conn)
                self._insert_document(conn, "bio", "Biology")
                self._insert_document(conn, "fin", "Finance")
                bio_rowid = self._insert_chunk(
                    conn, "chunk-bio", "bio", "Cell division drives growth."
                )
                fin_rowid = self._insert_chunk(
                    conn, "chunk-fin", "fin", "Cell division is a finance joke."
                )
                index_chunk(
                    conn, bio_rowid, self.embedder.embed_query("cell division drives growth")
                )
                index_chunk(
                    conn, fin_rowid, self.embedder.embed_query("cell division drives growth")
                )
                conn.commit()
                doc_hits = search_hybrid(
                    conn,
                    "cell division drives growth",
                    embedder=self.embedder,
                    doc_ids=["bio"],
                )
                subject_hits = search_hybrid(
                    conn,
                    "cell division drives growth",
                    embedder=self.embedder,
                    subject_name="Biology",
                )

        self.assertEqual(["chunk-bio"], [hit.chunk_id for hit in doc_hits])
        self.assertEqual(["chunk-bio"], [hit.chunk_id for hit in subject_hits])

    def test_candidate_k_overfetch_respects_limit_after_fusion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._configure_temp_runtime(root)
            with db.get_db() as conn:
                db.apply_migrations(conn)
                self._insert_document(conn, "doc-a", "Biology")
                for index in range(8):
                    rowid = self._insert_chunk(
                        conn,
                        f"chunk-{index}",
                        "doc-a",
                        f"Cell division fact {index} explains mitosis and meiosis.",
                    )
                    index_chunk(
                        conn,
                        rowid,
                        self.embedder.embed_query(
                            f"cell division fact {index} explains mitosis and meiosis"
                        ),
                    )
                conn.commit()
                hits = search_hybrid(
                    conn,
                    "cell division fact",
                    embedder=self.embedder,
                    limit=5,
                    candidate_k=30,
                )

        self.assertEqual(5, len(hits))

    def test_vec_only_fallback_works_when_fts_table_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._configure_temp_runtime(root)
            with db.get_db() as conn:
                db.apply_migrations(conn)
                self._insert_document(conn, "doc-a", "Biology")
                rowid = self._insert_chunk(
                    conn, "chunk-a", "doc-a", "Cell division includes mitosis."
                )
                index_chunk(
                    conn, rowid, self.embedder.embed_query("cell division includes mitosis")
                )
                conn.execute("DELETE FROM chunks_fts")
                conn.commit()
                hits = search_hybrid(
                    conn, "cell division includes mitosis", embedder=self.embedder, limit=3
                )

        self.assertEqual(["chunk-a"], [hit.chunk_id for hit in hits])
        self.assertEqual([("vec",)], [hit.sources for hit in hits])

    def test_fts_only_fallback_works_when_vector_table_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._configure_temp_runtime(root)
            with db.get_db() as conn:
                db.apply_migrations(conn)
                conn.execute("DROP TABLE IF EXISTS chunks_vec")
                self._insert_document(conn, "doc-a", "Biology")
                self._insert_chunk(conn, "chunk-a", "doc-a", "Cell division includes mitosis.")
                conn.commit()
                hits = search_hybrid(
                    conn, "cell division includes mitosis", embedder=self.embedder, limit=3
                )

        self.assertEqual(["chunk-a"], [hit.chunk_id for hit in hits])
        self.assertEqual([("fts",)], [hit.sources for hit in hits])


if __name__ == "__main__":
    unittest.main()
