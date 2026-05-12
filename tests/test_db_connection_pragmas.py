"""Concurrency regression test for `db.get_db` PRAGMA configuration.

PR-S4: Carrel runs FastAPI which serves concurrent /api/* requests AND
an in-process job worker that writes to SQLite during ingest. Before
this PR, `sqlite3.connect` was called with no `busy_timeout` set —
SQLite's default is 0ms, so any second writer would see an instant
`database is locked` OperationalError. The user's first concurrent
action (upload during review, two browser tabs, etc.) would 500.

These tests prove:
1. Every connection from `get_db()` has the three PRAGMAs applied
   (busy_timeout=5000ms, journal_mode=WAL, synchronous=NORMAL).
2. Ten concurrent writers against the same DB all succeed without
   `OperationalError`.
"""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

import db

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_SOURCE = REPO_ROOT / "migrations"


class ConnectionPragmaTests(unittest.TestCase):
    """Pin the per-connection PRAGMA contract."""

    def setUp(self) -> None:
        self._original_paths = (
            db.BASE_DIR,
            db.DATA_DIR,
            db.UPLOAD_DIR,
            db.DB_PATH,
            db.SCHEMA_PATH,
        )
        self._tempdir = tempfile.TemporaryDirectory()
        root = Path(self._tempdir.name)
        data_dir = root / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        (root / "schema.sql").write_text("-- test\n", encoding="utf-8")
        # Copy migrations so apply_migrations works; we need at least a
        # writable table to exercise the lock contract.
        shutil.copytree(MIGRATIONS_SOURCE, root / "migrations", dirs_exist_ok=True)
        db.configure_paths(
            base_dir=root,
            data_dir=data_dir,
            upload_dir=data_dir / "uploads",
            db_path=data_dir / "test.db",
            schema_path=root / "schema.sql",
        )
        (data_dir / "uploads").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        db.configure_paths(
            base_dir=self._original_paths[0],
            data_dir=self._original_paths[1],
            upload_dir=self._original_paths[2],
            db_path=self._original_paths[3],
            schema_path=self._original_paths[4],
        )
        self._tempdir.cleanup()

    def test_busy_timeout_is_five_seconds(self) -> None:
        with db.get_db() as conn:
            (timeout_ms,) = conn.execute("PRAGMA busy_timeout").fetchone()
            self.assertEqual(timeout_ms, 5000)

    def test_journal_mode_is_wal(self) -> None:
        with db.get_db() as conn:
            (mode,) = conn.execute("PRAGMA journal_mode").fetchone()
            self.assertEqual(mode.lower(), "wal")

    def test_synchronous_is_normal(self) -> None:
        # SQLite returns synchronous as an integer:
        #   0 = OFF, 1 = NORMAL, 2 = FULL, 3 = EXTRA.
        with db.get_db() as conn:
            (sync_level,) = conn.execute("PRAGMA synchronous").fetchone()
            self.assertEqual(sync_level, 1)

    def test_pragmas_applied_to_every_new_connection(self) -> None:
        # Open three connections and confirm each one has its own
        # busy_timeout / synchronous set (these are per-connection, so
        # we have to set them every time, not just on the first open).
        for _ in range(3):
            with db.get_db() as conn:
                (timeout_ms,) = conn.execute("PRAGMA busy_timeout").fetchone()
                (sync_level,) = conn.execute("PRAGMA synchronous").fetchone()
                self.assertEqual(timeout_ms, 5000)
                self.assertEqual(sync_level, 1)


class ConcurrentWriterTests(unittest.TestCase):
    """Real concurrency contract: N threads, N writes, zero locks lost.

    Cross-connection visibility is required to prove this — a single
    SAVEPOINT-scoped session would mask the race. Each thread opens
    its own connection via `db.get_db()` and commits real rows.
    """

    def setUp(self) -> None:
        self._original_paths = (
            db.BASE_DIR,
            db.DATA_DIR,
            db.UPLOAD_DIR,
            db.DB_PATH,
            db.SCHEMA_PATH,
        )
        self._tempdir = tempfile.TemporaryDirectory()
        root = Path(self._tempdir.name)
        data_dir = root / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "uploads").mkdir(parents=True, exist_ok=True)
        (root / "schema.sql").write_text("-- test\n", encoding="utf-8")
        shutil.copytree(MIGRATIONS_SOURCE, root / "migrations", dirs_exist_ok=True)
        db.configure_paths(
            base_dir=root,
            data_dir=data_dir,
            upload_dir=data_dir / "uploads",
            db_path=data_dir / "test.db",
            schema_path=root / "schema.sql",
        )
        # Single tiny table is enough to exercise the writer lock.
        with db.get_db() as conn:
            conn.execute("CREATE TABLE writer_probe (id INTEGER PRIMARY KEY, who TEXT NOT NULL)")
            conn.commit()

    def tearDown(self) -> None:
        db.configure_paths(
            base_dir=self._original_paths[0],
            data_dir=self._original_paths[1],
            upload_dir=self._original_paths[2],
            db_path=self._original_paths[3],
            schema_path=self._original_paths[4],
        )
        self._tempdir.cleanup()

    def test_ten_concurrent_writers_all_succeed(self) -> None:
        writer_count = 10
        ready = threading.Barrier(writer_count)
        results: list[Exception | None] = [None] * writer_count

        def write(idx: int) -> None:
            try:
                # Synchronize start so the contention actually races.
                ready.wait(timeout=5.0)
                with db.get_db() as conn:
                    conn.execute(
                        "INSERT INTO writer_probe (who) VALUES (?)",
                        (f"writer_{idx}",),
                    )
                    conn.commit()
            except Exception as exc:
                results[idx] = exc

        threads = [threading.Thread(target=write, args=(idx,)) for idx in range(writer_count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10.0)

        errors = [exc for exc in results if exc is not None]
        # The diagnostic message includes the actual exception types so
        # a failure tells you why immediately ("database is locked"
        # would be the regression signal we're guarding against).
        self.assertEqual(
            errors,
            [],
            msg=f"Concurrent writers hit errors: {[type(e).__name__ for e in errors]}: {errors}",
        )

        with db.get_db() as conn:
            (committed,) = conn.execute("SELECT COUNT(*) FROM writer_probe").fetchone()
            self.assertEqual(committed, writer_count)

    def test_reader_does_not_block_writer_under_wal(self) -> None:
        # Under WAL, a long-running reader should NOT block a writer.
        # If we ever regress from WAL to rollback journal, the writer
        # would block until the reader committed.
        with db.get_db() as reader_conn:
            reader_conn.execute("BEGIN")
            # Hold a read on the same table; writer should still go through.
            reader_conn.execute("SELECT COUNT(*) FROM writer_probe").fetchone()
            try:
                with db.get_db() as writer_conn:
                    writer_conn.execute(
                        "INSERT INTO writer_probe (who) VALUES (?)",
                        ("under_reader",),
                    )
                    writer_conn.commit()
            except sqlite3.OperationalError as exc:
                self.fail(f"WAL mode regressed: writer blocked under reader: {exc}")
            finally:
                reader_conn.execute("ROLLBACK")


if __name__ == "__main__":
    unittest.main()
