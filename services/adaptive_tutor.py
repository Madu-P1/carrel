import json
import sqlite3
import uuid
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from services import mastery_engine
from services import provenance_service
from services import tutor as tutor_service
from services.documents import clean_concept_label
from services.helpers import tokenize


def _pick_first(values: Optional[List[str]]) -> Optional[str]:
    return values[0] if values else None


def _payload_adapter(payload: Any):
    class Adapter:
        question = payload.question
        doc_id = _pick_first(getattr(payload, "source_scope", None))
        concept_id = _pick_first(getattr(payload, "concept_scope", None))
        subject_name = getattr(payload, "subject_name", None)
        selected_text = getattr(payload, "selected_text", None)
        confidence = getattr(payload, "learner_confidence", None)
        response_mode = getattr(payload, "response_mode", "standard")

    return Adapter()


def _related_concepts(conn: sqlite3.Connection, concept_id: Optional[str]) -> List[Dict[str, Any]]:
    if not concept_id:
        return []
    rows = conn.execute(
        """
        SELECT c.id, c.name, c.mastery, ce.relationship
        FROM concept_edges ce
        JOIN concepts c ON c.id = ce.target_id
        WHERE ce.source_id = ?
        UNION
        SELECT c.id, c.name, c.mastery, ce.relationship
        FROM concept_edges ce
        JOIN concepts c ON c.id = ce.source_id
        WHERE ce.target_id = ?
        LIMIT 4
        """,
        (concept_id, concept_id),
    ).fetchall()
    return [
        {
            **dict(row),
            "raw_name": row["name"],
            "name": clean_concept_label(row["name"]),
        }
        for row in rows
    ]


def _normalize_classification(label: str) -> str:
    return label.replace(" ", "_")


def classify_learner_response(answer: str, learner_response: str) -> str:
    cleaned = learner_response.strip()
    if len(cleaned.split()) < 5:
        return "omission"

    answer_tokens = set(tokenize(answer))
    learner_tokens = set(tokenize(cleaned))
    overlap = len(answer_tokens & learner_tokens)
    overlap_ratio = overlap / max(len(answer_tokens), 1)
    lowered = cleaned.lower()

    if any(token in lowered for token in ["always", "never", "only", "exactly the same"]):
        return "misconception"
    if "for example" in lowered and overlap_ratio < 0.25:
        return "wrong_example"
    if (
        any(token in lowered for token in ["causes", "because", "leads to", "depends on"])
        and overlap_ratio < 0.3
    ):
        return "wrong_relation"
    if overlap_ratio >= 0.55 and len(cleaned.split()) >= 20:
        return "robust_and_transferable"
    if overlap_ratio >= 0.3:
        return "shallow_but_correct"
    return "misconception"


def _repair_path(label: str) -> Dict[str, Any]:
    mapping = {
        "omission": {
            "surface": "tutor",
            "strategy": "concise_recap",
            "next_action": "Read the evidence excerpt, then restate the idea in one sentence.",
            "schedule_in_minutes": 90,
        },
        "misconception": {
            "surface": "concept",
            "strategy": "contrastive_explanation",
            "next_action": "Contrast the current answer with the cited passage and one counterexample.",
            "schedule_in_minutes": 20,
        },
        "wrong_relation": {
            "surface": "concept",
            "strategy": "causal_visual",
            "next_action": "Trace the dependency between the linked concepts before answering again.",
            "schedule_in_minutes": 30,
        },
        "wrong_example": {
            "surface": "tutor",
            "strategy": "corrected_example",
            "next_action": "Study the corrected example and explain why the original example missed the mechanism.",
            "schedule_in_minutes": 180,
        },
        "shallow_but_correct": {
            "surface": "review",
            "strategy": "application_probe",
            "next_action": "Answer one application question without rereading the excerpt.",
            "schedule_in_minutes": 2880,
        },
        "robust_and_transferable": {
            "surface": "review",
            "strategy": "promote_interval",
            "next_action": "Promote this concept to a longer spaced interval.",
            "schedule_in_minutes": 10080,
        },
    }
    return mapping[label]


def run_exchange(
    conn: sqlite3.Connection,
    payload: Any,
    *,
    log_study_event,
    fetch_recent_events,
) -> Dict[str, Any]:
    adapter = _payload_adapter(payload)
    response = tutor_service.grounded_tutor_envelope(
        conn,
        adapter,
        log_study_event=log_study_event,
        fetch_recent_events=fetch_recent_events,
    )
    concept_id = _pick_first(getattr(payload, "concept_scope", None))
    evidence = provenance_service.persist_evidence_references(
        conn,
        response.get("citations", []),
        concept_id=concept_id,
    )
    exchange_id = str(uuid.uuid4())
    model_confidence = min(0.96, 0.42 + (len(evidence) * 0.13))
    conn.execute(
        """
        INSERT INTO tutor_exchanges (
            id, session_id, goal_id, source_scope, concept_scope, mode, depth, evidence_strictness,
            question, answer, classification, learner_confidence, model_confidence
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            exchange_id,
            getattr(payload, "session_id", None),
            getattr(payload, "goal_id", None),
            json.dumps(getattr(payload, "source_scope", None) or []),
            json.dumps(getattr(payload, "concept_scope", None) or []),
            getattr(payload, "mode", "tutor"),
            getattr(payload, "depth", "standard"),
            getattr(payload, "evidence_strictness", "normal"),
            payload.question,
            response["answer"],
            None,
            getattr(payload, "learner_confidence", None),
            model_confidence,
        ),
    )
    for item in evidence:
        conn.execute(
            """
            INSERT OR IGNORE INTO tutor_exchange_evidence (exchange_id, evidence_reference_id)
            VALUES (?, ?)
            """,
            (exchange_id, item["id"]),
        )
    related_concepts = _related_concepts(conn, concept_id)
    next_actions = [
        {"type": "note", "label": "Save as note", "exchange_id": exchange_id},
        {"type": "flashcard", "label": "Convert to flashcard", "exchange_id": exchange_id},
        {"type": "quiz", "label": "Convert to quiz item", "exchange_id": exchange_id},
    ]
    return {
        "exchange_id": exchange_id,
        "answer": response["answer"],
        "mode": getattr(payload, "mode", "tutor"),
        "classification": None,
        "confidence": round(model_confidence, 2),
        "evidence": evidence,
        "citations": response.get("citations", []),
        "source_cards": response.get("source_cards", []),
        "scaffolds": response.get("scaffolds", []),
        "misconceptions": response.get("misconceptions", []),
        "related_concepts": related_concepts,
        "actions": next_actions,
        "next_actions": next_actions,
        "selected_concept": response.get("selected_concept"),
        "momentum": response.get("momentum"),
    }


def evaluate_exchange(
    conn: sqlite3.Connection,
    exchange_id: str,
    *,
    learner_response: str,
    mode: str,
) -> Dict[str, Any]:
    row = conn.execute(
        """
        SELECT id, concept_scope, answer, question, session_id, goal_id, learner_confidence
        FROM tutor_exchanges
        WHERE id = ?
        """,
        (exchange_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Tutor exchange not found.")

    classification = classify_learner_response(row["answer"] or "", learner_response)
    conn.execute(
        "UPDATE tutor_exchanges SET classification = ? WHERE id = ?",
        (classification, exchange_id),
    )
    evidence = provenance_service.fetch_exchange_evidence(conn, exchange_id)
    concept_scope = json.loads(row["concept_scope"] or "[]")
    repair_path = _repair_path(classification)
    mastery_state = None
    concept_id = _pick_first(concept_scope)
    if concept_id:
        mastery_state = mastery_engine.update_mastery_state(
            conn,
            concept_id,
            goal_id=row["goal_id"],
            session_id=row["session_id"],
            classification=classification,
            learner_confidence=row["learner_confidence"],
            evidence_quality=0.8 if evidence else 0.45,
        )
        doc_row = conn.execute("SELECT doc_id FROM concepts WHERE id = ?", (concept_id,)).fetchone()
        misconception_count = (
            1 if classification in {"misconception", "wrong_relation", "wrong_example"} else 0
        )
        conn.execute(
            """
            INSERT INTO study_events (id, event_type, doc_id, concept_id, confidence, payload)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                "tutor_exchange_evaluated",
                doc_row["doc_id"] if doc_row else None,
                concept_id,
                row["learner_confidence"],
                json.dumps(
                    {
                        "exchange_id": exchange_id,
                        "classification": classification,
                        "misconception_count": misconception_count,
                    }
                ),
            ),
        )
    return {
        "classification": classification,
        "repair_path": {
            "surface": repair_path["surface"],
            "strategy": repair_path["strategy"],
            "next_action": repair_path["next_action"],
            "mode": mode,
        },
        "revisit": {"schedule_in_minutes": repair_path["schedule_in_minutes"]},
        "evidence": evidence,
        "mastery_state": mastery_state,
        "next_actions": [
            {
                "type": "review",
                "label": repair_path["next_action"],
                "concept_id": concept_id,
            }
        ],
    }
