"""Runtime guard for the T1 recall tier (ADR-0012).

``t1_permitted()`` is the physically-inert switch the verify path checks before it ever
runs the local NLI selector. It is fail-closed: True only when the operator has BOTH
opted in (``CACHET_T1_RECALL`` truthy) AND a calibration gate-pass artifact exists whose
recorded inputs still match the files on disk. Any drift (someone widened thresholds,
swapped the corpus or guideline, or bumped the feature code without re-running the gate)
invalidates the pass, so a stale or hand-forged artifact can never silently enable T1.

This lives in ``services`` and NOT in ``benchmarks`` on purpose: the runtime must not
import the dev/CI gate harness, which is not guaranteed to ship in a packaged app. The
artifact FORMAT (the keys ``benchmarks.t1_calibration.write_gate_pass`` writes) is the
only contract shared across that boundary; the paths below point at the same committed
calibration data, kept in lock-step by that format rather than a shared import.

Two bindings are checked elsewhere, by design:
  - ``model_sha256`` is recorded in the artifact but verified at model LOAD, not here:
    re-hashing the weights on every verify request would tax the hot path, and the model
    only loads once T1 is actually enabled. That load-time check lands with the enable PR
    (the weights are not cache-present in CI to exercise it while T1 is dark).
  - ``rank_cutoff`` is NOT a separate hash: it lives in ``thresholds.json`` and rides
    ``thresholds_sha256``, so changing K invalidates a prior pass. That pins the K the
    runtime READS; it does NOT by itself prove the gate's predictions were generated at
    that K. The best-of-K equivalence (gated FAR == runtime FAR) is enforced by the
    corpus-generation step today and is not yet mechanically checked here; the enable PR
    adds that check (ADR-0012 "Implementation notes" + its before-T1-goes-live TODO).

Not process-cached: while dark, this returns False after one env read plus one missing-file
read and never hashes anything, so the dark hot path is already O(1). Caching would only
speed the not-yet-existing enabled path at the cost of mutable module state; add it (with
a latency benchmark) when the enabled path exists, not before.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

# Identity of the T1 candidacy + scoring implementation. Bump whenever the selection
# logic changes (candidacy strategy, label mapping, confidence math) so a gate-pass minted
# against the old code is invalidated. rank_cutoff is NOT here (it lives in thresholds.json).
FEATURE_VERSION = "t1-v1"

_ENV_FLAG = "CACHET_T1_RECALL"
_TRUTHY = frozenset({"1", "true", "yes", "on"})

# The committed calibration files. Same files benchmarks/t1_calibration.py hashes when it
# mints the pass; re-hashed here to detect post-gate drift.
_CALIBRATION_DIR = Path(__file__).resolve().parents[2] / "data" / "calibration"
_THRESHOLDS = _CALIBRATION_DIR / "thresholds.json"
_CORPUS = _CALIBRATION_DIR / "corpus" / "test.jsonl"
_GUIDELINE = _CALIBRATION_DIR / "GUIDELINE-v1.md"
_GATE_PASS = _CALIBRATION_DIR / "gate-pass.json"


def _truthy(value: str | None) -> bool:
    return value is not None and value.strip().lower() in _TRUTHY


def _sha256_file(path: Path) -> str | None:
    # Fail-closed: an unreadable file (missing, a directory, no permission, or deleted
    # after a .exists() check) resolves to None, never a raised error. A None here is then
    # compared against the artifact's recorded hash and a mismatch fails the guard.
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def t1_permitted() -> bool:
    """Fail-closed: True only if the operator opted in AND a still-valid gate-pass exists.

    Never raises: any error reading or parsing the artifact resolves to False (dark).
    """
    if not _truthy(os.getenv(_ENV_FLAG)):
        return False
    try:
        artifact = json.loads(_GATE_PASS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # ValueError covers json.JSONDecodeError AND a non-UTF-8 read (UnicodeDecodeError);
        # any unreadable or corrupt artifact resolves to dark, honoring "never raises".
        return False
    if not isinstance(artifact, dict) or artifact.get("passed") is not True:
        return False
    if artifact.get("feature_version") != FEATURE_VERSION:
        return False
    # Re-hash the cheap, committed inputs and compare. A mismatch means the corpus,
    # thresholds, or guideline drifted since the gate passed: fail closed. (model_sha256
    # is bound at model-load, not here; see the module docstring.)
    for key, path in (
        ("corpus_sha256", _CORPUS),
        ("thresholds_sha256", _THRESHOLDS),
        ("guideline_version", _GUIDELINE),
    ):
        if artifact.get(key) != _sha256_file(path):
            return False
    return True


def load_runtime_thresholds() -> tuple[float, int] | None:
    """``(verdict_threshold, rank_cutoff)`` from thresholds.json, or None if not fully set.

    Both are operator-committed gate outputs, never defaulted: a missing or null value
    means T1 has nothing calibrated to run with, so the caller does nothing and the claim
    stays could-not-check. Reads raw JSON; the gate (benchmarks) owns full validation.
    """
    try:
        data = json.loads(_THRESHOLDS.read_text(encoding="utf-8"))
    except (OSError, ValueError):  # ValueError: JSON decode + non-UTF-8 read, both -> dark
        return None
    if not isinstance(data, dict):
        return None
    epsilon = data.get("threshold_epsilon")
    rank_cutoff = data.get("rank_cutoff")
    if epsilon is None or rank_cutoff is None:
        return None
    try:
        return float(epsilon), int(rank_cutoff)
    except (TypeError, ValueError):
        return None
