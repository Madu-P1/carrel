"""Deterministic verify envelope: the litigator path with no LLM (Phase 5).

Produces the same envelope dict shape that
``services.verify._verify_result_from_envelope`` already consumes, but
the unit selection is deterministic (T0): the draft is split into
sentences, each sentence carrying a citation anchor is checked for
case-existence (offline against the bundled corpus, answered in-process
with no network unless a caller explicitly injects an online client),
holding-match stays OFF, a sentence with a checkable anchor but no source to
check it against becomes a neutral could-not-check claim, and a sentence with
no checkable anchor at all is marked ``untreated`` (no card, renders as plain
draft text) rather than being silently dropped or screaming could-not-check.

``services.verify.verify_draft`` swaps ``grounded_tutor_envelope`` for
this builder on the deterministic path. The Cachet ``/api/verify`` route
defaults to this builder (no egress, no LLM); the LLM grounding path is an
explicit opt-out via ``CACHET_DETERMINISTIC_VERIFY=0``. A direct caller of
``verify_draft`` keeps the conservative legacy opt-in default.

The case-verdict dict shape is produced by the canonical serializer
``services.legal.case_verification.serialize_case_verdict`` so the wire contract
stays in lock-step with the LLM path.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Sequence

import httpx

from services.legal.anchors import Anchor, build_alias_table, extract_anchors
from services.legal.case_verification import serialize_case_verdict, verify_claims_for_cases
from services.legal.citations_eyecite import CitationRef, caption_match_state, find_citations
from services.legal.contract_verify import (
    ClauseCandidate,
    ClauseVerdict,
    adjudicate_clause_candidates,
    verify_claim_against_clause,
)
from services.legal.local_caselaw import (
    CORPUS_ATTESTATION_ATTR,
    DEMO_MANIFEST,
    CorpusAttestation,
    CorpusManifest,
    local_caselaw_client,
    local_opinion_text,
)
from services.legal.quote_check import (
    extract_draft_quote_spans,
    first_letter_variants,
    quoted_subphrases,
    split_runs,
)
from services.legal.sentences import split_sentences
from services.legal.t1_gate import load_runtime_thresholds, t1_permitted
from services.legal.t1_selector import (
    T1Assessment,
    T1Candidate,
    active_model_id,
    assess,
    default_scorer,
)
from services.retrieval.embeddings import Embedder, offline_embedder
from services.retrieval.typed_hybrid import search_typed_hybrid
from services.retrieval.validators import verbatim_run_present

_DETERMINISTIC_MODEL = "deterministic-v1"

# courts-db id shape ("scotus", "ca9", "nysupct.newyork"): lowercase
# alphanumerics and dots, no spaces or slashes.
_COURT_ID = re.compile(r"[a-z0-9.]+")

# Anchor types verify_claim_against_clause actually tests against a clause. A
# sentence carrying one of these has a proposition the contract path can confirm or
# contradict; a defined_term alone does not (PR-1 grounds the defined term as
# context, never as a clause-checked verdict).
_CLAUSE_CHECKABLE = frozenset(
    {"money", "percent", "date", "duration", "governing_law", "polarity", "quote"}
)

# The could-not-check reason attached when T1's recall tier promotes an anchor-free
# sentence out of untreated (an assessment ran, so a check effectively happened).
# A constant because the promotion path and the could-not-check card text must stay
# identical. See docs/notes/2026-06-08-untreated-vs-could-not-check.md.
_ANCHOR_FREE_REASON = (
    "No verifiable anchor (such as a citation, quotation, amount, or date) was "
    "found, so this statement was not independently checked."
)


def _citation_key(value: str | None) -> str | None:
    """Fold a citation string to an alphanumeric, lowercase key.

    eyecite's ``matched_text`` keeps the draft's spacing ("347 U. S. 483") while
    CourtListener's citation-lookup API echoes its own form ("347 U.S. 483") and a
    separate ``normalized_citation``. Folding away whitespace and punctuation
    collapses those forms to one key ("347us483"), so the caption / year / court
    gates fire regardless of which parser's spacing won. Returns None for an empty
    value. Volume + reporter + page already identify a cite uniquely, so dropping
    formatting cannot collide two genuinely different citations.

    Guards on ``isinstance(value, str)`` rather than truthiness alone: the verdict
    is a plain dict, not the typed ``CaseVerdict``, so a malformed or spoofed
    payload could carry a non-string citation; folding must return None there, not
    crash the whole annotate pass on ``.lower()``.
    """
    if not isinstance(value, str) or not value:
        return None
    folded = re.sub(r"[^a-z0-9]+", "", value.lower())
    return folded or None


def _index_citation_refs(refs: list[CitationRef]) -> dict[str, list[CitationRef]]:
    """Index the draft's parsed cites under every folded form they resolve by.

    Keyed on both eyecite's matched substring and its ``corrected`` (canonical)
    form, so a verdict carrying CourtListener's echoed or normalized citation
    string still finds its draft cite across a spacing/punctuation difference.

    Each key maps to the LIST of distinct cites that fold to it. The same reporter
    number can appear more than once in a sentence with DIFFERENT captions (one
    real, one fabricated: "Brown ..., 347 U.S. 483; see also Sham ..., 347 U.S.
    483"). Collapsing them to a single ref (the old first-wins ``setdefault``) let a
    correct caption on one occurrence bless a fabricated caption on another, so the
    caller must see every candidate and refuse unless they all agree.
    """
    index: dict[str, list[CitationRef]] = {}
    for ref in refs:
        for form in (ref.matched_text, ref.corrected):
            key = _citation_key(form)
            if key is not None:
                bucket = index.setdefault(key, [])
                if ref not in bucket:
                    bucket.append(ref)
    return index


def _lookup_citation_refs(index: dict[str, list[CitationRef]], verdict: dict) -> list[CitationRef]:
    """Every draft cite a resolved verdict could correspond to, by folded form.

    Reconciles the citation-form gap by trying CourtListener's echoed ``citation``
    and its ``normalized_citation``, both folded through :func:`_citation_key`.
    Returns more than one cite when the same reporter number appears several times
    in the sentence; the caller must not bless unless every candidate caption is
    compatible, so a fabricated caption can never hide behind a correct one.
    """
    for form in (verdict.get("citation"), verdict.get("normalized_citation")):
        key = _citation_key(form)
        if key is not None and key in index:
            return index[key]
    return []


def _annotate_litigator_verdicts(
    sentence: str,
    case_verdicts: list[dict],
    manifest: CorpusManifest | None = None,
    attestation: CorpusAttestation | None = None,
) -> None:
    """Annotate the deterministic litigator verdicts in place.

    - ``holding_skipped``: holding-match was deliberately off, so a null holding
      result is "not evaluated" (a positive existence confirmation), distinct
      from the LLM path's "ran but could not determine".
    - ``caption_mismatch``: the number resolves but to a different case than the
      draft names (a fabricated caption on a real number). eyecite reads the
      draft's party names; ``caption_match_state`` compares them per side, so an
      abbreviated real caption is never falsely flagged.
    - ``caption_unconfirmed``: the refusal state. The verifier downgrades it to
      could-not-check, never to the mismatch flag and never to verified. Fires
      when one populated caption side matches the resolved case and the other does
      not ("Smith v. Board" on Brown's number); when the resolved citation cannot
      be reconciled to any cite parsed from the draft, or the resolved record
      carries no name to compare; and when the same reporter number is written more
      than once with captions that do not all match, so a correct caption can never
      bless a fabricated one riding the duplicate number.
    - ``year_mismatch`` / ``court_mismatch``: the number resolves and the caption
      fits, but the draft's court-year parenthetical disagrees with the corpus
      record ("347 U.S. 483 (1990)" on a 1954 case; "(9th Cir.)" on a SCOTUS
      cite). A common hallucination shape; also a refusal, never an accusation,
      because a wrong parenthetical on a real number is usually a draft typo.
      Vacuous when the draft gives no parenthetical.
    - ``bounded_corpus`` and the ``corpus_*`` fields come from the corpus
      MANIFEST (D13), not a constant: a demo or unattested corpus folds every
      miss to could-not-check, while a corpus attesting ``scope="complete"``
      lets a miss read as the loud "no such case as of <as_of>". A
      ``scope="complete"`` manifest is honored ONLY when it is cross-checked
      against the MEASURED corpus ``attestation`` and matches (E2); a manifest
      whose declared size/hash does not match the corpus actually loaded, or
      that arrives with no measurement to check against, folds back to the
      bounded could-not-check rather than emitting a false "no such case". This
      is the most dangerous direction (a false accusation), so the operator's
      string alone never decides it.
    """
    # E2: only a measured, matching attestation may unlock the loud miss. Demo and
    # unattested corpora stay bounded; a mismatched/unmeasured "complete" claim is
    # treated as unattested (bounded, and its unverifiable corpus_* fields are
    # suppressed so the card never reads "complete" for a corpus we could not
    # confirm).
    complete_honored = (
        manifest is not None
        and manifest.scope == "complete"
        and attestation is not None
        and manifest.matches(attestation)
    )
    bounded = not complete_honored
    emit_manifest_fields = manifest is not None and (
        manifest.scope != "complete" or complete_honored
    )
    # Folded-key index (D-citation-form): a fabricated caption cannot hide behind a
    # correct one when the same reporter number appears twice, and a spacing
    # difference between eyecite and CourtListener cannot skip the caption gate.
    refs = _index_citation_refs(find_citations(sentence))
    for batch in case_verdicts:
        for v in batch.get("verdicts", []):
            v["holding_skipped"] = True
            v["bounded_corpus"] = bounded
            if emit_manifest_fields:
                v["corpus_scope"] = manifest.scope
                v["corpus_case_count"] = manifest.case_count
                v["corpus_as_of"] = manifest.as_of
            if not v.get("exists"):
                continue
            matched = _lookup_citation_refs(refs, v)
            if not v.get("case_name") or not matched:
                # exists=True but the caption gate cannot run: either the resolved
                # record carries no name to compare against, or the citation cannot
                # be reconciled to any cite parsed from the draft (the two parsers'
                # forms diverge beyond the fold in _citation_key). REFUSE rather than
                # bless -- an exists=True verdict with no checkable caption reads
                # could-not-check (unknown), never verified. Without this a fabricated
                # caption on a real reporter number slipped the gate and read VERIFIED
                # whenever the forms differed or the name was absent (the existential
                # false-green; the demo corpus aligns the forms, so the gap only
                # showed on the live CourtListener path).
                v["caption_unconfirmed"] = True
                continue
            # Caption gate. With one candidate this is a direct comparison. With
            # several (the same reporter number written more than once in the
            # sentence, e.g. one real caption and one fabricated) the engine cannot
            # tell which occurrence resolved, so it must not let a correct caption
            # bless a fabricated one: refuse unless EVERY candidate caption is
            # compatible. Refuse, never accuse a specific occurrence (ADR-0012: no
            # false accusations).
            states = {caption_match_state(r, v["case_name"]) for r in matched}
            if len(matched) > 1:
                if states != {"match"}:
                    v["caption_unconfirmed"] = True
                    continue
            elif states == {"mismatch"}:
                v["caption_mismatch"] = True
            elif states == {"unconfirmed"}:
                v["caption_unconfirmed"] = True
            # year / court parenthetical checks, applied across every candidate cite
            # (all share the reporter number, so they describe one resolved case): a
            # mismatch on any occurrence is a refusal.
            for ref in matched:
                date_filed = str(v.get("date_filed") or "")
                if ref.year is not None and len(date_filed) >= 4 and date_filed[:4].isdigit():
                    resolved_year = int(date_filed[:4])
                    if ref.year != resolved_year:
                        v["year_mismatch"] = True
                        v["cited_year"] = ref.year
                        v["resolved_year"] = resolved_year
                resolved_court = str(v.get("court") or "")
                # Compare courts only when BOTH sides are courts-db ids ("scotus",
                # "ca9"). eyecite always emits ids, but a non-demo corpus may carry
                # CourtListener's URL or display-name form; comparing across formats
                # would flag every correct parenthetical (a blanket recall collapse),
                # so a non-id resolved court makes the check vacuous instead.
                if (
                    ref.court
                    and resolved_court
                    and _COURT_ID.fullmatch(resolved_court)
                    and ref.court != resolved_court
                ):
                    v["court_mismatch"] = True
                    v["cited_court"] = ref.court


def _opinions_from_verdicts(case_verdicts: list[dict]) -> list[str]:
    """Bundled opinion texts for the cites that resolved in these verdicts."""
    return [
        text
        for batch in case_verdicts
        for v in batch.get("verdicts", [])
        if v.get("exists") and (text := local_opinion_text(v.get("citation")))
    ]


def _attach_bundled_opinion_text(case_verdicts: list[dict]) -> None:
    """Attach the bundled opinion text to each resolved verdict (deterministic path).

    Holding-match is OFF here, so serialize_case_verdict leaves ``opinion_text``
    unset (None). The brief-level draft-quote panel reads ``opinion_text`` off the
    serialized verdict (services.verify._opinion_sources_from_case_verdict) to
    ground a quoted span, so without this a verbatim quote from a bundled opinion
    (e.g. Brown) reads could-not-check at the panel even though the same-sentence
    check confirmed it. Offline: local_opinion_text reads the in-process corpus, no
    network. It is stripped before the SSE wire by services.verify._strip_opinion_text.
    """
    for batch in case_verdicts:
        for v in batch.get("verdicts", []):
            if v.get("exists") and not v.get("opinion_text"):
                text = local_opinion_text(v.get("citation"))
                if text:
                    v["opinion_text"] = text


# C3: contract boilerplate carries no topic signal, so an overlap on these words does
# not make an off-topic clause relevant to the claim. Words shorter than 4 letters are
# already dropped by the extractor below.
_TOPIC_STOPWORDS = frozenset(
    {
        "shall",
        "term",
        "party",
        "agreement",
        "section",
        # Contract structural-name boilerplate: the document type ("Services
        # Agreement") recurs in clause headers across the whole contract, so a
        # shared "services" is not topical relevance. Without this, an off-topic
        # signing-bonus clause that shares only the contract name laundered a
        # coincidental value into a verified present (the demonstrated D5 gap in
        # the binary on-topic check; "agreement" was already here).
        "service",
        "services",
        "clause",
        "this",
        "that",
        "with",
        "from",
        "their",
        "under",
        "hereby",
        "herein",
        "thereof",
        "between",
        "which",
        "such",
        "other",
        "than",
        "into",
        "upon",
        "have",
        "been",
        "were",
        "will",
        "would",
        "there",
        "these",
        "those",
        "each",
        "they",
        "them",
    }
)

# The stopword set with the same trailing-s fold _clause_on_topic applies to
# content words, so the filter compares folded-to-folded ("agreements" and
# "agreement" are one stopword; "this" folds to "thi" on both sides).
_TOPIC_STOPWORDS_FOLDED = frozenset(w[:-1] if w.endswith("s") else w for w in _TOPIC_STOPWORDS)


def _content_tokens(text: str) -> set[str]:
    """Topic-bearing content words of ``text``: 4+ letter words, trailing-s folded,
    minus the folded stopword set.

    Fold the trailing s BEFORE the stopword filter: filtering first let plural
    stopword forms ("agreements", "sections") slip through and earn topic-overlap
    credit. Both sides fold, so a stopword like "this" ("thi" once folded) still
    filters correctly.

    Pulled out as a named function so the sentence side is computed ONCE per
    sentence and reused across every candidate clause (E1): the sentence tokens are
    identical for every clause comparison, so re-deriving them inside the per-node
    loop was pure CPU waste on the no-egress hot path.
    """
    folded = {w[:-1] if w.endswith("s") else w for w in re.findall(r"[a-z]{4,}", text.lower())}
    return folded - _TOPIC_STOPWORDS_FOLDED


def _shares_topic(sentence_tokens: set[str], clause: str) -> bool:
    """True if the precomputed sentence content tokens overlap the clause's.

    The clause side is the only part that varies per candidate node, so only it is
    tokenized here; ``sentence_tokens`` is hoisted out of the per-node loop by the
    caller. ``_shares_topic(_content_tokens(s), c)`` is byte-identical to the old
    ``_clause_on_topic(s, c)``.
    """
    return bool(sentence_tokens & _content_tokens(clause))


def _clause_on_topic(sentence: str, clause: str) -> bool:
    """A parametric present is on-topic only if the claim and the matched clause
    share a content word beyond the coincidental value.

    Blocks an off-topic clause that merely repeats the same number (an unrelated
    signing bonus's $42,000 vs a liability cap's $42,000). The case-existence path
    already gates on relevance ("mere topical relevance is not support"); the contract
    path did not, so an off-topic value coincidence could read a false "present". The
    safe direction is recall loss (could-not-check), never a false accusation.

    Used by the cross-clause adjudicator (PR #166) only as a present's accusation
    veto, not a contradiction floor: the adjudicator decides contradiction
    topicality structurally (a contradiction stands only when no clause carries
    the value), per docs/notes/2026-06-10-cachet-contradiction-topicality.md.

    Content words fold a trailing s so a singular/plural pair counts once, and
    the stopword filter compares folded-to-folded so plural stopword forms
    ("agreements", "sections") cannot slip through and earn topic credit. The hot
    path calls ``_content_tokens`` + ``_shares_topic`` directly to avoid re-deriving
    the sentence tokens per node; this thin wrapper is the single-shot equivalent.
    """
    return _shares_topic(_content_tokens(sentence), clause)


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
            for phrase in quoted_subphrases(run):
                phrase = phrase.strip()
                if phrase and not _run_present_any(phrase, opinions):
                    return (
                        f'The quoted language "{phrase}" could not be verified against '
                        "the source text checked."
                    )
    return None


def _run_present_any(run: str, opinions: list[str]) -> bool:
    """True if ``run`` (or its leading-letter case variant) is verbatim in any opinion."""
    return any(
        verbatim_run_present(variant, op)
        for variant in first_letter_variants(run)
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


def _grounding_verdict(
    anchors: list[Anchor],
    source_sections: frozenset[str],
) -> dict | None:
    """A hard verdict from a grounding anchor, or None.

    The only grounding anchor that yields a deterministic *verdict* (not merely
    could-not-check context) is a section reference ABSENT from the source: a draft
    that cites a section the contract does not contain is unsupported regardless of
    the surrounding predicate. Computed regardless of clause-checkable anchors: a
    fabricated section is an affirmative independent finding, and suppressing it
    let "Under Section 99, the royalty equals 50%" ride a matching value into a
    green card. Precedence with the clause verdict is decided at the mapping
    layer (services/verify.py): a parametric contradiction keeps its both-values
    reason; every other clause disposition yields to the fabricated-section
    finding.

    Asymmetry, deliberately:
      - The POSITIVE direction (a section that exists) is NOT promoted to a verdict.
        Existence is not proof of the sentence's predicate ("S 7.2 governs X" only
        verifies that 7.2 exists, not that it governs X), so it stays the honest
        could-not-check affirmation from ``_grounding_reason`` - never an
        overclaiming "verified".
      - PARTY anchors yield no verdict in either direction: the positive overclaims
        the same way, and an unmatched party is far more often name-form variance
        ("Acme" vs "Acme Corp.") than a fabricated party, so a hard "not a party"
        is the false-accusation direction the product refuses.

    Precision gate on the negative: fires only when ``source_sections`` is
    non-empty. An empty set means no sections were extracted from the source (an
    un-ingested source, or numbering in a form the detector misses, e.g. roman
    "Article VII"), in which case every draft section would read absent - so we stay
    could-not-check rather than false-accuse.
    """
    if not source_sections:
        return None
    sections = list(dict.fromkeys(a.text for a in anchors if a.type == "section"))
    absent = [s for s in sections if _normalize_section(s) not in source_sections]
    if not absent:
        return None
    listed = ", ".join(absent)
    return {
        "disposition": "section_absent",
        "sections": absent,
        "detail": (
            f"This statement references {listed}, which could not be located in the "
            "source contract."
        ),
    }


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
    # Retrieval is imprecise, so the matching clause may not be rank 1. Every
    # retrieved clause is evaluated and the PURE adjudicator decides
    # (contract_verify.adjudicate_clause_candidates, per the topicality
    # decision in docs/notes/2026-06-10-cachet-contradiction-topicality.md):
    # a contradiction stands only when no clause carries the claim's value for
    # that anchor type; a same-type present anywhere makes accusing from a
    # different clause a guess, so the engine refuses with both clauses named.
    # The old loop broke on the FIRST present-or-contradiction in rank order,
    # which let an off-topic clause accuse a claim whose value a later clause
    # confirmed (the live false-accusation finding).
    # The sentence's topic tokens are identical for every candidate clause, so
    # derive them ONCE here (E1) rather than re-tokenizing the sentence inside the
    # per-node loop. Only the clause side varies per node.
    sentence_tokens = _content_tokens(sentence)
    candidates: list[ClauseCandidate] = []
    for node in nodes:
        candidate = verify_claim_against_clause(sentence, node.verbatim_text)
        on_topic = True
        if candidate.disposition == "present" and candidate.anchor_type != "quote":
            # C3: an off-topic clause that merely shares the literal value is
            # not support. The adjudicator never greens it, but keeps it as an
            # accusation veto (the value IS verbatim in the contract).
            on_topic = _shares_topic(sentence_tokens, node.verbatim_text)
        elif candidate.disposition == "parametric_contradiction":
            # Accuser selection only: when several clauses contradict, the
            # adjudicator lets an on-topic accuser supply the evidence before
            # an off-topic one. Never gates whether the accusation stands.
            on_topic = _shares_topic(sentence_tokens, node.verbatim_text)
        candidates.append(
            ClauseCandidate(candidate, node.heading_path, node.verbatim_text, on_topic)
        )
    verdict, section, matched_clause = adjudicate_clause_candidates(candidates)
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
            # The verbatim draft figure the altered-figure pre-pass matched (e.g.
            # "60 billion"), so the verifier can surface it as a token highlight
            # inside the flagged statement. None on the per-type parametric path,
            # whose values are canonical, not verbatim. Server-internal otherwise.
            "claim_span": verdict.claim_span,
            "section": section,
            # D1: the matched clause text, server-internal (the contract_verdict is
            # not serialized to the wire). It seeds the brief-level quote pool so a
            # quote the claim already confirmed verbatim reads "verbatim" in the
            # QuotePanel too, instead of the two surfaces disagreeing.
            "clause_text": matched_clause,
        },
    }
    # C2 (anchor-laundering guard): a parametric present (money / date / duration
    # match) must not launder a quoted holding that is absent from the matched
    # clause. Re-check the sentence's quoted phrases against the clause that
    # produced the present; if one is not verbatim there, surface a could-not-check
    # reason so the verifier downgrades verified -> unknown. A present that came
    # FROM a verbatim quote (anchor_type "quote") is already confirmed and exempt.
    # Refuse, never accuse (ADR-0012 invariant 2).
    if (
        verdict.disposition == "present"
        and verdict.anchor_type != "quote"
        and matched_clause is not None
    ):
        quote_reason = _quote_unverified_reason(sentence, [matched_clause])
        if quote_reason:
            claim["quote_could_not_check_reason"] = quote_reason
    # Grounding overlay (defined_term + party + section). A sentence whose only
    # checkable signals are grounding anchors gets an honest could-not-check that
    # names them, never the misleading "language does not appear" and never a verdict.
    # A clause-checkable anchor suppresses it, so a parametric/quote result always
    # wins outright (ADR-0012 invariant 2).
    # A section reference absent from the source is a hard unsupported verdict; it
    # supersedes the could-not-check grounding prose (which would otherwise just name
    # the same missing section). Everything else stays could-not-check context.
    section_verdict = _grounding_verdict(anchors, source_sections)
    if section_verdict is not None:
        claim["section_verdict"] = section_verdict
    else:
        reason = _grounding_reason(anchors, source_parties, source_sections)
        if reason:
            claim["could_not_check_reason"] = reason
    return claim


def _t1_anchor_free_assessment(
    conn: sqlite3.Connection,
    sentence: str,
    doc_ids: Sequence[str],
    embedder: Embedder | None,
) -> dict | None:
    """ADR-0012 T1: a local-model assessment for an anchor-free sentence, or None.

    Dark behind ``t1_permitted()`` (the caller gates on it). Retrieves the top
    ``rank_cutoff`` source clauses and returns the BEST above-threshold assessment over
    them (best-of-K). ``rank_cutoff`` and the verdict threshold are read from the gate-bound
    thresholds.json. For the runtime false-affirmative rate to equal the gated rate, the
    gate's predictions must be generated under this same best-of-K strategy; that
    equivalence is the corpus step's responsibility and is not yet mechanically enforced
    (ADR-0012 "Implementation notes"). None keeps the claim in the could-not-check tray
    (invariant 2: no coverage-by-guessing).
    """
    thresholds = load_runtime_thresholds()
    if thresholds is None:
        return None
    verdict_threshold, rank_cutoff = thresholds
    nodes = search_typed_hybrid(
        conn, sentence, doc_ids=list(doc_ids), embedder=embedder, limit=rank_cutoff
    )
    scorer = default_scorer()
    best: T1Assessment | None = None
    for rank, node in enumerate(nodes, start=1):
        assessment = assess(
            T1Candidate(sentence=sentence, clause=node.verbatim_text, rank=rank),
            scorer=scorer,
            verdict_threshold=verdict_threshold,
            rank_cutoff=rank_cutoff,
        )
        if assessment is not None and (best is None or assessment.confidence > best.confidence):
            best = assessment
    if best is None:
        return None
    return {"label": best.label, "confidence": best.confidence, "model": active_model_id()}


def build_deterministic_envelope(
    draft: str,
    *,
    conn: sqlite3.Connection | None = None,
    doc_ids: Sequence[str] | None = None,
    client: httpx.Client | None = None,
    embedder: Embedder | None = None,
    corpus_manifest: CorpusManifest | None = None,
) -> dict:
    """Build a verify envelope for ``draft`` with no LLM.

    Litigator path: each citation-bearing sentence becomes a claim with its
    case-existence verdicts attached. Contract path (when ``conn`` + ``doc_ids``
    are given): each other anchor-bearing sentence is checked against the
    retrieved contract clause. A sentence with a checkable anchor but no source
    to check it against is a could-not-check claim; a sentence with no checkable
    anchor at all is marked ``untreated`` (the caller emits no card for it, so it
    renders as plain draft text).
    """
    # Offline by construction: case-existence is answered from the bundled corpus
    # via an in-process MockTransport, never the network. Going online is an
    # explicit code-level opt-in (inject a client); there is deliberately no env
    # var that turns on egress, so "no data leaves this device" holds even if the
    # operator's setup is wrong. The courtlistener token guard still passes with the
    # demo sentinel token, so without this floor the litigator path would POST the
    # brief text to courtlistener.com.
    cl_client = client if client is not None else local_caselaw_client()
    # The corpus manifest travels with the corpus, not the engine. The default
    # client serves DEMO_CORPUS, so it carries DEMO_MANIFEST; an injected client
    # without a manifest stays unattested, which folds conservatively to
    # bounded_corpus (a miss is could-not-check, never "no such case").
    manifest = (
        corpus_manifest
        if corpus_manifest is not None
        else (DEMO_MANIFEST if client is None else None)
    )
    # E2: the MEASURED attestation of the corpus this client serves, used to
    # cross-check a scope="complete" manifest before any miss can read "no such
    # case". A client built by local_caselaw_client carries it; a raw injected
    # client (e.g. a real CourtListener client) carries none, so a "complete"
    # claim against it cannot be honored and folds to could-not-check.
    corpus_attestation = getattr(cl_client, CORPUS_ATTESTATION_ATTR, None)

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
    # Offline by construction extends to retrieval. The contract path embeds the
    # draft to find clauses; with no injected embedder the retrieval layer would
    # otherwise build a network-capable default_embedder(), so we use the
    # offline-enforced one. Acquired LAZILY, on the first sentence that actually
    # needs it: a litigator-only draft (every sentence a case cite or anchor-free)
    # then never loads the weights and can never crash on a cold fastembed cache.
    # If the weights are missing, the contract sentence degrades to an honest
    # could-not-check below, never a dead request and never a silent pass.
    embedder_tried = embedder is not None

    def _ensure_embedder() -> Embedder | None:
        nonlocal embedder, embedder_tried
        if not embedder_tried:
            embedder_tried = True
            try:
                embedder = offline_embedder()
            except RuntimeError:
                embedder = None
        return embedder

    # Defined-term detection keys off the source contract's own definitions: built
    # once here (offline) and passed to every sentence's extraction. None on the
    # litigator-only path, leaving that path unchanged.
    alias_table = _source_alias_table(conn, doc_ids) if contract_mode else None
    source_parties, source_sections = (
        _source_party_section_sets(conn, doc_ids) if contract_mode else (frozenset(), frozenset())
    )
    sentences = split_sentences(draft)
    claims: list[dict] = []
    # Opinion text of the cases that resolved in each sentence. The altered-quote
    # pass below attributes SAME-SENTENCE only; this map is keyed by sentence
    # index for that pass.
    opinions_by_sentence: dict[int, list[str]] = {}
    for i, sentence in enumerate(sentences):
        anchors = extract_anchors(sentence, alias_table=alias_table)
        # Case-existence applies only to CASE citations. A law/regulation cite
        # (C.F.R., U.S.C., an EU Directive) is a citation anchor for grounding, but
        # it is not a case: routing it here would report a real regulation as
        # "cited case not found" (a false accusation). It instead flows to the
        # contract / could-not-check path, checked via its other anchors.
        if any(r.kind == "case" for r in find_citations(sentence)):
            verdicts = verify_claims_for_cases(
                [sentence], client=cl_client, enable_holding_match=False
            )
            serialized = [serialize_case_verdict(v) for v in verdicts]
            # Existence verifies the reporter number resolves; this also checks the
            # draft's caption names the resolved case, so a fabricated caption on a
            # real number ("Fake v. Nobody, 347 U.S. 483") is caught, not passed.
            _annotate_litigator_verdicts(
                sentence, serialized, manifest=manifest, attestation=corpus_attestation
            )
            # Holding-match is off, so the serialized verdicts carry no opinion text;
            # attach the bundled text so the brief-level quote panel can ground a
            # quoted span against the cited opinion (stripped before the SSE wire).
            _attach_bundled_opinion_text(serialized)
            opinions_by_sentence[i] = _opinions_from_verdicts(serialized)
            claims.append({"text": sentence, "citations": [], "case_verdicts": serialized})
        elif contract_mode and anchors:
            emb = _ensure_embedder()
            if emb is None:
                # The offline embedding weights are not cached on this machine, so the
                # clause retrieval cannot run. Degrade THIS sentence to an honest
                # could-not-check rather than killing the whole request: a litigator
                # cite in the same draft still verifies, and the operator sees a clear,
                # actionable reason instead of a dead stream.
                claims.append(
                    {
                        "text": sentence,
                        "citations": [],
                        "case_verdicts": [],
                        "could_not_check_reason": (
                            "The contract source index is unavailable on this machine "
                            "(the offline embedding model is not cached), so this "
                            "statement could not be checked against a clause."
                        ),
                    }
                )
            else:
                claims.append(
                    _contract_claim(
                        conn,
                        sentence,
                        doc_ids,
                        emb,
                        anchors=anchors,
                        source_parties=source_parties,
                        source_sections=source_sections,
                    )
                )
        elif not anchors:
            # UNTREATED: no checkable anchor of any kind (no citation, quotation,
            # amount, date, duration, party, section, or defined term). There is
            # nothing to check, so this is not a finding: the claim carries an
            # ``untreated`` marker, never becomes a card or a tray entry, and renders
            # as plain draft text. "Nothing to check here" is not a verdict, so it must
            # never read as could-not-check. This is the bulk of clean prose; surfacing
            # it as a per-sentence could-not-verify card was the "everything needs
            # review" alert fatigue. See
            # docs/notes/2026-06-08-untreated-vs-could-not-check.md.
            claim = {
                "text": sentence,
                "citations": [],
                "case_verdicts": [],
                "untreated": True,
            }
            # ADR-0012 T1 recall tier, DARK behind t1_permitted() (False on main: no
            # gate-pass artifact exists). When the gate is honestly open and a local
            # model returns an above-threshold assessment, the sentence is PROMOTED out
            # of untreated into an assessed could-not-check card (coverage by assessment
            # surfaces for the lawyer's review); the verdict stays unknown and the
            # assessment only rides as assistive provenance (invariant 1). With T1 dark
            # this never fires and the sentence stays untreated, byte-identical to
            # flag-off.
            if contract_mode and conn is not None and doc_ids and t1_permitted():
                emb = _ensure_embedder()
                if emb is not None:
                    assessment = _t1_anchor_free_assessment(conn, sentence, doc_ids, emb)
                    if assessment is not None:
                        del claim["untreated"]
                        claim["could_not_check_reason"] = _ANCHOR_FREE_REASON
                        claim["t1_assessment"] = assessment
            claims.append(claim)
        else:
            # COULD-NOT-CHECK: the sentence carries a checkable value (e.g. a money or
            # date anchor in a litigator-only draft with no contract loaded) but no
            # source was provided to check it against. A check was warranted and could
            # not complete, so it stays a neutral could-not-check card, never untreated.
            claims.append(
                {
                    "text": sentence,
                    "citations": [],
                    "case_verdicts": [],
                    "could_not_check_reason": (
                        "This statement carries a checkable value but no source was "
                        "provided to check it against."
                    ),
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
