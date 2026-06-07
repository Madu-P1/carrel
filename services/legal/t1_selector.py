"""T1 recall tier (ADR-0012): local discriminative selection for anchor-free claims.

DARK / off until the calibration gate passes. Nothing on a product path imports this
yet; a later PR wires it behind the physically-inert ``t1_permitted()`` guard, and it
stays off until its false-affirmative gate passes on a labeled corpus.

Two on-device, discriminative signals, no generation:

  1. Rank-only candidacy. A draft sentence is a verification CANDIDATE only if its
     best-matching source clause retrieved within the top-K rank. This is a pre-filter,
     not a precision boundary, so a coarse rank signal is the right tool (Vulcan / D1):
     precision is owned downstream by the NLI threshold and the false-affirmative
     calibration gate. Rank-only avoids loading a second ~1 GB cross-encoder reranker;
     the bounded rerank-score variant is a documented upgrade gated on a latency
     benchmark (D4).

  2. Local NLI entailment. A small 3-class cross-encoder (premise = source clause,
     hypothesis = draft sentence) yields support / contradict / cannot-determine plus a
     confidence. Loaded offline via ``services.legal._offline_model`` (fail-loud on a
     cold cache, never the network). fastembed cannot do 3-way NLI, so this uses
     transformers ``AutoModelForSequenceClassification``; the label order is read from
     ``config.id2label``, never hardcoded.

``assess`` returns a ``T1Assessment`` only for a support/contradict verdict above the
caller-supplied threshold. ``None`` is the only outcome for below-rank, cannot-determine,
below-threshold, or a model failure: the claim then stays in the could-not-check tray,
never a verdict (ADR-0012 invariant 2, no coverage-by-guessing). Thresholds are caller
inputs, never baked in here: they are outputs of a passing calibration gate.

The rationale is a fixed extractive template (the matched clause plus the label), never
model-authored: this tier is discriminative only and never generates prose (the locked
P6 line / ADR-0012 invariant 4). The confidence rides the wire for the gate and audit; it
is never rendered as a score on the card (D3).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

DEFAULT_NLI_MODEL = "cross-encoder/nli-deberta-v3-xsmall"

# The three discriminative classes, on our own vocabulary. The model's native label
# order is mapped onto these from config.id2label, never assumed by position.
SUPPORT = "support"
CONTRADICT = "contradict"
CANNOT_DETERMINE = "cannot_determine"


@dataclass(frozen=True)
class T1Candidate:
    """A draft sentence paired with its best-matching source clause and that clause's
    1-based retrieval rank. Built by the wiring layer from ``search_typed_hybrid``; the
    selector does no retrieval itself."""

    sentence: str
    clause: str
    rank: int


@dataclass(frozen=True)
class T1Assessment:
    """An above-threshold local-model assessment. ``label`` is ``support`` or
    ``contradict`` (cannot-determine never produces an assessment). ``confidence`` is on a
    0-100 scale, carried on the wire for the gate and audit, never rendered as a score
    (D3). ``rationale`` is a fixed extractive template, never model-authored."""

    label: str
    confidence: float
    rationale: str


class EntailmentScorer(Protocol):
    """Score one ``(premise, hypothesis)`` pair into the three discriminative classes.

    Returns probabilities keyed by ``support`` / ``contradict`` / ``cannot_determine``
    summing to ~1. Injected into :func:`assess` so the selection logic is testable
    without loading a model.
    """

    def score(self, premise: str, hypothesis: str) -> dict[str, float]: ...


def _build_label_map(config) -> dict[int, str]:
    """Map each model output index onto our three classes via ``config.id2label``.

    Never positional: NLI checkpoints disagree on label order. An entailment label maps
    to support, contradiction to contradict, neutral to cannot-determine, and any
    unrecognized label to cannot-determine (the safe direction: it can never become a
    false affirmative).
    """
    id2label = getattr(config, "id2label", None) or {}
    mapping: dict[int, str] = {}
    for raw_idx, raw_name in id2label.items():
        name = str(raw_name).lower()
        if "entail" in name:
            mapping[int(raw_idx)] = SUPPORT
        elif "contradict" in name:
            mapping[int(raw_idx)] = CONTRADICT
        else:
            mapping[int(raw_idx)] = CANNOT_DETERMINE
    return mapping


class TransformersEntailment:
    """3-way NLI cross-encoder via transformers, loaded offline and lazily.

    Mirrors ``services.retrieval.rerank.FastembedReranker``: the weights load on the
    first ``score`` call (heavy; pulls torch) and are cached on the instance, so a
    flag-off caller that never scores pays nothing. A cold cache fails LOUD via the
    offline loader instead of reaching the network.
    """

    def __init__(self, model_id: str | None = None) -> None:
        self.model_id = model_id or os.getenv("CACHET_NLI_MODEL") or DEFAULT_NLI_MODEL
        self._loaded = None  # lazy: (tokenizer, model, label_map)

    def _ensure(self):
        if self._loaded is None:
            from services.legal._offline_model import load_sequence_classifier

            tokenizer, model = load_sequence_classifier(self.model_id)
            model.eval()
            self._loaded = (tokenizer, model, _build_label_map(model.config))
        return self._loaded

    def score(self, premise: str, hypothesis: str) -> dict[str, float]:
        tokenizer, model, label_map = self._ensure()
        import torch

        with torch.no_grad():
            inputs = tokenizer(
                premise, hypothesis, return_tensors="pt", truncation=True, max_length=512
            )
            probs = torch.softmax(model(**inputs).logits[0], dim=-1).tolist()
        out = {SUPPORT: 0.0, CONTRADICT: 0.0, CANNOT_DETERMINE: 0.0}
        for idx, p in enumerate(probs):
            out[label_map.get(idx, CANNOT_DETERMINE)] += float(p)
        return out


def active_model_id() -> str:
    """The NLI model id the default scorer resolves to (env override or the pinned default).

    Used as the assessed-tier ``model`` provenance on the wire (audit), never rendered as a
    score on the card (D3). Single source for the same resolution ``TransformersEntailment``
    applies, so the recorded provenance matches the model that actually scored.
    """
    return os.getenv("CACHET_NLI_MODEL") or DEFAULT_NLI_MODEL


_default: EntailmentScorer | None = None


def default_scorer(model_id: str | None = None) -> EntailmentScorer:
    """Process-cached singleton scorer (mirrors ``rerank.default_reranker``).

    Reading ``CACHET_NLI_MODEL`` lets the model be swapped without code changes.
    Re-loading the model per request would blow any latency budget, so the instance
    persists for the process. The weights are still lazy: the model loads only on the
    first ``score`` call.
    """
    global _default
    if _default is not None and model_id is None:
        return _default
    _default = TransformersEntailment(model_id)
    return _default


def _rationale(candidate: T1Candidate, label: str) -> str:
    """Fixed extractive template, never model-authored (no generation, P6)."""
    verb = "appears to support" if label == SUPPORT else "appears to conflict with"
    clause = candidate.clause.strip()
    excerpt = clause if len(clause) <= 160 else clause[:157].rstrip() + "..."
    return f'A local model found this statement {verb} the source passage: "{excerpt}"'


def assess(
    candidate: T1Candidate,
    *,
    scorer: EntailmentScorer,
    verdict_threshold: float,
    rank_cutoff: int,
) -> T1Assessment | None:
    """Assess one candidate, or return ``None``.

    ``None`` is the only outcome for: the candidate failing the rank-only candidacy
    floor, a cannot-determine verdict, a verdict below ``verdict_threshold``, or a model
    failure. None means the claim stays in the could-not-check tray, never a verdict
    (ADR-0012 invariant 2). Thresholds are caller inputs (gate outputs), never baked in.
    """
    # Rank-only candidacy floor, applied BEFORE any NLI call: a non-candidate never
    # reaches the model. A pre-filter, not a precision boundary (the threshold + gate
    # own precision), so a coarse rank signal is correct here.
    if candidate.rank > rank_cutoff:
        return None
    try:
        probs = scorer.score(candidate.clause, candidate.sentence)
    except Exception:
        # Fail-closed: a model error is an honest could-not-check, never a guess.
        return None
    label = max(probs, key=probs.get)
    if label == CANNOT_DETERMINE:
        return None
    confidence = probs[label] * 100.0
    if confidence < verdict_threshold:
        return None
    return T1Assessment(label=label, confidence=confidence, rationale=_rationale(candidate, label))
