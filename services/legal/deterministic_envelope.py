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

from services.legal.anchors import Anchor, build_alias_table, extract_anchors
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

# Anchor types verify_claim_against_clause actually tests against a clause. A
# sentence carrying one of these has a proposition the contract path can confirm or
# contradict; a defined_term alone does not (PR-1 grounds the defined term as
# context, never as a clause-checked verdict).
_CLAUSE_CHECKABLE = frozenset({"money", "date", "duration", "quote"})


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


def _source_alias_table(
    conn: sqlite3.Connection | None, doc_ids: Sequence[str] | None
) -> dict[str, str] | None:
    """Defined-term alias table built from the source documents' own text (T0).

    Offline by construction: reads node text from the local DB, no network. Returns
    None (the detector stays inert, the default behavior) when there is no source,
    the nodes table is absent, or no term is defined, so a chunks-path corpus and
    the litigator-only path are byte-identical to before.
    """
    if conn is None or not doc_ids:
        return None
    placeholders = ",".join("?" for _ in doc_ids)
    try:
        rows = conn.execute(
            f"SELECT verbatim_text FROM nodes WHERE doc_id IN ({placeholders}) "
            "ORDER BY doc_id, reading_order",
            list(doc_ids),
        ).fetchall()
    except sqlite3.Error:
        return None
    source_text = "\n".join(row[0] for row in rows if row[0])
    return build_alias_table(source_text) or None


# Strip a trailing corporate suffix so "Acme Inc." and "Acme, Inc" normalize to the
# same key as the source's party list; the parenthetical-alias form keeps its inner
# term. Matching is lenient by design: an unmatched party is a could-not-check, never
# an accusation, so a missed normalization costs recall, never precision.
_PARTY_SUFFIX = re.compile(
    r"[,\s]+(?:Inc|LLC|L\.L\.C|Corp|Ltd|L\.P|LP|PLC|GmbH)\.?\s*$", re.IGNORECASE
)
_ALIAS_INNER = re.compile(r"""["“']([^"”']+)["”']""")
_SECTION_NUMBER = re.compile(r"\d+(?:\.\d+)*")


def _normalize_party(text: str) -> str:
    alias = _ALIAS_INNER.search(text)
    core = (
        alias.group(1) if text.lstrip().startswith("(") and alias else _PARTY_SUFFIX.sub("", text)
    )
    return re.sub(r"\s+", " ", core).strip().lower()


def _normalize_section(text: str) -> str:
    m = _SECTION_NUMBER.search(text)
    return m.group(0) if m else text.strip().lower()


def _source_party_section_sets(
    conn: sqlite3.Connection | None, doc_ids: Sequence[str] | None
) -> tuple[frozenset[str], frozenset[str]]:
    """Normalized party and section identifiers found in the source documents (T0).

    Offline by construction (reads node text from the local DB, no network), and
    symmetric with the draft: source parties/sections come from the same
    ``extract_anchors`` detectors the draft uses. Empty sets when there is no source
    or no nodes table, so a draft party or section is then simply unmatched, a
    could-not-check, never a false verdict.
    """
    if conn is None or not doc_ids:
        return frozenset(), frozenset()
    placeholders = ",".join("?" for _ in doc_ids)
    try:
        rows = conn.execute(
            f"SELECT verbatim_text FROM nodes WHERE doc_id IN ({placeholders}) "
            "ORDER BY doc_id, reading_order",
            list(doc_ids),
        ).fetchall()
    except sqlite3.Error:
        return frozenset(), frozenset()
    parties: set[str] = set()
    sections: set[str] = set()
    for (text,) in rows:
        if not text:
            continue
        for anchor in extract_anchors(text):
            if anchor.type == "party":
                parties.add(_normalize_party(anchor.text))
            elif anchor.type == "section":
                sections.add(_normalize_section(anchor.text))
    return frozenset(parties), frozenset(sections)


def _grounding_reason(
    anchors: list[Anchor],
    source_parties: frozenset[str],
    source_sections: frozenset[str],
) -> str | None:
    """An honest could-not-check reason for a sentence whose only checkable signals
    are grounding anchors (defined_term / party / section). Never a verdict.

    Returns None when the sentence carries a clause-checkable anchor (money / date /
    duration / quote), so a parametric or quote verdict always wins (ADR-0012
    invariant 2: a grounding anchor never manufactures or softens a verdict). Party
    and section are grounded against the source but never accused: an unmatched party
    or an unlocated section reads could-not-check, never unsupported, because
    name-form and numbering variance make a hard "not in the contract" the
    false-accusation direction the product refuses.
    """
    if any(a.type in _CLAUSE_CHECKABLE for a in anchors):
        return None
    parts: list[str] = []

    defined = list(dict.fromkeys(a.text for a in anchors if a.type == "defined_term"))
    if defined:
        parts.append(f"uses defined term(s) {', '.join(defined)} from the source contract")

    parties = list(dict.fromkeys(a.text for a in anchors if a.type == "party"))
    matched = [p for p in parties if _normalize_party(p) in source_parties]
    unmatched = [p for p in parties if _normalize_party(p) not in source_parties]
    if matched:
        parts.append(f"names {', '.join(matched)}, a party to the source contract")
    if unmatched:
        parts.append(
            f"names {', '.join(unmatched)}, which could not be matched to a party "
            "in the source contract"
        )

    sections = list(dict.fromkeys(a.text for a in anchors if a.type == "section"))
    found = [s for s in sections if _normalize_section(s) in source_sections]
    missing = [s for s in sections if _normalize_section(s) not in source_sections]
    if found:
        parts.append(f"references {', '.join(found)}, which exists in the source contract")
    if missing:
        parts.append(
            f"references {', '.join(missing)}, which could not be located in the source contract"
        )

    if not parts:
        return None
    return (
        "This statement "
        + "; ".join(parts)
        + ", but its assertion was not independently verified against a clause."
    )


def _contract_claim(
    conn: sqlite3.Connection,
    sentence: str,
    doc_ids: Sequence[str],
    embedder: Embedder | None,
    *,
    anchors: list[Anchor],
    source_parties: frozenset[str],
    source_sections: frozenset[str],
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
    claim = {
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
    # Grounding overlay (defined_term + party + section). A sentence whose only
    # checkable signals are grounding anchors gets an honest could-not-check that
    # names them, never the misleading "language does not appear" and never a verdict.
    # A clause-checkable anchor suppresses it, so a parametric/quote result always
    # wins outright (ADR-0012 invariant 2).
    reason = _grounding_reason(anchors, source_parties, source_sections)
    if reason:
        claim["could_not_check_reason"] = reason
    return claim


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
    # Defined-term detection keys off the source contract's own definitions: built
    # once here (offline) and passed to every sentence's extraction. None on the
    # litigator-only path, leaving that path unchanged.
    alias_table = _source_alias_table(conn, doc_ids) if contract_mode else None
    source_parties, source_sections = (
        _source_party_section_sets(conn, doc_ids) if contract_mode else (frozenset(), frozenset())
    )
    sentences = split_sentences(draft)
    claims: list[dict] = []
    # Opinion text of the cases that resolved in each sentence, so the altered-quote
    # pass can check a quote against cites in its own OR an adjacent sentence.
    opinions_by_sentence: dict[int, list[str]] = {}
    for i, sentence in enumerate(sentences):
        anchors = extract_anchors(sentence, alias_table=alias_table)
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
            claims.append(
                _contract_claim(
                    conn,
                    sentence,
                    doc_ids,
                    embedder,
                    anchors=anchors,
                    source_parties=source_parties,
                    source_sections=source_sections,
                )
            )
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
