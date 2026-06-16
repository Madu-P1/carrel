#!/usr/bin/env python
"""Generate the adversarial COLLISION canary for ADR-0013.

Every case is a same-VALUE / different-SUBJECT pair: the claim asserts a value for
obligation A, the clause states the SAME value for a different obligation B. The
honest verdict is could-not-check (the value coincides; the subjects differ), so a
`present` here is a FALSE GREEN, the one inviolable failure. This is the held-out set
the money/duration subject-labeler must drive to ZERO false greens before it ships.

Deterministic (no randomness) so the corpus is reproducible and owned. Regenerate:
    python evals/cachet_acceptance/gen_collision_corpus.py > evals/cachet_acceptance/collision_corpus.jsonl

The phrasing set deliberately spans both the regex-bindable shapes ("the X is V") and
the shapes a regex binder CANNOT bind ("shall be capped at V", "shall continue for V"),
because the latter are exactly where the value-only path leaks a false green.
"""

from __future__ import annotations

import itertools
import json

MONEY_SUBJECTS = [
    "liability cap",
    "indemnification cap",
    "security deposit",
    "late fee",
    "signing bonus",
    "termination penalty",
    "annual retainer",
    "minimum order value",
]
MONEY_VALUES = ["$5,000,000", "$250,000", "$1,000,000"]
MONEY_CLAUSE_TEMPLATES = [
    "The {b} is {v}.",
    "The {b} shall not exceed {v}.",
    "The Seller's {b} shall be capped at {v}.",  # regex-unbindable on purpose
]

DURATION_SUBJECTS = [
    "notice period",
    "initial term",
    "cure period",
    "warranty period",
    "non-compete period",
    "renewal term",
]
DURATION_VALUES = ["3 years", "90 days", "30 days"]
DURATION_CLAUSE_TEMPLATES = [
    "The {b} is {v}.",
    "The {b} shall be {v}.",
    "The {b} shall continue for {v}.",  # regex-unbindable on purpose
]

CLAIM_TEMPLATE = "The {a} is {v}."


def _emit(
    subjects: list[str], values: list[str], clause_templates: list[str], kind: str
) -> list[dict[str, str]]:
    cases = []
    for a, b in itertools.permutations(subjects, 2):
        for v in values:
            for ti, tpl in enumerate(clause_templates):
                cases.append(
                    {
                        "id": f"collision-{kind}-{a.replace(' ', '_')}-vs-{b.replace(' ', '_')}-{v.strip('$').replace(',', '').replace(' ', '')}-t{ti}",
                        "claim": CLAIM_TEMPLATE.format(a=a, v=v),
                        "clause": tpl.format(b=b, v=v),
                        "expected": "could_not_verify",
                        "note": f"COLLISION: claim about '{a}', clause states the same {kind} value for '{b}'. A present is a false green.",
                    }
                )
    return cases


def main() -> None:
    cases = []
    # Cap each type so the corpus stays a few hundred, balanced money/duration.
    money = _emit(MONEY_SUBJECTS, MONEY_VALUES, MONEY_CLAUSE_TEMPLATES, "money")
    duration = _emit(DURATION_SUBJECTS, DURATION_VALUES, DURATION_CLAUSE_TEMPLATES, "duration")
    # Deterministic stride-sample to land near N=240 without dropping any (a,b) pair type.
    cases = money[::2] + duration[::2]
    for c in cases:
        print(json.dumps(c))


if __name__ == "__main__":
    main()
