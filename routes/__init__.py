import db

from routes.cachet_web import register_cachet_web_routes
from routes.anchors import register_anchor_routes
from routes.ask_cards import register_ask_cards_routes
from routes.briefs import register_briefs_routes
from routes.calendar import register_calendar_routes
from routes.concepts import register_concept_routes
from routes.documents import register_document_routes
from routes.evidence import register_evidence_routes
from routes.events import register_event_routes
from routes.jobs import register_job_routes
from routes.plan import register_plan_routes
from routes.reader_nodes import register_reader_node_routes
from routes.search import register_search_routes
from routes.studio import register_studio_routes
from routes.study import register_study_routes
from routes.synthesis import register_synthesis_routes
from routes.system import register_system_routes
from routes.tutor import register_tutor_routes
from routes.verify import register_verify_routes
from routes.workspace import register_workspace_routes


def register_routes(app) -> None:
    register_workspace_routes(app)
    register_document_routes(app)
    register_concept_routes(app)
    register_study_routes(app)
    register_tutor_routes(app)
    # Carrel V2 Stage 1 — Verify-mode endpoint over the existing
    # grounded-tutor engine. See services/verify.py + ADR-0006.
    register_verify_routes(app)
    # Cachet PR6 — Shelf persistence (saved briefs) over services.briefs.
    register_briefs_routes(app)
    register_anchor_routes(app)
    register_studio_routes(app)
    register_synthesis_routes(app)
    register_evidence_routes(app)
    register_event_routes(app)
    register_job_routes(app)
    register_system_routes(app)
    # Hybrid (FTS + vector) library search. Wraps services.retrieval.
    register_search_routes(app)
    # Free-tier Ask cards over the typed-node retrieval path (PR 4).
    register_ask_cards_routes(app)
    # Reader-side typed-node lookup (PR 4.2). Powers ?node=N deep links.
    register_reader_node_routes(app)
    # Calendar-driven study planning (Phase 1: feed sync + stub coach).
    register_calendar_routes(app)
    register_plan_routes(app)


def register_cachet_routes(app) -> None:
    """Standalone-Cachet route set: only the verification product surfaces over
    the shared engine. No Carrel features (study, plan, calendar, notes,
    concepts, dashboard, ask, anchors, studio, synthesis, events, evidence,
    onboarding, workspace, reader). Used when CACHET_ONLY is set so the Cachet
    backend exposes nothing but Verify, the Shelf, Sources, and health. The
    shared services / db / migrations are unchanged; this only gates what the
    app serves, so the two products stay one codebase over one engine."""
    register_system_routes(app)  # health + provider status
    register_document_routes(app)  # Sources: ingest the record to verify against
    register_job_routes(app)  # ingestion job status for Sources
    register_search_routes(app)  # hybrid retrieval over the loaded sources
    register_verify_routes(app)  # the product
    register_briefs_routes(app)  # the Shelf

    # Serve the built frontend over loopback so the app runs in the user's own
    # browser (cross-platform delivery), injecting the local-API token into the
    # served HTML. Ungated (non-/api/ paths); protected by the loopback Host
    # guard installed in main.py. See docs/plans/cachet-localhost-browser-2026-06-05.md.
    register_cachet_web_routes(app)

    # /api/health lives in workspace.py alongside Carrel's workspace/srs routes,
    # which Cachet does not serve. Register the liveness probe directly so the
    # backend supervisor and the frontend's offline check work without pulling in
    # Carrel surface. Cheap and DB-free, matching the workspace health contract.
    @app.get("/api/health")
    def _cachet_health() -> dict:
        return {
            "status": "ok",
            "mode": "local",
            "paths": {"base_dir": str(db.BASE_DIR), "db_path": str(db.DB_PATH)},
        }
