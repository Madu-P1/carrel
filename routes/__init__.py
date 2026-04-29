from routes.calendar import register_calendar_routes
from routes.concepts import register_concept_routes
from routes.dashboard import register_dashboard_routes
from routes.documents import register_document_routes
from routes.evidence import register_evidence_routes
from routes.exports import register_export_routes
from routes.plan import register_plan_routes
from routes.studio import register_studio_routes
from routes.study import register_study_routes
from routes.synthesis import register_synthesis_routes
from routes.system import register_system_routes
from routes.tutor import register_tutor_routes
from routes.workspace import register_workspace_routes


def register_routes(app) -> None:
    register_workspace_routes(app)
    register_document_routes(app)
    register_concept_routes(app)
    register_study_routes(app)
    register_tutor_routes(app)
    register_studio_routes(app)
    register_synthesis_routes(app)
    register_evidence_routes(app)
    register_export_routes(app)
    register_system_routes(app)
    register_dashboard_routes(app)
    # Calendar-driven study planning (Phase 1: feed sync + stub coach).
    register_calendar_routes(app)
    register_plan_routes(app)
