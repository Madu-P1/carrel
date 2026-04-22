"""Evidence API routes — fetch evidence references for the evidence rail."""
from fastapi import Query
from typing import List, Optional

from db import get_db
from services import provenance_service
from services import stale_tracker


def register_evidence_routes(app) -> None:

    @app.get("/api/evidence")
    def get_evidence(
        concept_id: Optional[str] = Query(None),
        source_id: Optional[str] = Query(None),
        limit: int = Query(12),
    ):
        with get_db() as conn:
            if concept_id:
                evidence = provenance_service.fetch_evidence_for_concept(conn, concept_id, limit=limit)
            elif source_id:
                evidence = provenance_service.fetch_evidence_for_source(conn, source_id, limit=limit)
            else:
                evidence = provenance_service.fetch_recent_evidence(conn, limit=limit)
            return {"evidence": evidence}

    @app.get("/api/evidence/concept/{concept_id}")
    def get_evidence_for_concept(concept_id: str, limit: int = Query(10)):
        with get_db() as conn:
            return {"evidence": provenance_service.fetch_evidence_for_concept(conn, concept_id, limit=limit)}

    @app.get("/api/evidence/source/{source_id}")
    def get_evidence_for_source(source_id: str, limit: int = Query(12)):
        with get_db() as conn:
            return {"evidence": provenance_service.fetch_evidence_for_source(conn, source_id, limit=limit)}

    @app.get("/api/evidence/artifact/{artifact_id}")
    def get_evidence_for_artifact(artifact_id: str):
        with get_db() as conn:
            return {"evidence": provenance_service.fetch_artifact_evidence(conn, artifact_id)}

    @app.get("/api/stale/warnings")
    def get_stale_warnings(limit: int = Query(10)):
        with get_db() as conn:
            warnings = stale_tracker.get_stale_warnings(conn, limit=limit)
            stale_artifacts = stale_tracker.get_stale_artifacts(conn, limit=limit)
            return {"warnings": warnings, "stale_artifacts": stale_artifacts}

    @app.get("/api/stale/check/{source_id}")
    def check_stale_for_source(source_id: str):
        with get_db() as conn:
            stale_items = stale_tracker.check_stale(conn, source_id)
            conn.commit()
            return {"stale_count": len(stale_items), "stale_items": stale_items}
