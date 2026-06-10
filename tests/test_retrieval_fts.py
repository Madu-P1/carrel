import shutil
import tempfile
import unittest
from pathlib import Path

import db
from services.retrieval import search_keyword

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_SOURCE = REPO_ROOT / "migrations"


class RetrievalFTSTests(unittest.TestCase):
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
    ) -> None:
        conn.execute(
            """
            INSERT INTO chunks (id, doc_id, content, section, chunk_index, token_count)
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (chunk_id, doc_id, content, section, len(content.split())),
        )

    def test_fresh_database_query_returns_empty_list(self) -> None:
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
                hits = search_keyword(conn, "known phrase")

        self.assertIn("chunks_fts", tables)
        self.assertEqual([], hits)

    def test_search_returns_best_matching_chunk_first(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._configure_temp_runtime(root)
            with db.get_db() as conn:
                db.apply_migrations(conn)
                self._insert_document(conn, "doc-a", "Biology")
                self._insert_chunk(
                    conn,
                    "chunk-a",
                    "doc-a",
                    "Cell division depends on chromosome replication and spindle fibers.",
                )
                self._insert_chunk(
                    conn, "chunk-b", "doc-a", "Mitochondria support aerobic respiration."
                )
                self._insert_chunk(
                    conn,
                    "chunk-c",
                    "doc-a",
                    "Photosynthesis converts light energy into chemical energy.",
                )
                conn.commit()
                hits = search_keyword(conn, "chromosome replication")

        self.assertGreaterEqual(len(hits), 1)
        self.assertEqual("chunk-a", hits[0].chunk_id)

    def test_insert_trigger_indexes_without_manual_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._configure_temp_runtime(root)
            with db.get_db() as conn:
                db.apply_migrations(conn)
                self._insert_document(conn, "doc-a", "Biology")
                self._insert_chunk(
                    conn, "chunk-a", "doc-a", "Cell signaling uses receptor proteins."
                )
                conn.commit()
                hits = search_keyword(conn, "receptor proteins")

        self.assertEqual(["chunk-a"], [hit.chunk_id for hit in hits])

    def test_update_trigger_refreshes_indexed_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._configure_temp_runtime(root)
            with db.get_db() as conn:
                db.apply_migrations(conn)
                self._insert_document(conn, "doc-a", "Biology")
                self._insert_chunk(
                    conn, "chunk-a", "doc-a", "Cell signaling uses receptor proteins."
                )
                conn.commit()
                conn.execute(
                    "UPDATE chunks SET content = ?, token_count = ? WHERE id = ?",
                    ("Photosystems drive electron transport in chloroplasts.", 6, "chunk-a"),
                )
                conn.commit()
                old_hits = search_keyword(conn, "receptor proteins")
                new_hits = search_keyword(conn, "electron transport")

        self.assertEqual([], old_hits)
        self.assertEqual(["chunk-a"], [hit.chunk_id for hit in new_hits])

    def test_delete_trigger_removes_deleted_chunk(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._configure_temp_runtime(root)
            with db.get_db() as conn:
                db.apply_migrations(conn)
                self._insert_document(conn, "doc-a", "Biology")
                self._insert_chunk(conn, "chunk-a", "doc-a", "Enzymes lower activation energy.")
                conn.commit()
                conn.execute("DELETE FROM chunks WHERE id = ?", ("chunk-a",))
                conn.commit()
                hits = search_keyword(conn, "activation energy")

        self.assertEqual([], hits)

    def test_doc_ids_filter_limits_results(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._configure_temp_runtime(root)
            with db.get_db() as conn:
                db.apply_migrations(conn)
                self._insert_document(conn, "doc-a", "Biology")
                self._insert_document(conn, "doc-b", "Biology")
                self._insert_chunk(conn, "chunk-a", "doc-a", "Cell division includes mitosis.")
                self._insert_chunk(conn, "chunk-b", "doc-b", "Cell division also includes meiosis.")
                conn.commit()
                hits = search_keyword(conn, "cell division", doc_ids=["doc-b"])

        self.assertEqual(["chunk-b"], [hit.chunk_id for hit in hits])

    def test_subject_name_filter_limits_results(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._configure_temp_runtime(root)
            with db.get_db() as conn:
                db.apply_migrations(conn)
                self._insert_document(conn, "doc-a", "Biology")
                self._insert_document(conn, "doc-b", "Finance")
                self._insert_chunk(
                    conn, "chunk-a", "doc-a", "Beta measures market risk in a portfolio."
                )
                self._insert_chunk(
                    conn, "chunk-b", "doc-b", "Beta also appears in finance lecture notes."
                )
                conn.commit()
                hits = search_keyword(conn, "beta", subject_name="Biology")

        self.assertEqual(["chunk-a"], [hit.chunk_id for hit in hits])

    def test_empty_query_returns_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._configure_temp_runtime(root)
            with db.get_db() as conn:
                db.apply_migrations(conn)
                hits = search_keyword(conn, "   ")

        self.assertEqual([], hits)

    def test_query_with_fts_operators_is_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._configure_temp_runtime(root)
            with db.get_db() as conn:
                db.apply_migrations(conn)
                self._insert_document(conn, "doc-a", "Biology")
                self._insert_chunk(
                    conn, "chunk-a", "doc-a", "Cell division requires spindle fibers."
                )
                conn.commit()
                hits = search_keyword(conn, 'cell*"division (spindle')

        self.assertEqual(["chunk-a"], [hit.chunk_id for hit in hits])

    def test_multi_word_query_ranks_the_all_words_chunk_first(self) -> None:
        # OR-semantics ranked BM25 (2026-06-11): bare space-separated terms
        # were implicit AND, which returned ZERO rows for any sentence-shaped
        # query with one non-shared word — the recorded cause of the 0/14
        # smoke-eval groundedness hole and a vacuous FTS arm on the contract
        # path. The arm now RANKS: the chunk matching every query word comes
        # first; partial matches trail for the fusion to weigh.
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._configure_temp_runtime(root)
            with db.get_db() as conn:
                db.apply_migrations(conn)
                self._insert_document(conn, "doc-a", "Biology")
                self._insert_chunk(
                    conn, "chunk-a", "doc-a", "Cell division requires spindle fibers."
                )
                self._insert_chunk(conn, "chunk-b", "doc-a", "Cell membranes regulate transport.")
                self._insert_chunk(
                    conn, "chunk-c", "doc-a", "Division of labor appears in sociology."
                )
                conn.commit()
                hits = search_keyword(conn, "cell division")

        self.assertEqual("chunk-a", hits[0].chunk_id)
        self.assertEqual({"chunk-a", "chunk-b", "chunk-c"}, {hit.chunk_id for hit in hits})

    def test_reapplying_migrations_keeps_fts_triggers_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._configure_temp_runtime(root)
            with db.get_db() as conn:
                db.apply_migrations(conn)
                db.apply_migrations(conn)
                triggers = {
                    row["name"]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'trigger'"
                    ).fetchall()
                }
                tables = {
                    row["name"]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }

        self.assertIn("chunks_fts", tables)
        self.assertTrue({"chunks_ai", "chunks_ad", "chunks_au"} <= triggers)


if __name__ == "__main__":
    unittest.main()
