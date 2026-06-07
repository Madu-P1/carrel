"""Offline-by-construction model loading for the Cachet local-model tiers (T1).

The T1 recall tier (ADR-0012) runs a local NLI entailment model on-device. This
shared loader forces HuggingFace into offline mode and loads a locally-cached model
plus tokenizer, or fails LOUD when the weights are absent. No model ever downloads
at runtime on a Cachet path: a cold cache raises here instead of silently reaching
the network, so the "no data leaves this device" guarantee holds even if the
operator's environment is misconfigured. Mirrors
``services.retrieval.embeddings._enforce_offline_env``.

This carries no T1 logic: label mapping, softmax, confidence, thresholds, and
verdicts live in the selector (a later PR). transformers is imported lazily so the
default import path stays cheap and never loads torch unless a model is actually
requested. T1 remains dark/off until its calibration gate passes; this PR only
declares the dependency and the offline-load contract.
"""

from __future__ import annotations

import os

# Pre-cache the T1 weights once online into this directory, then run offline. Unset
# falls back to the HuggingFace default cache.
CACHE_DIR_ENV = "CARREL_T1_MODEL_CACHE_DIR"


def enforce_offline_env() -> None:
    """Force HuggingFace and transformers offline.

    UNCONDITIONAL assignment, not ``setdefault``: an inherited ``HF_HUB_OFFLINE=0``
    (from CI, a dotfile, or a parent process) would make ``setdefault`` a silent
    no-op, a load would then reach the network, and the certification would still
    attest "no data left this device" -- a false attestation. Forcing the value
    closes that hole.
    """
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"


def load_sequence_classifier(model_id: str, *, cache_dir: str | None = None):
    """Return ``(tokenizer, model)`` for a locally-cached sequence-classification
    model, or raise ``RuntimeError`` if its weights are not in the local cache.

    Never downloads: ``local_files_only=True`` plus the forced offline env mean a
    cold cache fails loud here, not silently over the network. Pre-cache the weights
    once online (set ``CARREL_T1_MODEL_CACHE_DIR``) before running on a Cachet path.
    """
    enforce_offline_env()
    try:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
    except ImportError as exc:  # pragma: no cover - transformers is a declared dependency
        raise RuntimeError(
            "T1 model loading requires `transformers` (declared in requirements.txt)."
        ) from exc

    cache = cache_dir or os.getenv(CACHE_DIR_ENV) or None
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_id, local_files_only=True, cache_dir=cache)
        model = AutoModelForSequenceClassification.from_pretrained(
            model_id, local_files_only=True, cache_dir=cache
        )
    except Exception as exc:
        raise RuntimeError(
            f"Cachet offline mode: the model '{model_id}' is not in the local cache and "
            "the network is disabled. Pre-cache it once online with "
            f"{CACHE_DIR_ENV} set before running."
        ) from exc
    return tokenizer, model
