"""The demandable certificate: a sealed, offline-revalidatable attestation.

ADR-0015's win condition is that a THIRD PARTY asks for this artifact ("where's
the Cachet cert?"). That requires the certificate to stand on its own:

- **Canonical.** One byte-stable JSON serialization (sorted keys, fixed
  separators), so the same attestation always fingerprints identically.
- **Sealed.** The fingerprint is the SHA-256 of the canonical certificate body;
  any tampering -- a flipped state, an edited detail, a swapped source hash --
  breaks it.
- **Revalidatable offline.** Given the certificate plus the original draft and
  sources, anyone with the kernel can recompute both the seal and the verdicts
  and compare. The engine is deterministic, so a mismatch means the artifact
  or the inputs changed, never the weather.
- **Honest.** The certificate never claims more than the engine ruled: it
  carries the three-state verdicts and the refusal counts with the same weight
  as the confirmations.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .adapter import DraftAttestation, SourceInput, _coerce_sources, attest_draft
from .contract import SCHEMA_VERSION

KERNEL_VERSION = "0.1.0"


def canonical_json(obj: Any) -> bytes:
    """Byte-stable serialization: sorted keys, fixed separators, no ASCII
    escaping (UTF-8 is the wire). The ONLY serialization certificates use."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _attestation_body(attestation: DraftAttestation) -> list[dict]:
    return [
        {
            "claim": c.claim,
            "state": c.attestation.state,
            "checks": [
                {
                    "state": chk.state,
                    "provenance": chk.provenance,
                    "detail": chk.detail,
                    "subject": chk.subject,
                }
                for chk in c.attestation.checks
            ],
        }
        for c in attestation.claims
    ]


def issue_certificate(
    draft: str,
    sources: list[SourceInput],
    attestation: DraftAttestation,
    issued_at: str,
) -> dict:
    """Seal an attestation into a certificate. ``issued_at`` is supplied by the
    caller (an ISO-8601 string) so issuance is deterministic and testable; the
    daemon injects its clock exactly once."""
    source_records = _coerce_sources(sources)
    body = {
        "schema_version": SCHEMA_VERSION,
        "kernel_version": KERNEL_VERSION,
        "issued_at": issued_at,
        "draft_sha256": sha256_hex(draft.encode("utf-8")),
        "source_sha256s": [sha256_hex(s.text.encode("utf-8")) for s in source_records],
        "state": attestation.state,
        "claims": _attestation_body(attestation),
    }
    return {**body, "fingerprint": sha256_hex(canonical_json(body))}


def attest_and_issue(draft: str, sources: list[SourceInput], issued_at: str) -> dict:
    return issue_certificate(draft, sources, attest_draft(draft, sources), issued_at)


def verify_certificate(cert: dict) -> bool:
    """Internal-consistency check: does the seal match the body? Detects any
    post-issuance tampering. Pure; no engine run."""
    if not isinstance(cert, dict) or "fingerprint" not in cert:
        return False
    body = {k: v for k, v in cert.items() if k != "fingerprint"}
    return cert["fingerprint"] == sha256_hex(canonical_json(body))


def revalidate_certificate(cert: dict, draft: str, sources: list[SourceInput]) -> dict:
    """Full offline revalidation: seal integrity, input identity, and a fresh
    engine run compared verdict-for-verdict. Returns a dict of booleans rather
    than one blended verdict so a reviewer sees exactly WHAT failed."""
    seal_ok = verify_certificate(cert)
    source_records = _coerce_sources(sources)
    draft_ok = bool(seal_ok) and cert.get("draft_sha256") == sha256_hex(draft.encode("utf-8"))
    sources_ok = bool(seal_ok) and cert.get("source_sha256s") == [
        sha256_hex(s.text.encode("utf-8")) for s in source_records
    ]
    if seal_ok and draft_ok and sources_ok:
        fresh = attest_draft(draft, sources)
        verdicts_ok = _attestation_body(fresh) == cert.get("claims") and fresh.state == cert.get(
            "state"
        )
    else:
        verdicts_ok = False
    return {
        "seal_ok": seal_ok,
        "draft_ok": draft_ok,
        "sources_ok": sources_ok,
        "verdicts_reproduced": verdicts_ok,
        "valid": seal_ok and draft_ok and sources_ok and verdicts_ok,
    }


_STATE_LINES = {
    "verified": "VERIFIED AGAINST THE RECORD",
    "altered": "ALTERED FROM THE RECORD",
    "could_not_check": "COULD NOT BE CHECKED",
}


def render_exhibit(cert: dict) -> str:
    """Filing-grade plain-text exhibit. Register rules: no celebratory
    language, refusals carry the same weight as confirmations, every line
    traceable to the sealed body."""
    counts = {"verified": 0, "altered": 0, "could_not_check": 0}
    for claim in cert.get("claims", []):
        state = claim.get("state", "could_not_check")
        counts[state] = counts.get(state, 0) + 1
    lines = [
        "CACHET ATTESTATION RECORD",
        "",
        f"Issued: {cert.get('issued_at', '')}",
        f"Kernel: cachet-verify {cert.get('kernel_version', '')} "
        f"(schema v{cert.get('schema_version', '')})",
        f"Draft SHA-256: {cert.get('draft_sha256', '')}",
        *(f"Source SHA-256: {h}" for h in cert.get("source_sha256s", [])),
        "",
        f"Statements examined: {len(cert.get('claims', []))}",
        f"  Verified against the record: {counts['verified']}",
        f"  Altered from the record: {counts['altered']}",
        f"  Could not be checked: {counts['could_not_check']}",
        "",
    ]
    for i, claim in enumerate(cert.get("claims", []), start=1):
        lines.append(f"{i}. {_STATE_LINES.get(claim.get('state'), 'COULD NOT BE CHECKED')}")
        lines.append(f"   {claim.get('claim', '')}")
        for chk in claim.get("checks", []):
            if chk.get("detail"):
                lines.append(f"   - {chk['detail']} [{chk.get('provenance', '')}]")
        lines.append("")
    lines.append(f"Seal (SHA-256 of the canonical record): {cert.get('fingerprint', '')}")
    lines.append(
        "This record attests only what a deterministic engine could trace to the "
        "sources named above. A statement marked could-not-be-checked is neither "
        "confirmed nor accused."
    )
    return "\n".join(lines)
