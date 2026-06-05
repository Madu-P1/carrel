"""Deterministic verify envelope: the litigator path with no LLM (Phase 5).

Produces the same envelope dict shape that
``services.verify._verify_result_from_envelope`` already consumes, but
the unit selection is deterministic (T0): the draft is split into
sentences, each sentence carrying a citation anchor is checked for
case-existence (offline against the bundled corpus, answered in-process
with no network unless a caller explicitly injects an online client),
holding-match stays OFF, and
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
import re
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


def _opinions_from_verdicts(case_verdicts: list[dict]) -> list[str]:
    """Bundled opinion texts for the cites that resolved in these verdicts."""
    return [
        text
        for batch in case_verdicts
        for v in batch.get("verdicts", [])
        if v.get("exists") and (text := local_opinion_text(v.get("citation")))
    ]


def _quoted_subphrases(run: str) -> list[str]:
    """The distinct quoted phrases inside a run, in case the span regex merged them.

    The quote-span extractor captures greedily from the first quote mark to the
    last, so a sentence with two quoted phrases ('"A" failed because "B"') yields a
    single run with the inner marks retained ('A" failed because "B'). Splitting on
    quote marks recovers the phrases at the even positions; the odd positions are
    the lawyer's own connecting prose, which was never quoted and must not be
    checked. A run with no inner marks yields itself unchanged.
    """
    parts = re.split(r'["“”]', run)
    phrases = [p for idx, p in enumerate(parts) if idx % 2 == 0 and p.strip()]
    return phrases or [run]


def _quote_unverified_reason(sentence: str, opinions: list[str]) -> str | None:
    """A quoted phrase that is not verbatim in the cited opinion text we hold.

    ``opinions`` is the bundled opinion text of the cases cited in THIS sentence
    (the build loop attributes same-sentence only). A phrase that is present is
    confirmed; a phrase that is ABSENT returns a could-not-check reason, NOT an
    "altered" accusation: the bundled opinion text is not guaranteed complete, so an
    absent phrase may be a misquote OR a real passage we do not hold. Refusing to
    verify is the honest call; a false "you fabricated this quote" is the
    malpractice direction. Returns None when there is nothing to quote or no opinion
    to check against. Each run is split into its distinct quoted phrases first, so
    two genuinely-verbatim quotes the greedy span regex merged into one run are
    checked separately, not flagged as one.
    """
    spans = extract_draft_quote_spans(sentence)
    if not spans or not opinions:
        return None
    for inner_text, _start, _end in spans:
        for run in split_runs(inner_text):
            for phrase in _quoted_subphrases(run):
                phrase = phrase.strip()
                if phrase and not _run_present_any(phrase, opinions):
                    return (
                        f'The quoted language "{phrase}" could not be verified against '
                        "the available opinion text."
                    )
    return None


def _first_letter_variants(run: str) -> tuple[str, ...]:
    """The run, plus the run with its first alphabetic character's case toggled.

    A lawyer who embeds a quote mid-sentence routinely lowercases the source's
    leading capital ("separate educational facilities..." from a sentence that
    opened "Separate ...") without the bracket convention ("[s]eparate"). That is
    a universally accepted edit, not an alteration, so the altered-quote check
    must accept either case at the leading letter. Interior case stays strict, so
    a substituted interior word is still caught.
    """
    for i, ch in enumerate(run):
        if ch.isalpha():
            swapped = ch.lower() if ch.isupper() else ch.upper()
            if swapped == ch:
                break
            return (run, run[:i] + swapped + run[i + 1 :])
    return (run,)


def _run_present_any(run: str, opinions: list[str]) -> bool:
    """True if ``run`` (or its leading-letter case variant) is verbatim in any opinion."""
    return any(
        verbatim_run_present(variant, op)
        for variant in _first_letter_variants(run)
        for op in opinions
    )


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
    # Offline by construction: case-existence is answered from the bundled corpus
    # via an in-process MockTransport, never the network. Going online is an
    # explicit code-level opt-in (inject a client); there is deliberately no env
    # var that turns on egress, so "no data leaves this device" holds even if the
    # operator's setup is wrong. The courtlistener token guard still passes with the
    # demo sentinel token, so without this floor the litigator path would POST the
    # brief text to courtlistener.com.
    cl_client = client if client is not None else local_caselaw_client()

    if conn is not None and not doc_ids:
        # Full-library fallback: the demo UI's stream sends no doc_ids, so scope the
        # contract check to every ready document. On the demo machine the only
        # ingested document is the contract, so the contract close runs without a
        # document picker. A litigator brief whose non-citation sentences match no
        # clause simply yields could_not_check, so this never pollutes the opener.
        # Fail safe to litigator-only if the documents table is absent.
        try:
            doc_ids = [
                row[0] for row in conn.execute("SELECT id FROM documents WHERE status = 'ready'")
            ]
        except sqlite3.Error:
            doc_ids = []
    contract_mode = conn is not None and bool(doc_ids)
    sentences = split_sentences(draft)
    claims: list[dict] = []
    # Opinion text of the cases that resolved in each sentence, so the altered-quote
    # pass can check a quote against cites in its own OR an adjacent sentence.
    opinions_by_sentence: dict[int, list[str]] = {}
    for i, sentence in enumerate(sentences):
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
            opinions_by_sentence[i] = _opinions_from_verdicts(serialized)
            claims.append({"text": sentence, "citations": [], "case_verdicts": serialized})
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

    # Altered-quote pass, SAME-SENTENCE attribution only. A quoted run is checked
    # only against the cases cited in its OWN sentence. Proximity is not attribution:
    # a quote in a sentence adjacent to an unrelated cite ("Brown, 347 U.S. 483. The
    # contract defined 'X'.") must never be accused of misquoting that case. The cost
    # is that an altered quote whose cite sits in a separate sentence is reported
    # could-not-check rather than flagged, which is the right trade for a tool whose
    # core promise is no false accusations.
    for i, sentence in enumerate(sentences):
        unverified = _quote_unverified_reason(sentence, opinions_by_sentence.get(i, []))
        if unverified:
            claims[i]["quote_could_not_check_reason"] = unverified

    return {
        "claims": claims,
        "unsupported_spans": [],
        "model": _DETERMINISTIC_MODEL,
        "error": None,
        "provider": "deterministic",
    }
