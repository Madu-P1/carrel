from __future__ import annotations

import os
from typing import Protocol, Sequence


class Embedder(Protocol):
    dim: int

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class FastembedEmbedder:
    dim = 384
    _MODEL = "BAAI/bge-small-en-v1.5"

    def __init__(self) -> None:
        from fastembed import TextEmbedding

        # Pin the weights cache so they can be pre-cached at build time and
        # served offline (airplane-mode demo). Unset -> fastembed default.
        cache_dir = os.getenv("CARREL_FASTEMBED_CACHE_DIR") or None
        self._model = TextEmbedding(model_name=self._MODEL, cache_dir=cache_dir)

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return [list(map(float, vector)) for vector in self._model.embed(list(texts))]

    def embed_query(self, text: str) -> list[float]:
        return list(map(float, next(iter(self._model.embed([text]))).tolist()))


_default: Embedder | None = None


def default_embedder() -> Embedder:
    global _default
    if _default is None:
        _default = FastembedEmbedder()
    return _default
