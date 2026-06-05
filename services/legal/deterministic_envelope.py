"""Deterministic verify envelope: the litigator path with no LLM (Phase 5).

Produces the same envelope dict shape that
``services.verify._verify_result_from_envelope`` already consumes, but
the unit selection is deterministic (T0): the draft is split into
sentences, each sentence carrying a citation anchor is checked for
case-existence (offline against the bundled corpus when
``CACHET_LOCAL_CASELAW`` is set), holding-match stays OFF, and
anchor-free sentences route to ``unsupported_spans`` instead of being
silently dropped.

``services.verify.verify_draft`` swaps ``grounded_tutor_envelope`` for
this builder when ``CACHET_DETERMINISTIC_VERIFY`` is set. The flag
defaults off, so the existing LLM flow is unchanged.

The case-verdict dict shape is produced by the canonical serializer
``services.tutor._serialize_case_verdict`` so the wire contract stays in
lock-step with the LLM path.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Sequence

import httpx

from services.legal.anchors import extract_anchors
from services.legal.case_verification import verify_claims_for_cases
from services.legal.contract_verify import ClauseVerdict, verify_claim_against_clause
from services.legal.local_caselaw import local_caselaw_client
from services.legal.sentences import split_sentences
from services.retrieval.embeddings import Embedder
from services.retrieval.typed_hybrid import search_typed_hybrid
from services.tutor import _serialize_case_verdict

_DETERMINISTIC_MODEL = "deterministic-v1"


def _enabled(name: str) -> bool:
    return os.getenv(name, "").lower() in {"1", "true", "yes"}


def deterministic_verify_enabled() -> bool:
    return _enabled("CACHET_DETERMINISTIC_VERIFY")


def local_caselaw_enabled() -> bool:
    return _enabled("CACHET_LOCAL_CASELAW")


def _contract_claim(
    conn: sqlite3.Connection,
    sentence: str,
    doc_ids: Sequence[str],
    embedder: Embedder | None,
) -> dict:
    """Verify one summary sentence against the retrieved contract clause (T0)."""
    nodes = search_typed_hybrid(conn, sentence, doc_ids=list(doc_ids), embedder=embedder, limit=3)
    # Retrieval is imprecise, so the matching clause may not be rank 1. Take the
    # first retrieved clause that yields a definitive verdict (present or
    # contradiction); fall back to not_found only if none does.
    verdict = ClauseVerdict("not_found", "no matching clause found in the contract")
    section = None
    for node in nodes:
        candidate = verify_claim_against_clause(sentence, node.verbatim_text)
        if candidate.disposition != "not_found":
            verdict = candidate
            section = node.heading_path
            break
    return {
        "text": sentence,
        "citations": [],
        "case_verdicts": [],
        "contract_verdict": {
            "disposition": verdict.disposition,
            "detail": verdict.detail,
            "anchor_type": verdict.anchor_type,
            "claim_values": list(verdict.claim_values),
            "clause_values": list(verdict.clause_values),
            "section": section,
        },
    }


def build_deterministic_envelope(
    draft: str,
    *,
    conn: sqlite3.Connection | None = None,
    doc_ids: Sequence[str] | None = None,
    client: httpx.Client | None = None,
    embedder: Embedder | None = None,
) -> dict:
    """Build a verify envelope for ``draft`` with no LLM.

    Litigator path: each citation-bearing sentence becomes a claim with its
    case-existence verdicts attached. Contract path (when ``conn`` + ``doc_ids``
    are given): each other anchor-bearing sentence is checked against the
    retrieved contract clause. Anchor-free sentences go to ``unsupported_spans``.
    """
    cl_client = client
    if cl_client is None and local_caselaw_enabled():
        cl_client = local_caselaw_client()

    contract_mode = conn is not None and bool(doc_ids)
    claims: list[dict] = []
    unsupported: list[str] = []
    for sentence in split_sentences(draft):
        anchors = extract_anchors(sentence)
        if any(a.type == "citation" for a in anchors):
            # FOLLOW-UP (review 2026-06-05): existence verifies the reporter number
            # resolves, NOT that the draft's caption matches the resolved case. A
            # fabricated caption on a real number ("Fake v. Nobody, 347 U.S. 483")
            # returns exists=True today. Mitigation now: the resolved case_name is
            # carried in the verdict so a human sees the mismatch. Deterministic
            # caption-similarity check (vs eyecite plaintiff/defendant, normalized)
            # is a tracked follow-up; it needs name normalization to avoid
            # false-flagging abbreviated real captions.
            verdicts = verify_claims_for_cases(
                [sentence], client=cl_client, enable_holding_match=False
            )
            claims.append(
                {
                    "text": sentence,
                    "citations": [],
                    "case_verdicts": [_serialize_case_verdict(v) for v in verdicts],
                }
            )
        elif anchors and contract_mode:
            claims.append(_contract_claim(conn, sentence, doc_ids, embedder))
        elif anchors:
            # Carries a non-citation anchor but no contract to check against.
            claims.append({"text": sentence, "citations": [], "case_verdicts": []})
        else:
            unsupported.append(sentence)

    return {
        "claims": claims,
        "unsupported_spans": unsupported,
        "model": _DETERMINISTIC_MODEL,
        "error": None,
        "provider": "deterministic",
    }
