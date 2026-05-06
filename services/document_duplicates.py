"""Source-hash based duplicate detection for the documents table.

A document is "duplicate" if another row shares its `source_hash`.
For uploads, that hash is the SHA-256 of the file bytes (truncated to
32 hex chars); for manually-pasted text it's a hash of the
`clean_learning_text` form, so two pastes that only differ in
whitespace match.

Lifted from `services.documents` (which had grown to 831 LoC mixing
duplicate detection, concept-label cleanup, subject grouping, and
document CRUD into one file). The public surface is re-exported from
`services/documents.py` so existing callers — `routes/documents.py`,
`services/jobs.py`, and tests — keep working unchanged.

The one cross-module call is `delete_document_record`, which lives in
`services.documents`. Rather than introduce a circular import we
accept it as a parameter on `cleanup_duplicate_documents`, defaulting
to the canonical implementation. Tests can pass a stub.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Callable, Dict, List, Optional

from services import stale_tracker
from services.extraction_pipeline import IngestedAsset
from services.ingestion.text_utils import clean_learning_text


def compute_document_source_hash(
    *,
    asset: Optional[IngestedAsset] = None,
    raw_text: Optional[str] = None,
) -> str:
    """Compute the `documents.source_hash` value for an upload.

    Matches the derivation used by `services.ingestion.orchestrator.ingest_document_record`
    so a pre-write duplicate check sees the same value the orchestrator would
    store. Truncated to 32 hex chars (128 bits) — the column convention.

    - File uploads: pass the extraction `asset`. Its `content_hash` is a
      SHA-256 of the raw file bytes, so re-exports with different metadata
      still hash the same as the original.
    - Manual text: pass `raw_text`. We hash the cleaned learning text, which
      normalises whitespace + de-boilerplates. Two pastes that only differ
      in trailing whitespace therefore match.
    """
    if asset is not None and getattr(asset, "content_hash", None):
        return str(asset.content_hash)[:32]
    text_for_hash = clean_learning_text(raw_text or "")
    return stale_tracker.compute_source_hash(text_for_hash)[:32]


def find_duplicate_groups(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Find every cluster of documents that share a source_hash.

    Returns one entry per cluster with 2+ members. Each entry exposes:

      source_hash    — the shared hash
      canonical      — the survivor (oldest upload_date, rowid tiebreak)
      duplicates     — every other row in the cluster, oldest-first
      total_cards    — SRS cards bound to the duplicate-only docs (what a
                       cleanup would delete from the review queue). Useful
                       so the UI can warn "this will remove 47 flashcards."

    Canonical choice: oldest. Rationale — earliest upload is what the user's
    existing citation flights, annotations, and session history probably
    reference. Newer dupes tend to be accidental re-drops.

    Rows with NULL source_hash are ignored (pre-hashing legacy rows). An
    empty DB returns []; a DB with no duplicates returns [].
    """
    rows = conn.execute(
        """
        SELECT source_hash, COUNT(*) AS cnt
        FROM documents
        WHERE source_hash IS NOT NULL AND source_hash <> ''
        GROUP BY source_hash
        HAVING COUNT(*) > 1
        ORDER BY cnt DESC
        """
    ).fetchall()

    groups: List[Dict[str, Any]] = []
    for row in rows:
        source_hash = row["source_hash"]
        members = [
            dict(member)
            for member in conn.execute(
                """
                SELECT id, filename, subject_name, file_type, upload_date,
                       page_count, status, duplicate_of
                FROM documents
                WHERE source_hash = ?
                ORDER BY
                    CASE WHEN upload_date IS NULL THEN 1 ELSE 0 END,
                    upload_date ASC,
                    rowid ASC
                """,
                (source_hash,),
            ).fetchall()
        ]
        if len(members) < 2:
            continue
        canonical = members[0]
        duplicates = members[1:]
        duplicate_ids = [d["id"] for d in duplicates]
        if duplicate_ids:
            placeholders = ",".join("?" * len(duplicate_ids))
            card_row = conn.execute(
                f"""
                SELECT COUNT(*) AS n
                FROM srs_cards s
                JOIN concepts c ON s.concept_id = c.id
                WHERE c.doc_id IN ({placeholders})
                """,
                duplicate_ids,
            ).fetchone()
            total_cards = int(card_row["n"] if card_row else 0)
        else:
            total_cards = 0
        groups.append(
            {
                "source_hash": source_hash,
                "canonical": canonical,
                "duplicates": duplicates,
                "total_cards": total_cards,
            }
        )
    return groups


def cleanup_duplicate_documents(
    conn: sqlite3.Connection,
    *,
    dry_run: bool = False,
    deleter: Optional[Callable[[sqlite3.Connection, str], bool]] = None,
) -> Dict[str, Any]:
    """Delete every non-canonical row in every duplicate cluster.

    Returns a structured summary so the caller can render "N deleted across
    M groups; kept K canonicals." On `dry_run=True` the function computes
    the same plan but does not mutate the DB — useful for a preview endpoint
    or test assertions.

    `deleter` defaults to `services.documents.delete_document_record`. It's
    parameterized so this module doesn't have to circularly import documents
    and tests can pass a stub. The deleter must cascade through concepts,
    srs_cards, notes, chunks, and chunk vectors — same semantics as a
    manual "Delete document" click.

    Safety notes:
      - Commits per row (via deleter's internal commit). If one delete
        fails midway, the prior successful deletes stay — the summary
        records `deleted` accurately.
      - After cleanup, any remaining row that pointed at a now-deleted
        canonical (via `duplicate_of`) would be orphaned, but because we
        only delete the NON-canonical members and canonicals stay, this
        cannot happen. Still, we null out dangling `duplicate_of` for the
        canonicals we keep (they might reference each other by accident if
        the history is tangled).
    """
    if deleter is None:
        # Late binding to avoid circular import at module load time;
        # documents.py imports this module to re-export the public API.
        from services.documents import delete_document_record as deleter  # noqa: PLC0415

    groups = find_duplicate_groups(conn)
    plan: List[Dict[str, Any]] = []
    for group in groups:
        plan.append(
            {
                "source_hash": group["source_hash"],
                "kept": group["canonical"]["id"],
                "kept_filename": group["canonical"]["filename"],
                "removed": [d["id"] for d in group["duplicates"]],
                "removed_filenames": [d["filename"] for d in group["duplicates"]],
                "cards_removed": group["total_cards"],
            }
        )

    if dry_run:
        return {
            "dry_run": True,
            "groups": len(groups),
            "would_delete": sum(len(p["removed"]) for p in plan),
            "would_remove_cards": sum(p["cards_removed"] for p in plan),
            "plan": plan,
        }

    deleted_total = 0
    cards_removed_total = 0
    for group, summary in zip(groups, plan):
        for duplicate in group["duplicates"]:
            if deleter(conn, duplicate["id"]):
                deleted_total += 1
        cards_removed_total += summary["cards_removed"]
        # Clear any lingering duplicate_of on the canonical so the UI's
        # "duplicates" indicator goes away immediately, even if a race
        # left it pointed at a now-dead row.
        conn.execute(
            "UPDATE documents SET duplicate_of = NULL WHERE id = ?",
            (group["canonical"]["id"],),
        )
    conn.commit()
    return {
        "dry_run": False,
        "groups": len(groups),
        "deleted": deleted_total,
        "cards_removed": cards_removed_total,
        "plan": plan,
    }


def find_canonical_duplicate(
    conn: sqlite3.Connection,
    source_hash: str,
) -> Optional[Dict[str, Any]]:
    """Return the existing canonical document for `source_hash`, if one exists.

    "Canonical" means `duplicate_of IS NULL` — a previously-rejected duplicate
    upload doesn't count as an obstacle to re-uploading after the user has
    deleted the original. We also skip rows whose status marks them as
    aborted (`'deleted'`) so transient failures never block a legitimate
    re-ingest.
    """
    if not source_hash:
        return None
    row = conn.execute(
        """
        SELECT id, filename, subject_name, file_type, upload_date, page_count,
               status
        FROM documents
        WHERE source_hash = ?
          AND duplicate_of IS NULL
          AND COALESCE(status, '') <> 'deleted'
        ORDER BY upload_date ASC
        LIMIT 1
        """,
        (source_hash,),
    ).fetchone()
    return dict(row) if row else None
