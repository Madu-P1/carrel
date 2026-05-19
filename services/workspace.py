import sqlite3
from datetime import date
from typing import Any, Dict, List, Optional

from services.documents import clean_concept_label


def fetch_mastery_snapshot(conn: sqlite3.Connection, limit: int = 8) -> List[Dict[str, Any]]:
    concept_rows = conn.execute(
        """
        SELECT c.id, c.doc_id, c.name, c.mastery, c.description, d.filename AS document_name, d.subject_name
        FROM concepts c
        JOIN documents d ON d.id = c.doc_id
        ORDER BY c.mastery ASC, c.rowid ASC
        """
    ).fetchall()
    due_counts = {
        row["concept_id"]: row["total"]
        for row in conn.execute(
            """
            SELECT concept_id, COUNT(*) AS total
            FROM srs_cards
            WHERE due_date IS NULL OR due_date <= ?
            GROUP BY concept_id
            """,
            (date.today().isoformat(),),
        ).fetchall()
    }
    snapshot: List[Dict[str, Any]] = []
    for row in concept_rows[:limit]:
        mastery = round(float(row["mastery"]) * 100)
        snapshot.append(
            {
                "id": row["id"],
                "name": clean_concept_label(row["name"]),
                "mastery": mastery,
                "band": "Struggling"
                if mastery < 45
                else "Developing"
                if mastery < 75
                else "Strong",
                "due_cards": due_counts.get(row["id"], 0),
                "description": row["description"],
                "document_name": row["document_name"],
                "subject_name": row["subject_name"],
            }
        )
    return snapshot


def related_concept_id(conn: sqlite3.Connection, concept_id: str) -> Optional[str]:
    row = conn.execute(
        """
        SELECT target_id FROM concept_edges WHERE source_id = ?
        UNION
        SELECT source_id FROM concept_edges WHERE target_id = ?
        LIMIT 1
        """,
        (concept_id, concept_id),
    ).fetchone()
    return row[0] if row else None


def build_momentum_engine(conn: sqlite3.Connection, fetch_recent_events) -> Dict[str, Any]:
    concept_rows = conn.execute(
        "SELECT id, name, mastery FROM concepts ORDER BY mastery ASC, rowid ASC"
    ).fetchall()
    event_rows = fetch_recent_events(conn, limit=24)
    due_rows = conn.execute(
        """
        SELECT concept_id, COUNT(*) AS total
        FROM srs_cards
        WHERE due_date IS NULL OR due_date <= ?
        GROUP BY concept_id
        """,
        (date.today().isoformat(),),
    ).fetchall()
    due_counts = {row["concept_id"]: row["total"] for row in due_rows}
    low_confidence: Dict[str, int] = {}
    confusion_counts: Dict[str, int] = {}
    switches = 0
    previous_topic = None
    for event in event_rows:
        topic_key = event["concept_id"] or event["doc_id"]
        if previous_topic and topic_key and topic_key != previous_topic:
            switches += 1
        if topic_key:
            previous_topic = topic_key
        if event.get("confidence") is not None and event["confidence"] < 55 and event["concept_id"]:
            low_confidence[event["concept_id"]] = low_confidence.get(event["concept_id"], 0) + 1
        payload = event.get("payload") or []
        if isinstance(payload, dict) and event["concept_id"]:
            confusion_counts[event["concept_id"]] = confusion_counts.get(
                event["concept_id"], 0
            ) + int(payload.get("misconception_count", 0))

    best_concept = None
    best_score = -1.0
    for row in concept_rows:
        concept_id = row["id"]
        score = (
            (1 - float(row["mastery"])) * 60
            + low_confidence.get(concept_id, 0) * 15
            + confusion_counts.get(concept_id, 0) * 12
            + due_counts.get(concept_id, 0) * 8
        )
        if score > best_score:
            best_score = score
            best_concept = row

    if not best_concept:
        return {
            "headline": "Upload a source to start building momentum",
            "reason": "The engine activates once there are concepts, questions, and study events to work with.",
            "actions": [{"label": "Upload a source", "type": "upload"}],
            "focus_concept_id": None,
            "focus_concept_name": None,
            "signals": [],
        }

    notes_exist = (
        conn.execute(
            "SELECT COUNT(*) AS total FROM notes WHERE concept_id = ?",
            (best_concept["id"],),
        ).fetchone()["total"]
        > 0
    )
    due_count = due_counts.get(best_concept["id"], 0)
    confusion = confusion_counts.get(best_concept["id"], 0)
    low_conf = low_confidence.get(best_concept["id"], 0)
    related_id = related_concept_id(conn, best_concept["id"])
    related_name = None
    if related_id:
        related_row = conn.execute(
            "SELECT name FROM concepts WHERE id = ?", (related_id,)
        ).fetchone()
        related_name = clean_concept_label(related_row["name"]) if related_row else None

    focus_name = clean_concept_label(best_concept["name"])

    if switches >= 4:
        headline = f"Run a 7-minute focus sprint on {focus_name}"
        reason = "You have been switching topics often. A short, single-topic sprint will improve retention more than opening another document."
        primary_action = {
            "label": "Start focus mode",
            "type": "focus",
            "concept_id": best_concept["id"],
        }
    elif confusion or low_conf:
        headline = f"Use scaffolded help on {focus_name}"
        reason = "Low confidence and repeated uncertainty suggest you need a guided explanation with direct source evidence before testing again."
        primary_action = {
            "label": "Ask grounded tutor",
            "type": "tutor",
            "concept_id": best_concept["id"],
        }
    elif due_count >= 4:
        headline = f"Clear the due cards for {focus_name}"
        reason = "You already have enough knowledge here to reinforce it quickly. A short card sprint will lock it in."
        primary_action = {
            "label": "Do review sprint",
            "type": "review",
            "concept_id": best_concept["id"],
        }
    elif not notes_exist:
        headline = f"Turn {focus_name} into a 3-bullet note"
        reason = "You have source material and partial understanding, but no compressed note yet. Writing one now raises future quiz performance."
        primary_action = {
            "label": "Capture smart note",
            "type": "note",
            "concept_id": best_concept["id"],
        }
    else:
        headline = f"Compare {focus_name} with {related_name or 'a nearby concept'}"
        reason = "The next gain comes from contrast. Comparing adjacent concepts tends to surface the misconceptions that simple rereading misses."
        primary_action = {
            "label": "Open compare mode",
            "type": "compare",
            "concept_id": best_concept["id"],
            "related_concept_id": related_id,
        }

    actions = [primary_action]
    if related_id and primary_action["type"] != "compare":
        actions.append(
            {
                "label": f"Compare with {related_name}",
                "type": "compare",
                "concept_id": best_concept["id"],
                "related_concept_id": related_id,
            }
        )
    if not notes_exist and primary_action["type"] != "note":
        actions.append({"label": "Create note", "type": "note", "concept_id": best_concept["id"]})
    if due_count and primary_action["type"] != "review":
        actions.append(
            {"label": f"{due_count} cards due", "type": "review", "concept_id": best_concept["id"]}
        )

    signals = [
        f"Mastery {round(float(best_concept['mastery']) * 100)}%",
        f"{low_conf} recent low-confidence moments" if low_conf else "Confidence stable recently",
        f"{confusion} misconception flags" if confusion else "No explicit misconception flags yet",
        f"{switches} recent topic switches",
    ]
    return {
        "headline": headline,
        "reason": reason,
        "actions": actions,
        "focus_concept_id": best_concept["id"],
        "focus_concept_name": focus_name,
        "signals": signals,
        "momentum_score": round(best_score, 1),
    }


def fetch_compare_options(conn: sqlite3.Connection) -> List[Dict[str, str]]:
    rows = conn.execute(
        """
        SELECT c.id, c.doc_id, c.name, d.filename AS document_name, d.subject_name
        FROM concepts c
        JOIN documents d ON d.id = c.doc_id
        ORDER BY d.subject_name ASC, d.filename ASC, c.name ASC
        """
    ).fetchall()
    return [
        {
            "id": row["id"],
            "doc_id": row["doc_id"],
            "name": clean_concept_label(row["name"]),
            "document_name": row["document_name"],
            "subject_name": row["subject_name"],
        }
        for row in rows
    ]


def fetch_workspace_state(
    conn: sqlite3.Connection,
    *,
    get_setting,
    fetch_recent_events,
    fetch_subject_groups,
) -> Dict[str, Any]:
    from services.tutor import fetch_notes

    return {
        "goal": get_setting(conn, "learning_goal", ""),
        "momentum": build_momentum_engine(conn, fetch_recent_events),
        "timeline": fetch_recent_events(conn, limit=10),
        "mastery": fetch_mastery_snapshot(conn, limit=8),
        "notes": fetch_notes(conn, limit=5),
        "compareOptions": fetch_compare_options(conn),
        "subjects": fetch_subject_groups(conn),
    }


def _load_scope(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        import json

        values = json.loads(raw)
    except Exception:
        return []
    return values if isinstance(values, list) else []


def fetch_goals(conn: sqlite3.Connection, *, fallback_goal: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, title, description, status, created_at, updated_at
        FROM goals
        ORDER BY updated_at DESC, created_at DESC
        """
    ).fetchall()
    goals = [dict(row) for row in rows]
    if fallback_goal and not any(item["title"] == fallback_goal for item in goals):
        goals.insert(
            0,
            {
                "id": "legacy-goal",
                "title": fallback_goal,
                "description": "Migrated from the original workspace goal field.",
                "status": "active",
            },
        )
    return goals


def fetch_artifacts(conn: sqlite3.Connection, limit: int = 8) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, artifact_kind, goal_id, session_id, difficulty, depth, status, stale, updated_at, created_at
        FROM artifacts
        ORDER BY updated_at DESC, created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_recent_exchanges(conn: sqlite3.Connection, limit: int = 6) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, session_id, goal_id, source_scope, concept_scope, mode, depth, evidence_strictness,
               question, answer, classification, learner_confidence, model_confidence, created_at
        FROM tutor_exchanges
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    items: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["source_scope"] = _load_scope(item["source_scope"])
        item["concept_scope"] = _load_scope(item["concept_scope"])
        items.append(item)
    return items


def _serialize_source(source: Dict[str, Any]) -> Dict[str, Any]:
    diagnostics = source.get("parser_diagnostics") or {}
    quality = diagnostics.get("quality") or {}
    return {
        "id": source["id"],
        "filename": source["filename"],
        "subject_name": source.get("subject_name"),
        "status": source.get("status"),
        "summary": source.get("summary"),
        "concept_count": source.get("concept_count", 0),
        "question_count": source.get("question_count", 0),
        "parser_status": source.get("parser_status"),
        "parser": quality.get("parser"),
        "warnings": quality.get("warnings", []),
        "preview_text": diagnostics.get("preview_text"),
    }


def fetch_workspace_state_v2(
    conn: sqlite3.Connection,
    *,
    get_setting,
    fetch_recent_events,
    fetch_subject_groups,
    fetch_documents,
    fetch_notes,
    fetch_graph,
    fetch_due_queue,
    fetch_exchange_evidence,
    list_sessions,
    goal_id: Optional[str] = None,
    source_ids: Optional[List[str]] = None,
    concept_ids: Optional[List[str]] = None,
    surface: str = "tutor",
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    goal_text = get_setting(conn, "learning_goal", "")
    momentum = build_momentum_engine(conn, fetch_recent_events)
    notes = fetch_notes(conn, limit=8)
    sources = [_serialize_source(item) for item in fetch_documents(conn)]
    sessions = list_sessions(conn, limit=6)
    recent_exchanges = fetch_recent_exchanges(conn, limit=4)
    active_exchange = None
    active_evidence: List[Dict[str, Any]] = []
    if recent_exchanges:
        active_exchange = recent_exchanges[0]
        active_evidence = fetch_exchange_evidence(conn, active_exchange["id"])

    concept_id = concept_ids[0] if concept_ids else momentum.get("focus_concept_id")
    related_concepts: List[Dict[str, Any]] = []
    if concept_id:
        rows = conn.execute(
            """
            SELECT c.id, c.name, c.mastery, c.description
            FROM concept_edges ce
            JOIN concepts c ON c.id = CASE WHEN ce.source_id = ? THEN ce.target_id ELSE ce.source_id END
            WHERE ce.source_id = ? OR ce.target_id = ?
            LIMIT 5
            """,
            (concept_id, concept_id, concept_id),
        ).fetchall()
        related_concepts = [
            {
                **dict(row),
                "raw_name": row["name"],
                "name": clean_concept_label(row["name"]),
            }
            for row in rows
        ]

    contradictions: List[Dict[str, Any]] = []
    if len({item["source_id"] for item in active_evidence if item.get("source_id")}) > 1:
        contradictions.append(
            {
                "label": "Cross-source tension check",
                "detail": "Multiple sources are supporting this answer. Compare the excerpts before treating them as identical.",
            }
        )

    review_queue = fetch_due_queue(
        conn,
        goal_id=goal_id,
        source_ids=source_ids,
        session_id=session_id,
        include_missed=True,
        limit=6,
    )
    graph = fetch_graph(conn, doc_id=source_ids[0] if source_ids and len(source_ids) == 1 else None)
    artifacts = fetch_artifacts(conn, limit=8)
    next_actions = momentum.get("actions", [])
    if review_queue:
        next_actions = [
            {
                "label": f"Review {len(review_queue)} due item{'s' if len(review_queue) != 1 else ''}",
                "type": "review",
                "concept_id": review_queue[0]["concept_id"],
            },
            *next_actions,
        ]

    center_payload: Dict[str, Any]
    if surface == "review":
        center_payload = {"queue": review_queue}
    elif surface == "concept":
        center_payload = {
            "graph": graph,
            "active_concept_id": concept_id,
            "related_concepts": related_concepts,
        }
    elif surface == "session":
        active_session = next(
            (item for item in sessions if item["status"] == "active"),
            sessions[0] if sessions else None,
        )
        center_payload = {
            "session": active_session,
            "recent_exchanges": recent_exchanges,
            "due_queue": review_queue[:3],
        }
    elif surface == "notes":
        center_payload = {"notes": notes}
    else:
        center_payload = {
            "active_exchange": active_exchange,
            "recent_exchanges": recent_exchanges,
            "goal": goal_text,
        }

    return {
        "scope": {
            "goal_id": goal_id,
            "source_ids": source_ids or [],
            "concept_ids": concept_ids or [],
            "surface": surface,
            "session_id": session_id,
            "source_scope_label": "selected_sources" if source_ids else "all_sources",
            "concept_scope_label": "selected_concepts" if concept_ids else "all_concepts",
        },
        "goal": goal_text,
        "momentum": momentum,
        "timeline": fetch_recent_events(conn, limit=10),
        "mastery": fetch_mastery_snapshot(conn, limit=8),
        "next_action": next_actions[0] if next_actions else None,
        "left_rail": {
            "sources": sources,
            "goals": fetch_goals(conn, fallback_goal=goal_text),
            "notes": notes,
            "sessions": sessions,
            "artifacts": artifacts,
            "filters": {
                "source_scope": source_ids or [],
                "concept_scope": concept_ids or [],
                "available_subjects": fetch_subject_groups(conn),
            },
        },
        "center_canvas": {
            "surface": surface,
            "payload": center_payload,
        },
        "right_rail": {
            "evidence": active_evidence,
            "confidence": {
                "model": active_exchange["model_confidence"] if active_exchange else None,
                "learner": active_exchange["learner_confidence"] if active_exchange else None,
                "evidence_count": len(active_evidence),
            },
            "contradictions": contradictions,
            "related_concepts": related_concepts,
            "next_actions": next_actions,
        },
        "compatibility": {
            "compareOptions": fetch_compare_options(conn),
            "subjects": fetch_subject_groups(conn),
        },
    }
