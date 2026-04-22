from contextlib import asynccontextmanager
import logging
import sqlite3

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import db as db_module
from app_logging import configure_backend_logging, get_logger, log_event
from app_runtime import resolve_runtime_paths
from routes import register_routes


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
    log_event(
        LOGGER,
        logging.INFO,
        "backend_startup",
        base_dir=str(BASE_DIR),
        data_dir=str(DATA_DIR),
        db_path=str(DB_PATH),
    )
    yield


app = FastAPI(title="Einstein Tutor", lifespan=lifespan)

# The app ships bundled inside a macOS WKWebView loading file:// HTML and, in dev,
# is reached from localhost via uvicorn. Both surfaces produce a null / file origin
# or a loopback origin. No legitimate caller lives on a public origin, so we keep
# the allow-list tight instead of the previous ["*"].
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^(https?://(localhost|127\.0\.0\.1)(:\d+)?|file://.*|null)$",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


register_routes(app)
