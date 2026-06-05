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
from services.legal.citations_eyecite import caption_matches, find_citations
from services.legal.contract_verify import ClauseVerdict, verify_claim_against_clause
from services.legal.local_caselaw import local_caselaw_client, local_opinion_text
from services.legal.quote_check import extract_draft_quote_spans, split_runs
from services.legal.sentences import split_sentences
from services.retrieval.embeddings import Embedder
from services.retrieval.typed_hybrid import search_typed_hybrid
from services.retrieval.validators import verbatim_run_present
from services.tutor import _serialize_case_verdict

_DETERMINISTIC_MODEL = "deterministic-v1"


def _enabled(name: str) -> bool:
    return os.getenv(name, "").lower() in {"1", "true", "yes"}


def deterministic_verify_enabled() -> bool:
    return _enabled("CACHET_DETERMINISTIC_VERIFY")


def local_caselaw_enabled() -> bool:
    return _enabled("CACHET_LOCAL_CASELAW")


def _annotate_litigator_verdicts(sentence: str, case_verdicts: list[dict]) -> None:
    """Annotate the deterministic litigator verdicts in place.

    - ``holding_skipped``: holding-match was deliberately off, so a null holding
      result is "not evaluated" (a positive existence confirmation), distinct
      from the LLM path's "ran but could not determine".
    - ``caption_mismatch``: the number resolves but to a different case than the
      draft names (a fabricated caption on a real number). eyecite reads the
      draft's party names; ``caption_matches`` compares them leniently so an
      abbreviated real caption is never falsely flagged.
    """
    refs = {r.matched_text: r for r in find_citations(sentence)}
    for batch in case_verdicts:
        for v in batch.get("verdicts", []):
            v["holding_skipped"] = True
            if not v.get("exists") or not v.get("case_name"):
                continue
            ref = refs.get(v.get("citation"))
            if ref is not None and not caption_matches(ref, v["case_name"]):
                v["caption_mismatch"] = True


def _quote_altered_reason(sentence: str, case_verdicts: list[dict]) -> str | None:
    """L4: a quoted run attributed to a cited case must appear verbatim in it.

    Checks the sentence's quoted runs against the bundled opinion text of the
    resolved cites. An absent run means the quote was altered (a word changed, or
    an ellipsis dropping context). Returns None when there is nothing to quote or
    no opinion text to check against (cannot determine, never a false flag).
    """
    spans = extract_draft_quote_spans(sentence)
    if not spans:
        return None
    opinions = [
        text
        for batch in case_verdicts
        for v in batch.get("verdicts", [])
        if v.get("exists") and (text := local_opinion_text(v.get("citation")))
    ]
    if not opinions:
        return None
    for inner_text, _start, _end in spans:
        for run in split_runs(inner_text):
            if run.strip() and not any(verbatim_run_present(run, op) for op in opinions):
                return (
                    f'The quoted language "{run.strip()}" does not appear verbatim in '
                    "the cited opinion."
                )
    return None


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
    for sentence in split_sentences(draft):
        anchors = extract_anchors(sentence)
        if any(a.type == "citation" for a in anchors):
            verdicts = verify_claims_for_cases(
                [sentence], client=cl_client, enable_holding_match=False
            )
            serialized = [_serialize_case_verdict(v) for v in verdicts]
            # Existence verifies the reporter number resolves; this also checks the
            # draft's caption names the resolved case, so a fabricated caption on a
            # real number ("Fake v. Nobody, 347 U.S. 483") is caught, not passed.
            _annotate_litigator_verdicts(sentence, serialized)
            claim = {"text": sentence, "citations": [], "case_verdicts": serialized}
            altered = _quote_altered_reason(sentence, serialized)
            if altered:
                claim["quote_altered_reason"] = altered
            claims.append(claim)
        elif contract_mode and anchors:
            claims.append(_contract_claim(conn, sentence, doc_ids, embedder))
        else:
            # No citation to check, and either no anchor or nothing to check a
            # non-citation anchor against. The honest "could not check": never a
            # silent pass, never an accusatory "unsupported".
            reason = (
                "No verifiable anchor (citation, quotation, amount, or date) was found, "
                "so this statement was not independently checked."
                if not anchors
                else "This statement carries a checkable value but no source was provided "
                "to check it against."
            )
            claims.append(
                {
                    "text": sentence,
                    "citations": [],
                    "case_verdicts": [],
                    "could_not_check_reason": reason,
                }
            )

    return {
        "claims": claims,
        "unsupported_spans": [],
        "model": _DETERMINISTIC_MODEL,
        "error": None,
        "provider": "deterministic",
    }
