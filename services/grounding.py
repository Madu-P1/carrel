"""The grounding seam (Cachet extraction, ADR-0011 P1).

Verify depends on this narrow interface, not on `services.tutor` internals, so
the grounding engine can be specialized or swapped without touching the verify
surface. Today both functions forward to the existing grounded-tutor engine; the
wrappers are a pure interposition (same inputs, same envelope), which is what
lets P1 land with verify output byte-identical. See
docs/plans/cachet-extraction-2026-06-05.md (P1).
"""

from __future__ import annotations

from typing import Any, Dict, Iterator

from services import tutor as _tutor


def ground(conn, payload, *, log_study_event, fetch_recent_events) -> Dict[str, Any]:
    """Produce the grounding envelope (claims, unsupported_spans, citations,
    provider, model, error) for a verify payload.

    Pure interposition over the grounded-tutor engine: verify, and any future
    Cachet surface, depends on this contract rather than on the engine module's
    internals.
    """
    return _tutor.grounded_tutor_envelope(
        conn,
        payload,
        log_study_event=log_study_event,
        fetch_recent_events=fetch_recent_events,
    )


def ground_stream(
    conn, payload, *, log_study_event, fetch_recent_events
) -> Iterator[Dict[str, Any]]:
    """Streamed grounding-envelope steps (progress, claims, cite_verdict,
    result). Pure interposition over the engine; the streamed and non-stream
    paths produce an identical envelope for the same inputs.
    """
    return _tutor.grounded_tutor_envelope_steps(
        conn,
        payload,
        log_study_event=log_study_event,
        fetch_recent_events=fetch_recent_events,
    )
