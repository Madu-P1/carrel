import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

import db
from api_models import GoalRequest, SessionStartRequest, StudyEventRequest
from app_logging import get_logger, log_event
from services import graph as graph_service
from services import session_engine as session_service
from services import study as study_service
from services import workspace as workspace_service
from services.app_state import (
    build_stats,
    fetch_due_queue_v2,
    fetch_recent_events,
    fetch_workspace_state,
    get_setting,
    log_study_event,
    set_setting,
)
from services.documents import fetch_documents, fetch_subject_groups
from services.local_api_security import get_local_api_token
from services.provenance_service import fetch_exchange_evidence
from services.session_engine import list_sessions
from services.tutor import fetch_notes


LOGGER = get_logger("workspace_api")
router = APIRouter()


@router.get("/", response_model=None)
def root() -> FileResponse:
    return FileResponse(db.BASE_DIR / "index.html")


@router.get("/api/health")
def health() -> Dict[str, object]:
    with db.get_db() as conn:
        return {
            "status": "ok",
            "mode": "local",
            "documents": len(fetch_documents(conn)),
            "paths": {
                "base_dir": str(db.BASE_DIR),
                "db_path": str(db.DB_PATH),
            },
        }


@router.get("/api/bootstrap")
def bootstrap() -> Dict[str, object]:
    with db.get_db() as conn:
        return {
            "documents": fetch_documents(conn),
            "questions": study_service.fetch_questions(conn),
            "dueCards": study_service.fetch_due_cards(conn),
            "graph": graph_service.fetch_graph(conn),
            "stats": build_stats(conn),
            "workspace": fetch_workspace_state(conn),
        }


@router.get("/api/local-token")
def local_token() -> Dict[str, str]:
    return {"token": get_local_api_token()}


@router.get("/api/workspace")
def workspace_state() -> Dict[str, Any]:
    with db.get_db() as conn:
        return fetch_workspace_state(conn)


@router.get("/api/workspace/v2")
def workspace_state_v2(
    goal_id: Optional[str] = None,
    source_ids: Optional[List[str]] = Query(default=None),
    concept_ids: Optional[List[str]] = Query(default=None),
    surface: str = "tutor",
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    with db.get_db() as conn:
        return workspace_service.fetch_workspace_state_v2(
            conn,
            get_setting=get_setting,
            fetch_recent_events=fetch_recent_events,
            fetch_subject_groups=fetch_subject_groups,
            fetch_documents=fetch_documents,
            fetch_notes=fetch_notes,
            fetch_graph=graph_service.fetch_graph,
            fetch_due_queue=fetch_due_queue_v2,
            fetch_exchange_evidence=fetch_exchange_evidence,
            list_sessions=list_sessions,
            goal_id=goal_id,
            source_ids=source_ids,
            concept_ids=concept_ids,
            surface=surface,
            session_id=session_id,
        )


@router.post("/api/goal")
def update_goal(payload: GoalRequest) -> Dict[str, Any]:
    with db.get_db() as conn:
        clean_goal = payload.goal.strip()
        set_setting(conn, "learning_goal", clean_goal)
        if clean_goal:
            conn.execute(
                """
                INSERT INTO goals (id, title, description, status)
                VALUES ('current-goal', ?, 'Current workspace goal', 'active')
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    description = excluded.description,
                    status = excluded.status,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (clean_goal,),
            )
        log_study_event(conn, "goal_updated", payload={"goal": clean_goal})
        return fetch_workspace_state(conn)


@router.post("/api/events")
def create_study_event(payload: StudyEventRequest) -> Dict[str, Any]:
    with db.get_db() as conn:
        log_study_event(
            conn,
            payload.event_type,
            doc_id=payload.doc_id,
            concept_id=payload.concept_id,
            confidence=payload.confidence,
            duration_seconds=payload.duration_seconds,
            payload=payload.payload,
        )
        return {"status": "logged", "workspace": fetch_workspace_state(conn)}


@router.get("/api/sessions/active")
def get_active_session() -> Dict[str, Any]:
    """Return the current active session, or an empty envelope.

    Used by the Dashboard's status card to refetch after any session
    mutation (start or complete). Separate from the full session list
    because the Dashboard only needs the one active row — serializing
    everything every time would be wasteful.

    Abandonment: rows with `status='active'` but `started_at` older than
    ACTIVE_SESSION_MAX_AGE_HOURS are treated as dormant and NOT returned.
    This mirrors services.dashboard._active_session so both endpoints
    agree on what "active" means. Without the filter, a closed-then-
    reopened app would show a 96-hour timer on a session the user
    already forgot about.

    Defensive: multiple eligible rows → return the most recent.
    """
    from services.dashboard import ACTIVE_SESSION_MAX_AGE_HOURS
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(hours=ACTIVE_SESSION_MAX_AGE_HOURS)
    # Match the T-separator + microseconds format that
    # services.session_engine writes via datetime.now().isoformat().
    # Space-separator cutoffs broke SQLite lexical TEXT comparison
    # (`T` > ` `), so every active row passed the cutoff check
    # regardless of age. Same fix applied in
    # services.dashboard._active_session.
    cutoff_iso = cutoff.isoformat()
    with db.get_db() as conn:
        row = conn.execute(
            """
            SELECT id, goal_id, objective, source_scope, concept_scope,
                   difficulty_target, duration_minutes, mode, status, started_at
            FROM sessions
            WHERE status = 'active'
              AND started_at IS NOT NULL
              AND started_at >= ?
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (cutoff_iso,),
        ).fetchone()
    if not row:
        return {"active_session": None}
    return {
        "active_session": {
            "id": row["id"],
            "goal_id": row["goal_id"],
            "objective": row["objective"],
            "mode": row["mode"],
            "duration_minutes": int(row["duration_minutes"] or 0),
            "difficulty_target": row["difficulty_target"],
            "started_at": row["started_at"],
            "status": row["status"],
        }
    }


@router.post("/api/sessions")
def create_session(payload: SessionStartRequest) -> Dict[str, Any]:
    with db.get_db() as conn:
        result = session_service.start_session(
            conn,
            goal_id=payload.goal_id,
            source_scope=payload.source_scope,
            concept_scope=payload.concept_scope,
            difficulty_target=payload.difficulty_target,
            duration_minutes=payload.duration_minutes,
            mode=payload.mode,
            objective=payload.objective,
        )
        log_study_event(
            conn,
            "session_started",
            concept_id=(payload.concept_scope or [None])[0],
            payload={
                "objective": payload.objective,
                "duration_minutes": payload.duration_minutes,
                "mode": payload.mode,
            },
        )
        conn.commit()
        return result


@router.post("/api/sessions/{session_id}/complete")
def complete_session(session_id: str) -> Dict[str, Any]:
    with db.get_db() as conn:
        result = session_service.complete_session(
            conn,
            session_id,
            fetch_due_queue=fetch_due_queue_v2,
            build_momentum_engine=lambda inner_conn: workspace_service.build_momentum_engine(
                inner_conn,
                fetch_recent_events=fetch_recent_events,
            ),
        )
        log_study_event(
            conn,
            "session_completed",
            payload={
                "session_id": session_id,
                "mastery_delta": result["mastery_delta"],
                "due_queue_count": result["due_queue_count"],
            },
        )
        conn.commit()
        return result


def register_workspace_routes(app) -> None:
    app.include_router(router)
