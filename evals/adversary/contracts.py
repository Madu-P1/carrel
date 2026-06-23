"""Shared data contracts for the adversarial discovery harness.

Every other module in ``evals/adversary`` conforms to the shapes here. The honest
verdict vocabulary and the disposition->state map mirror
``script/cachet-acceptance.py`` exactly; a test
(``tests/test_adversary_harness.py``) pins the two together so they cannot drift.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# The three honest states the product surfaces. Mirror of the user-facing states
# in script/cachet-acceptance.py::_state.
SUPPORTED = "supported"
CONTRADICTED = "contradicted"
COULD_NOT_VERIFY = "could_not_verify"

HONEST_STATES = frozenset({SUPPORTED, CONTRADICTED, COULD_NOT_VERIFY})

# disposition -> honest state. The harness's single source of truth; a test asserts
# this agrees with script/cachet-acceptance.py for every disposition the engine can
# emit, so a future engine change that adds a disposition fails loudly here.
STATE_BY_DISPOSITION: dict[str, str] = {
    "present": SUPPORTED,
    "parametric_contradiction": CONTRADICTED,
    "multi_value_unverifiable": COULD_NOT_VERIFY,
    "conflicting_clauses": COULD_NOT_VERIFY,
    "not_found": COULD_NOT_VERIFY,
    # grounding-only refusals (no clause check) — honest could-not-check.
    "section_absent": COULD_NOT_VERIFY,
}


def state_for_disposition(disposition: str) -> str:
    """Map an engine disposition to the honest state the product surfaces.

    An unknown disposition resolves to could-not-verify: the safe, honest default
    (never a silent ``supported``).
    """

    return STATE_BY_DISPOSITION.get(disposition, COULD_NOT_VERIFY)


class Mode(str, Enum):
    """Which engine path an attack exercises."""

    CONTRACT = "contract"  # verify_claim_against_clause(claim, clause)
    LITIGATOR = "litigator"  # build_deterministic_envelope(draft, client=...)


@dataclass(frozen=True)
class AttackCase:
    """One adversarial (claim, source) pair with its provable honest expectation.

    ``acceptable_states`` is the set of honest verdicts: the engine is RIGHT iff its
    state is in this set. The set is derived by construction (a mutator's audited
    rule, or a hand-authored family case), never guessed. The classifier turns any
    state outside this set into a typed crack.

    For CONTRACT mode, ``source`` is the clause text. For LITIGATOR mode, ``claim``
    is the full draft sentence (it carries the citation) and ``source`` documents
    the intended corpus truth for the ledger (it is not fed to the engine).
    """

    case_id: str
    family: str
    mode: Mode
    claim: str
    source: str
    acceptable_states: frozenset[str]
    rationale: str
    # Provenance: which seed + mutator (or "hand") produced this case, for the ledger.
    origin: str = "hand"

    def __post_init__(self) -> None:
        bad = set(self.acceptable_states) - HONEST_STATES
        if bad:
            raise ValueError(f"{self.case_id}: unknown acceptable_states {sorted(bad)}")
        if not self.acceptable_states:
            raise ValueError(f"{self.case_id}: acceptable_states must be non-empty")


class Outcome(str, Enum):
    """The classification of a single probe against its case's honest expectation."""

    HELD = "HELD"  # engine's state is honest (in acceptable_states)
    FALSE_GREEN = "FALSE_GREEN"  # P0 — affirmed a claim that is not honestly supportable
    FALSE_ACCUSATION = "FALSE_ACCUSATION"  # P1 — accused a clean claim
    LAUNDERING = "COULD_NOT_CHECK_LAUNDERING"  # P0 — dodged a genuine contradiction
    # Honest-direction: failed to confirm a true positive (refused a real quote). Safe,
    # never dangerous, but a coverage gap worth surfacing — NOT counted as a crack.
    MISSED_SUPPORT = "MISSED_SUPPORT"


# Severity ordering for sorting the ledger: cracks first, worst first.
SEVERITY: dict[Outcome, int] = {
    Outcome.FALSE_GREEN: 0,
    Outcome.LAUNDERING: 1,
    Outcome.FALSE_ACCUSATION: 2,
    Outcome.MISSED_SUPPORT: 3,
    Outcome.HELD: 4,
}

# What counts as a DANGEROUS crack for the headline. MISSED_SUPPORT is honest-direction
# (the engine refused rather than affirmed) so it is reported as a coverage observation,
# not a crack.
IS_CRACK: dict[Outcome, bool] = {
    Outcome.FALSE_GREEN: True,
    Outcome.LAUNDERING: True,
    Outcome.FALSE_ACCUSATION: True,
    Outcome.MISSED_SUPPORT: False,
    Outcome.HELD: False,
}


@dataclass(frozen=True)
class ProbeResult:
    """What the read-only probe read back from the real engine for one case."""

    state: str
    disposition: str
    anchor_type: str | None
    detail: str
    mode: Mode
    raw: dict[str, Any] = field(default_factory=dict)


def classify(case: AttackCase, result: ProbeResult) -> Outcome:
    """Classify one probe against its case's honest expectation.

    The rule is total and unambiguous given a correct ``acceptable_states``:
      - state in acceptable_states                -> HELD
      - engine said supported (and that's wrong)  -> FALSE_GREEN  (the catastrophe)
      - engine said contradicted (and that's wrong) -> FALSE_ACCUSATION
      - engine dodged to could-not-verify when a definite verdict was the honest
        answer                                    -> LAUNDERING
    """

    if result.state in case.acceptable_states:
        return Outcome.HELD
    if result.state == SUPPORTED:
        return Outcome.FALSE_GREEN
    if result.state == CONTRADICTED:
        return Outcome.FALSE_ACCUSATION
    # result.state == COULD_NOT_VERIFY, but it was not acceptable. Two sub-cases:
    if CONTRADICTED in case.acceptable_states:
        # the honest answer was a contradiction the engine dodged.
        return Outcome.LAUNDERING
    # the honest answer was an affirmation (a verbatim quote) the engine failed to
    # confirm — under-affirmation, the safe direction.
    return Outcome.MISSED_SUPPORT
