"""Persistence for saved briefs — the Shelf.

A brief is one checked draft the lawyer chose to keep: the draft text,
its SHA-256 fingerprint, the full verify response, the client-built
certification model, and a seal state. The Shelf (Cachet's warm home)
lists them most-recent-first; opening one re-hydrates the verify view
from the stored response without a re-verify.

Storage shape (migration 0024_briefs.sql):

    briefs(id, title, draft, fingerprint, response_json, cert_json,
           seal_state, created_at, updated_at)

`response_json` and `cert_json` are TEXT JSON blobs. They are heavy, so
the list path (`list_briefs`) selects summary columns only and never
deserializes a blob; only `get_brief` loads the full record for
re-hydration.

Seal state: only ``unsealed`` and ``sealed`` are ever written.
``cracked`` is *derived* at render time (the stored fingerprint no
longer matches the live draft) and is never persisted, so a client that
POSTs ``cracked`` (or anything unrecognized) is coerced to ``unsealed``.

Deleting a brief is the user removing their own saved row through an app
affordance — ordinary app behavior, a hard delete of a single
user-owned record. It is not the privileged "permanently delete data"
class (no trash, no cross-user blast radius). Returns False on a missing
id so the route can map a clean 404.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

# Shelf card titles cap at 120 chars; mirrors BriefSaveRequest.title max_length.
_TITLE_MAX_LEN = 120

# Only these reach the column. "cracked" is render-derived, never stored.
_PERSISTED_SEAL_STATES = {"unsealed", "sealed"}

# Summary columns: everything the Shelf list needs, none of the blobs.
_SUMMARY_KEYS = ("id", "title", "fingerprint", "seal_state", "created_at", "updated_at")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _derive_title(draft: str) -> str:
    """First non-empty line of the draft, trimmed. The matter caption is
    not in the verify payload, so the draft's opening line is the best
    available human-readable identity for the Shelf card."""

    for line in (draft or "").splitlines():
        clean = line.strip()
        if clean:
            return clean[:_TITLE_MAX_LEN]
    return "Untitled brief"


def _coerce_seal_state(seal_state: Optional[str]) -> str:
    return seal_state if seal_state in _PERSISTED_SEAL_STATES else "unsealed"


def _integrity_seal_state(seal_state: str, draft: str, fingerprint: str) -> str:
    """SM-V8: re-verify a sealed brief at read time. Recompute the draft's
    SHA-256 (the same content fingerprint the client sealed under) and compare
    to the stored fingerprint. A mismatch means the stored draft no longer
    matches what was sealed (tampering, corruption, migration drift), so the
    seal is surfaced as 'cracked'. The Shelf is then a live ledger of what still
    holds, not a museum of a stored flag. Only a sealed brief can crack; the
    state is derived per read and never persisted."""
    if seal_state != "sealed":
        return seal_state
    actual = hashlib.sha256((draft or "").encode("utf-8")).hexdigest()
    return "sealed" if actual == fingerprint else "cracked"


def _row_to_summary(row: sqlite3.Row) -> Dict[str, Any]:
    """Map a row selected with the summary columns. No blobs touched."""

    return {
        "id": row["id"],
        "title": row["title"],
        "fingerprint": row["fingerprint"],
        "seal_state": row["seal_state"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_detail(row: sqlite3.Row) -> Dict[str, Any]:
    """Map a full row, deserializing the JSON blobs for re-hydration.

    `response_json` is NOT NULL so it always parses; `cert_json` is
    nullable and stays None when the brief was saved without a cert.
    """

    cert_raw = row["cert_json"]
    return {
        "id": row["id"],
        "title": row["title"],
        "fingerprint": row["fingerprint"],
        "seal_state": row["seal_state"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "draft": row["draft"],
        "response": json.loads(row["response_json"]),
        "cert": json.loads(cert_raw) if cert_raw is not None else None,
    }


def list_briefs(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Every saved brief as a summary, most-recent-first.

    Reads the summary columns plus the (bounded) draft text so each sealed
    brief's integrity can be re-verified per read (SM-V8): a sealed brief whose
    stored draft no longer hashes to its sealed fingerprint is surfaced as
    'cracked'. The heavy JSON blobs (response, cert) are still never read, so
    the list stays light no matter how large individual responses are, and the
    returned summary still carries no blobs (draft included).
    """

    rows = conn.execute(
        """
        SELECT id, title, draft, fingerprint, seal_state, created_at, updated_at
        FROM briefs
        ORDER BY created_at DESC, rowid DESC
        """
    ).fetchall()
    summaries: List[Dict[str, Any]] = []
    for row in rows:
        summary = _row_to_summary(row)
        summary["seal_state"] = _integrity_seal_state(
            row["seal_state"], row["draft"], row["fingerprint"]
        )
        summaries.append(summary)
    return summaries


def get_brief(conn: sqlite3.Connection, brief_id: str) -> Optional[Dict[str, Any]]:
    """Full brief for re-hydration, or None if the id is unknown."""

    row = conn.execute(
        """
        SELECT id, title, draft, fingerprint, response_json, cert_json,
               seal_state, created_at, updated_at
        FROM briefs
        WHERE id = ?
        """,
        (brief_id,),
    ).fetchone()
    return _row_to_detail(row) if row else None


def save_brief(
    conn: sqlite3.Connection,
    *,
    draft: str,
    fingerprint: str,
    response: Dict[str, Any],
    cert: Optional[Dict[str, Any]] = None,
    seal_state: str = "unsealed",
    title: Optional[str] = None,
) -> Dict[str, Any]:
    """Persist one checked draft and return its summary.

    The full response/cert the client just POSTed are stored but not
    echoed back — the client already holds them. The save response
    confirms identity (id, title) and timestamps only, keeping the wire
    lean.
    """

    clean_draft = draft or ""
    if not clean_draft.strip():
        raise HTTPException(status_code=400, detail="Cannot save an empty draft.")

    clean_title = (title or "").strip() or _derive_title(clean_draft)
    state = _coerce_seal_state(seal_state)
    response_blob = json.dumps(response)
    cert_blob = json.dumps(cert) if cert is not None else None

    # Fingerprint upsert: a brief is one row per draft fingerprint, and its
    # seal_state evolves in place (saved unsealed, then re-saved sealed once
    # the human seals it). Saving the same draft again must update that one
    # row, not litter the Shelf with duplicate cards. There is no UNIQUE
    # constraint on fingerprint, so we look up the most-recent matching row
    # and branch: UPDATE it (last write wins, id + created_at preserved) when
    # found, INSERT a fresh row otherwise. Different fingerprint => new row.
    existing = conn.execute(
        "SELECT id FROM briefs WHERE fingerprint = ? ORDER BY created_at DESC, rowid DESC LIMIT 1",
        (fingerprint,),
    ).fetchone()

    now = _now_iso()
    if existing is not None:
        brief_id = existing["id"]
        conn.execute(
            """
            UPDATE briefs
            SET title = ?, draft = ?, response_json = ?, cert_json = ?,
                seal_state = ?, updated_at = ?
            WHERE id = ?
            """,
            (clean_title, clean_draft, response_blob, cert_blob, state, now, brief_id),
        )
    else:
        brief_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO briefs (
                id, title, draft, fingerprint, response_json, cert_json,
                seal_state, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                brief_id,
                clean_title,
                clean_draft,
                fingerprint,
                response_blob,
                cert_blob,
                state,
                now,
                now,
            ),
        )
    conn.commit()

    row = conn.execute(
        """
        SELECT id, title, fingerprint, seal_state, created_at, updated_at
        FROM briefs
        WHERE id = ?
        """,
        (brief_id,),
    ).fetchone()
    if row is None:
        # SELECT-after-INSERT should always succeed: we just committed.
        # If it does not, a 500 is the honest shape.
        raise HTTPException(status_code=500, detail="Brief saved but could not be read back.")
    return _row_to_summary(row)


def delete_brief(conn: sqlite3.Connection, brief_id: str) -> bool:
    """Hard-delete one brief the user owns. True if a row went; False if
    the id was unknown (the route maps that to 404)."""

    cur = conn.execute("SELECT id FROM briefs WHERE id = ?", (brief_id,))
    if cur.fetchone() is None:
        return False
    conn.execute("DELETE FROM briefs WHERE id = ?", (brief_id,))
    conn.commit()
    return True
