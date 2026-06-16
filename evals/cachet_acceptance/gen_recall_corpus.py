#!/usr/bin/env python
"""Generate the SEEDED-RECALL canary for ADR-0013.

The collision and injection canaries say "never green the wrong thing"; this one is
the counterweight: "DO decide the right thing." Without it the safety gates could be
passed trivially by refusing everything. Every case is a legitimate SAME-SUBJECT pair
the engine should resolve to a definite state:

- same subject, same value     -> supported
- same subject, different value -> contradicted

It spans two tiers on purpose:

- FLOOR-bindable clauses ("The liability cap is $5,000,000") that the regex floor
  handles today, so the floor already scores them definite.
- AFM-needed clauses whose phrasing the regex floor cannot bind ("shall not exceed",
  "is fixed at", "shall continue for"), which the floor routes to could-not-check
  (the documented recall cost) and the on-device labeler must recover.

So definite-rate on the regex floor is the recall BASELINE (well under the 0.70 bar by
design, because a third of the cases are AFM-needed); the shipping bar (>= 0.70, no
regression vs the floor) is met on the AFM path. No case here is a false green or a
false accusation, so bars 1 and 2 must stay clean on every config.

Deterministic. Regenerate:
    python evals/cachet_acceptance/gen_recall_corpus.py > evals/cachet_acceptance/recall_corpus.jsonl
"""

from __future__ import annotations

import itertools
import json

MONEY_SUBJECTS = [
    "liability cap",
    "indemnification cap",
    "security deposit",
    "signing bonus",
    "termination penalty",
    "annual retainer",
]
MONEY_VALUES = ["$5,000,000", "$250,000"]
MONEY_OTHER = {"$5,000,000": "$10,000,000", "$250,000": "$750,000"}
# clause phrasing that the regex floor canNOT bind (AFM-recovery tier)
MONEY_UNBINDABLE = "Pursuant to Section 8, the {s} shall not exceed {v} in the aggregate."

DURATION_SUBJECTS = [
    "notice period",
    "initial term",
    "cure period",
    "warranty period",
    "renewal term",
]
DURATION_VALUES = ["3 years", "90 days"]
DURATION_OTHER = {"3 years": "5 years", "90 days": "30 days"}
DURATION_UNBINDABLE = "The {s} shall continue for {v} from the Effective Date."


def _emit(
    subjects: list[str],
    values: list[str],
    other: dict[str, str],
    unbindable: str,
    kind: str,
) -> list[dict[str, str]]:
    cases = []
    for s, v in itertools.product(subjects, values):
        sid = s.replace(" ", "_")
        vid = v.strip("$").replace(",", "").replace(" ", "")
        # 1) supported, floor-bindable
        cases.append(
            {
                "id": f"recall-{kind}-{sid}-{vid}-supported-floor",
                "claim": f"The {s} is {v}.",
                "clause": f"The {s} is {v}.",
                "expected": "supported",
                "note": f"Same subject ({s}), same value, floor-bindable. Must be supported.",
            }
        )
        # 2) contradicted, floor-bindable
        cases.append(
            {
                "id": f"recall-{kind}-{sid}-{vid}-contradicted-floor",
                "claim": f"The {s} is {other[v]}.",
                "clause": f"The {s} is {v}.",
                "expected": "contradicted",
                "note": f"Same subject ({s}), different value. Must be contradicted.",
            }
        )
        # 3) supported, AFM-needed (clause phrasing the floor cannot bind)
        cases.append(
            {
                "id": f"recall-{kind}-{sid}-{vid}-supported-afm",
                "claim": f"The {s} is {v}.",
                "clause": unbindable.format(s=s, v=v),
                "expected": "supported",
                "note": f"Same subject ({s}), same value, clause phrasing the regex floor cannot bind. Floor -> could-not-check; AFM must recover.",
            }
        )
    return cases


def main() -> None:
    cases = _emit(MONEY_SUBJECTS, MONEY_VALUES, MONEY_OTHER, MONEY_UNBINDABLE, "money") + _emit(
        DURATION_SUBJECTS, DURATION_VALUES, DURATION_OTHER, DURATION_UNBINDABLE, "duration"
    )
    for c in cases:
        print(json.dumps(c))


if __name__ == "__main__":
    main()
