"""Orchestrator for the adversarial discovery battery.

Builds every attack case, runs each through the REAL engine via the read-only
probe (inside a socket ban that proves zero-egress), classifies the outcome
against the case's provable honest expectation, and writes the confession ledger.

CLI:
    python -m evals.adversary.harness [--out DIR] [--quiet]
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from services.legal.local_caselaw import local_caselaw_client

from .contracts import IS_CRACK, SEVERITY, AttackCase, Mode, Outcome, ProbeResult, classify
from .corpus import Seed
from .engine_probe import forbid_sockets, probe_contract, probe_litigator
from .families import all_cases

# Families whose contradiction-catching is not asserted as a hard expectation; the
# ledger reports their catch-rate as a coverage stat rather than counting an honest
# could-not-verify as a crack.
EXPLORATORY_FAMILIES = frozenset({"governing-law-lookalike", "polarity-flip"})


@dataclass(frozen=True)
class Record:
    """One probed case: the attack, the engine's answer, and the classification."""

    case: AttackCase
    result: ProbeResult
    outcome: Outcome

    @property
    def is_crack(self) -> bool:
        return IS_CRACK[self.outcome]


@dataclass
class BatteryResult:
    records: list[Record] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.records)

    @property
    def cracks(self) -> list[Record]:
        return sorted(
            (r for r in self.records if r.is_crack),
            key=lambda r: (SEVERITY[r.outcome], r.case.family, r.case.case_id),
        )

    @property
    def families(self) -> list[str]:
        return sorted({r.case.family for r in self.records})

    def outcome_counts(self) -> Counter[Outcome]:
        return Counter(r.outcome for r in self.records)

    def family_stats(self) -> dict[str, dict[str, Any]]:
        stats: dict[str, dict[str, Any]] = {}
        for fam in self.families:
            rows = [r for r in self.records if r.case.family == fam]
            stats[fam] = {
                "total": len(rows),
                "held": sum(1 for r in rows if r.outcome is Outcome.HELD),
                "cracks": sum(1 for r in rows if r.is_crack),
                "by_state": Counter(r.result.state for r in rows),
                "exploratory": fam in EXPLORATORY_FAMILIES,
            }
        return stats


def run_battery(seeds: list[Seed] | None = None) -> BatteryResult:
    """Run the full battery under a socket ban (proving zero-egress)."""

    cases = all_cases(seeds)
    result = BatteryResult()
    with forbid_sockets():
        client = local_caselaw_client()
        for case in cases:
            if case.mode is Mode.LITIGATOR:
                probe = probe_litigator(case.claim, client=client)
            else:
                probe = probe_contract(case.claim, case.source)
            result.records.append(Record(case=case, result=probe, outcome=classify(case, probe)))
    return result


def _print_summary(result: BatteryResult) -> None:
    counts = result.outcome_counts()
    print(
        f"\nCachet confession battery  |  {result.total} probes across {len(result.families)} families\n"
    )
    print(f"  HELD ................. {counts.get(Outcome.HELD, 0)}")
    print(f"  FALSE_GREEN (P0) ..... {counts.get(Outcome.FALSE_GREEN, 0)}")
    print(f"  LAUNDERING (P0) ...... {counts.get(Outcome.LAUNDERING, 0)}")
    print(f"  FALSE_ACCUSATION (P1)  {counts.get(Outcome.FALSE_ACCUSATION, 0)}")
    print(f"  MISSED_SUPPORT (obs) . {counts.get(Outcome.MISSED_SUPPORT, 0)}")
    cracks = result.cracks
    if cracks:
        print(f"\n  {len(cracks)} CRACK(S) SURFACED:")
        for r in cracks:
            print(f"    [{r.outcome.value}] {r.case.family}: {r.case.claim[:80]}")
    else:
        print("\n  No cracks surfaced. The refusal held across the battery.")
    observations = [r for r in result.records if r.outcome is Outcome.MISSED_SUPPORT]
    if observations:
        print(
            f"\n  {len(observations)} honest-direction observation(s) (refused a true positive, not a crack):"
        )
        for r in observations:
            print(f"    [{r.outcome.value}] {r.case.family}: {r.case.claim[:80]}")
    print()


def main() -> int:
    ap = argparse.ArgumentParser(description="Cachet adversarial discovery battery")
    default_out = Path(__file__).resolve().parents[2] / ".claude" / "adversary"
    ap.add_argument("--out", type=Path, default=default_out)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    result = run_battery()
    if not args.quiet:
        _print_summary(result)

    # Imported lazily so the battery itself has no I/O dependency.
    from .ledger import write_ledger

    paths = write_ledger(result, args.out)
    print(f"  ledger: {paths['markdown']}")
    print(f"  data:   {paths['json']}")
    if paths.get("fixtures"):
        print(f"  fixtures: {len(paths['fixtures'])} crack fixture(s) frozen")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
