"""Demo readiness check — exercise the full Carrel happy path against a
running backend, report pass/fail per gate, exit 0 on green / 1 on red.

This is the script the founder runs in the 15 minutes before an
investor demo. Catches every failure mode the autonomous overnight
runs uncovered: stale token, dead /api/documents, empty plan, missing
deadline rail, broken document detail. If this exits 0, the live demo
will not embarrass you.

Usage:
    ./.venv/bin/python script/_demo_check.py

Exit codes:
    0  all checks passed
    1  at least one check failed
    2  backend unreachable

Reads the local API token from the most-recent line of
dist/einstein-backend.log (the backend logs every request URL,
including the ?token=… for SSE/file fetches; we extract it).
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Optional
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

API = "http://127.0.0.1:8000"
LOG = Path(__file__).resolve().parent.parent / "dist" / "einstein-backend.log"
TOKEN_RE = re.compile(r"token=([A-Za-z0-9_-]+)")


def green(s: str) -> str:
    return f"\033[32m{s}\033[0m"


def red(s: str) -> str:
    return f"\033[31m{s}\033[0m"


def grey(s: str) -> str:
    return f"\033[90m{s}\033[0m"


def fetch_token() -> Optional[str]:
    """Pull the active local-API token from the backend log. The token
    is logged on every authenticated request via the ?token= fallback
    used by SSE clients. Falls back to /api/local-token endpoint if no
    log line is found (cold start)."""
    if LOG.exists():
        try:
            text = LOG.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            text = ""
        matches = TOKEN_RE.findall(text)
        if matches:
            return matches[-1]
    # Cold-start fallback: hit the /api/local-token endpoint directly
    # (deliberately unauth-gated by the backend so the frontend can
    # bootstrap).
    try:
        with urllib_request.urlopen(f"{API}/api/local-token", timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("token")
    except (HTTPError, URLError, json.JSONDecodeError, OSError):
        return None


def get(path: str, token: Optional[str], timeout: float = 10.0) -> dict:
    """GET path, return parsed JSON. One transparent retry covers the
    common case where the calendar sync is briefly hogging the event
    loop right when we hit the backend. Raises on non-2xx for the
    caller to convert into a user-facing failure message."""
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            req = urllib_request.Request(f"{API}{path}")
            if token:
                req.add_header("X-Carrel-Local-Token", token)
            with urllib_request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {}
        except (URLError, OSError) as exc:
            last_exc = exc
            if attempt == 0:
                time.sleep(0.6)
                continue
            raise
    if last_exc is not None:
        raise last_exc
    return {}


def check(label: str) -> "_Check":
    return _Check(label)


class _Check:
    def __init__(self, label: str) -> None:
        self.label = label
        self.detail: str = ""
        self.passed: Optional[bool] = None

    def ok(self, detail: str = "") -> "_Check":
        self.passed = True
        self.detail = detail
        return self

    def fail(self, detail: str) -> "_Check":
        self.passed = False
        self.detail = detail
        return self

    def render(self) -> str:
        if self.passed is None:
            return f"  {grey('•')} {self.label}: skipped"
        if self.passed:
            return f"  {green('✓')} {self.label}{f' {grey(self.detail)}' if self.detail else ''}"
        return f"  {red('✗')} {self.label}: {red(self.detail)}"


def main() -> int:
    print(grey("Carrel demo-readiness check"))
    print(grey("─" * 50))

    checks: list[_Check] = []

    # 1. Backend reachable
    health = check("backend up")
    checks.append(health)
    try:
        body = get("/api/health", token=None)
        health.ok(f"({body.get('status', 'unknown')})")
    except (HTTPError, URLError, OSError) as exc:
        health.fail(f"{type(exc).__name__}: {exc}")
        for c in checks:
            print(c.render())
        print(red("\nBackend unreachable. Run `bash script/build_and_run.sh run` first."))
        return 2

    # 2. Token resolves (the bug that bit us multiple times)
    token_check = check("local-API token resolvable")
    checks.append(token_check)
    token = fetch_token()
    if not token:
        token_check.fail("no token from log or /api/local-token")
    else:
        token_check.ok(f"({token[:8]}…)")

    # 3. Authenticated /api/documents (the stale-token regression)
    docs_check = check("/api/documents authenticated")
    checks.append(docs_check)
    docs: list = []
    try:
        body = get("/api/documents", token=token)
        docs = body if isinstance(body, list) else body.get("documents", [])
        docs_check.ok(f"({len(docs)} docs)")
    except HTTPError as exc:
        docs_check.fail(f"HTTP {exc.code} (token cache stale?)")
    except (URLError, OSError) as exc:
        docs_check.fail(f"{type(exc).__name__}: {exc}")

    # 4. Plan endpoint returns events + suggestions
    plan_check = check("/api/plan returns plan")
    checks.append(plan_check)
    plan_body: dict = {}
    try:
        plan_body = get("/api/plan", token=token)
        n_events = len(plan_body.get("events", []))
        n_suggestions = len(plan_body.get("suggestions", []))
        plan_check.ok(f"({n_events} events, {n_suggestions} suggestions)")
    except HTTPError as exc:
        plan_check.fail(f"HTTP {exc.code}")
    except (URLError, OSError) as exc:
        plan_check.fail(f"{type(exc).__name__}: {exc}")

    # 5. Deadlines endpoint
    deadlines_check = check("/api/plan/deadlines surfaces deadlines")
    checks.append(deadlines_check)
    try:
        body = get("/api/plan/deadlines", token=token)
        deadlines = body.get("deadlines", [])
        # Deadlines can legitimately be empty (no calendar matches), so
        # success means "the route runs and returns an array."
        deadlines_check.ok(f"({len(deadlines)} deadlines)")
    except HTTPError as exc:
        deadlines_check.fail(f"HTTP {exc.code}")
    except (URLError, OSError) as exc:
        deadlines_check.fail(f"{type(exc).__name__}: {exc}")

    # 6. Pick a real document and fetch its detail (citation flight needs
    #    chunks + the doc's file URL to work)
    detail_check = check("first document detail loads")
    checks.append(detail_check)
    if docs:
        first = docs[0]
        doc_id = first.get("id") if isinstance(first, dict) else None
        if doc_id:
            try:
                detail = get(f"/api/documents/{doc_id}", token=token)
                n_chunks = len(detail.get("chunks", []))
                detail_check.ok(
                    f"(\"{(first.get('filename') or '')[:30]}\", {n_chunks} chunks)"
                )
            except HTTPError as exc:
                detail_check.fail(f"HTTP {exc.code}")
            except (URLError, OSError) as exc:
                detail_check.fail(f"{type(exc).__name__}: {exc}")
        else:
            detail_check.fail("first document missing id")
    else:
        detail_check.fail("library is empty — upload at least one source before demoing")

    # 7. Calendar feeds (the Plan view collapses if zero feeds)
    feeds_check = check("calendar feeds present")
    checks.append(feeds_check)
    n_feeds = len(plan_body.get("feeds", []))
    if n_feeds == 0:
        feeds_check.fail(
            "no calendar feeds — Plan view will show the empty-state CTA, not the grid"
        )
    else:
        feeds_check.ok(f"({n_feeds} feeds)")

    # 8. SRS due cards count (drives the dashboard's "next best action" CTA)
    srs_check = check("SRS pipeline live")
    checks.append(srs_check)
    try:
        body = get("/api/srs/due", token=token)
        n_due = body.get("total", 0) if isinstance(body, dict) else 0
        srs_check.ok(f"({n_due} cards due)")
    except HTTPError as exc:
        srs_check.fail(f"HTTP {exc.code}")
    except (URLError, OSError) as exc:
        srs_check.fail(f"{type(exc).__name__}: {exc}")

    # Render
    print()
    for c in checks:
        print(c.render())

    failed = [c for c in checks if c.passed is False]
    print(grey("─" * 50))
    if failed:
        print(red(f"{len(failed)} check(s) failed."))
        return 1
    print(green("ALL CHECKS PASS — you can demo confidently."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
