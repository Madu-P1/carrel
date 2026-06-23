"""Read-only adapter over Cachet's deterministic verify engine.

This is the ONLY module that touches the engine, and it touches it read-only: it
calls the public verdict functions and reads the result back. It imports from the
gated truth-surface modules; it never modifies them.

Two probes:
  - ``probe_contract(claim, clause)`` -> the contract clause path
    (``verify_claim_against_clause``), a pure function with no DB and no network.
  - ``probe_litigator(draft, client=...)`` -> the litigator citation path
    (``build_deterministic_envelope`` with the bundled local-caselaw client), fully
    in-memory.

Both run safely inside ``forbid_sockets()`` — proving the discovery battery makes
no network call — because the contract path is pure and the litigator path is served
by the bundled corpus over an httpx ``MockTransport``.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast
from unittest import mock

from services.legal.contract_verify import verify_claim_against_clause
from services.legal.deterministic_envelope import build_deterministic_envelope
from services.legal.local_caselaw import local_caselaw_client

from .contracts import (
    CONTRADICTED,
    COULD_NOT_VERIFY,
    SUPPORTED,
    Mode,
    ProbeResult,
    state_for_disposition,
)

# Litigator refusal flags that mean the engine actively flagged a discrepancy on a
# citation (the 2026 sanctions-frontier surface: real number, wrong attribution).
_LITIGATOR_FLAG_KEYS = ("caption_mismatch", "year_mismatch", "court_mismatch")


@contextmanager
def forbid_sockets() -> Iterator[None]:
    """Make any real socket construction fail loudly for the duration.

    Mirrors ``tests/test_zero_egress.py``: the deterministic paths must complete
    without opening a real socket. Running the whole battery inside this context is
    the strongest proof the discovery harness is zero-egress.
    """

    def _raise(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the adversarial discovery harness attempted to open a real socket")

    with mock.patch.object(socket, "socket", _raise):
        yield


def probe_contract(claim: str, clause: str) -> ProbeResult:
    """Run the contract clause path on one (claim, clause) pair, read-only."""

    verdict = verify_claim_against_clause(claim, clause)
    return ProbeResult(
        state=state_for_disposition(verdict.disposition),
        disposition=verdict.disposition,
        anchor_type=verdict.anchor_type,
        detail=verdict.detail,
        mode=Mode.CONTRACT,
    )


def _litigator_first_verdict(envelope: dict[str, Any]) -> dict[str, Any] | None:
    """Pull the first citation verdict out of a deterministic envelope, or None."""

    for claim in envelope.get("claims", ()):
        for group in claim.get("case_verdicts", ()):
            for verdict in group.get("verdicts", ()):
                return cast("dict[str, Any]", verdict)
    return None


def _litigator_state(verdict: dict[str, Any]) -> str:
    """Map a litigator citation verdict to the honest three-state vocabulary.

    - ``supported``        : the cite resolves AND no attribution flag fired.
    - ``contradicted``     : the engine actively flagged a caption/year/court
                             mismatch (a real number, wrong case).
    - ``could_not_verify`` : not found / bounded-corpus miss / ambiguous — an honest
                             refusal, never an affirmation.
    """

    flagged = any(bool(verdict.get(k)) for k in _LITIGATOR_FLAG_KEYS)
    if flagged:
        return CONTRADICTED
    if verdict.get("exists") is True:
        return SUPPORTED
    return COULD_NOT_VERIFY


def probe_litigator(draft: str, *, client: Any = None) -> ProbeResult:
    """Run the litigator citation path on one draft sentence, read-only.

    Pass a shared ``client`` (from ``local_caselaw_client()``) across many calls to
    avoid rebuilding the bundled corpus each time.
    """

    caselaw_client = client if client is not None else local_caselaw_client()
    envelope = build_deterministic_envelope(draft, client=caselaw_client)
    verdict = _litigator_first_verdict(envelope)
    if verdict is None:
        # No citation parsed out of the draft: nothing to affirm, honest no-op.
        return ProbeResult(
            state=COULD_NOT_VERIFY,
            disposition="no_citation",
            anchor_type=None,
            detail="no citation parsed from the draft sentence",
            mode=Mode.LITIGATOR,
            raw={},
        )
    state = _litigator_state(verdict)
    disposition = (
        "exists"
        if verdict.get("exists") is True and state == SUPPORTED
        else next((k for k in _LITIGATOR_FLAG_KEYS if verdict.get(k)), "not_found")
    )
    return ProbeResult(
        state=state,
        disposition=disposition,
        anchor_type="citation",
        detail=str(verdict.get("error_message") or verdict.get("case_name") or ""),
        mode=Mode.LITIGATOR,
        raw={k: verdict.get(k) for k in (*_LITIGATOR_FLAG_KEYS, "exists", "status", "case_name")},
    )
