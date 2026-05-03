from __future__ import annotations

import re
import sqlite3
from typing import Any, Sequence

from services import mastery_engine


def maybe_update_note_mastery(
    conn: sqlite3.Connection,
    *,
    concept_id: str | None,
    content: str | None,
    evidence_reference_ids: Sequence[str] | None,
    goal_id: str | None,
    session_id: str | None,
) -> dict[str, Any] | None:
    if not concept_id:
        return None

    content_words = len(re.findall(r"[A-Za-z0-9]+", content or ""))
    if content_words < 8:
        return None

    evidence_count = len(evidence_reference_ids or [])
    return mastery_engine.update_mastery_state(
        conn,
        concept_id,
        goal_id=goal_id,
        session_id=session_id,
        classification="shallow_but_correct",
        learner_confidence=min(95, max(45, content_words + evidence_count * 8)),
        evidence_quality=0.85 if evidence_count else 0.58,
    )
