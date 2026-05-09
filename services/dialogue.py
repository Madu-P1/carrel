from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Dict, Optional

from services.app_state import load_messages, log_study_event


def start_dialogue(conn: sqlite3.Connection, *, concept_id: Optional[str]) -> Dict[str, object]:
    concept = None
    if concept_id:
        concept = conn.execute(
            "SELECT id, name FROM concepts WHERE id = ?",
            (concept_id,),
        ).fetchone()
    if not concept:
        concept = conn.execute(
            "SELECT id, name FROM concepts ORDER BY mastery ASC LIMIT 1"
        ).fetchone()
    if not concept:
        raise ValueError("No concepts available for dialogue.")

    session_id = str(uuid.uuid4())
    opening = f"What do you already know about {concept['name']}?"
    conn.execute(
        """
        INSERT INTO dialogue_sessions (id, concept_id, messages, misconceptions, final_understanding)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            session_id,
            concept["id"],
            json.dumps([{"role": "assistant", "content": opening}]),
            json.dumps([]),
            None,
        ),
    )
    conn.commit()
    log_study_event(
        conn, "dialogue_started", concept_id=concept["id"], payload={"opening": opening}
    )
    return {"session_id": session_id, "opening_prompt": opening}


def post_message(
    conn: sqlite3.Connection,
    *,
    session_id: Optional[str],
    message: str,
    concept_id: Optional[str],
) -> Dict[str, object]:
    session = None
    if session_id:
        session = conn.execute(
            "SELECT id, concept_id, messages FROM dialogue_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()

    if not session:
        concept = None
        if concept_id:
            concept = conn.execute("SELECT id FROM concepts WHERE id = ?", (concept_id,)).fetchone()
        if not concept:
            concept = conn.execute(
                "SELECT id FROM concepts ORDER BY mastery ASC LIMIT 1"
            ).fetchone()
        if not concept:
            raise ValueError("No concepts available for dialogue.")
        session_id = str(uuid.uuid4())
        session = {"id": session_id, "concept_id": concept["id"], "messages": "[]"}
        conn.execute(
            """
            INSERT INTO dialogue_sessions (id, concept_id, messages, misconceptions, final_understanding)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, concept["id"], "[]", json.dumps([]), None),
        )

    concept = conn.execute(
        "SELECT id, name, description, mastery FROM concepts WHERE id = ?",
        (session["concept_id"],),
    ).fetchone()
    if not concept:
        raise ValueError("Dialogue concept is unavailable.")

    reply = (
        f"Before we jump to the answer, what is one clue from your document that points to {concept['name']}? "
        "If you're unsure, compare it to a related idea and tell me what changes."
    )
    messages = load_messages(session["messages"])
    messages.extend(
        [
            {"role": "user", "content": message},
            {"role": "assistant", "content": reply},
        ]
    )
    understanding = 4 if len(message.split()) > 20 else 2
    conn.execute(
        """
        UPDATE dialogue_sessions
        SET messages = ?, final_understanding = ?
        WHERE id = ?
        """,
        (json.dumps(messages), understanding, session["id"]),
    )
    conn.commit()
    log_study_event(
        conn,
        "dialogue_message",
        concept_id=session["concept_id"],
        confidence=70.0 if understanding >= 4 else 45.0,
        payload={"understanding": understanding},
    )
    return {"reply": reply, "understanding": understanding, "session_id": session["id"]}
