"""cachet-verify: the deterministic attestation kernel (ADR-0015).

One source of truth for the honesty contract every Cachet surface depends on:

    verify(claim, sources) -> verified | altered | could_not_check

This package is the strangler-fig seed (ADR-0014 step 2): today it wraps the
hardened engine in ``services.legal`` behind the frozen contract; the companion
migrates onto it next, then the vendored fork dies. The contract module is the
forever-API -- additive-only from here.

Structural honesty rules (enforced by shape, not discipline):
  - three states, no fourth, no confidence float;
  - ``altered`` beats everything, ``could_not_check`` is the floor,
    ``verified`` requires every participating check verified;
  - provenance is mandatory on every check result;
  - evidence providers propose, only the kernel pronounces (a semantic
    assessor's result type has no verified variant).
"""

from .contract import (
    SCHEMA_VERSION,
    CheckResult,
    Verdict,
    combine,
)

__all__ = ["SCHEMA_VERSION", "CheckResult", "Verdict", "combine"]
