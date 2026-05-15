import logging
import os
import re
import sqlite3
from pathlib import Path
from typing import NamedTuple

from app_logging import get_logger, log_event
from app_runtime import resolve_runtime_paths

RUNTIME_PATHS = resolve_runtime_paths()
BASE_DIR = RUNTIME_PATHS.base_dir
DATA_DIR = RUNTIME_PATHS.data_dir
UPLOAD_DIR = RUNTIME_PATHS.upload_dir
DB_PATH = RUNTIME_PATHS.db_path
SCHEMA_PATH = RUNTIME_PATHS.schema_path


class ManagedConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class MigrationFile(NamedTuple):
    version: int
    name: str
    path: Path


OBSOLETE_MIGRATION_NAMES = {"20260412_learning_os.sql"}
VECTOR_MIGRATION_VERSIONS = {7}
LOGGER = get_logger("db")
_SQLITE_VEC_WARNING_KEYS: set[str] = set()


def configure_paths(
    *,
    base_dir: Path,
    data_dir: Path,
    upload_dir: Path,
    db_path: Path,
    schema_path: Path,
) -> None:
    global BASE_DIR, DATA_DIR, UPLOAD_DIR, DB_PATH, SCHEMA_PATH
    BASE_DIR = base_dir
    DATA_DIR = data_dir
    UPLOAD_DIR = upload_dir
    DB_PATH = db_path
    SCHEMA_PATH = schema_path


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, factory=ManagedConnection)
    conn.row_factory = sqlite3.Row
    _apply_connection_pragmas(conn)
    _load_extensions(conn)
    return conn


def _apply_connection_pragmas(conn: sqlite3.Connection) -> None:
    """Set per-connection SQLite PRAGMAs that the default is wrong for.

    PR-S4: Carrel runs FastAPI which serves concurrent requests + an
    in-process job worker that writes during ingest. Out of the box,
    SQLite's busy_timeout is 0ms: any second writer sees an instant
    "database is locked" OperationalError. With WAL mode, readers and
    one writer can coexist without blocking, but two writers still
    race; a 5s busy_timeout lets the loser wait for the winner to
    commit instead of erroring out. 5s is generous for any normal
    write on this machine (~ms range).

    journal_mode=WAL is database-level rather than connection-level —
    the first connection that opens the DB persists the mode into the
    file header, and subsequent connections inherit it. Setting it on
    every connection is idempotent and self-heals if some other tool
    flipped the mode (e.g., the user opening the DB with `sqlite3` and
    running `.mode delete`).

    synchronous=NORMAL is per-connection. The SQLite default under WAL
    is FULL, which fsyncs more aggressively than WAL needs. NORMAL is
    the documented safe complement to WAL (no torn writes; one fsync
    per checkpoint instead of two).
    """
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return bool(row)


def column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    if not table_exists(conn, table_name):
        return False
    columns = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row["name"] == column_name for row in columns)


def _migration_version(name: str) -> int:
    match = re.match(r"^(\d+)", Path(name).stem)
    if not match:
        raise ValueError(f"Migration filename must start with a numeric version: {name}")
    return int(match.group(1))


def _list_migration_files(migrations_dir: Path) -> list[MigrationFile]:
    migrations: list[MigrationFile] = []
    for migration_path in sorted(migrations_dir.glob("*.sql")):
        migrations.append(
            MigrationFile(
                version=_migration_version(migration_path.name),
                name=migration_path.name,
                path=migration_path,
            )
        )
    return migrations


def sqlite_vec_runtime_supported() -> bool:
    try:
        conn = sqlite3.connect(":memory:")
    except Exception:
        return False
    try:
        if not hasattr(conn, "enable_load_extension"):
            return False
        try:
            import sqlite_vec  # noqa: F401
        except Exception:
            return False
        return True
    finally:
        conn.close()


def _log_sqlite_vec_warning(reason: str, **context: object) -> None:
    if reason in _SQLITE_VEC_WARNING_KEYS:
        return
    _SQLITE_VEC_WARNING_KEYS.add(reason)
    log_event(LOGGER, logging.WARNING, "sqlite_vec_unavailable", reason=reason, **context)


def _load_extensions(conn: sqlite3.Connection) -> bool:
    if not hasattr(conn, "enable_load_extension"):
        _log_sqlite_vec_warning("enable_load_extension_missing")
        return False

    try:
        conn.enable_load_extension(True)
    except Exception as exc:
        _log_sqlite_vec_warning("enable_load_extension_failed", error=str(exc))
        return False

    try:
        import sqlite_vec

        sqlite_vec.load(conn)
        return True
    except Exception as exc:
        _log_sqlite_vec_warning("sqlite_vec_load_failed", error=str(exc))
        return False
    finally:
        try:
            conn.enable_load_extension(False)
        except Exception:
            pass


def _ensure_schema_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _backfill_legacy_migration_rows(
    conn: sqlite3.Connection, migrations: list[MigrationFile]
) -> None:
    if not table_exists(conn, "schema_migrations"):
        return
    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(schema_migrations)").fetchall()
    }
    if "version" in columns:
        return

    existing_names = [
        row["name"]
        for row in conn.execute(
            "SELECT name FROM schema_migrations ORDER BY applied_at ASC"
        ).fetchall()
    ]
    conn.execute("ALTER TABLE schema_migrations RENAME TO schema_migrations_legacy")
    _ensure_schema_migrations_table(conn)
    by_name = {migration.name: migration for migration in migrations}
    for name in existing_names:
        migration = by_name.get(name)
        if migration is None:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, name) VALUES (?, ?)",
            (migration.version, migration.name),
        )
    conn.execute("DROP TABLE schema_migrations_legacy")
    conn.commit()


def _insert_migration_row(conn: sqlite3.Connection, migration: MigrationFile) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations (version, name) VALUES (?, ?)",
        (migration.version, migration.name),
    )


def _has_tables(conn: sqlite3.Connection, table_names: list[str]) -> bool:
    return all(table_exists(conn, table_name) for table_name in table_names)


def _has_columns(conn: sqlite3.Connection, table_name: str, column_names: list[str]) -> bool:
    return all(column_exists(conn, table_name, column_name) for column_name in column_names)


def _has_initial_schema_baseline(conn: sqlite3.Connection) -> bool:
    required_tables = [
        "documents",
        "chunks",
        "concepts",
        "concept_edges",
        "questions",
        "quiz_log",
        "srs_cards",
        "dialogue_sessions",
        "notes",
        "study_events",
        "app_settings",
        "goals",
        "claims",
        "concept_examples",
        "misconceptions",
        "evidence_references",
        "tutor_exchanges",
        "tutor_exchange_evidence",
        "sessions",
        "session_artifacts",
        "mastery_states",
        "review_events",
        "artifacts",
        "artifact_evidence",
        "artifact_exports",
        "flashcard_evidence",
        "quiz_evidence",
        "note_evidence",
        "stale_dependencies",
    ]
    if not _has_tables(conn, required_tables):
        return False
    return (
        _has_columns(
            conn,
            "documents",
            [
                "source_kind",
                "source_hash",
                "source_version",
                "parser_status",
                "parser_diagnostics",
                "duplicate_of",
                "extracted_at",
            ],
        )
        and _has_columns(
            conn,
            "chunks",
            ["chunk_hash", "source_version", "provenance_json", "embedding_status"],
        )
        and _has_columns(
            conn,
            "concepts",
            [
                "canonical_name",
                "concept_type",
                "source_count",
                "misconception_count",
                "open_question_count",
            ],
        )
        and _has_columns(conn, "notes", ["note_type", "goal_id", "session_id", "provenance_json"])
        and _has_columns(conn, "questions", ["artifact_id", "source_snapshot_hash", "confidence"])
        and _has_columns(conn, "srs_cards", ["artifact_id", "source_snapshot_hash", "confidence"])
    )


def _mark_legacy_baseline_if_needed(
    conn: sqlite3.Connection, migrations: list[MigrationFile]
) -> None:
    by_version = {migration.version: migration for migration in migrations}
    applied_versions = {
        int(row["version"])
        for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
        if row["version"] is not None
    }
    applied_names = {
        str(row["name"])
        for row in conn.execute("SELECT name FROM schema_migrations").fetchall()
        if row["name"]
    }

    checks = {
        1: _has_initial_schema_baseline(conn),
        2: _has_columns(conn, "documents", ["storage_name", "subject_name"]),
        3: _has_columns(conn, "documents", ["updated_at"]),
        4: _has_columns(conn, "concepts", ["doc_id"]),
        5: _has_columns(conn, "concept_edges", ["doc_id"]),
        12: _has_columns(conn, "calendar_feeds", ["keychain_ref"]),
        14: _has_columns(conn, "calendar_feeds", ["kind"]),
        # PR 5.1 (ADR 0002) — legacy databases that already have the
        # srs_cards.kind column should be marked as having applied 0017
        # rather than re-running ALTER TABLE (which would fail with
        # "duplicate column name").
        17: _has_columns(conn, "srs_cards", ["kind"]),
        # Same pattern for the two more recent ADD COLUMN migrations.
        # If the column is already present we mark them applied;
        # otherwise the normal migration loop runs them.
        19: _has_columns(conn, "srs_cards", ["doc_id"]),
        20: _has_columns(conn, "notes", ["folder_id"]) and table_exists(conn, "note_folders"),
    }

    for version, satisfied in checks.items():
        migration = by_version.get(version)
        if migration is None or version in applied_versions or not satisfied:
            continue
        _insert_migration_row(conn, migration)
        applied_versions.add(version)

    if applied_names & OBSOLETE_MIGRATION_NAMES:
        conn.executemany(
            "DELETE FROM schema_migrations WHERE name = ?",
            ((name,) for name in sorted(applied_names & OBSOLETE_MIGRATION_NAMES)),
        )
    conn.commit()


def apply_migrations(conn: sqlite3.Connection) -> None:
    migrations_dir = SCHEMA_PATH.parent / "migrations"
    if not migrations_dir.exists():
        return

    migrations = _list_migration_files(migrations_dir)
    sqlite_vec_loaded = _load_extensions(conn)
    _backfill_legacy_migration_rows(conn, migrations)
    _ensure_schema_migrations_table(conn)
    _mark_legacy_baseline_if_needed(conn, migrations)
    applied_versions = {
        int(row["version"])
        for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
    }

    for migration in migrations:
        if migration.version in applied_versions:
            continue
        if migration.version in VECTOR_MIGRATION_VERSIONS and not sqlite_vec_loaded:
            continue
        conn.executescript(migration.path.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
            (migration.version, migration.name),
        )
    conn.commit()


def initialize_database() -> None:
    from services.ingestion import ingest_document_record

    DATA_DIR.mkdir(exist_ok=True)
    UPLOAD_DIR.mkdir(exist_ok=True)
    with get_db() as conn:
        apply_migrations(conn)
        seed_demo_data(conn, ingest_document_record)


def seed_demo_data(conn: sqlite3.Connection, ingest_document_record) -> None:
    if os.getenv("CARREL_SEED_LEGACY_DEMO", "").lower() not in {"1", "true", "yes"}:
        return
    existing = conn.execute("SELECT COUNT(*) AS total FROM documents").fetchone()["total"]
    if existing:
        return

    sample_text = """
Cell division allows living organisms to grow, repair tissue, and reproduce.
Mitosis creates two genetically identical daughter cells and is used for growth and maintenance.
Meiosis creates haploid cells for sexual reproduction and increases variation through recombination.
Chromosomes package DNA so it can be copied and separated accurately during division.
Cell-cycle checkpoints pause progression if DNA is damaged or if spindle attachment is incomplete.
"""
    ingest_document_record(
        conn=conn,
        filename="seed-biology-notes.md",
        file_type="md",
        extracted_text=sample_text,
        page_count=None,
        subject_name="Biology",
    )
