"""Cross-document labeled-fact consistency ledger for the Cachet engine.

The fact-ledger primitive (``services/fact_ledger.py``) decides when one
document binds the same quoted defined term to two irreconcilable figures, and
``services/cross_document.py`` lifts that exact-term ledger across named
documents. This module is the operator-mandated widening of the LABEL side of
that fact: it ingests two or more documents (a list of ``{doc_id, text}``
dicts), extracts figure-anchored facts -- money, duration, percent, calendar
date, integer count -- attached to an EXACTLY-matching normalized label, and
emits a deterministic ``contradicted`` finding when two documents state
different values for the same (label, unit) fact. Three label shapes key the
ledger, all exact after case/whitespace normalization only:

* a quoted defined term ('the "Termination Fee" shall be $50,000'), reusing
  the fact-ledger primitive's own extraction verbatim;
* a section-qualified line label ('Section 8.2 Break Fee: $200,000');
* an identical literal line label ('TERMINATION FEE: $50,000' meets
  'Termination Fee: $75,000' -- case and whitespace normalize, nothing else).

Deciding with certainty that Document A and Document B disagree about the same
fact is work everyone assumes needs an LLM; the engine does it with exact
string keys and refuses cleanly everywhere the keys do not exactly match.

Campaign invariants (honesty floor), enforced by construction:

* ONLY ``contradicted`` or ``could_not_verify`` ever leaves this module.
  There is no supported/verified/green output state anywhere --
  ``CrossDocLedgerFinding.__post_init__`` rejects any other verdict at
  construction -- so a false green is impossible structurally, not by tuning.
* SILENT when consistent and SILENT when labels do not exactly match. A label
  whose every cross-document value normalizes equal, a label present in one
  document only, a document set with no labeled facts, and near-miss labels
  ("Termination Fee" vs "Early Termination Fee") all produce NO finding. No
  fuzzy, stemmed, semantic, or substring label matching exists in this file
  (ADR-0013: no regex subject-proxy affirmation); case/whitespace
  normalization is the entire matching relation.
* EVERY finding names its own figures: both document ids, the shared label,
  and both conflicting literal values verbatim. Content-free findings fail
  review.
* UNITS normalize before comparison only where the conversion is exact
  (years x12 -> months, weeks x7 -> days, inherited from the fact ledger).
  Where normalization is not certain -- calendar days vs calendar months,
  USD vs EUR -- the module refuses with ``could_not_verify`` naming both
  values rather than guessing in either direction.
* NEVER accuse a faithful copier. ``verbatim_run_present=True`` (or a
  per-document ``"verbatim": true`` mark) attributes a surviving conflict to
  the underlying sources with a refusal; the drafters are never accused.
* Hedged figures ('approximately') refuse unless every figure shares one
  bound-style hedge class, and a document internally inconsistent on a key
  poisons the cross-document comparison into a refusal (the intra-document
  conflict is the single-document detector's domain).

Pure stdlib (``re``, ``datetime``, ``decimal``, ``dataclasses``); no network,
no LLM, no I/O, no learned weights anywhere in the call path. All regex
quantifiers are bounded (CWE-1333 hardening, kernel ReDoS precedent).
Deterministic: same inputs, same output list, always.

    from services.crossdoc_ledger import detect_crossdoc_contradictions

    findings = detect_crossdoc_contradictions(
        [
            {"doc_id": "Agreement", "text": agreement_text},
            {"doc_id": "Amendment No. 2", "text": amendment_text},
        ]
    )
    for f in findings:
        print(f["verdict"], f["label"], f["detail"])
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from decimal import Decimal

# Read-only reuse of the fact-ledger primitive's extraction and normalization
# helpers (the module-level pattern cross_document.py established): term
# collection, the figure grammar, figure parsing, hedge classes, sentence
# snippets, whitespace normalization, and dimension labels stay single-sourced
# with the ledger instead of drifting copies. Nothing here mutates or
# monkeypatches the primitive.
from services.fact_ledger import (
    ALLOWED_VERDICTS,
    CONTRADICTED,
    COULD_NOT_VERIFY,
    _classify_hedge,
    _collect_defined_terms,
    _dim_label,
    _FIGURE_SRC,
    _HEDGE_SRC,
    _MAX_TEXT,
    _normalize,
    _parse_figure,
    _snippet,
    _TERM_RE,
    extract_bindings,
)

__all__ = [
    "ALLOWED_VERDICTS",
    "CONTRADICTED",
    "COULD_NOT_VERIFY",
    "CrossDocFact",
    "CrossDocLedgerFinding",
    "detect_crossdoc_contradictions",
    "extract_labeled_facts",
]

_MAX_DOCS = 32  # DoS bound, cross_document precedent.

# --- Date grammar --------------------------------------------------------------
#
# Only formats with a spelled month name (or ISO 8601) are extracted: they are
# the only calendar-date surfaces with exactly one reading. Numeric slash
# dates ('03/04/2026') are DD/MM vs MM/DD ambiguous, so they are never bound
# at all -- a fact the engine cannot read with certainty never enters the
# ledger and can never conflict.

_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))

_DATE_SRC = (
    rf"(?<![A-Za-z])(?P<xdmon>(?i:{_MONTH_ALT}))\s+(?P<xdday>\d{{1,2}})(?!\d)\s*,?\s+"
    rf"(?P<xdyear>\d{{4}})(?!\d)"
    rf"|(?<!\d)(?P<xdday2>\d{{1,2}})\s+(?P<xdmon2>(?i:{_MONTH_ALT}))(?![A-Za-z])\s*,?\s+"
    rf"(?P<xdyear2>\d{{4}})(?!\d)"
    r"|(?<![\d-])(?P<xdiso>\d{4}-\d{2}-\d{2})(?![\d-])"
)

# Non-USD currencies exist here ONLY so a cross-currency reuse of one label
# can refuse with both figures named; there is no exchange-rate path anywhere.
_ALT_MONEY_SRC = (
    r"(?:(?P<xcur>(?i:EUR|GBP)(?![A-Za-z])|€|£)\s?)"
    r"(?P<xamt>\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d{1,12}(?:\.\d{1,2})?)(?!,?\d)(?!\.\d)"
)

# A labeled bare integer ('Permitted Assignees: 3'). Lowest-priority
# alternative; it only ever compares against another labeled bare integer.
# Leading zeros and slash/dash/colon-adjacent digit runs are never bound:
# '03/04/2026' is an ambiguous numeric date, not a count of anything.
_BARE_INT_SRC = r"(?<![\d.$€£/:-])(?!0\d)(?P<xint>\d{1,9})(?!\d)(?![.,]\d)(?![ \t]?%)(?![/:-]\d)"

_VALUE_SRC = (
    rf"(?P<xfact>(?:(?P<xhedge>{_HEDGE_SRC})\s+)?"
    rf"(?:{_DATE_SRC}|{_ALT_MONEY_SRC}|{_FIGURE_SRC}|{_BARE_INT_SRC}))"
)

# --- Line-label grammar ---------------------------------------------------------
#
# A colon label binds only at line start, only when the figure directly
# follows the colon, and only when the label's first word is capitalized;
# tail words must be capitalized or drawn from a closed connector set. This
# keeps 'Time is of the essence: 30 days' from minting a fact while
# 'Section 8.2 Break Fee: $200,000' and 'Closing Date: 2027-01-15' bind.

_LABEL_CONNECTORS = r"of|and|or|the|for|to|in|per"
_SECTION_SRC = r"(?:Section\s+\d{1,3}(?:\.\d{1,3}){0,3}\s+)?"
_LABEL_SRC = (
    rf"(?P<xlabel>{_SECTION_SRC}[A-Z][A-Za-z0-9'&-]{{0,29}}"
    rf"(?:[ \t]+(?:[A-Z][A-Za-z0-9'&-]{{0,29}}|{_LABEL_CONNECTORS})){{0,7}})"
)
_COLON_FACT_RE = re.compile(rf"(?m)^[ \t]*{_LABEL_SRC}[ \t]*:[ \t]*{_VALUE_SRC}")

# Standalone generic headings that are not the name of a fact. A normalized
# label equal to one of these never binds: two documents both opening a line
# with 'Note:' are not stating the same labeled fact, and accusing on that
# key would be a false accusation. Multi-word labels containing these words
# ("Purchase Price", "Closing Date") are unaffected.
_GENERIC_LABELS = frozenset(
    {
        "note",
        "notes",
        "nb",
        "important",
        "warning",
        "caution",
        "attention",
        "example",
        "examples",
        "summary",
        "background",
        "recitals",
        "whereas",
        "exhibit",
        "schedule",
        "appendix",
        "annex",
        "disclaimer",
        "confidential",
        "draft",
        "date",
        "page",
        "total",
        "subtotal",
        "item",
        "amount",
        "price",
        "value",
        "number",
        "no",
        "re",
        "subject",
        "from",
        "to",
        "cc",
    }
)

# --- Quoted-term date/alt-currency binder ---------------------------------------
#
# The fact-ledger primitive binds money/duration/percent/count to quoted
# defined terms; this small companion binds the two figure shapes the
# primitive does not carry (calendar dates, non-USD money) through the same
# quotes-hug-the-exact-string discipline. No unquoted shape exists here.

_XDEF_VERBS_SRC = (
    r"(?i:shall\s+mean|shall\s+be|shall\s+occur\s+on|will\s+be|will\s+occur\s+on"
    r"|occurs\s+on|is\s+scheduled\s+for|means|equals|is)"
)
_XFILLER_SRC = r"(?:(?i:the|an?|on|of|to)\s+){0,3}"
_XEXTRA_VALUE_SRC = rf"(?P<xfact>(?:(?P<xhedge>{_HEDGE_SRC})\s+)?(?:{_DATE_SRC}|{_ALT_MONEY_SRC}))"


def _term_extra_pattern(term: str) -> re.Pattern[str]:
    e = re.escape(term)
    return re.compile(
        rf"(?:(?i:the)\s+)?\"(?P<xtermocc>{e})\"\s+{_XDEF_VERBS_SRC}\s+"
        rf"{_XFILLER_SRC}{_XEXTRA_VALUE_SRC}"
    )


# --- Figure parsing --------------------------------------------------------------


def _parse_date(gd: dict) -> tuple[str, str] | None:
    """("date", ISO value) from a date match's groups, or None when invalid."""
    if gd.get("xdiso"):
        y, mo, d = (int(p) for p in gd["xdiso"].split("-"))
    else:
        mon = gd.get("xdmon") or gd.get("xdmon2")
        day = gd.get("xdday") or gd.get("xdday2")
        year = gd.get("xdyear") or gd.get("xdyear2")
        if not (mon and day and year):
            return None
        y, mo, d = int(year), _MONTHS[mon.lower()], int(day)
    try:
        return "date", datetime.date(y, mo, d).isoformat()
    except ValueError:
        return None  # '2027-02-31' is not a calendar date; never bound.


def _parse_value(gd: dict) -> tuple[str, str] | None:
    """(dimension, canonical value) for one matched value, or None."""
    if gd.get("xdiso") or gd.get("xdmon") or gd.get("xdmon2"):
        return _parse_date(gd)
    if gd.get("xamt"):
        cur = {"€": "EUR", "£": "GBP"}.get(gd["xcur"], gd["xcur"].upper())
        cents = int(Decimal(gd["xamt"].replace(",", "")) * 100)
        return f"money_{cur.lower()}", f"{cur} {cents // 100}.{cents % 100:02d}"
    if gd.get("xint"):
        return "count", str(int(gd["xint"]))
    return _parse_figure(gd)  # money_usd / percent / duration / count_<noun>


def _label_for_dim(dimension: str) -> str:
    if dimension == "date":
        return "calendar date"
    if dimension == "money_eur":
        return "money (EUR)"
    if dimension == "money_gbp":
        return "money (GBP)"
    if dimension == "count":
        return "integer count"
    return _dim_label(dimension)


# Unit classes inside which two different dimensions are the SAME kind of fact
# in incomparable units (refuse, name both). Dimensions outside one class
# (a duration here, a money amount there) are different facts and stay silent.
_UNIT_CLASSES = {
    "duration_days": "time",
    "duration_months": "time",
    "money_usd": "money",
    "money_eur": "money",
    "money_gbp": "money",
}
_CLASS_REFUSAL_NOTE = {
    "time": (
        "Calendar days and calendar months have no deterministic conversion, so the "
        "engine cannot prove these figures equal or unequal across documents"
    ),
    "money": (
        "Amounts in different currencies have no deterministic conversion (no exchange "
        "rate is a fact of the documents), so the engine cannot prove these figures "
        "equal or unequal across documents"
    ),
}


# --- Fact and finding shapes -----------------------------------------------------


@dataclass(frozen=True)
class CrossDocFact:
    """One labeled figure located in one named document."""

    doc_id: str
    label: str  # verbatim label surface, e.g. 'TERMINATION FEE'
    label_key: str  # case/whitespace-normalized exact key
    dimension: str  # money_usd | money_eur | money_gbp | percent | date |
    # duration_days | duration_months | count | count_<noun>
    value: str  # canonical normalized value, e.g. "USD 50000.00", "2027-01-15"
    surface: str  # verbatim figure text, hedge included when present
    hedge: str | None  # approx | cap | floor | None
    start: int  # figure character offsets in the document
    end: int
    snippet: str
    verbatim: bool  # caller-marked faithful copy of a source


@dataclass(frozen=True)
class CrossDocLedgerFinding:
    """One verdict this detector adds. Never a green one.

    ``__post_init__`` makes the zero-green invariant structural: constructing
    a finding with any verdict outside ``ALLOWED_VERDICTS`` raises, so no code
    path in (or importing) this module can mint a supported state from it.
    """

    verdict: str  # "contradicted" | "could_not_verify", nothing else
    kind: str
    label: str
    dimension: str
    detail: str
    figures: tuple  # per-figure dicts: doc_id, label, surface, normalized,
    # hedge, start, end, snippet, verbatim

    def __post_init__(self) -> None:
        if self.verdict not in ALLOWED_VERDICTS:
            raise ValueError(
                "crossdoc_ledger detector can only emit "
                f"{sorted(ALLOWED_VERDICTS)}; got {self.verdict!r}. "
                "It has no green output state by design."
            )


def _figure_payloads(facts: list[CrossDocFact]) -> tuple:
    return tuple(
        {
            "doc_id": f.doc_id,
            "label": f.label,
            "surface": f.surface,
            "normalized": f.value,
            "hedge": f.hedge,
            "start": f.start,
            "end": f.end,
            "snippet": f.snippet,
            "verbatim": f.verbatim,
        }
        for f in facts
    )


def _figure_phrase(facts: list[CrossDocFact]) -> str:
    return "; ".join(
        f"{f.doc_id} states '{f.surface}' (= {f.value}) at offset {f.start}" for f in facts
    )


def _distinct(values) -> list[str]:
    seen: dict[str, None] = {}
    for v in values:
        seen.setdefault(v, None)
    return list(seen)


# --- Input normalization ----------------------------------------------------------


def _normalize_documents(documents) -> list[tuple[str, str, bool]]:
    """(doc_id, text, verbatim) triples in caller order, validated."""
    if isinstance(documents, Mapping):
        items = [{"doc_id": k, "text": v} for k, v in documents.items()]
    else:
        items = list(documents) if not isinstance(documents, str) else None
        if items is None:
            raise TypeError("documents must be a list of {doc_id, text} dicts, not a str")
    if len(items) > _MAX_DOCS:
        raise ValueError(f"at most {_MAX_DOCS} documents per comparison; got {len(items)}")
    triples: list[tuple[str, str, bool]] = []
    seen: set[str] = set()
    for item in items:
        if isinstance(item, Mapping):
            doc_id, text = item.get("doc_id"), item.get("text")
            verbatim = bool(item.get("verbatim", False))
        else:
            try:
                doc_id, text, verbatim = item[0], item[1], False
            except (TypeError, IndexError, KeyError) as exc:
                raise TypeError(
                    "each document must be a {doc_id, text} dict or a (doc_id, text) pair"
                ) from exc
        if not isinstance(doc_id, str) or not doc_id.strip():
            raise ValueError(f"doc_id must be a non-blank string; got {doc_id!r}")
        if not isinstance(text, str):
            raise TypeError(f"document {doc_id!r} text must be str, got {type(text).__name__}")
        if doc_id in seen:
            raise ValueError(f"duplicate doc_id {doc_id!r}: identities must be unambiguous")
        seen.add(doc_id)
        triples.append((doc_id, text, verbatim))
    return triples


# --- Extraction --------------------------------------------------------------------


def extract_labeled_facts(
    doc_id: str,
    text: str,
    *,
    extra_terms=(),
    verbatim: bool = False,
) -> list[CrossDocFact]:
    """Every labeled figure in one document, document order.

    Three layers, all exact-match: the fact-ledger primitive's quoted-term
    bindings (reused verbatim via ``extract_bindings``), a quoted-term binder
    for the two figure shapes the primitive lacks (calendar dates, non-USD
    money), and line-start colon labels. ``extra_terms`` additively widens the
    quoted-term candidate list with exact strings defined in sibling
    documents, exactly as the primitive documents.
    """
    if not isinstance(text, str):
        raise TypeError(f"text must be str, got {type(text).__name__}")
    if len(text) > _MAX_TEXT:
        raise ValueError(f"text exceeds the {_MAX_TEXT}-char crossdoc-ledger bound")

    facts: dict[tuple[str, str, int], CrossDocFact] = {}

    def _add(label: str, dimension: str, value: str, hedge, start: int, end: int) -> None:
        key = _normalize(label)
        if not key or key in _GENERIC_LABELS:
            return
        facts.setdefault(
            (key, dimension, start),
            CrossDocFact(
                doc_id=doc_id,
                label=label,
                label_key=key,
                dimension=dimension,
                value=value,
                surface=re.sub(r"\s+", " ", text[start:end]).strip(),
                hedge=hedge,
                start=start,
                end=end,
                snippet=_snippet(text, start, end),
                verbatim=verbatim,
            ),
        )

    # Layer 1: the fact-ledger primitive's own quoted-term bindings.
    for b in extract_bindings(text, extra_terms=extra_terms):
        _add(b.term, b.dimension, b.value, b.hedge, b.start, b.end)

    # Layer 2: quoted-term dates and non-USD money.
    terms: dict[str, None] = {}
    for t in _collect_defined_terms(text):
        terms.setdefault(t, None)
    for t in extra_terms:
        if isinstance(t, str) and _TERM_RE.fullmatch(f'"{t}"'):
            terms.setdefault(t, None)
    for term in sorted(terms, key=lambda t: (-len(t), t)):
        for m in _term_extra_pattern(term).finditer(text):
            parsed = _parse_value(m.groupdict())
            if parsed is None:
                continue
            dimension, value = parsed
            hedge = _classify_hedge(m.groupdict().get("xhedge"))
            _add(term, dimension, value, hedge, *m.span("xfact"))

    # Layer 3: line-start colon labels.
    for m in _COLON_FACT_RE.finditer(text):
        gd = m.groupdict()
        parsed = _parse_value(gd)
        if parsed is None:
            continue
        dimension, value = parsed
        hedge = _classify_hedge(gd.get("xhedge")) or _classify_hedge(gd.get("hedge"))
        _add(m.group("xlabel").strip(), dimension, value, hedge, *m.span("xfact"))

    return sorted(facts.values(), key=lambda f: (f.start, f.label_key, f.dimension))


# --- Disposition --------------------------------------------------------------------


def _dispose_dimension(
    label_key: str,
    dimension: str,
    facts: list[CrossDocFact],
    doc_index: dict[str, int],
    verbatim_override: bool | None,
) -> CrossDocLedgerFinding | None:
    ordered = sorted(facts, key=lambda f: (doc_index[f.doc_id], f.start))
    if len(_distinct(f.value for f in ordered)) < 2:
        return None  # one value across every document: consistent, SILENT.

    label = _distinct(f.label for f in ordered)[0]
    dim_label = _label_for_dim(dimension)
    unhedged = [f for f in ordered if f.hedge is None]
    hedge_classes = {f.hedge for f in ordered}

    if len(_distinct(f.value for f in unhedged)) >= 2:
        relevant = unhedged
        hedge_note = ""
    elif hedge_classes == {"cap"} or hedge_classes == {"floor"}:
        relevant = ordered
        bound_word = (
            "upper-bound ('up to')" if hedge_classes == {"cap"} else "lower-bound ('at least')"
        )
        hedge_note = f" Every figure shares the same {bound_word} hedge semantics."
    else:
        # 'approximately'-class or mixed hedging: no deterministic comparison
        # exists. Refuse, naming every document and figure this key carries.
        return CrossDocLedgerFinding(
            verdict=COULD_NOT_VERIFY,
            kind="crossdoc_hedged_figures",
            label=label,
            dimension=dimension,
            detail=(
                f'The label "{label}" is bound to differing {dim_label} figures across '
                f"documents that are hedged: {_figure_phrase(ordered)}. Hedged figures "
                "without shared bound semantics cannot be compared deterministically; "
                "the engine names the figures and refuses rather than guess. Review "
                "manually."
            ),
            figures=_figure_payloads(ordered),
        )

    # A document that asserts two values for this key on its own poisons the
    # cross-document comparison: no single per-document value exists.
    per_doc: dict[str, list[CrossDocFact]] = {}
    for f in relevant:
        per_doc.setdefault(f.doc_id, []).append(f)
    for doc, group in per_doc.items():
        if len(_distinct(f.value for f in group)) >= 2:
            return CrossDocLedgerFinding(
                verdict=COULD_NOT_VERIFY,
                kind="crossdoc_intra_document_conflict",
                label=label,
                dimension=dimension,
                detail=(
                    f'The label "{label}" carries conflicting {dim_label} figures across '
                    f"documents: {_figure_phrase(relevant)}. However, {doc} is internally "
                    "inconsistent on this label, so no single per-document value exists "
                    "to compare across documents. The engine names every figure and "
                    "refuses rather than guess; the intra-document conflict itself is "
                    "the single-document fact-ledger detector's domain."
                ),
                figures=_figure_payloads(relevant),
            )

    per_doc_value = {doc: group[0].value for doc, group in per_doc.items()}
    if len(per_doc_value) < 2 or len(_distinct(per_doc_value.values())) < 2:
        return None  # the disagreement does not span two documents: SILENT.

    verbatim_involved = (
        verbatim_override if verbatim_override is not None else any(f.verbatim for f in relevant)
    )
    if verbatim_involved:
        # At least one conflicting figure was faithfully copied from a source:
        # the conflict belongs to the sources, and the engine will not accuse
        # a drafter who copied faithfully.
        return CrossDocLedgerFinding(
            verdict=COULD_NOT_VERIFY,
            kind="crossdoc_verbatim_source_conflict",
            label=label,
            dimension=dimension,
            detail=(
                f'The label "{label}" is bound to conflicting {dim_label} values across '
                f"documents: {_figure_phrase(relevant)}. One or more of these figures is "
                "marked as copied verbatim from a source, so the conflict originates in "
                "the underlying sources, not in the drafting; the engine attributes the "
                "disagreement to the sources and does not accuse the drafter. Review "
                "which source controls."
            ),
            figures=_figure_payloads(relevant),
        )
    return CrossDocLedgerFinding(
        verdict=CONTRADICTED,
        kind="crossdoc_conflict",
        label=label,
        dimension=dimension,
        detail=(
            f'The label "{label}" is bound to conflicting {dim_label} values across '
            f"{len(per_doc_value)} documents: {_figure_phrase(relevant)}. The same fact "
            f"surfaces in more than one document with more than one figure.{hedge_note} "
            "The engine reports the disagreement verbatim and does not decide which "
            "document controls."
        ),
        figures=_figure_payloads(relevant),
    )


def _incomparable_findings(
    label_key: str,
    by_dim: dict[str, list[CrossDocFact]],
    doc_index: dict[str, int],
) -> list[CrossDocLedgerFinding]:
    """One refusal per unit class this label is bound to in two dimensions
    across two or more documents. Never contradicted: days vs months and
    USD vs EUR have no deterministic conversion, so neither equality nor
    inequality is provable; the engine names both figures and refuses."""
    out: list[CrossDocLedgerFinding] = []
    by_class: dict[str, list[str]] = {}
    for dim in by_dim:
        cls = _UNIT_CLASSES.get(dim)
        if cls:
            by_class.setdefault(cls, []).append(dim)
    for cls in sorted(by_class):
        dims = sorted(by_class[cls])
        if len(dims) < 2:
            continue
        facts = sorted(
            (f for dim in dims for f in by_dim[dim]),
            key=lambda f: (doc_index[f.doc_id], f.start),
        )
        if len({f.doc_id for f in facts}) < 2:
            continue  # both units inside one document: single-document domain.
        label = _distinct(f.label for f in facts)[0]
        out.append(
            CrossDocLedgerFinding(
                verdict=COULD_NOT_VERIFY,
                kind="crossdoc_incomparable_units",
                label=label,
                dimension="+".join(dims),
                detail=(
                    f'The label "{label}" is bound to figures in incomparable units '
                    f"across documents: {_figure_phrase(facts)}. "
                    f"{_CLASS_REFUSAL_NOTE[cls]}; it names both values and refuses "
                    "rather than guess. Review manually."
                ),
                figures=_figure_payloads(facts),
            )
        )
    return out


# --- Entry point ---------------------------------------------------------------------


def detect_crossdoc_contradictions(
    documents,
    *,
    verbatim_run_present: bool | None = None,
) -> list[dict]:
    """Cross-document labeled-fact check; returns only non-green findings.

    ``documents`` is a list of ``{"doc_id": ..., "text": ...}`` dicts (a
    mapping of doc_id -> text or (doc_id, text) pairs are also accepted);
    doc_ids must be unique and non-blank, and a document may carry
    ``"verbatim": true`` to mark its facts as faithful copies of a source.

    Returns ``[]`` when fewer than two documents are given, when no
    normalized label spans two documents, or when every spanning (label,
    unit) fact carries one normalized value: silence is the consistent
    output, and this function has no way to say "supported". Per (label,
    unit) fact that DOES span documents with differing values, exactly one
    ``contradicted`` or ``could_not_verify`` finding, per the module
    docstring's invariants. ``verbatim_run_present`` forces the
    faithful-copy disposition in either direction (True: attribute every
    conflict to the sources; False: ignore per-document verbatim marks).

    Pure function of its inputs: no network, no LLM, no I/O, deterministic.
    """
    triples = _normalize_documents(documents)
    if len(triples) < 2:
        return []  # no cross-document fact exists; silence, not an error.

    union_terms: dict[str, None] = {}
    for _, text, _ in triples:
        for t in _collect_defined_terms(text):
            union_terms.setdefault(t, None)
    extra = tuple(union_terms)

    doc_index = {doc_id: i for i, (doc_id, _, _) in enumerate(triples)}
    by_key: dict[str, dict[str, list[CrossDocFact]]] = {}
    for doc_id, text, verbatim in triples:
        for f in extract_labeled_facts(doc_id, text, extra_terms=extra, verbatim=verbatim):
            by_key.setdefault(f.label_key, {}).setdefault(f.dimension, []).append(f)

    findings: list[CrossDocLedgerFinding] = []
    for label_key in sorted(by_key):
        by_dim = by_key[label_key]
        all_docs = {f.doc_id for group in by_dim.values() for f in group}
        if len(all_docs) < 2:
            continue  # the label surfaces in one document only: SILENT.
        for dimension in sorted(by_dim):
            group = by_dim[dimension]
            if len({f.doc_id for f in group}) < 2:
                continue  # this unit of the fact lives in one document: SILENT.
            finding = _dispose_dimension(
                label_key, dimension, group, doc_index, verbatim_run_present
            )
            if finding is not None:
                findings.append(finding)
        findings.extend(_incomparable_findings(label_key, by_dim, doc_index))

    findings.sort(key=lambda f: (_normalize(f.label), f.dimension, f.kind))
    return [asdict(f) for f in findings]
