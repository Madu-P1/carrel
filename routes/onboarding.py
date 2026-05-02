from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, FastAPI, Query

import db
from api_models import DemoLibrarySeedResponse
from services.onboarding import seed_demo_library


router = APIRouter()


@router.post("/api/onboarding/demo-library", response_model=DemoLibrarySeedResponse)
def seed_demo_library_route(force: bool = Query(default=False)) -> Dict[str, Any]:
    with db.get_db() as conn:
        return seed_demo_library(conn, force=force)


def register_onboarding_routes(app: FastAPI) -> None:
    app.include_router(router)
