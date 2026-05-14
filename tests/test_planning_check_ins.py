"""Tests for Coach Phase 2.B session check-ins.

Two layers:
  - Repository unit tests against an isolated temp DB.
  - API e2e tests via TestClient hitting POST /api/plan/check-in.

Pydantic validates 1..5 at the API boundary (422 on bad input).
The CHECK constraint in migration 0020 enforces the same range at
write time as the unbypassable backstop.
"""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import db
from services.calendar import repository

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_SOURCE = REPO_ROOT / "migrations"


class _CheckInTestCase(unittest.TestCase):
    """Shared fixture: temp DB with all migrations applied."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.original_paths = (
            db.BASE_DIR,
            db.DATA_DIR,
            db.UPLOAD_DIR,
            db.DB_PATH,
            db.SCHEMA_PATH,
        )
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


class CheckInRepositoryTests(_CheckInTestCase):
    """insert_check_in + list_recent_check_ins."""

    def test_insert_returns_id_and_persists_row(self) -> None:
        with db.get_db() as conn:
            check_in_id = repository.insert_check_in(conn, stress_level=3, energy_level=4)
            row = conn.execute(
                "SELECT stress_level, energy_level FROM session_check_ins WHERE id = ?",
                (check_in_id,),
            ).fetchone()
        self.assertIsNotNone(check_in_id)
        self.assertEqual(row["stress_level"], 3)
        self.assertEqual(row["energy_level"], 4)

    def test_insert_rejects_out_of_range_stress(self) -> None:
        """CHECK constraint is the unbypassable backstop."""
        with db.get_db() as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                repository.insert_check_in(conn, stress_level=0, energy_level=3)
            with self.assertRaises(sqlite3.IntegrityError):
                repository.insert_check_in(conn, stress_level=6, energy_level=3)

    def test_insert_rejects_out_of_range_energy(self) -> None:
        with db.get_db() as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                repository.insert_check_in(conn, stress_level=3, energy_level=0)
            with self.assertRaises(sqlite3.IntegrityError):
                repository.insert_check_in(conn, stress_level=3, energy_level=6)

    def test_list_recent_returns_newest_first(self) -> None:
        with db.get_db() as conn:
            first = repository.insert_check_in(conn, stress_level=2, energy_level=3)
            second = repository.insert_check_in(conn, stress_level=4, energy_level=2)
            recent = repository.list_recent_check_ins(conn, hours=24)
        self.assertEqual(len(recent), 2)
        # Newest first.
        self.assertEqual(recent[0].id, second)
        self.assertEqual(recent[1].id, first)

    def test_list_recent_respects_window(self) -> None:
        """Rows older than `hours` window are excluded."""
        with db.get_db() as conn:
            # Insert a fresh row, then a stale row by direct manipulation.
            fresh_id = repository.insert_check_in(conn, stress_level=3, energy_level=3)
            stale_iso = (
                (datetime.now(timezone.utc) - timedelta(hours=48))
                .isoformat()
                .replace("+00:00", "Z")
            )
            conn.execute(
                """
                INSERT INTO session_check_ins (id, user_id, stress_level, energy_level, created_at)
                VALUES (?, 'local', 2, 2, ?)
                """,
                ("stale-id", stale_iso),
            )
            conn.commit()
            recent = repository.list_recent_check_ins(conn, hours=24)
        ids = [r.id for r in recent]
        self.assertIn(fresh_id, ids)
        self.assertNotIn("stale-id", ids)


class CheckInApiTests(unittest.TestCase):
    """POST /api/plan/check-in via TestClient."""

    def setUp(self) -> None:
        from fastapi.testclient import TestClient

        import main
        from services.calendar.secrets import set_default_secret_store_for_testing
        from services.local_api_security import HEADER_NAME, get_local_api_token

        class _FakeStore:
            def __init__(self):
                self.values: dict[str, str] = {}

            def store_url(self, feed_id: str, raw_url: str) -> str:
                ref = f"fake:{feed_id}"
                self.values[ref] = raw_url
                return ref

            def get_url(self, reference: str):
                return self.values.get(reference)

            def delete_url(self, reference: str) -> None:
                self.values.pop(reference, None)

        set_default_secret_store_for_testing(_FakeStore())

        self.temp_dir = tempfile.TemporaryDirectory()
        base = Path(self.temp_dir.name)
        self.originals = {
            "BASE_DIR": main.BASE_DIR,
            "DATA_DIR": main.DATA_DIR,
            "UPLOAD_DIR": main.UPLOAD_DIR,
            "DB_PATH": main.DB_PATH,
        }
        main.BASE_DIR = base
        main.DATA_DIR = base / "data"
        main.UPLOAD_DIR = main.DATA_DIR / "uploads"
        main.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        main.DB_PATH = main.DATA_DIR / "test.db"
        main.initialize_database()

        self.main = main
        self.HEADER_NAME = HEADER_NAME
        self.client = TestClient(main.app, headers={HEADER_NAME: get_local_api_token()})

    def tearDown(self) -> None:
        from services.calendar.secrets import set_default_secret_store_for_testing

        set_default_secret_store_for_testing(None)
        for k, v in self.originals.items():
            setattr(self.main, k, v)
        self.temp_dir.cleanup()

    def test_happy_path_returns_id_and_status(self) -> None:
        response = self.client.post(
            "/api/plan/check-in",
            json={"stress_level": 4, "energy_level": 2},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["status"], "recorded")
        self.assertIsNotNone(body["id"])

        # Row appears in the DB.
        with db.get_db() as conn:
            row = conn.execute(
                "SELECT stress_level, energy_level FROM session_check_ins WHERE id = ?",
                (body["id"],),
            ).fetchone()
        self.assertEqual(row["stress_level"], 4)
        self.assertEqual(row["energy_level"], 2)

    def test_rejects_stress_below_one(self) -> None:
        response = self.client.post(
            "/api/plan/check-in",
            json={"stress_level": 0, "energy_level": 3},
        )
        self.assertEqual(response.status_code, 422)

    def test_rejects_stress_above_five(self) -> None:
        response = self.client.post(
            "/api/plan/check-in",
            json={"stress_level": 6, "energy_level": 3},
        )
        self.assertEqual(response.status_code, 422)

    def test_rejects_energy_out_of_range(self) -> None:
        for bad in (0, 6, -1, 99):
            response = self.client.post(
                "/api/plan/check-in",
                json={"stress_level": 3, "energy_level": bad},
            )
            self.assertEqual(response.status_code, 422, f"expected 422 for energy={bad}")

    def test_rejects_missing_fields(self) -> None:
        response = self.client.post("/api/plan/check-in", json={"stress_level": 3})
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
