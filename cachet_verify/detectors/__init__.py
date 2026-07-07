"""Self-contained self-contradiction detectors for the Cachet kernel.

Vendored from ``services/`` (the campaign detectors) so the frozen
``cachet-engine`` binary actually runs them: PyInstaller bundles
``cachet_verify`` only, never ``services``. Every module here imports RELATIVE
within ``cachet_verify``; the kernel imports nothing from ``services``.

Two entry points:

* ``scan_draft(draft)`` runs the seven INTRA-draft detectors over one document
  and returns a flat list of finding dicts (each carries kind, disposition,
  detail, span, start, end).
* ``scan_cross_document(sources)`` runs the cross-document ledger over two or
  more sources and returns cross-document finding dicts (each carries kind,
  disposition, label, dimension, detail, figures[]).

The verdict -> disposition mapping mirrors
``services/legal/deterministic_envelope.py`` exactly: verdict ``contradicted``
-> ``flagged`` (the confident catch); any other verdict -> ``could_not_check``
(the honest gap). Every detector call is guarded so one detector's failure
degrades to "no finding" and never breaks attestation. There is no network,
database, or model on this path.
"""

from __future__ import annotations

from dataclasses import asdict

from ._findings import COULD_NOT_CHECK, FLAGGED, StructuralFinding
from .bound_pairs import detect_bound_pair_conflicts
from .crossdoc_ledger import detect_crossdoc_contradictions
from .crossref_integrity import detect_crossref_defects
from .date_duration_conflict import detect_date_duration_conflicts
from .enumeration_count import detect_enumeration_conflicts
from .table_footing import detect_footing_conflicts
from .temporal_graph import detect_temporal_contradictions
from .words_figures import check_words_figures

__all__ = ["scan_cross_document", "scan_draft"]

# The document-scale temporal detector is superlinear; a draft past this bound
# skips it entirely (no findings). Replicates the envelope's _TEMPORAL_MAX_CHARS.
_TEMPORAL_MAX_CHARS = 50_000


def scan_draft(draft: str) -> list[dict]:
    """Run the seven intra-draft detectors over one document.

    Returns a flat list of finding dicts. A clean draft yields ``[]``. Each
    detector is guarded independently: a detector that refuses (or crashes on a
    malformed draft) contributes nothing rather than breaking the whole scan.
    """
    findings: list[dict] = []
    if not isinstance(draft, str) or not draft:
        return findings

    # Words vs figures ("thirty (40) days"): a definite intra-span
    # self-contradiction is FLAGGED; an unresolved pair is COULD_NOT_CHECK.
    # check_words_figures returns dataclasses carrying .verdict/.detail/.span/
    # .start/.end.
    try:
        _wf_findings = check_words_figures(draft)
    except (ValueError, TypeError):
        _wf_findings = []
    for _wf in _wf_findings:
        findings.append(
            asdict(
                StructuralFinding(
                    kind="words_figures_conflict"
                    if _wf.verdict == "contradicted"
                    else "words_figures_unresolved",
                    disposition=FLAGGED if _wf.verdict == "contradicted" else COULD_NOT_CHECK,
                    detail=_wf.detail,
                    span=_wf.span,
                    start=_wf.start,
                    end=_wf.end,
                )
            )
        )

    # Date-range vs stated-duration self-contradiction. Detector returns dicts.
    try:
        _dd_findings = detect_date_duration_conflicts(draft)
    except (ValueError, TypeError):
        _dd_findings = []
    for _dd in _dd_findings:
        findings.append(
            asdict(
                StructuralFinding(
                    kind="date_duration_conflict"
                    if _dd["verdict"] == "contradicted"
                    else "date_duration_unresolved",
                    disposition=FLAGGED if _dd["verdict"] == "contradicted" else COULD_NOT_CHECK,
                    detail=_dd["detail"],
                    span=_dd["span"],
                    start=_dd["start"],
                    end=_dd["end"],
                )
            )
        )

    # Inverted floor/ceiling bound pairs. Detector returns dicts.
    try:
        _bp_findings = detect_bound_pair_conflicts(draft)
    except (ValueError, TypeError):
        _bp_findings = []
    for _bp in _bp_findings:
        findings.append(
            asdict(
                StructuralFinding(
                    kind="bound_pair_conflict"
                    if _bp["verdict"] == "contradicted"
                    else "bound_pair_unresolved",
                    disposition=FLAGGED if _bp["verdict"] == "contradicted" else COULD_NOT_CHECK,
                    detail=_bp["detail"],
                    span=_bp["span"],
                    start=_bp["start"],
                    end=_bp["end"],
                )
            )
        )

    # Enumeration count vs enumerated list. Detector returns dicts carrying
    # frame_start/frame_end + declared_surface (no single end offset).
    try:
        _en_findings = detect_enumeration_conflicts(draft)
    except (ValueError, TypeError):
        _en_findings = []
    for _en in _en_findings:
        findings.append(
            asdict(
                StructuralFinding(
                    kind="enumeration_count_conflict"
                    if _en["verdict"] == "contradicted"
                    else "enumeration_count_unresolved",
                    disposition=FLAGGED if _en["verdict"] == "contradicted" else COULD_NOT_CHECK,
                    detail=_en["detail"],
                    span=_en["declared_surface"],
                    start=_en["frame_start"],
                    end=_en["frame_end"],
                )
            )
        )

    # Cross-reference / defined-term integrity. Findings carry their OWN curated
    # span (start/end are a first-to-last-occurrence envelope for multi-occurrence
    # kinds), so use the detector's span, never draft[start:end].
    try:
        _cr_findings = detect_crossref_defects(draft)
    except (ValueError, TypeError):
        _cr_findings = []
    for _cr in _cr_findings:
        findings.append(
            asdict(
                StructuralFinding(
                    kind="crossref_conflict"
                    if _cr["verdict"] == "contradicted"
                    else "crossref_unresolved",
                    disposition=FLAGGED if _cr["verdict"] == "contradicted" else COULD_NOT_CHECK,
                    detail=_cr["detail"],
                    span=_cr["span"],
                    start=_cr["start"],
                    end=_cr["end"],
                )
            )
        )

    # Document-scale temporal ordering. Size-guarded (superlinear). Uses the
    # detector's own curated cycle span.
    if len(draft) <= _TEMPORAL_MAX_CHARS:
        try:
            _tg_findings = detect_temporal_contradictions(draft)
        except (ValueError, TypeError):
            _tg_findings = []
    else:
        _tg_findings = []
    for _tg in _tg_findings:
        findings.append(
            asdict(
                StructuralFinding(
                    kind="temporal_conflict"
                    if _tg["verdict"] == "contradicted"
                    else "temporal_unresolved",
                    disposition=FLAGGED if _tg["verdict"] == "contradicted" else COULD_NOT_CHECK,
                    detail=_tg["detail"],
                    span=_tg["span"],
                    start=_tg["start"],
                    end=_tg["end"],
                )
            )
        )

    # Table footing: a stated Total that does not equal the exact sum of line
    # items. The detector is LINE-based (rows carry line numbers, no char
    # offsets), so convert line -> char span here using the draft's own line
    # boundaries, matching the detector's text.splitlines() exactly.
    try:
        _tf_findings = detect_footing_conflicts(draft)
    except (ValueError, TypeError):
        _tf_findings = []
    _tf_content: list[str] = []
    _tf_line_off: list[int] = []
    if _tf_findings:
        _tf_content = draft.splitlines()
        _tf_acc = 0
        for _tf_k in draft.splitlines(keepends=True):
            _tf_line_off.append(_tf_acc)
            _tf_acc += len(_tf_k)
    for _tf in _tf_findings:
        _tf_lines = [
            r["line"]
            for r in _tf.get("rows", ())
            if isinstance(r, dict)
            and isinstance(r.get("line"), int)
            and 0 <= r["line"] < len(_tf_line_off)
        ]
        if _tf_lines:
            _tf_lo, _tf_hi = min(_tf_lines), max(_tf_lines)
            _tf_start = _tf_line_off[_tf_lo]
            _tf_end = _tf_line_off[_tf_hi] + len(_tf_content[_tf_hi])
        else:
            _tf_start = _tf_end = 0
        findings.append(
            asdict(
                StructuralFinding(
                    kind="table_footing_conflict"
                    if _tf["verdict"] == "contradicted"
                    else "table_footing_unresolved",
                    disposition=FLAGGED if _tf["verdict"] == "contradicted" else COULD_NOT_CHECK,
                    detail=_tf["detail"],
                    span=draft[_tf_start:_tf_end],
                    start=_tf_start,
                    end=_tf_end,
                )
            )
        )

    return findings


def scan_cross_document(sources: list[tuple[str, str]]) -> list[dict]:
    """Run the cross-document ledger over two or more sources.

    ``sources`` is a list of ``(doc_id, text)`` pairs. Returns cross-document
    finding dicts (kind, disposition, label, dimension, detail, figures[]). A
    corpus of fewer than two documents, or one with no spanning conflict, yields
    ``[]``. The whole pass is guarded: any failure degrades to ``[]``.
    """
    if not sources or len(sources) < 2:
        return []
    out: list[dict] = []
    try:
        for _cd in detect_crossdoc_contradictions(list(sources)):
            _cd_contra = _cd["verdict"] == "contradicted"
            out.append(
                {
                    "kind": "cross_document_conflict"
                    if _cd_contra
                    else "cross_document_unresolved",
                    "disposition": FLAGGED if _cd_contra else COULD_NOT_CHECK,
                    "label": _cd["label"],
                    "dimension": _cd["dimension"],
                    "detail": _cd["detail"],
                    "figures": [
                        {
                            "document": _f["doc_id"],
                            "surface": _f["surface"],
                            "normalized": _f["normalized"],
                            "start": _f["start"],
                            "end": _f["end"],
                            "snippet": _f["snippet"],
                        }
                        for _f in _cd.get("figures", ())
                    ],
                }
            )
    except (ValueError, TypeError, KeyError):
        return []
    return out
