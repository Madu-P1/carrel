#!/usr/bin/env python
"""Generate the adversarial PERCENT collision canary (ADR-0013 percent addendum).

Every collision case is a same-VALUE / different-SUBJECT percent pair: the claim asserts
a rate for obligation A, the clause states the SAME rate for a different obligation B. The
honest verdict is could-not-check (the value coincides; the subjects differ), so a
`present` here is a FALSE GREEN, the one inviolable failure. This is the held-out set that
LOCKS the subject-less percent scope-out the way collision_corpus.jsonl locks money/
duration and polarity_collision_corpus.jsonl locks polarity.

The subjects are common nouns ("royalty", "tax", ...) precisely because the proper-noun
adjacency binder (`_percent_subject`) does NOT bind them, so each pair exercises the
value-only fallthrough that used to green. The clause templates deliberately span the
regex-bindable shape ("the X is V") and shapes a regex binder cannot bind ("shall be
capped at V", "accrues at V").

The file also carries a few NON-VACUITY anchors (a true contradiction, a true support)
so the corpus exercises the decide-path, not only refusals -- mirroring
polarity_collision_corpus.jsonl. The supported case uses a proper-noun-bound subject
("10% France"), the ONE percent green path the scope-out preserves.

Deterministic (no randomness) so the corpus is reproducible and owned. The percent path is
labeler-INDEPENDENT (the subject labeler only labels money/magnitude/duration), so this
corpus must show ZERO false greens under BOTH `--labeler off` and `--labeler regex`.

Regenerate:
    python evals/cachet_acceptance/gen_percent_collision_corpus.py > \
        evals/cachet_acceptance/percent_collision_corpus.jsonl
"""

from __future__ import annotations

import itertools
import json

PERCENT_SUBJECTS = [
    "royalty",
    "tax",
    "discount",
    "interest rate",
    "commission",
    "late fee",
    "default rate",
    "profit share",
]
PERCENT_VALUES = ["10%", "5%", "2.5%"]
# Clause shapes: the first is regex-bindable ("the X is V"); the rest are exactly the
# phrasings a leading-qualifier regex binder cannot bind, where the value-only path leaks.
CLAUSE_TEMPLATES = [
    "The {b} is {v}.",
    "The {b} shall be {v}.",
    "The {b} shall be capped at {v}.",
    "{b_cap} accrues at {v} per annum.",
]
CLAIM_TEMPLATE = "The {a} is {v}."


def _collisions() -> list[dict[str, str]]:
    cases = []
    # Thin the (a, b) SUBJECT PAIRS, but keep ALL values x ALL clause templates for each
    # kept pair. A flat stride over the fully-built list would alias to a single template
    # index (len(CLAUSE_TEMPLATES) divides the inner-loop period), silently dropping the
    # non-regex-bindable shapes ("shall be capped at V", "accrues at V") -- exactly the
    # phrasings where the value-only path leaks. Sampling the pairs instead guarantees
    # every clause shape appears.
    pairs = list(itertools.permutations(PERCENT_SUBJECTS, 2))[::7]
    for a, b in pairs:
        for v in PERCENT_VALUES:
            for ti, tpl in enumerate(CLAUSE_TEMPLATES):
                cases.append(
                    {
                        "id": (
                            f"percent-collision-{a.replace(' ', '_')}-vs-"
                            f"{b.replace(' ', '_')}-{v.strip('%').replace('.', 'p')}-t{ti}"
                        ),
                        "claim": CLAIM_TEMPLATE.format(a=a, v=v),
                        "clause": tpl.format(b=b, b_cap=b[:1].upper() + b[1:], v=v),
                        "expected": "could_not_verify",
                        "note": (
                            f"COLLISION: claim about '{a}', clause states the same percent "
                            f"value for '{b}' via template t{ti}. A present is a false green."
                        ),
                    }
                )
    # Every clause template must survive the pair-sampling, or the non-bindable shapes go
    # untested (the bug a flat list-stride introduced).
    assert {c["id"].rsplit("-", 1)[1] for c in cases} == {
        f"t{i}" for i in range(len(CLAUSE_TEMPLATES))
    }
    return cases


def _non_vacuity() -> list[dict[str, str]]:
    return [
        {
            "id": "percent-true-contradiction-france",
            "claim": "Allocation is 20% France.",
            "clause": "Allocation is 10% France.",
            "expected": "contradicted",
            "note": (
                "Non-vacuity + the real percent catch: a proper-noun-bound SAME subject with "
                "a flipped value is a contradiction, so the corpus exercises the decide-path, "
                "not only refusals."
            ),
        },
        {
            "id": "percent-true-support-france",
            "claim": "Allocation is 10% France.",
            "clause": "Allocation is 10% France.",
            "expected": "supported",
            "note": (
                "Non-vacuity: the ONE percent green the scope-out preserves -- a proper-noun-"
                "bound subject the clause confirms still reads supported. Guards against the "
                "scope-out over-refusing the safe green."
            ),
        },
        {
            "id": "percent-true-support-germany",
            "claim": "The allocation is 25% Germany.",
            "clause": "The allocation is 25% Germany.",
            "expected": "supported",
            "note": (
                "Second proper-noun + value so the preserved-green path is not pinned to one "
                "subject/value (Germany, 25%): a regression that only breaks '10% France' "
                "adjacency is still caught."
            ),
        },
        {
            "id": "percent-true-contradiction-germany",
            "claim": "The allocation is 25% Germany.",
            "clause": "The allocation is 30% Germany.",
            "expected": "contradicted",
            "note": "Second subject-bound contradiction shape (Germany, 25% vs 30%).",
        },
    ]


def _adversary_locked() -> list[dict[str, str]]:
    """Cracks the cachet-adversary skill threw at the fixed percent path and the engine
    HELD (2026-06-16). Qualitatively distinct from the single-anchor generator collisions:
    surface shapes the generator does not emit (word-form / basis-points / percent-of-X)
    and MULTI-ANCHOR laundering (an unconfirmed percent must not ride a genuinely-confirmed
    sibling -- governing-law / polarity / verbatim-quote / subject-bound-percent -- to a
    green). Locked here so a future engine change cannot silently reopen them."""
    cnv = "could_not_verify"
    return [
        # Surface shapes: same value, different subject.
        {
            "id": "percent-shape-wordform",
            "claim": "The royalty is ten percent.",
            "clause": "The tax is ten percent.",
            "expected": cnv,
            "note": "Word-form percent, same value, different subject.",
        },
        {
            "id": "percent-shape-bps-vs-pct",
            "claim": "The discount is 50 bps.",
            "clause": "The late fee is 0.5%.",
            "expected": cnv,
            "note": "Basis points canonicalize to 0.5% (same value), different subject.",
        },
        {
            "id": "percent-shape-pct-of-x",
            "claim": "The royalty is 10% of net revenue.",
            "clause": "The commission is 10% of gross sales.",
            "expected": cnv,
            "note": "Percent-of-X (the demo shape), same value, different subject.",
        },
        # Multi-anchor laundering: the unconfirmed percent must not ride a confirmed sibling.
        {
            "id": "percent-launder-via-govlaw",
            "claim": "Governed by Delaware law and the royalty is 10%.",
            "clause": "This Agreement is governed by Delaware law. The tax is 10%.",
            "expected": cnv,
            "note": "A confirmed governing-law present must NOT carry the unconfirmed percent to a green.",
        },
        {
            "id": "percent-launder-via-polarity",
            "claim": "The license is exclusive and the royalty is 10%.",
            "clause": "The license is exclusive. The tax is 10%.",
            "expected": cnv,
            "note": "A confirmed polarity present must NOT carry the unconfirmed percent to a green.",
        },
        {
            "id": "percent-launder-via-quote",
            "claim": 'The royalty is 10% and fees are "received each quarter".',
            "clause": 'Fees are "received each quarter". The tax is 10%.',
            "expected": cnv,
            "note": "A verbatim quote must NOT carry the unconfirmed percent to a green.",
        },
        {
            "id": "percent-launder-via-bound-percent",
            "claim": "Allocation is 10% France and the royalty is 10%.",
            "clause": "Allocation is 10% France. The tax is 10%.",
            "expected": cnv,
            "note": "A confirmed subject-bound percent must NOT carry an unconfirmed sibling percent to a green.",
        },
    ]


def main() -> None:
    # Only same-value collisions + the two proper-noun non-vacuity anchors are emitted.
    # The different-value/different-subject case is intentionally NOT emitted: ADR-0013
    # retains the value-only contradiction as the altered-figure catch, so the bare
    # function returns `contradicted` there (a retrieval-mitigated artifact, not a gate
    # case). The gate stays focused on the false GREEN it must lock.
    cases = _collisions() + _non_vacuity() + _adversary_locked()
    for c in cases:
        print(json.dumps(c))


if __name__ == "__main__":
    main()
