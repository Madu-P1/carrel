import sqlite3
import uuid
from typing import Any, Dict, Iterable, List, Optional


def source_snapshot_hash(conn: sqlite3.Connection, source_id: Optional[str]) -> Optional[str]:
    if not source_id:
        return None
    row = conn.execute(
        "SELECT source_hash, source_version FROM documents WHERE id = ?",
        (source_id,),
    ).fetchone()
    if not row:
        return None
    return row["source_hash"] or f"{source_id}:v{row['source_version'] or 1}"


def _row_to_evidence_payload(row: sqlite3.Row) -> Dict[str, Any]:
    source_chip = row["document_name"] or "Source"
    section = row["section_label"] or "Excerpt"
    return {
        "id": row["id"],
        "source_id": row["source_id"],
        "chunk_id": row["chunk_id"],
        "concept_id": row["concept_id"],
        "anchor_text": row["anchor_text"],
        "anchor_start": row["anchor_start"],
        "anchor_end": row["anchor_end"],
        "page_num": row["page_num"],
        "section_label": section,
        "confidence": round(float(row["confidence"] or 0.0), 2),
        "contradiction_group": row["contradiction_group"],
        "snapshot_hash": row["snapshot_hash"],
        "document_name": row["document_name"],
        "source_chip": source_chip,
        "label": f"{source_chip} · {section}",
        "actions": [
            "open_excerpt",
            "open_context",
            "copy_citation",
            "attach_to_note",
            "convert_to_card",
            "convert_to_quiz",
        ],
    }


def build_evidence_reference(
    conn: sqlite3.Connection,
    citation: Dict[str, Any],
    *,
    concept_id: Optional[str] = None,
    confidence: Optional[float] = None,
) -> Dict[str, Any]:
    source_id = citation.get("document_id")
    # T05 renamed the citation payload key from `chunk_id` to `node_id`.
    # The evidence_references schema column is still `chunk_id` (T14
    # migrates the column); SQLite TEXT affinity accepts the int value
    # from the nodes branch and the str-UUID from the legacy chunks
    # branch alike. Column rename and field rename land independently.
    chunk_id = citation.get("node_id")
    anchor_text = (citation.get("snippet") or citation.get("content") or "").strip()
    if not source_id or not chunk_id or not anchor_text:
        raise ValueError("Citation must include document_id, node_id, and snippet/content.")

    existing = conn.execute(
        """
        SELECT er.id, er.source_id, er.chunk_id, er.concept_id, er.anchor_text, er.anchor_start,
               er.anchor_end, er.page_num, er.section_label, er.confidence, er.contradiction_group,
               er.snapshot_hash, d.filename AS document_name
        FROM evidence_references er
        LEFT JOIN documents d ON d.id = er.source_id
        WHERE er.source_id = ? AND er.chunk_id = ? AND er.anchor_text = ?
        LIMIT 1
        """,
        (source_id, chunk_id, anchor_text),
    ).fetchone()
    if existing:
        return _row_to_evidence_payload(existing)

    evidence_id = str(uuid.uuid4())
    snapshot_hash = source_snapshot_hash(conn, source_id)
    evidence_confidence = (
        confidence if confidence is not None else min(0.95, 0.45 + (citation.get("score", 0) / 30))
    )
    conn.execute(
        """
        INSERT INTO evidence_references (
            id, source_id, chunk_id, concept_id, anchor_text, page_num, section_label, confidence, snapshot_hash
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            evidence_id,
            source_id,
            chunk_id,
            concept_id,
            anchor_text,
            citation.get("page_num"),
            citation.get("section"),
            evidence_confidence,
            snapshot_hash,
        ),
    )
    row = conn.execute(
        """
        SELECT er.id, er.source_id, er.chunk_id, er.concept_id, er.anchor_text, er.anchor_start,
               er.anchor_end, er.page_num, er.section_label, er.confidence, er.contradiction_group,
               er.snapshot_hash, d.filename AS document_name
        FROM evidence_references er
        LEFT JOIN documents d ON d.id = er.source_id
        WHERE er.id = ?
        """,
        (evidence_id,),
    ).fetchone()
    return _row_to_evidence_payload(row)


def persist_evidence_references(
    conn: sqlite3.Connection,
    citations: Iterable[Dict[str, Any]],
    *,
    concept_id: Optional[str] = None,
    confidence: Optional[float] = None,
) -> List[Dict[str, Any]]:
    references: List[Dict[str, Any]] = []
    for citation in citations:
        references.append(
            build_evidence_reference(
                conn,
                citation,
                concept_id=concept_id,
                confidence=confidence,
            )
        )
    return references


def fetch_exchange_evidence(conn: sqlite3.Connection, exchange_id: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT er.id, er.source_id, er.chunk_id, er.concept_id, er.anchor_text, er.anchor_start,
               er.anchor_end, er.page_num, er.section_label, er.confidence, er.contradiction_group,
               er.snapshot_hash, d.filename AS document_name
        FROM tutor_exchange_evidence tee
        JOIN evidence_references er ON er.id = tee.evidence_reference_id
        LEFT JOIN documents d ON d.id = er.source_id
        WHERE tee.exchange_id = ?
        ORDER BY er.rowid ASC
        """,
        (exchange_id,),
    ).fetchall()
    return [_row_to_evidence_payload(row) for row in rows]


def fetch_note_evidence(conn: sqlite3.Connection, note_id: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT er.id, er.source_id, er.chunk_id, er.concept_id, er.anchor_text, er.anchor_start,
               er.anchor_end, er.page_num, er.section_label, er.confidence, er.contradiction_group,
               er.snapshot_hash, d.filename AS document_name
        FROM note_evidence ne
        JOIN evidence_references er ON er.id = ne.evidence_reference_id
        LEFT JOIN documents d ON d.id = er.source_id
        WHERE ne.note_id = ?
        ORDER BY er.rowid ASC
        """,
        (note_id,),
    ).fetchall()
    return [_row_to_evidence_payload(row) for row in rows]


def attach_evidence_to_note(
    conn: sqlite3.Connection,
    note_id: str,
    evidence_reference_ids: Iterable[str],
) -> None:
    for evidence_reference_id in evidence_reference_ids:
        conn.execute(
            """
            INSERT OR IGNORE INTO note_evidence (note_id, evidence_reference_id)
            VALUES (?, ?)
            """,
            (note_id, evidence_reference_id),
        )


def fetch_recent_evidence(conn: sqlite3.Connection, limit: int = 8) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT er.id, er.source_id, er.chunk_id, er.concept_id, er.anchor_text, er.anchor_start,
               er.anchor_end, er.page_num, er.section_label, er.confidence, er.contradiction_group,
               er.snapshot_hash, d.filename AS document_name
        FROM evidence_references er
        LEFT JOIN documents d ON d.id = er.source_id
        ORDER BY er.rowid DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [_row_to_evidence_payload(row) for row in rows]


# ---------------------------------------------------------------------------
# Evidence linkage for cards, quizzes, and artifacts  (Phase 1a)
# ---------------------------------------------------------------------------


def link_evidence_to_card(
    conn: sqlite3.Connection,
    card_id: str,
    evidence_reference_ids: Iterable[str],
) -> None:
    """Link evidence references to a flashcard via flashcard_evidence junction."""
    for eid in evidence_reference_ids:
        conn.execute(
            "INSERT OR IGNORE INTO flashcard_evidence (card_id, evidence_reference_id) VALUES (?, ?)",
            (card_id, eid),
        )


def link_evidence_to_quiz(
    conn: sqlite3.Connection,
    question_id: str,
    evidence_reference_ids: Iterable[str],
) -> None:
    """Link evidence references to a quiz question via quiz_evidence junction."""
    for eid in evidence_reference_ids:
        conn.execute(
            "INSERT OR IGNORE INTO quiz_evidence (question_id, evidence_reference_id) VALUES (?, ?)",
            (question_id, eid),
        )


def link_evidence_to_artifact(
    conn: sqlite3.Connection,
    artifact_id: str,
    evidence_reference_ids: Iterable[str],
) -> None:
    """Link evidence references to an artifact via artifact_evidence junction."""
    for eid in evidence_reference_ids:
        conn.execute(
            "INSERT OR IGNORE INTO artifact_evidence (artifact_id, evidence_reference_id) VALUES (?, ?)",
            (artifact_id, eid),
        )


def link_session_artifact(
    conn: sqlite3.Connection,
    session_id: str,
    artifact_id: str,
) -> None:
    """Record that an artifact was generated during a session."""
    conn.execute(
        "INSERT OR IGNORE INTO session_artifacts (session_id, artifact_id) VALUES (?, ?)",
        (session_id, artifact_id),
    )


# ---------------------------------------------------------------------------
# Fetch evidence by entity
# ---------------------------------------------------------------------------


def fetch_card_evidence(conn: sqlite3.Connection, card_id: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT er.id, er.source_id, er.chunk_id, er.concept_id, er.anchor_text, er.anchor_start,
               er.anchor_end, er.page_num, er.section_label, er.confidence, er.contradiction_group,
               er.snapshot_hash, d.filename AS document_name
        FROM flashcard_evidence fe
        JOIN evidence_references er ON er.id = fe.evidence_reference_id
        LEFT JOIN documents d ON d.id = er.source_id
        WHERE fe.card_id = ?
        ORDER BY er.rowid ASC
        """,
        (card_id,),
    ).fetchall()
    return [_row_to_evidence_payload(row) for row in rows]


def fetch_quiz_evidence(conn: sqlite3.Connection, question_id: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT er.id, er.source_id, er.chunk_id, er.concept_id, er.anchor_text, er.anchor_start,
               er.anchor_end, er.page_num, er.section_label, er.confidence, er.contradiction_group,
               er.snapshot_hash, d.filename AS document_name
        FROM quiz_evidence qe
        JOIN evidence_references er ON er.id = qe.evidence_reference_id
        LEFT JOIN documents d ON d.id = er.source_id
        WHERE qe.question_id = ?
        ORDER BY er.rowid ASC
        """,
        (question_id,),
    ).fetchall()
    return [_row_to_evidence_payload(row) for row in rows]


def fetch_artifact_evidence(conn: sqlite3.Connection, artifact_id: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT er.id, er.source_id, er.chunk_id, er.concept_id, er.anchor_text, er.anchor_start,
               er.anchor_end, er.page_num, er.section_label, er.confidence, er.contradiction_group,
               er.snapshot_hash, d.filename AS document_name
        FROM artifact_evidence ae
        JOIN evidence_references er ON er.id = ae.evidence_reference_id
        LEFT JOIN documents d ON d.id = er.source_id
        WHERE ae.artifact_id = ?
        ORDER BY er.rowid ASC
        """,
        (artifact_id,),
    ).fetchall()
    return [_row_to_evidence_payload(row) for row in rows]


def fetch_evidence_for_concept(
    conn: sqlite3.Connection, concept_id: str, limit: int = 10
) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT er.id, er.source_id, er.chunk_id, er.concept_id, er.anchor_text, er.anchor_start,
               er.anchor_end, er.page_num, er.section_label, er.confidence, er.contradiction_group,
               er.snapshot_hash, d.filename AS document_name
        FROM evidence_references er
        LEFT JOIN documents d ON d.id = er.source_id
        WHERE er.concept_id = ?
        ORDER BY er.confidence DESC, er.rowid DESC
        LIMIT ?
        """,
        (concept_id, limit),
    ).fetchall()
    return [_row_to_evidence_payload(row) for row in rows]


def fetch_evidence_for_source(
    conn: sqlite3.Connection, source_id: str, limit: int = 12
) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT er.id, er.source_id, er.chunk_id, er.concept_id, er.anchor_text, er.anchor_start,
               er.anchor_end, er.page_num, er.section_label, er.confidence, er.contradiction_group,
               er.snapshot_hash, d.filename AS document_name
        FROM evidence_references er
        LEFT JOIN documents d ON d.id = er.source_id
        WHERE er.source_id = ?
        ORDER BY er.confidence DESC, er.rowid DESC
        LIMIT ?
        """,
        (source_id, limit),
    ).fetchall()
    return [_row_to_evidence_payload(row) for row in rows]
