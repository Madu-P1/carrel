"""The frozen verdict contract -- the forever-API (ADR-0015).

Everything here is wire-visible and therefore additive-only from the moment it
ships (Hyrum's law: embedders will bind to all of it). The three-state model
and the combine() precedence ARE the product's honesty promise, made
executable. Changing their semantics is not a refactor; it is a different
product.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Literal

SCHEMA_VERSION = 1

# The three states. No fourth state, no numeric confidence: a score invites
# rounding a 0.9 into a green, which is exactly the failure the kernel exists
# to make impossible.
Verdict = Literal["verified", "altered", "could_not_check"]

_VALID_STATES: frozenset[str] = frozenset(("verified", "altered", "could_not_check"))


@dataclass(frozen=True)
class CheckResult:
    """One check's verdict, with mandatory provenance.

    ``provenance`` names the evidence root that produced this result
    ("deterministic", "public-corpus:<name>", "user-vault:<doc>", ...). Every
    green is scoped and attributable: a certification policy may exclude
    evidence roots it does not trust, which is the honest ceiling against a
    lying corpus (attributable-never-silent).
    """

    state: Verdict
    provenance: str
    detail: str = ""
    # What the check actually examined (an anchor surface, a quoted phrase).
    subject: str = ""

    def __post_init__(self) -> None:
        if self.state not in _VALID_STATES:
            raise ValueError(f"not a verdict state: {self.state!r}")
        if not self.provenance:
            raise ValueError("provenance is mandatory on every check result")


@dataclass(frozen=True)
class Attestation:
    """The kernel's answer for one claim: the combined state plus every
    participating check, so the caller can render receipts and a policy layer
    can re-derive the state from a filtered evidence set."""

    state: Verdict
    checks: tuple[CheckResult, ...] = field(default_factory=tuple)
    schema_version: int = SCHEMA_VERSION


def combine(results: Iterable[CheckResult]) -> Verdict:
    """The honesty algebra. ~20 lines that must never change semantics:

    - any ``altered`` wins outright (a caught fabrication cannot be averaged
      away by ten passing checks);
    - otherwise any ``could_not_check`` floors the combined verdict (a claim
      is not verified while any participating check abstained);
    - ``verified`` only when every participating check verified;
    - no participating checks at all is ``could_not_check`` -- silence is
      never a pass.
    """
    saw_any = False
    saw_refusal = False
    for r in results:
        saw_any = True
        if r.state == "altered":
            return "altered"
        if r.state == "could_not_check":
            saw_refusal = True
    if not saw_any or saw_refusal:
        return "could_not_check"
    return "verified"


def attest(results: Iterable[CheckResult]) -> Attestation:
    checks = tuple(results)
    return Attestation(state=combine(checks), checks=checks)


# The daemon's wire contract, documented as data so surfaces and tests share
# one description. Additive-only: new fields may appear; none may be removed
# or change meaning.
WIRE_CONTRACT = {
    "schema_version": SCHEMA_VERSION,
    "request": {
        "claim": "string, the claim text to attest",
        "sources": "list of strings, the evidence the claim is checked against",
    },
    "response": {
        "schema_version": "int",
        "state": "verified | altered | could_not_check",
        "checks": "list of {state, provenance, detail, subject}",
    },
}
