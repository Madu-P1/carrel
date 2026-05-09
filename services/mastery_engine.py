import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional


CLASSIFICATION_IMPACT = {
    "omission": {"recall": -0.04, "transfer": -0.02, "risk": 0.12, "minutes": 90},
    "misconception": {"recall": -0.06, "transfer": -0.05, "risk": 0.2, "minutes": 20},
    "wrong_relation": {"recall": -0.05, "transfer": -0.07, "risk": 0.18, "minutes": 30},
    "wrong_example": {"recall": -0.04, "transfer": -0.05, "risk": 0.14, "minutes": 180},
    "shallow_but_correct": {"recall": 0.03, "transfer": 0.01, "risk": -0.03, "minutes": 2880},
    "robust_and_transferable": {"recall": 0.08, "transfer": 0.09, "risk": -0.08, "minutes": 10080},
}


def _clamp(value: float, *, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def ensure_mastery_state(
    conn: sqlite3.Connection,
    concept_id: str,
    *,
    goal_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    row = conn.execute(
        """
        SELECT id, concept_id, goal_id, session_id, recall_score, transfer_score, misconception_risk,
               confidence_alignment, last_evidence_quality, next_due_at, updated_at
        FROM mastery_states
        WHERE concept_id = ? AND COALESCE(goal_id, '') = COALESCE(?, '')
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (concept_id, goal_id),
    ).fetchone()
    if row:
        return dict(row)

    concept = conn.execute(
        "SELECT mastery FROM concepts WHERE id = ?",
        (concept_id,),
    ).fetchone()
    baseline = float(concept["mastery"] if concept else 0.1)
    mastery_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO mastery_states (
            id, concept_id, goal_id, session_id, recall_score, transfer_score, misconception_risk,
            confidence_alignment, last_evidence_quality, next_due_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            mastery_id,
            concept_id,
            goal_id,
            session_id,
            baseline,
            max(0.05, baseline - 0.05),
            0.12,
            0.0,
            0.0,
            None,
        ),
    )
    row = conn.execute(
        "SELECT * FROM mastery_states WHERE id = ?",
        (mastery_id,),
    ).fetchone()
    return dict(row)


def update_mastery_state(
    conn: sqlite3.Connection,
    concept_id: str,
    *,
    goal_id: Optional[str] = None,
    session_id: Optional[str] = None,
    classification: Optional[str] = None,
    learner_confidence: Optional[float] = None,
    evidence_quality: float = 0.0,
) -> Dict[str, Any]:
    state = ensure_mastery_state(conn, concept_id, goal_id=goal_id, session_id=session_id)
    impact = CLASSIFICATION_IMPACT.get(
        classification or "",
        {"recall": 0.01, "transfer": 0.0, "risk": 0.0, "minutes": 1440},
    )
    recall_score = _clamp(float(state["recall_score"] or 0.1) + impact["recall"])
    transfer_score = _clamp(float(state["transfer_score"] or 0.1) + impact["transfer"])
    misconception_risk = _clamp(float(state["misconception_risk"] or 0.0) + impact["risk"])
    expected_confidence = round(recall_score * 100, 2)
    actual_confidence = float(
        learner_confidence if learner_confidence is not None else expected_confidence
    )
    confidence_alignment = _clamp(1 - abs(actual_confidence - expected_confidence) / 100)
    next_due_at = (
        datetime.now(timezone.utc) + timedelta(minutes=int(impact["minutes"]))
    ).isoformat()

    conn.execute(
        """
        UPDATE mastery_states
        SET session_id = ?, recall_score = ?, transfer_score = ?, misconception_risk = ?,
            confidence_alignment = ?, last_evidence_quality = ?, next_due_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            session_id,
            round(recall_score, 3),
            round(transfer_score, 3),
            round(misconception_risk, 3),
            round(confidence_alignment, 3),
            round(evidence_quality, 3),
            next_due_at,
            datetime.now(timezone.utc).isoformat(),
            state["id"],
        ),
    )
    concept_mastery = round((recall_score * 0.6) + (transfer_score * 0.4), 2)
    conn.execute(
        "UPDATE concepts SET mastery = ?, last_tested = ? WHERE id = ?",
        (concept_mastery, datetime.now(timezone.utc).isoformat(), concept_id),
    )
    row = conn.execute(
        "SELECT * FROM mastery_states WHERE id = ?",
        (state["id"],),
    ).fetchone()
    return dict(row)


def compute_session_mastery_delta(conn: sqlite3.Connection, session_id: str) -> float:
    rows = conn.execute(
        """
        SELECT recall_score, transfer_score
        FROM mastery_states
        WHERE session_id = ?
        """,
        (session_id,),
    ).fetchall()
    if not rows:
        return 0.0
    total = sum(
        ((float(row["recall_score"] or 0) + float(row["transfer_score"] or 0)) / 2) for row in rows
    )
    return round(total / len(rows), 3)
