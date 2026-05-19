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

    foreign_keys=ON is per-connection. SQLite parses REFERENCES clauses
    either way, but it only enforces them when the pragma is enabled.
    Carrel relies on cascades for source deletion and SET NULL for
    durable job/calendar references, so every app connection must opt in.
    """
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
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
    columns = conn.execute(f"PRAGMA table_info({_quote_identifier(table_name)})").fetchall()
    return any(row["name"] == column_name for row in columns)


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


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


def _delete_missing_parent(
    conn: sqlite3.Connection,
    *,
    child_table: str,
    child_column: str,
    parent_table: str,
    parent_column: str = "id",
) -> int:
    if not (
        table_exists(conn, child_table)
        and table_exists(conn, parent_table)
        and column_exists(conn, child_table, child_column)
        and column_exists(conn, parent_table, parent_column)
    ):
        return 0
    child = _quote_identifier(child_table)
    parent = _quote_identifier(parent_table)
    child_col = _quote_identifier(child_column)
    parent_col = _quote_identifier(parent_column)
    cursor = conn.execute(
        f"""
        DELETE FROM {child}
        WHERE rowid IN (
            SELECT c.rowid
            FROM {child} AS c
            LEFT JOIN {parent} AS p ON p.{parent_col} = c.{child_col}
            WHERE c.{child_col} IS NOT NULL AND p.{parent_col} IS NULL
        )
        """
    )
    return int(cursor.rowcount if cursor.rowcount is not None else 0)


def _null_missing_parent(
    conn: sqlite3.Connection,
    *,
    child_table: str,
    child_column: str,
    parent_table: str,
    parent_column: str = "id",
) -> int:
    if not (
        table_exists(conn, child_table)
        and table_exists(conn, parent_table)
        and column_exists(conn, child_table, child_column)
        and column_exists(conn, parent_table, parent_column)
    ):
        return 0
    child = _quote_identifier(child_table)
    parent = _quote_identifier(parent_table)
    child_col = _quote_identifier(child_column)
    parent_col = _quote_identifier(parent_column)
    cursor = conn.execute(
        f"""
        UPDATE {child}
        SET {child_col} = NULL
        WHERE rowid IN (
            SELECT c.rowid
            FROM {child} AS c
            LEFT JOIN {parent} AS p ON p.{parent_col} = c.{child_col}
            WHERE c.{child_col} IS NOT NULL AND p.{parent_col} IS NULL
        )
        """
    )
    return int(cursor.rowcount if cursor.rowcount is not None else 0)


def _delete_orphan_vectors(
    conn: sqlite3.Connection,
    *,
    vector_table: str,
    vector_column: str,
    parent_table: str,
    parent_column: str,
) -> int:
    if not (
        table_exists(conn, vector_table)
        and table_exists(conn, parent_table)
        and column_exists(conn, vector_table, vector_column)
        and (parent_column.lower() == "rowid" or column_exists(conn, parent_table, parent_column))
    ):
        return 0
    vector = _quote_identifier(vector_table)
    parent = _quote_identifier(parent_table)
    vector_col = _quote_identifier(vector_column)
    parent_col = "rowid" if parent_column.lower() == "rowid" else _quote_identifier(parent_column)
    cursor = conn.execute(
        f"""
        DELETE FROM {vector}
        WHERE {vector_col} NOT IN (SELECT {parent_col} FROM {parent})
        """
    )
    return int(cursor.rowcount if cursor.rowcount is not None else 0)


def _rebuild_fts_index(conn: sqlite3.Connection, table_name: str) -> None:
    if table_exists(conn, table_name):
        quoted = _quote_identifier(table_name)
        conn.execute(f"INSERT INTO {quoted}({quoted}) VALUES('rebuild')")


def _delete_orphan_concept_subgraph(conn: sqlite3.Connection) -> dict[str, int]:
    if not _has_tables(conn, ["concepts", "documents"]):
        return {}
    concept_ids = [
        row["id"]
        for row in conn.execute(
            """
            SELECT c.id
            FROM concepts AS c
            LEFT JOIN documents AS d ON d.id = c.doc_id
            WHERE c.doc_id IS NOT NULL AND d.id IS NULL
            """
        ).fetchall()
    ]
    if not concept_ids:
        return {}

    counts: dict[str, int] = {}
    placeholders = ",".join("?" * len(concept_ids))

    def add(key: str, cursor: sqlite3.Cursor) -> None:
        count = int(cursor.rowcount if cursor.rowcount is not None else 0)
        if count:
            counts[key] = counts.get(key, 0) + count

    if table_exists(conn, "questions"):
        question_ids = [
            row["id"]
            for row in conn.execute(
                f"SELECT id FROM questions WHERE concept_id IN ({placeholders})",
                concept_ids,
            ).fetchall()
        ]
        if question_ids:
            question_placeholders = ",".join("?" * len(question_ids))
            if table_exists(conn, "quiz_log"):
                add(
                    "quiz_log",
                    conn.execute(
                        f"DELETE FROM quiz_log WHERE question_id IN ({question_placeholders})",
                        question_ids,
                    ),
                )
            if table_exists(conn, "quiz_evidence"):
                add(
                    "quiz_evidence",
                    conn.execute(
                        f"DELETE FROM quiz_evidence WHERE question_id IN ({question_placeholders})",
                        question_ids,
                    ),
                )
            if table_exists(conn, "review_events"):
                add(
                    "review_events",
                    conn.execute(
                        f"UPDATE review_events SET question_id = NULL WHERE question_id IN ({question_placeholders})",
                        question_ids,
                    ),
                )
        add(
            "questions",
            conn.execute(
                f"DELETE FROM questions WHERE concept_id IN ({placeholders})", concept_ids
            ),
        )

    if table_exists(conn, "srs_cards"):
        card_ids = [
            row["id"]
            for row in conn.execute(
                f"SELECT id FROM srs_cards WHERE concept_id IN ({placeholders})",
                concept_ids,
            ).fetchall()
        ]
        if card_ids:
            card_placeholders = ",".join("?" * len(card_ids))
            if table_exists(conn, "flashcard_evidence"):
                add(
                    "flashcard_evidence",
                    conn.execute(
                        f"DELETE FROM flashcard_evidence WHERE card_id IN ({card_placeholders})",
                        card_ids,
                    ),
                )
            if table_exists(conn, "card_pairs"):
                add(
                    "card_pairs",
                    conn.execute(
                        f"DELETE FROM card_pairs WHERE card_a_id IN ({card_placeholders}) OR card_b_id IN ({card_placeholders})",
                        card_ids * 2,
                    ),
                )
            if table_exists(conn, "review_events"):
                add(
                    "review_events",
                    conn.execute(
                        f"UPDATE review_events SET card_id = NULL WHERE card_id IN ({card_placeholders})",
                        card_ids,
                    ),
                )
        add(
            "srs_cards",
            conn.execute(
                f"DELETE FROM srs_cards WHERE concept_id IN ({placeholders})", concept_ids
            ),
        )

    if table_exists(conn, "notes"):
        note_ids = [
            row["id"]
            for row in conn.execute(
                f"SELECT id FROM notes WHERE concept_id IN ({placeholders})",
                concept_ids,
            ).fetchall()
        ]
        if note_ids and table_exists(conn, "note_evidence"):
            note_placeholders = ",".join("?" * len(note_ids))
            add(
                "note_evidence",
                conn.execute(
                    f"DELETE FROM note_evidence WHERE note_id IN ({note_placeholders})",
                    note_ids,
                ),
            )
        add(
            "notes",
            conn.execute(f"DELETE FROM notes WHERE concept_id IN ({placeholders})", concept_ids),
        )

    if table_exists(conn, "evidence_references"):
        evidence_ids = [
            row["id"]
            for row in conn.execute(
                f"SELECT id FROM evidence_references WHERE concept_id IN ({placeholders})",
                concept_ids,
            ).fetchall()
        ]
        if evidence_ids:
            evidence_placeholders = ",".join("?" * len(evidence_ids))
            for table in (
                "artifact_evidence",
                "flashcard_evidence",
                "note_evidence",
                "quiz_evidence",
                "tutor_exchange_evidence",
            ):
                if table_exists(conn, table):
                    add(
                        table,
                        conn.execute(
                            f"DELETE FROM {table} WHERE evidence_reference_id IN ({evidence_placeholders})",
                            evidence_ids,
                        ),
                    )
            add(
                "evidence_references",
                conn.execute(
                    f"DELETE FROM evidence_references WHERE id IN ({evidence_placeholders})",
                    evidence_ids,
                ),
            )

    for table in (
        "claims",
        "concept_examples",
        "misconceptions",
        "dialogue_sessions",
        "study_events",
    ):
        if table_exists(conn, table):
            add(
                table,
                conn.execute(
                    f"DELETE FROM {table} WHERE concept_id IN ({placeholders})", concept_ids
                ),
            )

    if table_exists(conn, "mastery_states"):
        mastery_ids = [
            row["id"]
            for row in conn.execute(
                f"SELECT id FROM mastery_states WHERE concept_id IN ({placeholders})",
                concept_ids,
            ).fetchall()
        ]
        if mastery_ids:
            mastery_placeholders = ",".join("?" * len(mastery_ids))
            if table_exists(conn, "review_events"):
                add(
                    "review_events",
                    conn.execute(
                        f"UPDATE review_events SET mastery_state_id = NULL WHERE mastery_state_id IN ({mastery_placeholders})",
                        mastery_ids,
                    ),
                )
            add(
                "mastery_states",
                conn.execute(
                    f"DELETE FROM mastery_states WHERE id IN ({mastery_placeholders})",
                    mastery_ids,
                ),
            )

    if table_exists(conn, "concept_edges"):
        add(
            "concept_edges",
            conn.execute(
                f"DELETE FROM concept_edges WHERE source_id IN ({placeholders}) OR target_id IN ({placeholders})",
                concept_ids * 2,
            ),
        )
    add("concepts", conn.execute(f"DELETE FROM concepts WHERE id IN ({placeholders})", concept_ids))
    return counts


def repair_foreign_key_orphans(conn: sqlite3.Connection) -> dict[str, int]:
    """Repair pre-FK-enforcement orphans before normal app writes run.

    This is intentionally idempotent and code-driven rather than a pure SQL
    migration because sqlite-vec virtual tables are optional at runtime. A
    static migration that references `chunks_vec` or `node_embeddings` fails
    on machines where sqlite-vec is unavailable, exactly where startup should
    stay graceful.
    """

    if conn.in_transaction:
        conn.commit()

    conn.execute("PRAGMA foreign_keys = OFF")
    counts: dict[str, int] = {}

    def add(key: str, count: int) -> None:
        if count:
            counts[key] = counts.get(key, 0) + count

    try:
        # Source-owned rows must not survive after their document disappears.
        for key, count in _delete_orphan_concept_subgraph(conn).items():
            add(key, count)
        add(
            "node_embeddings",
            _delete_orphan_vectors(
                conn,
                vector_table="node_embeddings",
                vector_column="node_id",
                parent_table="nodes",
                parent_column="id",
            ),
        )
        add(
            "nodes",
            _delete_missing_parent(
                conn,
                child_table="nodes",
                child_column="doc_id",
                parent_table="documents",
            ),
        )
        add(
            "node_embeddings",
            _delete_orphan_vectors(
                conn,
                vector_table="node_embeddings",
                vector_column="node_id",
                parent_table="nodes",
                parent_column="id",
            ),
        )
        add(
            "chunks_vec",
            _delete_orphan_vectors(
                conn,
                vector_table="chunks_vec",
                vector_column="chunk_id",
                parent_table="chunks",
                parent_column="rowid",
            ),
        )
        add(
            "chunks",
            _delete_missing_parent(
                conn,
                child_table="chunks",
                child_column="doc_id",
                parent_table="documents",
            ),
        )
        add(
            "chunks_vec",
            _delete_orphan_vectors(
                conn,
                vector_table="chunks_vec",
                vector_column="chunk_id",
                parent_table="chunks",
                parent_column="rowid",
            ),
        )
        for table in ("notes", "study_events", "anchors", "stale_dependencies"):
            column = (
                "document_id"
                if table == "anchors"
                else "source_id"
                if table == "stale_dependencies"
                else "doc_id"
            )
            add(
                table,
                _delete_missing_parent(
                    conn,
                    child_table=table,
                    child_column=column,
                    parent_table="documents",
                ),
            )
        add(
            "evidence_references",
            _delete_missing_parent(
                conn,
                child_table="evidence_references",
                child_column="source_id",
                parent_table="documents",
            ),
        )
        add(
            "srs_cards",
            _delete_missing_parent(
                conn,
                child_table="srs_cards",
                child_column="doc_id",
                parent_table="documents",
            ),
        )

        # Nullable back-references should be cleared, not used as a reason to
        # delete otherwise user-authored state.
        for table, column, parent in (
            ("documents", "duplicate_of", "documents"),
            ("ingestion_jobs", "document_id", "documents"),
            ("study_suggestions", "doc_id", "documents"),
            ("study_suggestions", "source_event_id", "calendar_events"),
            ("anchors", "chunk_id", "chunks"),
            ("anchors", "srs_card_id", "srs_cards"),
            ("claims", "source_chunk_id", "chunks"),
            ("concept_examples", "source_chunk_id", "chunks"),
            ("misconceptions", "source_chunk_id", "chunks"),
            ("evidence_references", "chunk_id", "chunks"),
            ("notes", "folder_id", "note_folders"),
            ("review_events", "mastery_state_id", "mastery_states"),
            ("review_events", "card_id", "srs_cards"),
            ("review_events", "question_id", "questions"),
            ("artifacts", "parent_artifact_id", "artifacts"),
            ("artifacts", "goal_id", "goals"),
            ("artifacts", "session_id", "sessions"),
            ("artifact_exports", "artifact_id", "artifacts"),
        ):
            add(
                table,
                _null_missing_parent(
                    conn, child_table=table, child_column=column, parent_table=parent
                ),
            )

        # Generic final sweep for any FK we missed. Nullable columns are nulled;
        # required child rows are removed.
        for _ in range(8):
            violations = conn.execute("PRAGMA foreign_key_check").fetchall()
            if not violations:
                break
            changed = 0
            for violation in violations:
                table = str(violation[0])
                rowid = violation[1]
                fk_id = int(violation[3])
                fk_rows = [
                    row
                    for row in conn.execute(
                        f"PRAGMA foreign_key_list({_quote_identifier(table)})"
                    ).fetchall()
                    if int(row["id"]) == fk_id
                ]
                if rowid is None or not fk_rows:
                    continue
                child_column = str(fk_rows[0]["from"])
                table_info = {
                    row["name"]: row
                    for row in conn.execute(
                        f"PRAGMA table_info({_quote_identifier(table)})"
                    ).fetchall()
                }
                child_meta = table_info.get(child_column)
                nullable = child_meta is not None and not bool(child_meta["notnull"])
                action = str(fk_rows[0]["on_delete"] or "").upper()
                quoted_table = _quote_identifier(table)
                quoted_column = _quote_identifier(child_column)
                if nullable or action == "SET NULL":
                    cursor = conn.execute(
                        f"UPDATE {quoted_table} SET {quoted_column} = NULL WHERE rowid = ?",
                        (rowid,),
                    )
                else:
                    cursor = conn.execute(f"DELETE FROM {quoted_table} WHERE rowid = ?", (rowid,))
                changed += int(cursor.rowcount if cursor.rowcount is not None else 0)
            if not changed:
                break
            add("foreign_key_check", changed)

        remaining_violations = len(conn.execute("PRAGMA foreign_key_check").fetchall())
        add("foreign_key_unresolved", remaining_violations)
        _rebuild_fts_index(conn, "chunks_fts")
        _rebuild_fts_index(conn, "node_fts")
        conn.commit()
    except Exception:
        conn.rollback()
        conn.execute("PRAGMA foreign_keys = ON")
        raise
    conn.execute("PRAGMA foreign_keys = ON")

    if counts:
        log_event(LOGGER, logging.WARNING, "foreign_key_orphans_repaired", **counts)
    return counts


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
        # Notes Phase A ADD COLUMN migrations. Renumbered from 0019/0020
        # to 0022/0023 mid-development to clear a version collision with
        # the coach feature's session-check-ins + study-suggestions
        # migrations on main. If the column / table is already present
        # we mark these applied so a re-apply doesn't ALTER twice.
        22: _has_columns(conn, "srs_cards", ["doc_id"]),
        23: _has_columns(conn, "notes", ["folder_id"]) and table_exists(conn, "note_folders"),
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
    repair_foreign_key_orphans(conn)


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
