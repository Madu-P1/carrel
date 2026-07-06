"""Cross-document fact-consistency detector for the Cachet engine.

The fact-ledger primitive (``services/fact_ledger.py``) decides when ONE
document binds the same defined term to two irreconcilable figures. This
module is the category expansion that primitive was architected to enable: it
takes fact ledgers built from TWO OR MORE named documents (contract vs
amendment, brief vs exhibit, agreement vs term sheet) and decides
deterministically when the same exact-string (term, dimension) key surfaces
in more than one document with values that unambiguously conflict -- Section
8.2 of the Agreement says 'the "Termination Fee" shall be $50,000' and
Amendment No. 2 says 'the "Termination Fee" shall be $75,000'. The
disagreement is a literal fact a reader can confirm by opening both
documents; this module detects it and stops. It never says which document
controls, and it never affirms anything.

The detector operates on the ledger layer, not on raw text: it consumes the
primitive's own ``Binding`` structures via ``build_fact_ledger``, so every
dimension the ledger keys today (durations, money, percentages, counts) and
every dimension it learns to key later becomes cross-document checkable here
for free. No parallel parser exists in this file; the only text scanning it
performs is the whitespace-normalized verbatim-quotation guard.

Campaign invariants, enforced by construction:

* SILENT by default. A term consistent across documents, a term present in
  only one document, a term reused across unrelated dimensions (a duration in
  the contract, a money amount in the exhibit), or a document set with no
  bindings at all produces NO finding. There is no supported/verified/green
  output state anywhere in this module -- ``CrossDocumentFinding.__post_init__``
  rejects any verdict outside {"contradicted", "could_not_verify"} -- so a
  false green is impossible structurally, not by tuning.
* EXACT string keys only, inherited from the ledger. "Renewal Term" in the
  amendment never feeds the agreement's "Term" key; the ledger's quoted-hug
  and capitalized-neighbor guards apply unchanged because this module never
  re-derives bindings.
* A finding NAMES both documents and both figures verbatim, always.
  "Agreement states '$50,000' (= USD 50000.00); Amendment No. 2 states
  '$75,000' (= USD 75000.00)" -- never content-free. When three or more
  documents disagree and all but one agree, the finding names the odd one out.
* NEVER accuse a faithful copier. A binding whose sentence appears
  whitespace-normalized verbatim in another named document is a quotation,
  not independent drafting: it is excluded from authorship attribution, and a
  conflict that survives only through quoted sentences refuses with
  ``could_not_verify`` instead of accusing. Callers may force either
  disposition with ``verbatim_run_present``.
* NOT-PROVABLY-EQUAL refuses, never accuses. Calendar days vs calendar months
  across documents ("30 days" in the agreement, "one (1) month" in the
  guaranty) has no deterministic conversion, so it refuses naming both
  figures -- the same mandate decision the single-document primitive made.
  'approximately'-hedged or mixed-hedge differences refuse likewise. A
  document that is internally inconsistent on a key poisons the
  cross-document comparison and refuses (the intra-document conflict itself
  is the single-document detector's domain).

Pure stdlib; no network, no LLM, no I/O, no learned weights anywhere in the
call path. Deterministic: same inputs, same output list, always.

    from services.cross_document import detect_cross_document_contradictions

    findings = detect_cross_document_contradictions(
        {"Agreement": agreement_text, "Amendment No. 2": amendment_text}
    )
    for f in findings:
        print(f["verdict"], f["term"], f["detail"])
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass

# Read-only reuse of the primitive's internals (_collect_defined_terms,
# _dim_label, _normalize) keeps term collection, dimension labels, and
# whitespace normalization single-sourced with the ledger instead of drifting
# copies. Nothing here mutates or monkeypatches the primitive.
from services.fact_ledger import (
    ALLOWED_VERDICTS,
    CONTRADICTED,
    COULD_NOT_VERIFY,
    Binding,
    _collect_defined_terms,
    _dim_label,
    _normalize,
    build_fact_ledger,
)

__all__ = [
    "ALLOWED_VERDICTS",
    "CONTRADICTED",
    "COULD_NOT_VERIFY",
    "CrossDocumentFinding",
    "build_named_ledgers",
    "compare_named_ledgers",
    "detect_cross_document_contradictions",
]

_MAX_DOCS = 32  # DoS bound on the O(n^2) quotation scan.


@dataclass(frozen=True)
class CrossDocumentFinding:
    """One verdict this detector adds. Never a green one.

    ``__post_init__`` makes the zero-green invariant structural: constructing
    a finding with any verdict outside ``ALLOWED_VERDICTS`` raises, so no code
    path in (or importing) this module can mint a supported state from it.
    """

    verdict: str  # "contradicted" | "could_not_verify", nothing else
    kind: str
    term: str
    dimension: str
    detail: str
    figures: tuple  # per-figure dicts: document, surface, normalized, hedge,
    # start, end, snippet, copied

    def __post_init__(self) -> None:
        if self.verdict not in ALLOWED_VERDICTS:
            raise ValueError(
                "cross_document detector can only emit "
                f"{sorted(ALLOWED_VERDICTS)}; got {self.verdict!r}. "
                "It has no green output state by design."
            )


# --- Input normalization -----------------------------------------------------


def _normalize_documents(documents) -> list[tuple[str, str]]:
    """(name, text) pairs in caller order, validated: unique non-blank names."""
    if isinstance(documents, Mapping):
        pairs = list(documents.items())
    else:
        try:
            pairs = [(p[0], p[1]) for p in documents]
        except (TypeError, IndexError, KeyError) as exc:
            raise TypeError(
                "documents must be a mapping of name -> text or an iterable of (name, text) pairs"
            ) from exc
    if len(pairs) > _MAX_DOCS:
        raise ValueError(f"at most {_MAX_DOCS} documents per comparison; got {len(pairs)}")
    seen: set[str] = set()
    for name, text in pairs:
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"document names must be non-blank strings; got {name!r}")
        if not isinstance(text, str):
            raise TypeError(f"document {name!r} text must be str, got {type(text).__name__}")
        if name in seen:
            raise ValueError(f"duplicate document name {name!r}: identities must be unambiguous")
        seen.add(name)
    return pairs


# --- Ledger construction -------------------------------------------------------


def build_named_ledgers(documents) -> dict[str, dict[tuple[str, str], list[Binding]]]:
    """One fact ledger per named document, keyed by the UNION of defined terms.

    Terms quoted in any document widen every document's candidate list (via
    the ledger's additive ``extra_terms``), so a contract that defines
    '"Term"' and an exhibit that merely writes 'the 36-month Term' still meet
    on the same exact-string key. The ledger's own guards decide whether an
    occurrence binds; this function adds no parsing of its own.
    """
    pairs = _normalize_documents(documents)
    union_terms: dict[str, None] = {}
    for _, text in pairs:
        for t in _collect_defined_terms(text):
            union_terms.setdefault(t, None)
    return {name: build_fact_ledger(text, extra_terms=tuple(union_terms)) for name, text in pairs}


# --- Formatting helpers --------------------------------------------------------


def _distinct(values: Iterable[str]) -> list[str]:
    seen: dict[str, None] = {}
    for v in values:
        seen.setdefault(v, None)
    return list(seen)


def _figure_payloads(tagged: list[tuple[str, Binding]], copied: dict[int, bool]) -> tuple:
    return tuple(
        {
            "document": doc,
            "surface": b.surface,
            "normalized": b.value,
            "hedge": b.hedge,
            "start": b.start,
            "end": b.end,
            "snippet": b.snippet,
            "copied": copied.get(id(b), False),
        }
        for doc, b in tagged
    )


def _figure_phrase(tagged: list[tuple[str, Binding]], copied: dict[int, bool]) -> str:
    parts = []
    for doc, b in tagged:
        mark = " [verbatim copy]" if copied.get(id(b), False) else ""
        parts.append(f"{doc} states '{b.surface}' (= {b.value}) at offset {b.start}{mark}")
    return "; ".join(parts)


def _odd_one_out_note(per_doc_value: dict[str, str], tagged: list[tuple[str, Binding]]) -> str:
    """Names the odd document out when all documents but one agree."""
    by_value: dict[str, list[str]] = {}
    for doc, value in per_doc_value.items():
        by_value.setdefault(value, []).append(doc)
    if len(by_value) != 2:
        return ""
    (v1, docs1), (v2, docs2) = by_value.items()
    if len(docs1) >= 2 and len(docs2) == 1:
        majority_value, majority_docs, odd_doc, odd_value = v1, docs1, docs2[0], v2
    elif len(docs2) >= 2 and len(docs1) == 1:
        majority_value, majority_docs, odd_doc, odd_value = v2, docs2, docs1[0], v1
    else:
        return ""
    odd_surfaces = ", ".join(
        f"'{b.surface}'" for doc, b in tagged if doc == odd_doc and b.value == odd_value
    )
    return (
        f" {' and '.join(majority_docs)} agree on {majority_value}; {odd_doc} is the "
        f"odd one out with {odd_surfaces} (= {odd_value})."
    )


# --- Disposition ---------------------------------------------------------------


def _mark_copied(
    tagged: list[tuple[str, Binding]],
    norm_texts: dict[str, str] | None,
    verbatim_override: bool | None,
) -> dict[int, bool]:
    """Which bindings sit in sentences another named document carries verbatim.

    Keyed by ``id(binding)``; a copied binding is a quotation, not independent
    drafting. ``verbatim_override`` short-circuits the scan in either
    direction. No fuzzy fallback by design: only exact (whitespace-normalized)
    sentence matches count, mirroring the primitive's source guard.
    """
    if verbatim_override is True:
        return {id(b): True for _, b in tagged}
    if verbatim_override is False or not norm_texts:
        return {}
    copied: dict[int, bool] = {}
    for doc, b in tagged:
        snip = _normalize(b.snippet)
        if snip and any(snip in norm_texts[other] for other in norm_texts if other != doc):
            copied[id(b)] = True
    return copied


def _dispose_key(
    term: str,
    dimension: str,
    per_doc: dict[str, list[Binding]],
    doc_index: dict[str, int],
    norm_texts: dict[str, str] | None,
    verbatim_override: bool | None,
) -> CrossDocumentFinding | None:
    tagged_all = sorted(
        ((doc, b) for doc, group in per_doc.items() for b in group),
        key=lambda db: (doc_index[db[0]], db[1].start),
    )
    if len(_distinct(b.value for _, b in tagged_all)) < 2:
        return None  # one value across every document: consistent, SILENT.

    label = _dim_label(dimension)
    unhedged = [(doc, b) for doc, b in tagged_all if b.hedge is None]
    hedge_classes = {b.hedge for _, b in tagged_all}

    if len(_distinct(b.value for _, b in unhedged)) >= 2:
        relevant = unhedged
        hedge_note = ""
    elif hedge_classes == {"cap"} or hedge_classes == {"floor"}:
        relevant = tagged_all
        bound_word = (
            "upper-bound ('up to')" if hedge_classes == {"cap"} else "lower-bound ('at least')"
        )
        hedge_note = f" Every figure shares the same {bound_word} hedge semantics."
    else:
        # 'approximately'-class or mixed hedging: no deterministic comparison
        # exists across documents any more than within one. Refuse, naming
        # every document and every figure this key carries.
        return CrossDocumentFinding(
            verdict=COULD_NOT_VERIFY,
            kind="cross_document_hedged_figures",
            term=term,
            dimension=dimension,
            detail=(
                f'The defined term "{term}" is bound to differing {label} figures across '
                f"documents that are hedged: {_figure_phrase(tagged_all, {})}. Hedged "
                "figures without shared bound semantics cannot be compared "
                "deterministically; the engine names the figures and refuses rather "
                "than guess. Review manually."
            ),
            figures=_figure_payloads(tagged_all, {}),
        )

    copied = _mark_copied(relevant, norm_texts, verbatim_override)
    independent: dict[str, list[Binding]] = {}
    for doc, b in relevant:
        if not copied.get(id(b), False):
            independent.setdefault(doc, []).append(b)

    # A document that independently asserts two values for this key poisons
    # the cross-document comparison: no single per-document value exists.
    for doc in independent:
        if len(_distinct(b.value for b in independent[doc])) >= 2:
            return CrossDocumentFinding(
                verdict=COULD_NOT_VERIFY,
                kind="cross_document_intra_document_conflict",
                term=term,
                dimension=dimension,
                detail=(
                    f'The defined term "{term}" carries conflicting {label} figures across '
                    f"documents: {_figure_phrase(relevant, copied)}. However, {doc} is "
                    "internally inconsistent on this term, so no single per-document value "
                    "exists to compare across documents. The engine names every figure and "
                    "refuses rather than guess; the intra-document conflict itself is the "
                    "single-document fact-ledger detector's domain."
                ),
                figures=_figure_payloads(relevant, copied),
            )

    per_doc_value = {doc: group[0].value for doc, group in independent.items()}
    if len(per_doc_value) >= 2 and len(_distinct(per_doc_value.values())) >= 2:
        odd_note = _odd_one_out_note(per_doc_value, relevant)
        return CrossDocumentFinding(
            verdict=CONTRADICTED,
            kind="cross_document_conflict",
            term=term,
            dimension=dimension,
            detail=(
                f'The defined term "{term}" is bound to conflicting {label} values across '
                f"{len(per_doc)} documents: {_figure_phrase(relevant, copied)}. The same "
                f"fact surfaces in more than one document with more than one figure."
                f"{odd_note}{hedge_note} The engine reports the disagreement verbatim and "
                "does not decide which document controls."
            ),
            figures=_figure_payloads(relevant, copied),
        )

    # The conflict survives only through sentences a document carries verbatim
    # from another: at least one side is a faithful quotation, and authorship
    # of the conflicting figure cannot be attributed deterministically.
    return CrossDocumentFinding(
        verdict=COULD_NOT_VERIFY,
        kind="cross_document_verbatim_copy",
        term=term,
        dimension=dimension,
        detail=(
            f'The defined term "{term}" surfaces with conflicting {label} figures across '
            f"documents: {_figure_phrase(relevant, copied)}. The conflict cannot be "
            "attributed to two independent drafters: the figures marked [verbatim copy] "
            "sit in sentences that appear verbatim in another named document, so the "
            "quoting document did not draft them. The engine refuses to accuse a faithful "
            "copier; it names every figure instead. Review which document controls."
        ),
        figures=_figure_payloads(relevant, copied),
    )


def _incommensurable_findings(
    named_ledgers: Mapping[str, Mapping[tuple[str, str], list[Binding]]],
    doc_index: dict[str, int],
) -> list[CrossDocumentFinding]:
    """One refusal per term bound to day-family durations in one document and
    month-family durations in another. Never contradicted: days<->months has
    no deterministic conversion, so neither equality nor inequality is
    provable -- the same mandate decision the single-document primitive made.
    A term whose two families both live inside one single document is that
    detector's domain, not this one's."""
    days: dict[str, dict[str, list[Binding]]] = {}
    months: dict[str, dict[str, list[Binding]]] = {}
    for doc, ledger in named_ledgers.items():
        for (term, dim), group in ledger.items():
            if dim == "duration_days":
                days.setdefault(term, {})[doc] = list(group)
            elif dim == "duration_months":
                months.setdefault(term, {})[doc] = list(group)
    out: list[CrossDocumentFinding] = []
    for term in sorted(set(days) & set(months)):
        involved = set(days[term]) | set(months[term])
        if len(involved) < 2:
            continue  # both families inside one document: single-document domain.
        tagged = sorted(
            [(doc, b) for doc, group in days[term].items() for b in group]
            + [(doc, b) for doc, group in months[term].items() for b in group],
            key=lambda db: (doc_index[db[0]], db[1].start),
        )
        out.append(
            CrossDocumentFinding(
                verdict=COULD_NOT_VERIFY,
                kind="cross_document_incommensurable_units",
                term=term,
                dimension="duration_days+duration_months",
                detail=(
                    f'The defined term "{term}" is bound to durations in incommensurable '
                    f"units across documents: {_figure_phrase(tagged, {})}. Calendar days "
                    "and calendar months have no deterministic conversion, so the engine "
                    "cannot prove these figures equal or unequal across documents; it "
                    "names both and refuses rather than guess. Review manually."
                ),
                figures=_figure_payloads(tagged, {}),
            )
        )
    return out


# --- Entry points ----------------------------------------------------------------


def compare_named_ledgers(
    named_ledgers: Mapping[str, Mapping[tuple[str, str], list[Binding]]],
    document_texts: Mapping[str, str] | None = None,
    *,
    verbatim_run_present: bool | None = None,
) -> list[dict]:
    """Compare prebuilt fact ledgers across named documents; only non-green findings.

    ``named_ledgers`` maps a document identifier to the structure
    ``services.fact_ledger.build_fact_ledger`` returns. Returns ``[]`` when
    fewer than two documents are given, when no (term, dimension) key spans
    two documents, or when every spanning key carries one normalized value:
    silence is the consistent output, and this function has no way to say
    "supported". Per key that DOES span documents with differing values,
    exactly one ``contradicted`` or ``could_not_verify`` finding, per the
    module docstring's invariants.

    ``document_texts`` (name -> raw text) powers the verbatim-quotation guard;
    without it the guard runs only via ``verbatim_run_present``. The
    convenience entry ``detect_cross_document_contradictions`` always supplies
    it. Deterministic: same inputs, same output list, always.
    """
    if not isinstance(named_ledgers, Mapping):
        raise TypeError(
            f"named_ledgers must be a mapping of name -> ledger, got {type(named_ledgers).__name__}"
        )
    if document_texts is not None and not isinstance(document_texts, Mapping):
        raise TypeError(
            f"document_texts must be a mapping of name -> text or None, got "
            f"{type(document_texts).__name__}"
        )
    doc_order = list(named_ledgers)
    if len(doc_order) < 2:
        return []  # no cross-document fact exists; silence, not an error.
    if len(doc_order) > _MAX_DOCS:
        raise ValueError(f"at most {_MAX_DOCS} documents per comparison; got {len(doc_order)}")
    doc_index = {doc: i for i, doc in enumerate(doc_order)}
    norm_texts = None
    if document_texts:
        norm_texts = {
            name: _normalize(text) for name, text in document_texts.items() if isinstance(text, str)
        }

    keys: dict[tuple[str, str], None] = {}
    for doc in doc_order:
        for key in named_ledgers[doc]:
            keys.setdefault(key, None)

    findings: list[CrossDocumentFinding] = []
    for term, dimension in keys:
        per_doc = {
            doc: list(named_ledgers[doc][(term, dimension)])
            for doc in doc_order
            if named_ledgers[doc].get((term, dimension))
        }
        if len(per_doc) < 2:
            continue  # the term surfaces in one document only: SILENT.
        finding = _dispose_key(
            term, dimension, per_doc, doc_index, norm_texts, verbatim_run_present
        )
        if finding is not None:
            findings.append(finding)
    findings.extend(_incommensurable_findings(named_ledgers, doc_index))
    findings.sort(key=lambda f: (f.term, f.dimension, f.kind))
    return [asdict(f) for f in findings]


def detect_cross_document_contradictions(
    documents,
    *,
    verbatim_run_present: bool | None = None,
) -> list[dict]:
    """Build one fact ledger per named document and compare them.

    ``documents`` is a mapping of document identifier -> raw text, or an
    iterable of (identifier, text) pairs; order is preserved and identifiers
    must be unique and non-blank. Fewer than two documents returns ``[]``.
    Pure function of its inputs: no network, no LLM, no I/O, deterministic.
    """
    pairs = _normalize_documents(documents)
    return compare_named_ledgers(
        build_named_ledgers(pairs),
        dict(pairs),
        verbatim_run_present=verbatim_run_present,
    )
