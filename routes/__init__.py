from routes.briefs import register_briefs_routes
from routes.calendar import register_calendar_routes
from routes.documents import register_document_routes
from routes.evidence import register_evidence_routes
from routes.events import register_event_routes
from routes.jobs import register_job_routes
from routes.plan import register_plan_routes
from routes.reader_nodes import register_reader_node_routes
from routes.study import register_study_routes
from routes.system import register_system_routes
from routes.tutor import register_tutor_routes
from routes.verify import register_verify_routes
from routes.workspace import register_workspace_routes


def register_routes(app) -> None:
    register_workspace_routes(app)
    register_document_routes(app)
    register_study_routes(app)
    register_tutor_routes(app)
    # Carrel V2 Stage 1 — Verify-mode endpoint over the existing
    # grounded-tutor engine. See services/verify.py + ADR-0006.
    register_verify_routes(app)
    # Cachet PR6 — Shelf persistence (saved briefs) over services.briefs.
    register_briefs_routes(app)
    register_evidence_routes(app)
    register_event_routes(app)
    register_job_routes(app)
    register_system_routes(app)
    # Reader-side typed-node lookup (PR 4.2). Powers ?node=N deep links.
    register_reader_node_routes(app)
    # Calendar-driven study planning (Phase 1: feed sync + stub coach).
    register_calendar_routes(app)
    register_plan_routes(app)
