"""The conformance suite: the executable honesty contract (ADR-0014 step 1).

Any implementation claiming to BE the Cachet kernel -- this package's adapter,
the companion's vendored engine, a future Rust or WASM port -- must pass this
suite against the shared corpus. The suite asserts the floors that define the
product; an implementation that fails ANY floor is not a slower or weaker
kernel, it is not a Cachet kernel at all:

  1. no false green: an altered case never returns "verified";
  2. no false accusation: a faithful case never returns "altered";
  3. honest refusal: an uncheckable case returns "could_not_check";
  4. the three-state vocabulary and nothing else.

Catch RATE is reported, not gated (implementations may differ in coverage;
they may never differ in honesty).

Corpus format: JSONL, one case per line:
    {"id": "F1", "domain": "finance", "truth": "altered",
     "claim": "...", "source": "...", "note": "..."}
``truth`` is one of altered | faithful | uncheckable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

VALID_STATES = frozenset(("verified", "altered", "could_not_check"))

# verify_fn(claim, sources) -> state string. The ONLY interface an
# implementation must offer to be conformance-tested.
VerifyFn = Callable[[str, list[str]], str]


@dataclass(frozen=True)
class ConformanceCase:
    id: str
    truth: str  # altered | faithful | uncheckable
    claim: str
    source: str
    domain: str = ""
    note: str = ""


@dataclass(frozen=True)
class ConformanceReport:
    total: int
    violations: tuple[str, ...]  # human-readable floor violations, empty = conformant
    altered_total: int
    altered_caught: int
    faithful_total: int
    faithful_confirmed: int
    uncheckable_total: int
    uncheckable_refused: int
    outcomes: dict = field(default_factory=dict)  # case id -> state

    @property
    def conformant(self) -> bool:
        return not self.violations

    @property
    def catch_rate(self) -> float:
        return self.altered_caught / self.altered_total if self.altered_total else 0.0


def load_corpus(path: str | Path) -> list[ConformanceCase]:
    cases: list[ConformanceCase] = []
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            raw = json.loads(line)
            if raw["truth"] not in ("altered", "faithful", "uncheckable"):
                raise ValueError(f"{path}:{line_no}: bad truth {raw['truth']!r}")
            cases.append(
                ConformanceCase(
                    id=raw["id"],
                    truth=raw["truth"],
                    claim=raw["claim"],
                    source=raw["source"],
                    domain=raw.get("domain", ""),
                    note=raw.get("note", ""),
                )
            )
    ids = [c.id for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: duplicate case ids")
    return cases


def run_conformance(verify_fn: VerifyFn, cases: Iterable[ConformanceCase]) -> ConformanceReport:
    violations: list[str] = []
    outcomes: dict[str, str] = {}
    tallies = {
        "altered": [0, 0],  # total, caught
        "faithful": [0, 0],  # total, confirmed
        "uncheckable": [0, 0],  # total, refused
    }
    for case in cases:
        state = verify_fn(case.claim, [case.source])
        outcomes[case.id] = state
        if state not in VALID_STATES:
            violations.append(f"{case.id}: off-vocabulary state {state!r} (floor 4)")
            continue
        tally = tallies[case.truth]
        tally[0] += 1
        if case.truth == "altered":
            if state == "verified":
                violations.append(f"{case.id}: FALSE GREEN -- altered case returned verified")
            elif state == "altered":
                tally[1] += 1
        elif case.truth == "faithful":
            if state == "altered":
                violations.append(f"{case.id}: FALSE ACCUSATION -- faithful case returned altered")
            elif state == "verified":
                tally[1] += 1
        else:  # uncheckable
            if state == "could_not_check":
                tally[1] += 1
            else:
                violations.append(
                    f"{case.id}: uncheckable case must refuse, returned {state!r} (floor 3)"
                )
    # A conformance claim requires the floors to have actually been
    # exercised: an empty corpus (or one missing a truth class) proves
    # nothing, and a vacuous pass would let a truncated corpus certify a
    # broken distribution (mythos batchE-20260702, high).
    for truth, (total, _) in tallies.items():
        if total == 0:
            violations.append(
                f"corpus exercises no {truth} cases; conformance cannot be claimed vacuously"
            )
    return ConformanceReport(
        total=len(outcomes),
        violations=tuple(violations),
        altered_total=tallies["altered"][0],
        altered_caught=tallies["altered"][1],
        faithful_total=tallies["faithful"][0],
        faithful_confirmed=tallies["faithful"][1],
        uncheckable_total=tallies["uncheckable"][0],
        uncheckable_refused=tallies["uncheckable"][1],
        outcomes=outcomes,
    )


DEFAULT_CORPUS = Path(__file__).parent / "conformance_corpus" / "nonlegal-v1.jsonl"
