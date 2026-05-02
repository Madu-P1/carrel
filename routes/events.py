from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, FastAPI, HTTPException, Query

import db
from api_models import UsageEventRequest, UsageEventResponse
from services.usage_events import list_recent_events, record_event


router = APIRouter()


@router.post("/api/usage-events", response_model=UsageEventResponse)
def track_usage_event(payload: UsageEventRequest) -> Dict[str, Any]:
    try:
        with db.get_db() as conn:
            return record_event(
                conn,
                event_name=payload.event_name,
                properties=payload.properties,
                surface=payload.surface,
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_usage_event", "message": str(exc)},
        ) from exc


@router.get("/api/usage-events/recent", response_model=List[UsageEventResponse])
def recent_usage_events(limit: int = Query(default=50, ge=1, le=200)) -> List[Dict[str, Any]]:
    with db.get_db() as conn:
        return list(list_recent_events(conn, limit=limit))


def register_event_routes(app: FastAPI) -> None:
    app.include_router(router)
