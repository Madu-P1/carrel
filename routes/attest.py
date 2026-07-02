"""ADR-0015 — the attestation endpoint over the extracted kernel.

POST /api/attest takes a draft plus RAW SOURCES (no vault dependency) and
returns the sealed certificate from ``cachet_verify.certificate``. This is the
app-server twin of the kernel daemon's /attest: same kernel, same certificate,
so a surface that talks to the Carrel backend and a surface that talks to the
loopback daemon receive byte-compatible artifacts.

Deliberately vault-free: sources travel in the request. The vault-scoped
attestation (doc_ids like /api/verify) composes later without changing this
wire shape (additive-only).
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app_logging import get_logger
from cachet_verify.certificate import attest_and_issue

LOGGER = get_logger("attest_api")

router = APIRouter()


class AttestSourceModel(BaseModel):
    text: str
    truncated: bool = False
    complete: bool = True


class AttestRequest(BaseModel):
    draft: str
    # Raw strings or {text, truncated, complete} records; mirrors the kernel
    # daemon's wire contract.
    sources: list[str | AttestSourceModel] = Field(default_factory=list)
    # Optional caller-supplied issuance timestamp (ISO-8601) for deterministic
    # certificates under test; the live path omits it and gets the server
    # clock, recorded verbatim in the sealed body.
    issued_at: str | None = None


def register_attest_routes(app) -> None:
    @router.post("/api/attest")
    def attest(request: AttestRequest) -> dict:
        issued_at = request.issued_at or datetime.now(timezone.utc).isoformat()
        sources = [
            s
            if isinstance(s, str)
            else {"text": s.text, "truncated": s.truncated, "complete": s.complete}
            for s in request.sources
        ]
        cert = attest_and_issue(request.draft, sources, issued_at)
        LOGGER.info("attest: %d claims, state=%s", len(cert.get("claims", [])), cert.get("state"))
        return cert

    app.include_router(router)
