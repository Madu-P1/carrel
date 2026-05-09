import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import db
from ai.router import ClaudeRouter
from app_runtime import resolve_runtime_paths


class Phase0FoundationTests(unittest.TestCase):
    def test_runtime_paths_can_be_resolved_from_explicit_base_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            paths = resolve_runtime_paths(base_dir=base_dir)

        self.assertEqual(base_dir.resolve(), paths.base_dir)
        self.assertEqual((base_dir / "data").resolve(), paths.data_dir)
        self.assertEqual((base_dir / "schema.sql").resolve(), paths.schema_path)

    def test_runtime_paths_honor_environment_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            override_db = root / "custom" / "einstein.db"
            override_schema = root / "custom" / "schema.sql"
            with mock.patch.dict(
                os.environ,
                {
                    "EINSTEIN_BASE_DIR": str(root),
                    "EINSTEIN_DB_PATH": str(override_db),
                    "EINSTEIN_SCHEMA_PATH": str(override_schema),
                },
                clear=False,
            ):
                paths = resolve_runtime_paths()

        self.assertEqual(root.resolve(), paths.base_dir)
        self.assertEqual(override_db.resolve(), paths.db_path)
        self.assertEqual(override_schema.resolve(), paths.schema_path)

    def test_claude_router_returns_structured_failure_without_api_key(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            router = ClaudeRouter()
            result = router.request_text(
                request_kind="unit_test",
                system="You are a test helper.",
                prompt="Say hello.",
                task="fast",
            )

        self.assertFalse(result.ok)
        self.assertEqual("missing_api_key", result.error_code)
        self.assertIsNone(result.text)
        self.assertEqual("fast", result.task)

    def test_apply_migrations_records_numeric_version_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            upload_dir = data_dir / "uploads"
            schema_path = root / "schema.sql"
            migrations_dir = root / "migrations"
            migrations_dir.mkdir(parents=True, exist_ok=True)
            schema_path.write_text(
                "CREATE TABLE IF NOT EXISTS base_table (id INTEGER);", encoding="utf-8"
            )
            migration_name = "20260420_test.sql"
            (migrations_dir / migration_name).write_text(
                "CREATE TABLE IF NOT EXISTS phase_one_table (id INTEGER);",
                encoding="utf-8",
            )

            original = (db.BASE_DIR, db.DATA_DIR, db.UPLOAD_DIR, db.DB_PATH, db.SCHEMA_PATH)
            try:
                db.configure_paths(
                    base_dir=root,
                    data_dir=data_dir,
                    upload_dir=upload_dir,
                    db_path=data_dir / "test.db",
                    schema_path=schema_path,
                )
                conn = sqlite3.connect(":memory:", factory=db.ManagedConnection)
                conn.row_factory = sqlite3.Row
                db.apply_migrations(conn)
                row = conn.execute(
                    "SELECT version, name FROM schema_migrations WHERE name = ?",
                    (migration_name,),
                ).fetchone()
            finally:
                db.configure_paths(
                    base_dir=original[0],
                    data_dir=original[1],
                    upload_dir=original[2],
                    db_path=original[3],
                    schema_path=original[4],
                )

        self.assertIsNotNone(row)
        self.assertEqual(20260420, row["version"])
        self.assertEqual(migration_name, row["name"])

    def test_apply_migrations_backfills_legacy_name_only_table(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            upload_dir = data_dir / "uploads"
            schema_path = root / "schema.sql"
            migrations_dir = root / "migrations"
            migrations_dir.mkdir(parents=True, exist_ok=True)
            schema_path.write_text(
                "CREATE TABLE IF NOT EXISTS base_table (id INTEGER);", encoding="utf-8"
            )
            migration_name = "20260420_test.sql"
            (migrations_dir / migration_name).write_text(
                "CREATE TABLE IF NOT EXISTS phase_one_table (id INTEGER);",
                encoding="utf-8",
            )

            original = (db.BASE_DIR, db.DATA_DIR, db.UPLOAD_DIR, db.DB_PATH, db.SCHEMA_PATH)
            try:
                db.configure_paths(
                    base_dir=root,
                    data_dir=data_dir,
                    upload_dir=upload_dir,
                    db_path=data_dir / "test.db",
                    schema_path=schema_path,
                )
                conn = sqlite3.connect(":memory:", factory=db.ManagedConnection)
                conn.row_factory = sqlite3.Row
                conn.execute(
                    """
                    CREATE TABLE schema_migrations (
                        name TEXT PRIMARY KEY,
                        applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute("INSERT INTO schema_migrations (name) VALUES (?)", (migration_name,))
                conn.commit()
                db.apply_migrations(conn)
                columns = {
                    row["name"]
                    for row in conn.execute("PRAGMA table_info(schema_migrations)").fetchall()
                }
                row = conn.execute(
                    "SELECT version, name FROM schema_migrations WHERE name = ?",
                    (migration_name,),
                ).fetchone()
            finally:
                db.configure_paths(
                    base_dir=original[0],
                    data_dir=original[1],
                    upload_dir=original[2],
                    db_path=original[3],
                    schema_path=original[4],
                )

        self.assertIn("version", columns)
        self.assertIsNotNone(row)
        self.assertEqual(20260420, row["version"])


if __name__ == "__main__":
    unittest.main()
