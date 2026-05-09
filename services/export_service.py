"""Export service — export artifacts to Markdown, plain text, and JSON formats."""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from db import DATA_DIR


EXPORT_DIR = DATA_DIR / "exports"


def _ensure_export_dir() -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    return EXPORT_DIR


def _sanitize_filename(name: str) -> str:
    """Remove or replace characters unsafe for filenames."""
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name)
    return safe.strip()[:80] or "artifact"


def export_artifact(
    conn: sqlite3.Connection,
    artifact_id: str,
    export_format: str = "markdown",
) -> Dict[str, Any]:
    """Export an artifact to a file and record the export."""
    row = conn.execute(
        """
        SELECT id, artifact_kind, output_markdown, audience, depth, output_length, created_at
        FROM artifacts WHERE id = ?
        """,
        (artifact_id,),
    ).fetchone()
    if not row:
        raise ValueError(f"Artifact {artifact_id} not found")

    artifact = dict(row)
    markdown = artifact.get("output_markdown") or ""
    kind_label = (artifact.get("artifact_kind") or "artifact").replace("_", " ").title()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_kind = _sanitize_filename(kind_label)

    export_dir = _ensure_export_dir()
    export_id = str(uuid.uuid4())

    if export_format == "markdown" or export_format == "md":
        filename = f"{safe_kind}_{timestamp}.md"
        filepath = export_dir / filename
        filepath.write_text(markdown, encoding="utf-8")
    elif export_format == "text" or export_format == "txt":
        filename = f"{safe_kind}_{timestamp}.txt"
        filepath = export_dir / filename
        # Strip basic markdown syntax for plain text
        plain = markdown
        for prefix in ("# ", "## ", "### ", "**", "**", "*", "_", "> ", "---"):
            plain = plain.replace(prefix, "")
        filepath.write_text(plain, encoding="utf-8")
    elif export_format == "json":
        filename = f"{safe_kind}_{timestamp}.json"
        filepath = export_dir / filename
        export_data = {
            "artifact_id": artifact_id,
            "artifact_kind": artifact.get("artifact_kind"),
            "audience": artifact.get("audience"),
            "depth": artifact.get("depth"),
            "output_length": artifact.get("output_length"),
            "content": markdown,
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }
        filepath.write_text(json.dumps(export_data, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        raise ValueError(
            f"Unsupported export format: {export_format}. Use markdown, text, or json."
        )

    # Record export in artifact_exports
    conn.execute(
        """
        INSERT INTO artifact_exports (id, artifact_id, export_format, export_path, status)
        VALUES (?, ?, ?, ?, 'ready')
        """,
        (export_id, artifact_id, export_format, str(filepath)),
    )
    conn.commit()

    return {
        "export_id": export_id,
        "artifact_id": artifact_id,
        "export_format": export_format,
        "filename": filename,
        "path": str(filepath),
        "size_bytes": filepath.stat().st_size,
    }


def list_exports(
    conn: sqlite3.Connection, artifact_id: Optional[str] = None, limit: int = 20
) -> list:
    """List recent exports, optionally filtered by artifact."""
    if artifact_id:
        rows = conn.execute(
            """
            SELECT id, artifact_id, export_format, export_path, status, created_at
            FROM artifact_exports WHERE artifact_id = ?
            ORDER BY created_at DESC LIMIT ?
            """,
            (artifact_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, artifact_id, export_format, export_path, status, created_at
            FROM artifact_exports
            ORDER BY created_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def export_notes_bundle(
    conn: sqlite3.Connection,
    doc_id: Optional[str] = None,
    export_format: str = "markdown",
) -> Dict[str, Any]:
    """Export all notes (optionally filtered by doc) as a single file."""
    if doc_id:
        rows = conn.execute(
            "SELECT title, content, note_type, created_at FROM notes WHERE doc_id = ? ORDER BY created_at ASC",
            (doc_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT title, content, note_type, created_at FROM notes ORDER BY created_at ASC"
        ).fetchall()

    if not rows:
        return {"error": "No notes found to export."}

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    export_dir = _ensure_export_dir()

    if export_format in ("markdown", "md"):
        lines = ["# Study Notes\n"]
        for note in rows:
            lines.append(f"## {note['title'] or 'Untitled'}")
            lines.append(
                f"_Type: {(note['note_type'] or 'note').replace('_', ' ')} · {note['created_at']}_\n"
            )
            lines.append(note["content"] or "")
            lines.append("\n---\n")
        filename = f"Notes_Bundle_{timestamp}.md"
        filepath = export_dir / filename
        filepath.write_text("\n".join(lines), encoding="utf-8")
    elif export_format == "json":
        data = [dict(r) for r in rows]
        filename = f"Notes_Bundle_{timestamp}.json"
        filepath = export_dir / filename
        filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        raise ValueError(f"Unsupported format: {export_format}")

    return {
        "filename": filename,
        "path": str(filepath),
        "note_count": len(rows),
        "size_bytes": filepath.stat().st_size,
    }
