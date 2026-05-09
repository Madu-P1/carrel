"""Cross-encoder reranker for the typed-node retrieval path.

PR 3 of 6 from the Ask-pipeline rebuild. The hybrid retriever in
`typed_hybrid.py` returns RRF-fused candidates from BM25 + vector
lists; this module re-scores the top of that list with a cross-encoder
that reads the (query, document) pair jointly. Cross-encoders are slow
relative to bi-encoders but recall@k jumps because the model attends
across the pair instead of comparing two independent embeddings.

**Model choice — deviation from the parent algorithm spec.** The spec
specifies `BAAI/bge-reranker-v2-m3` (568M params, multi-lingual). That
model isn't yet exposed by fastembed 0.8 (the bundled list runs from
`Xenova/ms-marco-MiniLM-L-6-v2` (80MB) up through
`jinaai/jina-reranker-v2-base-multilingual` (1.1GB)).

We default to `Xenova/ms-marco-MiniLM-L-12-v2` (120 MB) based on the
2026-05-08 side-by-side validation against the founder's library
(see `docs/algorithms/validation-2026-05-08.md`):

- 5x average latency win over the heavier BAAI/bge-reranker-base
  (per-query rerank cost dropped from 2-31s to 0.4-9.3s on a CPU).
- Quality matched on 4/5 hand-graded queries; one slight regression
  on the most technical query (multiple linear regression spec).
- 9x smaller first-run download.

The model is configurable via `RETRIEVAL_RERANKER_MODEL` so operators
can swap to BAAI/bge-reranker-base, jina-reranker-v2, or the spec's
v2-m3 (once fastembed adds it / via manual ONNX export) without a
code change.
"""

from __future__ import annotations

import math
import os
from typing import Iterable, Protocol, Sequence

# fastembed's TextCrossEncoder is shipped under fastembed.rerank in
# 0.8.x. The import is lazy at the bottom of this module so callers
# who never instantiate `default_reranker()` don't pay any runtime
# cost — important for the flag-off path.

DEFAULT_RERANKER_MODEL = "Xenova/ms-marco-MiniLM-L-12-v2"


class Reranker(Protocol):
    """Score `(query, document)` pairs in [0, 1]. Higher is more relevant."""

    def rerank_pairs(self, query: str, documents: Sequence[str]) -> list[float]: ...


def _sigmoid(x: float) -> float:
    """Squash a logit into [0, 1].

    Cross-encoder rerankers emit logit-like scores that are not bounded
    to a probability range. The blended-score formula in
    `typed_hybrid.search_typed_hybrid` expects rerank scores in [0, 1]
    so we sigmoid the raw model output here.
    """
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


class FastembedReranker:
    """Wraps `fastembed.rerank.cross_encoder.TextCrossEncoder`.

    Lazy-loads the underlying ONNX model on first call. First-run
    downloads ~1 GB of model weights into the user's fastembed cache
    (same cache as the chunks/nodes embedder).
    """

    def __init__(self, model_name: str = DEFAULT_RERANKER_MODEL) -> None:
        self.model_name = model_name
        self._encoder = None  # lazy-init

    def _ensure(self):
        if self._encoder is None:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            self._encoder = TextCrossEncoder(self.model_name)
        return self._encoder

    def rerank_pairs(self, query: str, documents: Sequence[str]) -> list[float]:
        if not documents:
            return []
        encoder = self._ensure()
        raw_scores = list(encoder.rerank(query, list(documents)))
        return [_sigmoid(float(score)) for score in raw_scores]


_default: Reranker | None = None


def default_reranker(model_name: str | None = None) -> Reranker:
    """Cache a single FastembedReranker instance for the process.

    Reading ``RETRIEVAL_RERANKER_MODEL`` lets operators swap models
    without code changes. Once instantiated, the cached encoder
    persists for the process lifetime — re-loading the ONNX graph
    on every Ask request would blow the latency budget.
    """
    global _default
    if _default is not None and model_name is None:
        return _default
    chosen = model_name or os.getenv("RETRIEVAL_RERANKER_MODEL", DEFAULT_RERANKER_MODEL)
    _default = FastembedReranker(chosen)
    return _default


def normalize_scores(scores: Iterable[float]) -> list[float]:
    """Rescale to [0, 1] via min-max with a flat-list fallback.

    Sigmoid alone leaves a lot of useful spread on the table — when
    every score lands near 0.5, the blended formula collapses. This
    additional pass min-max normalizes against the result set so the
    top hit is always 1.0. Used by the typed-hybrid blender.
    """
    values = list(scores)
    if not values:
        return []
    lo = min(values)
    hi = max(values)
    span = hi - lo
    if span <= 0:
        return [1.0] * len(values)
    return [(v - lo) / span for v in values]
