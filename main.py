from contextlib import asynccontextmanager
import logging
import os
import sqlite3

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import db as db_module
from app_logging import configure_backend_logging, get_logger, log_event
from app_runtime import resolve_runtime_paths
from routes import register_cachet_routes, register_routes
from services.local_api_security import (
    has_valid_local_api_token,
    requires_local_api_token,
)


RUNTIME_PATHS = resolve_runtime_paths()
BASE_DIR = RUNTIME_PATHS.base_dir
DATA_DIR = RUNTIME_PATHS.data_dir
UPLOAD_DIR = RUNTIME_PATHS.upload_dir
DB_PATH = RUNTIME_PATHS.db_path
SCHEMA_PATH = RUNTIME_PATHS.schema_path

configure_backend_logging(RUNTIME_PATHS.log_dir)
LOGGER = get_logger("main")


def _sync_runtime_paths() -> None:
    db_module.configure_paths(
        base_dir=BASE_DIR,
        data_dir=DATA_DIR,
        upload_dir=UPLOAD_DIR,
        db_path=DB_PATH,
        schema_path=SCHEMA_PATH,
    )


def get_db() -> sqlite3.Connection:
    _sync_runtime_paths()
    return db_module.get_db()


def initialize_database() -> None:
    _sync_runtime_paths()
    db_module.initialize_database()


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    from services.retrieval.backfill import maybe_run_backfill

    maybe_run_backfill()
    _resume_ingestion_jobs()
    _kick_startup_calendar_sync()
    log_event(
        LOGGER,
        logging.INFO,
        "backend_startup",
        base_dir=str(BASE_DIR),
        data_dir=str(DATA_DIR),
        db_path=str(DB_PATH),
    )
    try:
        yield
    finally:
        from services.calendar.sync_queue import shutdown_calendar_sync_queue

        shutdown_calendar_sync_queue()


def _kick_startup_calendar_sync() -> None:
    """Async refresh any stale calendar feed at app startup.

    Stale = last_synced_at is null OR > 30 minutes ago. Submitted to
    the same background pool used by /api/plan's SWR loop so we don't
    spawn a second pool. Errors are logged and swallowed; one bad feed
    must not block boot.
    """
    try:
        from routes.plan import _kick_background_sync
        from services.calendar import repository

        with db_module.get_db() as conn:
            stale = repository.list_stale_feeds(conn, threshold_minutes=30)

        for feed in stale:
            _kick_background_sync(feed.id)

        if stale:
            log_event(
                LOGGER,
                logging.INFO,
                "calendar_startup_sync_kicked",
                stale_feed_count=len(stale),
            )
    except Exception as exc:
        # Defensive: any failure here must not prevent app startup.
        log_event(
            LOGGER,
            logging.WARNING,
            "calendar_startup_sync_skipped",
            reason=exc.__class__.__name__,
        )


def _resume_ingestion_jobs() -> None:
    try:
        from services.jobs import resume_unfinished_jobs

        resume_unfinished_jobs()
    except Exception as exc:
        log_event(
            LOGGER,
            logging.WARNING,
            "jobs_resume_skipped",
            reason=exc.__class__.__name__,
        )


# Standalone-Cachet mode (CACHET_ONLY) serves only the verification product
# routes over the shared engine; the default mode serves the full Carrel app.
# One codebase, one engine, two products gated here.
_CACHET_ONLY = os.getenv("CACHET_ONLY", "").lower() in {"1", "true", "yes"}

app = FastAPI(title="Cachet" if _CACHET_ONLY else "Carrel", lifespan=lifespan)

# WKWebView loads via `loadFileURL`, which presents the page to fetch() as
# `null` origin. Every API call therefore triggers a CORS preflight; without
# `null` / `file://` in the allow list the browser blocks the request before
# the token middleware ever sees it. CORS is NOT the security boundary on
# the loopback API — the `X-Carrel-Local-Token` header is. A malicious local
# HTML file CAN preflight to 127.0.0.1, but it cannot mutate without the
# token, which it can no longer steal (route deleted, file mode 0600). So
# we keep the CORS allowlist wide for local origins and lean on the token.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^(https?://(localhost|127\.0\.0\.1)(:\d+)?|file://.*|null)$",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.middleware("http")
async def require_local_api_token(request: Request, call_next):
    if requires_local_api_token(request) and not has_valid_local_api_token(request):
        return JSONResponse(
            status_code=403,
            content={
                "detail": {
                    "code": "missing_or_invalid_local_api_token",
                    "message": "Local API requests require a valid Carrel token.",
                }
            },
        )
    return await call_next(request)


if _CACHET_ONLY:
    register_cachet_routes(app)
else:
    register_routes(app)
