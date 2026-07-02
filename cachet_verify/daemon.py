"""The attestation daemon: one loopback process, one curl-able contract.

Every surface -- app, companion, Word add-in, IDE panel, CI gate -- is a thin
client of this process:

    POST http://127.0.0.1:<port>/verify
    X-Cachet-Token: <token>
    {"claim": "...", "sources": ["...", ...]}

    -> {"schema_version": 1, "state": "verified|altered|could_not_check",
        "checks": [{"state", "provenance", "detail", "subject"}, ...]}

Security posture (the trust spine, enforced by shape):
  - binds 127.0.0.1 ONLY; refuses any other bind address at construction;
  - constant-time token comparison (mirrors the companion bridge's rule);
  - stdlib http.server, zero third-party dependencies;
  - the verify path itself makes no network call (the deterministic engine is
    socket-ban proven); the daemon only ever answers loopback requests.

This is the packaging decision from ADR-0015: zero-egress is a PROCESS
property, so the kernel ships as one signed process you can point a packet
capture at -- not a library that inherits every host's network stack.
"""

from __future__ import annotations

import hmac
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .adapter import verify_claim
from .contract import SCHEMA_VERSION

_MAX_BODY_BYTES = 2 * 1024 * 1024  # a draft, not an archive


class AttestationHandler(BaseHTTPRequestHandler):
    server_version = "cachet-verify"
    protocol_version = "HTTP/1.1"

    def _respond(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        supplied = self.headers.get("X-Cachet-Token", "")
        expected = getattr(self.server, "token", "")
        return bool(expected) and hmac.compare_digest(supplied, expected)

    def do_POST(self) -> None:  # noqa: N802 (http.server contract)
        if self.path != "/verify":
            self._respond(404, {"error": "unknown path"})
            return
        if not self._authorized():
            self._respond(401, {"error": "missing or invalid token"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > _MAX_BODY_BYTES:
            self._respond(400, {"error": "body required (max 2 MiB)"})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            claim = payload["claim"]
            sources = payload["sources"]
            if not isinstance(claim, str) or not isinstance(sources, list):
                raise TypeError
            sources = [s for s in sources if isinstance(s, str)]
        except (json.JSONDecodeError, KeyError, TypeError, UnicodeDecodeError):
            self._respond(400, {"error": "expected {claim: str, sources: [str]}"})
            return

        attestation = verify_claim(claim, sources)
        self._respond(
            200,
            {
                "schema_version": SCHEMA_VERSION,
                "state": attestation.state,
                "checks": [
                    {
                        "state": c.state,
                        "provenance": c.provenance,
                        "detail": c.detail,
                        "subject": c.subject,
                    }
                    for c in attestation.checks
                ],
            },
        )

    def do_GET(self) -> None:  # noqa: N802 (http.server contract)
        # The contract is POST-only; a GET must not leak anything.
        self._respond(405, {"error": "POST /verify"})

    def log_message(self, *_args) -> None:
        # Never log request content: a claim may carry privileged text.
        return


class AttestationDaemon:
    """Owns the loopback server. ``port=0`` picks an ephemeral port (tests)."""

    def __init__(self, token: str, port: int = 0, host: str = "127.0.0.1") -> None:
        if host != "127.0.0.1":
            raise ValueError("the attestation daemon binds loopback only")
        if not token:
            raise ValueError("a non-empty token is required")
        self._server = ThreadingHTTPServer((host, port), AttestationHandler)
        self._server.token = token  # type: ignore[attr-defined]
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    def start(self) -> None:
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
