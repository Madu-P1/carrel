"""Dashboard route.

Thin wrapper around services.dashboard.build_dashboard_payload. Single
endpoint because the Dashboard view needs every metric at once — one
round trip beats four.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

import db
from services.dashboard import build_dashboard_payload

router = APIRouter()


@router.get("/api/dashboard")
def dashboard_payload() -> Dict[str, Any]:
    with db.get_db() as conn:
        return build_dashboard_payload(conn)


def register_dashboard_routes(app) -> None:
    app.include_router(router)
