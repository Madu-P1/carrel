"""Run the kernel-residue parity experiment and write the report.

Usage:
    ./.venv/bin/python -m evals.kernel_residue.run [--out evals/reports/FILE.md]

Exit code 0 iff the honesty floor holds (zero false greens AND zero false
accusations). The catch rate itself is reported, not gated: it is the council's
sizing number, not a pass/fail bar.
"""

from __future__ import annotations

import argparse
import sys

from .corpus import CASES
from .harness import ParitySummary, evaluate


def render_report(summary: ParitySummary) -> str:
    lines: list[str] = []
    lines.append("# Kernel-residue parity report (ADR-0015, revisit-trigger #3)")
    lines.append("")
    lines.append(
        "The kernel adapter (cachet_verify: legal-engine parametrics + kernel residue "
        "detectors + quote check) against non-legal AI fabrications. No citation or caselaw pack in play."
    )
    lines.append("")
    lines.append("## Headline numbers")
    lines.append("")
    lines.append(
        f"- **Altered-catch rate: {summary.altered_flagged}/{summary.altered_total} "
        f"({summary.catch_rate:.0%})** on anchored, near-verbatim fabrications"
    )
    lines.append(f"- **False greens: {len(summary.false_greens)}** (floor: 0)")
    lines.append(f"- **False accusations: {len(summary.false_accusations)}** (floor: 0)")
    lines.append(f"- Faithful confirmed: {summary.faithful_supported}/{summary.faithful_total}")
    lines.append(
        f"- Honest refusal on uncheckable/blind-spot cases: "
        f"{summary.uncheckable_refused}/{summary.uncheckable_total}"
    )
    lines.append("")
    lines.append("## Per-case results")
    lines.append("")
    lines.append("| id | domain | truth | outcome | engine says | note |")
    lines.append("|---|---|---|---|---|---|")
    for r in summary.results:
        lines.append(
            f"| {r.case.id} | {r.case.domain} | {r.case.truth} | {r.outcome} "
            f"| `{r.raw}` | {r.case.note} |"
        )
    lines.append("")
    lines.append("## Details (flagged cases)")
    lines.append("")
    for r in summary.results:
        if r.outcome == "flagged":
            lines.append(f"- **{r.case.id}**: {r.detail}")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=None, help="write the markdown report here")
    args = parser.parse_args(argv)

    summary = evaluate(CASES)
    report = render_report(summary)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"report written to {args.out}")
    else:
        print(report)

    floor_holds = not summary.false_greens and not summary.false_accusations
    if not floor_holds:
        for r in summary.false_greens:
            print(f"FALSE GREEN: {r.case.id} ({r.raw}) {r.detail}", file=sys.stderr)
        for r in summary.false_accusations:
            print(f"FALSE ACCUSATION: {r.case.id} ({r.raw}) {r.detail}", file=sys.stderr)
    return 0 if floor_holds else 1


if __name__ == "__main__":
    raise SystemExit(main())
