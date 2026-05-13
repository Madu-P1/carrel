import json
import re
import sqlite3
import uuid
from datetime import date
from typing import Any, Dict, List, Optional

from services.documents import clean_concept_label


# PR 5.1 (ADR 0002) — cloze marker `{{cN::term}}`. Matches single-occlusion
# Anki-style cloze; the three-segment form `{{cN::term::hint}}` is out of
# scope for PR 5.1 per the plan and ADR.
_CLOZE_MARKER_RE = re.compile(r"\{\{c\d+::([^}]+)\}\}")


def _strip_cloze_markers(text: str) -> str:
    """Return `text` with `{{cN::term}}` markers replaced by `term`.

    Used by the search projection in `list_cards` so a user searching for
    a concept doesn't get cloze noise (literal `c1` matching the marker
    token) nor false positives on hidden terms (the marker syntax
    obscures the inner word from a plain LIKE).
    """
    if not text:
        return ""
    return _CLOZE_MARKER_RE.sub(lambda m: m.group(1), str(text))


def _name_replacements(conn: sqlite3.Connection) -> List[tuple[str, str]]:
    rows = conn.execute(
        "SELECT name FROM concepts ORDER BY LENGTH(name) DESC, rowid ASC"
    ).fetchall()
    pairs = []
    seen = set()
    for row in rows:
        raw_name = str(row["name"] or "").strip()
        if not raw_name or raw_name in seen:
            continue
        seen.add(raw_name)
        cleaned = clean_concept_label(raw_name)
        if cleaned and cleaned != raw_name:
            pairs.append((raw_name, cleaned))
    return pairs


def _normalize_card_text(text: str, replacements: List[tuple[str, str]]) -> str:
    """Apply concept-name cleanups to card text without corrupting cloze
    markers.

    PR 5.1 (ADR 0002) — naive `value.replace(raw_name, cleaned)` would
    rewrite a concept literally named "c1" (financial coupon labels,
    chemistry compound identifiers, etc.) inside a `{{c1::...}}` cloze
    marker, breaking the render. We split the text on marker boundaries,
    rewrite only the prose segments, and stitch the markers back in
    unchanged.
    """
    value = str(text or "")
    if not value:
        return value
    parts: List[str] = []
    last_end = 0
    for match in _CLOZE_MARKER_RE.finditer(value):
        prose = value[last_end : match.start()]
        for raw_name, cleaned in replacements:
            prose = prose.replace(raw_name, cleaned)
        parts.append(prose)
        parts.append(match.group(0))
        last_end = match.end()
    tail = value[last_end:]
    for raw_name, cleaned in replacements:
        tail = tail.replace(raw_name, cleaned)
    parts.append(tail)
    return "".join(parts)


def fetch_questions(conn: sqlite3.Connection, limit: int = 10) -> List[Dict[str, object]]:
    rows = conn.execute(
        """
        SELECT q.id, q.question, q.answer, q.explanation, q.distractors, q.difficulty,
               c.name AS concept, d.filename AS document_name, d.subject_name
        FROM questions q
        JOIN concepts c ON q.concept_id = c.id
        JOIN documents d ON c.doc_id = d.id
        ORDER BY q.rowid DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    items = []
    replacements = _name_replacements(conn)
    for row in rows:
        item = dict(row)
        item["difficulty"] = (
            "Hard"
            if item["difficulty"] >= 0.7
            else "Medium"
            if item["difficulty"] >= 0.45
            else "Easy"
        )
        item["options"] = [item["answer"], *json.loads(item["distractors"] or "[]")]
        item["raw_concept"] = item["concept"]
        item["concept"] = clean_concept_label(item["concept"])
        item["question"] = _normalize_card_text(item["question"], replacements)
        items.append(item)
    return items


def fetch_due_cards(
    conn: sqlite3.Connection,
    *,
    subject: str | None = None,
    doc_id: str | None = None,
) -> List[Dict[str, object]]:
    """Cards due for review, optionally scoped to a subject or doc.

    `subject` and `doc_id` AND together. Passing neither returns the
    full due queue (the legacy behaviour). Subject match is exact on
    `documents.subject_name`; doc_id match is exact on `concepts.doc_id`.
    """
    today = date.today().isoformat()
    sql = [
        "SELECT s.id, s.front, s.back, s.state, s.stability, s.difficulty, s.reps,",
        "       s.lapses, s.due_date, s.kind, c.name AS concept, d.filename AS document_name,",
        "       d.subject_name, d.id AS document_id,",
        "       a.chunk_id, a.page_num, a.quote_text",
        "FROM srs_cards s",
        "LEFT JOIN concepts c ON s.concept_id = c.id",
        "LEFT JOIN documents d ON c.doc_id = d.id",
        # Most-recent anchor bound to this card carries the source citation
        # (chunk + page + verbatim quote). LEFT JOIN so cards without an
        # anchor still appear; the citation fields stay NULL and the UI
        # hides the citation row for those cards.
        "LEFT JOIN anchors a ON a.srs_card_id = s.id",
        "  AND a.rowid = (SELECT MAX(rowid) FROM anchors a2 WHERE a2.srs_card_id = s.id)",
        "WHERE (s.due_date IS NULL OR s.due_date <= ?)",
    ]
    params: List[object] = [today]
    if subject is not None:
        sql.append("AND d.subject_name = ?")
        params.append(subject)
    if doc_id is not None:
        sql.append("AND c.doc_id = ?")
        params.append(doc_id)
    sql.append("ORDER BY COALESCE(s.due_date, ?) ASC, s.rowid ASC")
    params.append(today)

    rows = conn.execute("\n".join(sql), params).fetchall()
    replacements = _name_replacements(conn)
    items = []
    for row in rows:
        item = dict(row)
        item["raw_concept"] = item["concept"]
        item["concept"] = clean_concept_label(item["concept"])
        item["front"] = _normalize_card_text(item["front"], replacements)
        item["back"] = _normalize_card_text(item["back"], replacements)
        items.append(item)
    return items


def list_cards(
    conn: sqlite3.Connection,
    *,
    subject: str | None = None,
    doc_id: str | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, object]:
    """List flashcards with optional filters, for the Manage Cards view.

    Returns a total count alongside the page so the UI can show "123 of 857"
    without a second round-trip. `search` matches front or back text via a
    simple LIKE — fine at the current data volume; migrate to FTS5 if cards
    grow past ~10k.
    """
    # PR 5.1 (ADR 0002) — register the cloze-marker strip as a SQLite UDF on
    # this connection so the search WHERE clause can compare against
    # marker-stripped text. Re-registering on the same connection is a noop
    # for sqlite3.
    conn.create_function("_strip_cloze", 1, _strip_cloze_markers)
    where: List[str] = []
    params: List[object] = []
    if subject:
        where.append("d.subject_name = ?")
        params.append(subject)
    if doc_id:
        where.append("d.id = ?")
        params.append(doc_id)
    if search:
        # PR 5.1 (ADR 0002) — strip `{{cN::term}}` markers before LIKE so a
        # cloze front "the {{c1::powerhouse}} of the cell" matches a search
        # for "powerhouse" (the hidden term is the actual content) without
        # also matching the literal "c1" marker token. The strip is applied
        # to the SQL projection, not the search needle, so qa cards (which
        # contain no markers) compare identically to today.
        where.append(
            "(LOWER(_strip_cloze(s.front)) LIKE ? OR LOWER(_strip_cloze(s.back)) LIKE ?)"
        )
        needle = f"%{search.lower()}%"
        params.extend([needle, needle])
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    total_row = conn.execute(
        f"""
        SELECT COUNT(*) AS total
        FROM srs_cards s
        LEFT JOIN concepts c ON s.concept_id = c.id
        LEFT JOIN documents d ON c.doc_id = d.id
        {where_sql}
        """,
        params,
    ).fetchone()
    total = int(total_row["total"] if total_row else 0)

    page_params = list(params) + [int(limit), int(offset)]
    rows = conn.execute(
        f"""
        SELECT s.id, s.front, s.back, s.state, s.difficulty, s.reps, s.lapses,
               s.due_date, s.last_review, s.card_type, s.kind,
               c.id AS concept_id, c.name AS concept,
               d.id AS document_id, d.filename AS document_name,
               d.subject_name
        FROM srs_cards s
        LEFT JOIN concepts c ON s.concept_id = c.id
        LEFT JOIN documents d ON c.doc_id = d.id
        {where_sql}
        ORDER BY d.subject_name, d.filename, s.rowid
        LIMIT ? OFFSET ?
        """,
        page_params,
    ).fetchall()

    replacements = _name_replacements(conn)
    items: List[Dict[str, object]] = []
    for row in rows:
        item = dict(row)
        item["raw_concept"] = item["concept"]
        item["concept"] = clean_concept_label(item["concept"])
        item["front"] = _normalize_card_text(item["front"], replacements)
        item["back"] = _normalize_card_text(item["back"], replacements)
        items.append(item)

    return {"cards": items, "total": total, "limit": limit, "offset": offset}


def list_subjects(conn: sqlite3.Connection) -> List[Dict[str, object]]:
    """Subjects aggregated for the Manage Cards filter.

    Each row has the subject name, total card count, and how many are due
    today. The frontend uses this both for the filter chips and for the
    intro-screen status line ("857 cards, 12 due today").
    """
    today = date.today().isoformat()
    rows = conn.execute(
        """
        SELECT d.subject_name,
               COUNT(*) AS card_count,
               SUM(CASE WHEN s.due_date IS NULL OR s.due_date <= ? THEN 1 ELSE 0 END) AS due_count
        FROM srs_cards s
        LEFT JOIN concepts c ON s.concept_id = c.id
        LEFT JOIN documents d ON c.doc_id = d.id
        GROUP BY d.subject_name
        ORDER BY card_count DESC
        """,
        (today,),
    ).fetchall()
    return [
        {
            "subject_name": row["subject_name"] or "General",
            "card_count": int(row["card_count"] or 0),
            "due_count": int(row["due_count"] or 0),
        }
        for row in rows
    ]


def delete_card(conn: sqlite3.Connection, card_id: str) -> bool:
    """Delete a single card. Returns True if a row was deleted.

    Also cleans up the `flashcard_evidence` junction if it exists so we don't
    leave orphan provenance rows pointing at a deleted card.
    """
    # flashcard_evidence may or may not exist depending on migration state;
    # be defensive.
    try:
        conn.execute("DELETE FROM flashcard_evidence WHERE card_id = ?", (card_id,))
    except sqlite3.OperationalError:
        pass
    cursor = conn.execute("DELETE FROM srs_cards WHERE id = ?", (card_id,))
    return cursor.rowcount > 0


def bulk_delete_cards(conn: sqlite3.Connection, card_ids: List[str]) -> int:
    """Delete many cards in one transaction. Returns deleted row count."""
    if not card_ids:
        return 0
    placeholders = ",".join("?" * len(card_ids))
    try:
        conn.execute(
            f"DELETE FROM flashcard_evidence WHERE card_id IN ({placeholders})",
            card_ids,
        )
    except sqlite3.OperationalError:
        pass
    cursor = conn.execute(
        f"DELETE FROM srs_cards WHERE id IN ({placeholders})",
        card_ids,
    )
    return int(cursor.rowcount or 0)


def create_card(
    conn: sqlite3.Connection,
    *,
    front: str,
    back: str,
    concept_id: Optional[str] = None,
    card_type: str = "custom",
    kind: str = "qa",
) -> Dict[str, Any]:
    """Insert a user-authored flashcard and return the row shape list_cards emits.

    The SRS schedulor treats state='new' cards as immediately due (due_date=today),
    so a freshly-created card shows up in the next session alongside whatever the
    ingestion pipeline already queued. concept_id is optional — orphan cards are
    surfaced by list_cards' LEFT JOIN and show up under the "All" subject filter
    with a null concept/document. We set stability / difficulty to the same
    defaults the schema uses (1.0 / 0.3) rather than leaving them implicit so the
    row shape matches what the ORM callers already consume.

    PR 5.1 (ADR 0002) — `kind` selects the render mode. `kind='cloze'`
    requires at least one `{{cN::term}}` marker in `front` (the same
    text should be supplied for `back`; cloze renders both faces from
    one source). `kind='qa'` accepts any non-empty front/back as today.
    The route layer (api_models.CardCreateRequest) limits kind to the
    enum; this service is the second guard.

    PR 5.2 (ADR 0003) widened the allowlist to include 'reverse'. The
    SQL CHECK on srs_cards.kind was dropped in migration 0018; the
    allowlist below is now the only validation surface alongside the
    Pydantic Literal. Future card kinds add a value to this tuple.
    """
    if kind not in ("qa", "cloze", "reverse"):
        raise ValueError(
            f"kind must be 'qa', 'cloze', or 'reverse', got {kind!r}"
        )
    cleaned_front = (front or "").strip()
    cleaned_back = (back or "").strip()
    if not cleaned_front or not cleaned_back:
        raise ValueError("front and back must each be non-empty after trimming")
    if kind == "cloze" and not _CLOZE_MARKER_RE.search(cleaned_front):
        raise ValueError(
            "cloze cards must contain at least one {{cN::term}} marker"
        )

    card_id = str(uuid.uuid4())
    today = date.today().isoformat()

    resolved_concept_id: Optional[str] = None
    if concept_id:
        row = conn.execute(
            "SELECT id FROM concepts WHERE id = ?",
            (concept_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"concept_id {concept_id!r} does not exist")
        resolved_concept_id = str(row["id"])

    conn.execute(
        """
        INSERT INTO srs_cards (
            id, concept_id, card_type, kind, front, back,
            state, stability, difficulty,
            elapsed_days, scheduled_days, reps, lapses,
            due_date, confidence
        )
        VALUES (?, ?, ?, ?, ?, ?, 'new', 1.0, 0.3, 0, 0, 0, 0, ?, ?)
        """,
        (
            card_id,
            resolved_concept_id,
            card_type,
            kind,
            cleaned_front,
            cleaned_back,
            today,
            1.0,
        ),
    )
    conn.commit()

    row = conn.execute(
        """
        SELECT s.id, s.front, s.back, s.state, s.difficulty, s.reps, s.lapses,
               s.due_date, s.last_review, s.card_type, s.kind,
               c.id AS concept_id, c.name AS concept,
               d.id AS document_id, d.filename AS document_name,
               d.subject_name
        FROM srs_cards s
        LEFT JOIN concepts c ON s.concept_id = c.id
        LEFT JOIN documents d ON c.doc_id = d.id
        WHERE s.id = ?
        """,
        (card_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"freshly-inserted card {card_id} missing on read-back")

    replacements = _name_replacements(conn)
    item = dict(row)
    item["raw_concept"] = item["concept"]
    item["concept"] = clean_concept_label(item["concept"]) if item["concept"] else None
    item["front"] = _normalize_card_text(item["front"], replacements)
    item["back"] = _normalize_card_text(item["back"], replacements)
    return item


def create_card_pair(
    conn: sqlite3.Connection,
    *,
    front: str,
    back: str,
    concept_id: Optional[str] = None,
    card_type: str = "custom",
) -> Dict[str, Any]:
    """Insert a Q→A card AND its reverse A→Q twin, plus a card_pairs link.

    All three inserts run inside one savepoint so a failure rolls back
    every row. The pair row uses the lexicographically smaller id as
    `card_a_id` to satisfy the CHECK (card_a_id < card_b_id) invariant
    from migration 0018.

    PR 5.2 (ADR 0003). The primary card is the user-typed direction
    (front→back, kind='qa'); the reverse is the same content with
    front/back swapped and kind='reverse'. Each row carries its own
    FSRS state — they schedule independently, which mirrors the
    real-world case where you remember a term but not its inverse.

    Returns {"primary": <card-shape>, "reverse": <card-shape>,
    "primary_id": str, "reverse_id": str} so the client can drop both
    rows into its cached list without a round-trip.
    """
    cleaned_front = (front or "").strip()
    cleaned_back = (back or "").strip()
    if not cleaned_front or not cleaned_back:
        raise ValueError("front and back must each be non-empty after trimming")

    resolved_concept_id: Optional[str] = None
    if concept_id:
        row = conn.execute(
            "SELECT id FROM concepts WHERE id = ?",
            (concept_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"concept_id {concept_id!r} does not exist")
        resolved_concept_id = str(row["id"])

    primary_id = str(uuid.uuid4())
    reverse_id = str(uuid.uuid4())
    today = date.today().isoformat()

    # Order the pair so card_a_id < card_b_id (CHECK invariant from 0018).
    if primary_id < reverse_id:
        pair_a, pair_b = primary_id, reverse_id
    else:
        pair_a, pair_b = reverse_id, primary_id

    conn.execute("SAVEPOINT create_card_pair")
    try:
        for new_id, f_text, b_text, kind in (
            (primary_id, cleaned_front, cleaned_back, "qa"),
            (reverse_id, cleaned_back, cleaned_front, "reverse"),
        ):
            conn.execute(
                """
                INSERT INTO srs_cards (
                    id, concept_id, card_type, kind, front, back,
                    state, stability, difficulty,
                    elapsed_days, scheduled_days, reps, lapses,
                    due_date, confidence
                )
                VALUES (?, ?, ?, ?, ?, ?, 'new', 1.0, 0.3, 0, 0, 0, 0, ?, ?)
                """,
                (
                    new_id,
                    resolved_concept_id,
                    card_type,
                    kind,
                    f_text,
                    b_text,
                    today,
                    1.0,
                ),
            )
        conn.execute(
            "INSERT INTO card_pairs (card_a_id, card_b_id) VALUES (?, ?)",
            (pair_a, pair_b),
        )
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT create_card_pair")
        conn.execute("RELEASE SAVEPOINT create_card_pair")
        raise
    conn.execute("RELEASE SAVEPOINT create_card_pair")
    conn.commit()

    replacements = _name_replacements(conn)

    def _read_back(card_id: str) -> Dict[str, Any]:
        row = conn.execute(
            """
            SELECT s.id, s.front, s.back, s.state, s.difficulty, s.reps, s.lapses,
                   s.due_date, s.last_review, s.card_type, s.kind,
                   c.id AS concept_id, c.name AS concept,
                   d.id AS document_id, d.filename AS document_name,
                   d.subject_name
            FROM srs_cards s
            LEFT JOIN concepts c ON s.concept_id = c.id
            LEFT JOIN documents d ON c.doc_id = d.id
            WHERE s.id = ?
            """,
            (card_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"freshly-inserted card {card_id} missing on read-back")
        item = dict(row)
        item["raw_concept"] = item["concept"]
        item["concept"] = (
            clean_concept_label(item["concept"]) if item["concept"] else None
        )
        item["front"] = _normalize_card_text(item["front"], replacements)
        item["back"] = _normalize_card_text(item["back"], replacements)
        return item

    return {
        "primary": _read_back(primary_id),
        "reverse": _read_back(reverse_id),
        "primary_id": primary_id,
        "reverse_id": reverse_id,
    }
