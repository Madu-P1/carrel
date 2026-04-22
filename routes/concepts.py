from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

import db
from api_models import CompareRequest
from services import graph as graph_service
from services import tutor as tutor_service
from services import workspace as workspace_service
from services.app_state import log_study_event
from services.helpers import build_explanation, concept_takeaway


router = APIRouter()


@router.get("/api/concepts/graph")
def concept_graph(
    doc_id: Optional[str] = None,
    subject_name: Optional[str] = None,
) -> Dict[str, List[Dict[str, object]]]:
    with db.get_db() as conn:
        return graph_service.fetch_graph(conn, doc_id=doc_id, subject_name=subject_name)


@router.get("/api/concepts/options")
def concept_options() -> List[Dict[str, str]]:
    with db.get_db() as conn:
        return workspace_service.fetch_compare_options(conn)


@router.get("/api/concepts/{concept_id}/explain")
def explain_concept(concept_id: str, level: int = 2) -> Dict[str, object]:
    with db.get_db() as conn:
        row = conn.execute(
            """
            SELECT c.id, c.doc_id, c.name AS concept, c.description, d.filename AS document_name, d.subject_name
            FROM concepts c
            JOIN documents d ON d.id = c.doc_id
            WHERE c.id = ?
            """,
            (concept_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Concept not found")
        description = row["description"] or row["concept"]
        claims = [
            dict(r)
            for r in conn.execute(
                "SELECT id, claim_text, claim_type, confidence FROM claims WHERE concept_id = ? ORDER BY confidence DESC LIMIT 5",
                (concept_id,),
            ).fetchall()
        ]
        examples = [
            dict(r)
            for r in conn.execute(
                "SELECT id, example_text, example_type, confidence FROM concept_examples WHERE concept_id = ? ORDER BY confidence DESC LIMIT 5",
                (concept_id,),
            ).fetchall()
        ]
        misconceptions = [
            dict(r)
            for r in conn.execute(
                "SELECT id, label, description, repair_strategy, confidence FROM misconceptions WHERE concept_id = ? ORDER BY confidence DESC LIMIT 5",
                (concept_id,),
            ).fetchall()
        ]
        return {
            "concept": row["concept"],
            "document_name": row["document_name"],
            "subject_name": row["subject_name"],
            "level": level,
            "explanation": build_explanation(description, level),
            "takeaway": concept_takeaway(description),
            "claims": claims,
            "examples": examples,
            "misconceptions": misconceptions,
        }


@router.post("/api/compare")
def compare_concepts(payload: CompareRequest) -> Dict[str, Any]:
    with db.get_db() as conn:
        result = tutor_service.compare_concepts_record(conn, payload.left_id, payload.right_id)
        log_study_event(
            conn,
            "compare_opened",
            concept_id=payload.left_id,
            payload={"right_id": payload.right_id},
        )
        return result


def register_concept_routes(app) -> None:
    app.include_router(router)
