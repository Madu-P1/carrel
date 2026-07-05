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

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app_logging import get_logger
from cachet_verify.certificate import attest_and_issue

LOGGER = get_logger("attest_api")

router = APIRouter()


class AttestSourceModel(BaseModel):
    text: str
    truncated: bool = False
    complete: bool = True


class DraftProvenanceModel(BaseModel):
    """When the draft came from an uploaded DOCUMENT (via /api/verify/
    extract-draft), name the ORIGINAL file and the extraction identity so the
    certificate can too. Additive-only: omit it for a pasted-text draft and the
    sealed body is byte-identical to before."""

    file_sha256: str = Field(max_length=64)
    extractor: str = Field(max_length=120)


class AttestRequest(BaseModel):
    # Caps mirror the kernel daemon's 2 MiB posture (mythos batchE-20260702:
    # the engine's sentence-pair fan-out is superlinear, so an unbounded body
    # can wedge the sync worker for minutes on a KB-scale crafted draft).
    draft: str = Field(max_length=100_000)
    # Raw strings or {text, truncated, complete} records; mirrors the kernel
    # daemon's wire contract.
    sources: list[str | AttestSourceModel] = Field(default_factory=list, max_length=20)
    # Optional caller-supplied issuance timestamp (ISO-8601) for deterministic
    # certificates under test; the live path omits it and gets the server
    # clock, recorded verbatim in the sealed body.
    issued_at: str | None = None
    # Optional draft-file provenance (document drafts). Rides into the sealed
    # body when present; absent leaves the certificate byte-identical.
    draft_provenance: DraftProvenanceModel | None = None


def register_attest_routes(app) -> None:
    @router.post("/api/attest")
    def attest(request: AttestRequest) -> dict:
        total_source_chars = sum(
            len(s) if isinstance(s, str) else len(s.text) for s in request.sources
        )
        if total_source_chars > 2_000_000:
            raise HTTPException(
                status_code=413,
                detail="sources exceed 2 MiB; attach fewer or smaller records",
            )
        if request.issued_at is not None:
            # The field's own contract says ISO-8601; a non-date string would
            # otherwise seal verbatim into the exhibit's "Issued:" line
            # (mythos batchE/final-sweep, low). Reject rather than seal garbage.
            try:
                datetime.fromisoformat(request.issued_at)
            except ValueError as e:
                raise HTTPException(
                    status_code=422, detail="issued_at must be an ISO-8601 timestamp"
                ) from e
        issued_at = request.issued_at or datetime.now(timezone.utc).isoformat()
        sources = [
            s
            if isinstance(s, str)
            else {"text": s.text, "truncated": s.truncated, "complete": s.complete}
            for s in request.sources
        ]
        provenance = (
            {
                "file_sha256": request.draft_provenance.file_sha256,
                "extractor": request.draft_provenance.extractor,
            }
            if request.draft_provenance is not None
            else None
        )
        cert = attest_and_issue(request.draft, sources, issued_at, draft_provenance=provenance)
        LOGGER.info("attest: %d claims, state=%s", len(cert.get("claims", [])), cert.get("state"))
        return cert

    app.include_router(router)
