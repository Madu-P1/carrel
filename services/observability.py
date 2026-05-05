"""Lightweight observability — request ID, metrics, optional Sentry.

Designed for a desktop app, not a SaaS:
  * Request-ID middleware — assigns / propagates `X-Request-ID`,
    threads it through the JSON logger via contextvars so every log
    line emitted during the request is tagged with the same id.
  * In-process metrics — counters + duration buckets keyed by
    (route, method, status). Exposed at `/api/metrics` as JSON. No
    Prometheus dependency; the desktop never needs a scrape target.
  * Sentry — opt-in via `SENTRY_DSN` env var. The SDK is imported
    lazily; absence is non-fatal so dev installs don't need the
    extra dep.
"""

from __future__ import annotations

import contextvars
import os
import time
import uuid
from collections import defaultdict
from threading import Lock
from typing import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from app_logging import get_logger


REQUEST_ID_HEADER = "X-Request-ID"
LOGGER = get_logger("observability")

# Thread/coroutine-local request id. Read by JsonFormatter via the
# `request_id` LogRecord attr we set in the middleware.
request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "carrel_request_id", default=None,
)


# --- Metrics ---------------------------------------------------------------

class _Metrics:
    """In-memory counters + duration buckets, thread-safe.

    Bucket layout matches Prometheus conventions so we can swap to a
    real exporter later without changing call sites:
      counter[(route, method, status)] -> int
      duration_ms_sum[(route, method)] -> float
      duration_ms_count[(route, method)] -> int
      duration_ms_buckets[(route, method)] -> {le: count}
    """

    BUCKETS_MS = (5, 10, 25, 50, 100, 250, 500, 1_000, 2_500, 5_000, 10_000)

    def __init__(self) -> None:
        self._lock = Lock()
        self.requests: dict[tuple[str, str, int], int] = defaultdict(int)
        self.duration_sum: dict[tuple[str, str], float] = defaultdict(float)
        self.duration_count: dict[tuple[str, str], int] = defaultdict(int)
        self.duration_buckets: dict[tuple[str, str], dict[int, int]] = defaultdict(
            lambda: {b: 0 for b in self.BUCKETS_MS}
        )
        # Process-level: never reset across requests.
        self.started_at = time.monotonic()

    def observe(self, route: str, method: str, status: int, duration_ms: float) -> None:
        with self._lock:
            self.requests[(route, method, status)] += 1
            self.duration_sum[(route, method)] += duration_ms
            self.duration_count[(route, method)] += 1
            buckets = self.duration_buckets[(route, method)]
            for bucket in self.BUCKETS_MS:
                if duration_ms <= bucket:
                    buckets[bucket] += 1

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "uptime_seconds": round(time.monotonic() - self.started_at, 1),
                "requests": [
                    {
                        "route": route,
                        "method": method,
                        "status": status,
                        "count": count,
                    }
                    for (route, method, status), count in sorted(self.requests.items())
                ],
                "duration_ms": [
                    {
                        "route": route,
                        "method": method,
                        "count": self.duration_count[(route, method)],
                        "avg": round(
                            self.duration_sum[(route, method)]
                            / max(1, self.duration_count[(route, method)]),
                            2,
                        ),
                        "buckets": dict(self.duration_buckets[(route, method)]),
                    }
                    for (route, method) in sorted(self.duration_count.keys())
                ],
            }


metrics = _Metrics()


def _route_of(request: Request) -> str:
    """Match the request to its route template so `/api/documents/123`
    and `/api/documents/456` collapse into one bucket. Falls back to
    the raw path when the router didn't bind the request (404)."""
    route = request.scope.get("route")
    template = getattr(route, "path", None)
    if isinstance(template, str) and template:
        return template
    return request.url.path


# --- Middleware ------------------------------------------------------------

async def request_id_and_metrics_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    incoming = request.headers.get(REQUEST_ID_HEADER)
    rid = incoming if incoming else uuid.uuid4().hex
    token = request_id_var.set(rid)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        # Record the failure as a 500 so dashboards see it; re-raise
        # so FastAPI's exception handlers still run.
        elapsed_ms = (time.perf_counter() - started) * 1_000
        metrics.observe(_route_of(request), request.method, 500, elapsed_ms)
        request_id_var.reset(token)
        raise
    elapsed_ms = (time.perf_counter() - started) * 1_000
    metrics.observe(_route_of(request), request.method, response.status_code, elapsed_ms)
    response.headers[REQUEST_ID_HEADER] = rid
    request_id_var.reset(token)
    return response


# --- Endpoints -------------------------------------------------------------

def metrics_endpoint() -> JSONResponse:
    """Exposed at `/api/metrics`. No auth gate (intentional — the
    middleware allowlist would have to be extended; for now treat
    metrics as world-readable on the local machine)."""
    return JSONResponse(metrics.snapshot())


# --- Sentry ----------------------------------------------------------------

def init_sentry() -> bool:
    """Initialize Sentry if `SENTRY_DSN` is set and the SDK is
    installed. Returns True if active. Safe to call multiple times."""
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
    except ImportError:
        LOGGER.warning(
            "SENTRY_DSN set but sentry-sdk not installed; "
            "run `pip install sentry-sdk[fastapi]` to enable."
        )
        return False
    sentry_sdk.init(
        dsn=dsn,
        integrations=[StarletteIntegration(), FastApiIntegration()],
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        environment=os.getenv("CARREL_ENV", "local"),
        release=os.getenv("CARREL_VERSION") or _read_version_file(),
    )
    LOGGER.info("Sentry initialized")
    return True


def _read_version_file() -> str | None:
    from pathlib import Path
    version_path = Path(__file__).resolve().parent.parent / "VERSION"
    try:
        return version_path.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None
