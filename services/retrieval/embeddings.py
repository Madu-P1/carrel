from __future__ import annotations

import os
from typing import Protocol, Sequence


class Embedder(Protocol):
    dim: int

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


def _offline_embedder_required() -> bool:
    """The Cachet deterministic path must never let the embedder reach the network."""
    return os.getenv("CACHET_DETERMINISTIC_VERIFY", "").lower() in {"1", "true", "yes"}


def _enforce_offline_env() -> None:
    """Force HuggingFace offline when the deterministic path is active.

    UNCONDITIONAL assignment, not ``setdefault``: an inherited ``HF_HUB_OFFLINE=0``
    (from CI, a dotfile, or a parent process) would make ``setdefault`` a silent
    no-op, the embedder would then download the weights off-device, and the
    certification would still attest "no data left this device" -- a false
    attestation. Forcing the value closes that hole.
    """
    if _offline_embedder_required():
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"


class FastembedEmbedder:
    dim = 384
    _MODEL = "BAAI/bge-small-en-v1.5"

    def __init__(self) -> None:
        from fastembed import TextEmbedding

        # Pin the weights cache so they can be pre-cached at build time and
        # served offline (airplane-mode demo). Unset -> fastembed default.
        cache_dir = os.getenv("CARREL_FASTEMBED_CACHE_DIR") or None
        if _offline_embedder_required():
            # Offline floor for the Cachet contract path: a COLD cache fails LOUD
            # here instead of silently downloading the weights off-device. Pre-cache
            # once online via CARREL_FASTEMBED_CACHE_DIR before the demo.
            _enforce_offline_env()
            try:
                self._model = TextEmbedding(model_name=self._MODEL, cache_dir=cache_dir)
            except Exception as exc:
                raise RuntimeError(
                    "Cachet offline mode: the embedding weights are not in the local "
                    "cache and the network is disabled. Pre-cache them by running once "
                    "online with CARREL_FASTEMBED_CACHE_DIR set before the demo."
                ) from exc
        else:
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
