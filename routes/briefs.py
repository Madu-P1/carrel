"""Cachet PR6 — Shelf persistence routes.

CRUD over saved briefs (the Shelf). Thin wrappers over services.briefs;
the persistence work happens there. All four endpoints sit under /api/*,
so the existing local-API-token gate covers them automatically.

    GET    /api/briefs            list summaries, most-recent-first
    POST   /api/briefs            save one checked draft
    GET    /api/briefs/{id}       full brief for re-hydration
    DELETE /api/briefs/{id}       remove a brief the user owns

Deleting is the user removing their own saved row through an app
affordance — ordinary app behavior, not the privileged "permanently
delete data" class. A missing id maps to a clean 404.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

import db
from api_models import (
    BriefDeleteResponse,
    BriefDetail,
    BriefListResponse,
    BriefSaveRequest,
    BriefSaveResponse,
)
from services import briefs as briefs_service

router = APIRouter()


@router.get("/api/briefs", response_model=BriefListResponse)
def list_briefs_endpoint() -> Dict[str, Any]:
    with db.get_db() as conn:
        return {"briefs": briefs_service.list_briefs(conn)}


@router.post("/api/briefs", response_model=BriefSaveResponse)
def save_brief_endpoint(payload: BriefSaveRequest) -> Dict[str, Any]:
    with db.get_db() as conn:
        brief = briefs_service.save_brief(
            conn,
            draft=payload.draft,
            fingerprint=payload.fingerprint,
            response=payload.response,
            cert=payload.cert,
            seal_state=payload.seal_state,
            title=payload.title,
        )
        return {"brief": brief}


@router.get("/api/briefs/{brief_id}", response_model=BriefDetail)
def get_brief_endpoint(brief_id: str) -> Dict[str, Any]:
    with db.get_db() as conn:
        brief = briefs_service.get_brief(conn, brief_id)
        if brief is None:
            raise HTTPException(status_code=404, detail="Brief not found.")
        return brief


@router.delete("/api/briefs/{brief_id}", response_model=BriefDeleteResponse)
def delete_brief_endpoint(brief_id: str) -> Dict[str, Any]:
    with db.get_db() as conn:
        ok = briefs_service.delete_brief(conn, brief_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Brief not found.")
        return {"deleted": True, "brief_id": brief_id}


def register_briefs_routes(app) -> None:
    app.include_router(router)
