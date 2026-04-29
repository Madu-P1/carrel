import shutil
import tempfile
import unittest
from pathlib import Path

import db

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_SOURCE = REPO_ROOT / "migrations"


class DatabaseMigrationTests(unittest.TestCase):
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

    def test_fresh_database_applies_all_numbered_migrations(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._configure_temp_runtime(root)

            with db.get_db() as conn:
                db.apply_migrations(conn)
                migration_rows = conn.execute(
                    "SELECT version, name FROM schema_migrations ORDER BY version"
                ).fetchall()
                document_columns = {
                    row["name"] for row in conn.execute("PRAGMA table_info(documents)").fetchall()
                }
                concept_columns = {
                    row["name"] for row in conn.execute("PRAGMA table_info(concepts)").fetchall()
                }
                edge_columns = {
                    row["name"] for row in conn.execute("PRAGMA table_info(concept_edges)").fetchall()
                }
                tables = {
                    row["name"]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
                triggers = {
                    row["name"]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'trigger'"
                    ).fetchall()
                }

        # Vector migration (0007) is conditionally applied based on
        # whether sqlite-vec is available at runtime; the rest are
        # unconditional. Build the expected list in version order so the
        # 0008 / 0009 migrations always tail the vector slot.
        expected_rows = [
            (1, "0001_initial.sql"),
            (2, "0002_documents_storage_and_subject.sql"),
            (3, "0003_documents_updated_at_backfill.sql"),
            (4, "0004_concepts_doc_id.sql"),
            (5, "0005_concept_edges_doc_id.sql"),
            (6, "0006_chunks_fts5.sql"),
        ]
        if db.sqlite_vec_runtime_supported():
            expected_rows.append((7, "0007_chunks_vec.sql"))
        expected_rows.extend(
            [
                (8, "0008_anchors.sql"),
                (9, "0009_calendar_and_planning.sql"),
            ]
        )
        self.assertEqual(expected_rows, [(row["version"], row["name"]) for row in migration_rows])
        self.assertTrue({"storage_name", "subject_name", "updated_at"} <= document_columns)
        self.assertIn("doc_id", concept_columns)
        self.assertIn("doc_id", edge_columns)
        self.assertIn("artifacts", tables)
        self.assertIn("mastery_states", tables)
        self.assertIn("chunks_fts", tables)
        self.assertTrue({"chunks_ai", "chunks_ad", "chunks_au"} <= triggers)
        if db.sqlite_vec_runtime_supported():
            self.assertIn("chunks_vec", tables)

    def test_reapplying_migrations_is_a_no_op(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._configure_temp_runtime(root)

            with db.get_db() as conn:
                db.apply_migrations(conn)
                db.apply_migrations(conn)
                total = conn.execute("SELECT COUNT(*) AS total FROM schema_migrations").fetchone()["total"]

        # +2 for 0008_anchors and 0009_calendar_and_planning, which
        # always apply (no runtime gate like sqlite-vec).
        expected_total = (7 if db.sqlite_vec_runtime_supported() else 6) + 2
        self.assertEqual(expected_total, total)

    def test_legacy_database_is_marked_without_reexecuting_migrations(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._configure_temp_runtime(root)

            with db.get_db() as conn:
                db.apply_migrations(conn)
                conn.execute("DROP TABLE schema_migrations")
                conn.commit()
                db.apply_migrations(conn)
                rows = conn.execute(
                    "SELECT version, name FROM schema_migrations ORDER BY version"
                ).fetchall()

        expected_names = [
            "0001_initial.sql",
            "0002_documents_storage_and_subject.sql",
            "0003_documents_updated_at_backfill.sql",
            "0004_concepts_doc_id.sql",
            "0005_concept_edges_doc_id.sql",
            "0006_chunks_fts5.sql",
        ]
        if db.sqlite_vec_runtime_supported():
            expected_names.append("0007_chunks_vec.sql")
        expected_names.extend(
            [
                "0008_anchors.sql",
                "0009_calendar_and_planning.sql",
            ]
        )
        self.assertEqual(len(expected_names), len(rows))
        self.assertEqual(expected_names, [row["name"] for row in rows])

    def test_invalid_migration_filename_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._configure_temp_runtime(root)
            (root / "migrations" / "bad_name.sql").write_text("SELECT 1;", encoding="utf-8")

            with db.get_db() as conn:
                with self.assertRaises(ValueError):
                    db.apply_migrations(conn)


if __name__ == "__main__":
    unittest.main()
