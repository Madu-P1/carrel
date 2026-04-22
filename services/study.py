import json
import sqlite3
from datetime import date
from typing import Dict, List

from services.documents import clean_concept_label


def _name_replacements(conn: sqlite3.Connection) -> List[tuple[str, str]]:
    rows = conn.execute("SELECT name FROM concepts ORDER BY LENGTH(name) DESC, rowid ASC").fetchall()
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
    value = str(text or "")
    for raw_name, cleaned in replacements:
        value = value.replace(raw_name, cleaned)
    return value


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
            "Hard" if item["difficulty"] >= 0.7 else "Medium" if item["difficulty"] >= 0.45 else "Easy"
        )
        item["options"] = [item["answer"], *json.loads(item["distractors"] or "[]")]
        item["raw_concept"] = item["concept"]
        item["concept"] = clean_concept_label(item["concept"])
        item["question"] = _normalize_card_text(item["question"], replacements)
        items.append(item)
    return items


def fetch_due_cards(conn: sqlite3.Connection) -> List[Dict[str, object]]:
    rows = conn.execute(
        """
        SELECT s.id, s.front, s.back, s.state, s.stability, s.difficulty, s.reps,
               s.lapses, s.due_date, c.name AS concept, d.filename AS document_name, d.subject_name
        FROM srs_cards s
        JOIN concepts c ON s.concept_id = c.id
        JOIN documents d ON c.doc_id = d.id
        WHERE s.due_date IS NULL OR s.due_date <= ?
        ORDER BY COALESCE(s.due_date, ?) ASC, s.rowid ASC
        """,
        (date.today().isoformat(), date.today().isoformat()),
    ).fetchall()
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
    where: List[str] = []
    params: List[object] = []
    if subject:
        where.append("d.subject_name = ?")
        params.append(subject)
    if doc_id:
        where.append("d.id = ?")
        params.append(doc_id)
    if search:
        where.append("(LOWER(s.front) LIKE ? OR LOWER(s.back) LIKE ?)")
        needle = f"%{search.lower()}%"
        params.extend([needle, needle])
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    total_row = conn.execute(
        f"""
        SELECT COUNT(*) AS total
        FROM srs_cards s
        JOIN concepts c ON s.concept_id = c.id
        JOIN documents d ON c.doc_id = d.id
        {where_sql}
        """,
        params,
    ).fetchone()
    total = int(total_row["total"] if total_row else 0)

    page_params = list(params) + [int(limit), int(offset)]
    rows = conn.execute(
        f"""
        SELECT s.id, s.front, s.back, s.state, s.difficulty, s.reps, s.lapses,
               s.due_date, s.last_review, s.card_type,
               c.id AS concept_id, c.name AS concept,
               d.id AS document_id, d.filename AS document_name,
               d.subject_name
        FROM srs_cards s
        JOIN concepts c ON s.concept_id = c.id
        JOIN documents d ON c.doc_id = d.id
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
        JOIN concepts c ON s.concept_id = c.id
        JOIN documents d ON c.doc_id = d.id
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
