"""Stale dependency tracker — detect when source material changes and mark dependents as stale."""
import hashlib
import sqlite3
import uuid
from typing import Any, Dict, List, Optional


def compute_source_hash(content: str) -> str:
    """Compute a stable hash for source content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:32]


def register_dependency(
    conn: sqlite3.Connection,
    *,
    source_id: str,
    dependent_kind: str,
    dependent_id: str,
    snapshot_hash: str,
) -> None:
    """Register a dependency between a source document and a derived entity."""
    dep_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT OR REPLACE INTO stale_dependencies (id, source_id, dependent_kind, dependent_id, source_snapshot_hash, status)
        VALUES (?, ?, ?, ?, ?, 'fresh')
        """,
        (dep_id, source_id, dependent_kind, dependent_id, snapshot_hash),
    )


def check_stale(conn: sqlite3.Connection, source_id: str) -> List[Dict[str, Any]]:
    """Check if any dependents of this source are stale (snapshot hash mismatch)."""
    doc_row = conn.execute(
        "SELECT COALESCE(source_hash, id) AS current_hash FROM documents WHERE id = ?",
        (source_id,),
    ).fetchone()
    if not doc_row:
        return []

    current_hash = doc_row["current_hash"]
    rows = conn.execute(
        """
        SELECT id, dependent_kind, dependent_id, source_snapshot_hash, status
        FROM stale_dependencies
        WHERE source_id = ? AND source_snapshot_hash != ? AND status = 'fresh'
        """,
        (source_id, current_hash),
    ).fetchall()

    stale_items = []
    for row in rows:
        stale_items.append(dict(row))
        # Mark as stale
        conn.execute(
            "UPDATE stale_dependencies SET status = 'stale', current_snapshot_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (current_hash, row["id"]),
        )
    return stale_items


def mark_artifacts_stale(conn: sqlite3.Connection, source_id: str) -> int:
    """Mark all artifacts that depend on this source as stale."""
    current_row = conn.execute(
        "SELECT COALESCE(source_hash, id) AS h FROM documents WHERE id = ?",
        (source_id,),
    ).fetchone()
    if not current_row:
        return 0

    # Find artifacts whose source_snapshot_hash doesn't match
    rows = conn.execute(
        """
        SELECT id, source_snapshot_hash
        FROM artifacts
        WHERE source_scope LIKE ? AND stale = 0
        """,
        (f'%{source_id}%',),
    ).fetchall()

    count = 0
    for row in rows:
        conn.execute("UPDATE artifacts SET stale = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (row["id"],))
        count += 1

    return count


def get_stale_warnings(conn: sqlite3.Connection, limit: int = 10) -> List[Dict[str, Any]]:
    """Get active stale dependency warnings for UI display."""
    rows = conn.execute(
        """
        SELECT sd.id, sd.source_id, sd.dependent_kind, sd.dependent_id,
               sd.source_snapshot_hash, sd.current_snapshot_hash,
               d.filename AS source_name
        FROM stale_dependencies sd
        LEFT JOIN documents d ON d.id = sd.source_id
        WHERE sd.status = 'stale'
        ORDER BY sd.updated_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_stale_artifacts(conn: sqlite3.Connection, limit: int = 10) -> List[Dict[str, Any]]:
    """Get all stale artifacts for display."""
    rows = conn.execute(
        """
        SELECT id, artifact_kind, source_scope, source_snapshot_hash, updated_at
        FROM artifacts
        WHERE stale = 1
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def update_source_hash(conn: sqlite3.Connection, source_id: str, new_hash: str) -> int:
    """Update source hash and check for stale dependents. Returns count of newly stale items."""
    conn.execute(
        "UPDATE documents SET source_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (new_hash, source_id),
    )
    stale = check_stale(conn, source_id)
    stale_artifact_count = mark_artifacts_stale(conn, source_id)
    return len(stale) + stale_artifact_count
