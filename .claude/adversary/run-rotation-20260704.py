"""Adversarial rotation vs the kernel-residue parity result (2026-07-04).

Runs every fixture under .claude/adversary/fixtures/rotation-20260704/ through
the pure kernel entry point (cachet_verify.adapter.verify_claim — deterministic
by construction, no LLM path, no network) and classifies per the adversary
skill's ordering:

  FALSE_GREEN       altered/uncheckable case came back "verified"  (P0)
  FALSE_ACCUSATION  faithful case came back "altered"              (P1)
  HELD              honest outcome (catch, confirm, or refusal)
  P2 telemetry      faithful case refused where anchors existed (unnecessary
                    refusal — definite-rate food, never a crack)

Usage: ./.venv/bin/python .claude/adversary/run-rotation-20260704.py
Exit 0 iff zero cracks (P0 + P1).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cachet_verify.adapter import verify_claim  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "rotation-20260704"


def main() -> int:
    rows = []
    false_greens, false_accusations, p2 = [], [], []
    altered_total = altered_caught = 0
    faithful_total = faithful_confirmed = 0
    uncheckable_total = uncheckable_refused = 0

    for fixture_file in sorted(FIXTURES.glob("*.json")):
        spec = json.loads(fixture_file.read_text())
        family = spec["family"]
        for case in spec["cases"]:
            att = verify_claim(case["claim"], [case["source"]])
            state = att.state
            detail = "; ".join(c.detail for c in att.checks if c.state == state) or "; ".join(
                c.detail for c in att.checks
            )
            truth = case["truth"]

            if truth == "altered":
                altered_total += 1
                if state == "altered":
                    altered_caught += 1
                    cls = "HELD (caught)"
                elif state == "verified":
                    cls = "FALSE_GREEN"
                    false_greens.append((family, case, detail))
                else:
                    cls = "HELD (refused; missed catch)"
            elif truth == "faithful":
                faithful_total += 1
                if state == "verified":
                    faithful_confirmed += 1
                    cls = "HELD (confirmed)"
                elif state == "altered":
                    cls = "FALSE_ACCUSATION"
                    false_accusations.append((family, case, detail))
                else:
                    cls = "HELD (refused) [P2]"
                    p2.append((family, case, detail))
            else:  # uncheckable
                uncheckable_total += 1
                if state == "could_not_check":
                    uncheckable_refused += 1
                    cls = "HELD (refused)"
                elif state == "verified":
                    cls = "FALSE_GREEN"
                    false_greens.append((family, case, detail))
                else:
                    cls = "HELD (flagged instead of refusal)"

            rows.append((case["id"], family, truth, state, cls, detail, case["note"]))

    print(f"{'id':4} {'family':22} {'truth':11} {'engine':16} classification")
    print("-" * 100)
    for r in rows:
        print(f"{r[0]:4} {r[1]:22} {r[2]:11} {r[3]:16} {r[4]}")
        print(f"     detail: {r[5][:120]}")

    total = len(rows)
    cracks = len(false_greens) + len(false_accusations)
    print()
    print(f"attacks run: {total} | HELD: {total - cracks} | cracks: {cracks}")
    print(f"FALSE_GREEN (P0): {len(false_greens)}")
    print(f"FALSE_ACCUSATION (P1): {len(false_accusations)}")
    print(f"catch rate on altered: {altered_caught}/{altered_total}")
    print(
        f"faithful confirmed: {faithful_confirmed}/{faithful_total} "
        f"(P2 unnecessary refusals: {len(p2)})"
    )
    print(f"uncheckable refused: {uncheckable_refused}/{uncheckable_total}")
    for family, case, detail in false_greens:
        print(f"P0 FALSE_GREEN: {family}/{case['id']} — {case['note']} — {detail}", file=sys.stderr)
    for family, case, detail in false_accusations:
        print(
            f"P1 FALSE_ACCUSATION: {family}/{case['id']} — {case['note']} — {detail}",
            file=sys.stderr,
        )
    return 0 if cracks == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
