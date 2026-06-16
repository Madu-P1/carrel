#!/usr/bin/env python
"""Cachet demo acceptance gate: the decidable definition of "not broken".

Runs the deterministic clause-level verifier over a FROZEN corpus of real
(claim, source-clause, expected) cases and enforces four bars. This is the STOP
condition for engine work: green means stop touching the engine, red prints the
exact gap. The number, not anyone's judgment, holds the veto.

The bars (a demo is "not broken" iff all four hold):
  1. Zero false greens      - engine never says supported on a non-supported claim.
  2. Zero false accusations  - engine never says contradicted on a clean claim.
  3. No boilerplate wall      - every refusal NAMES its own statement's figures
                                (specificity), so it never reads as content-free
                                boilerplate. A specific refusal is the gem; a
                                content-free wall is the only real defect.
  4. Definite-rate >= bar     - of cases that SHOULD reach a definite verdict
                                (supported/contradicted), the share the engine
                                actually decides. Default 0.70.

Usage:
    ./.venv/bin/python script/cachet-acceptance.py [--corpus PATH] [--bar 0.70]
                                                   [--labeler off|regex]
Exit 0 iff all four bars pass.

``--labeler regex`` runs with the subject labeler's regex floor ON
(``CARREL_SUBJECT_LABELER=regex``), so the gate exercises the subject-bound
percent/polarity path, not just the figure scope-out. Run BOTH modes: the
figure corpora (collision) are scoped out under ADR-0013 either way, while the
labeled-collision corpus only decides anything with the labeler on. Default
``off`` keeps the shipped default config.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.legal.contract_verify import verify_claim_against_clause  # noqa: E402

# disposition -> the three honest states the product surfaces.
_DEFINITE = {"present": "supported", "parametric_contradiction": "contradicted"}
_REFUSAL = {"multi_value_unverifiable", "conflicting_clauses", "not_found"}


def _state(disposition: str) -> str:
    if disposition in _DEFINITE:
        return _DEFINITE[disposition]
    return "could_not_verify"


def run(corpus_path: Path, bar: float) -> int:
    cases = [json.loads(line) for line in corpus_path.read_text().splitlines() if line.strip()]
    rows = []
    for c in cases:
        vd = verify_claim_against_clause(c["claim"], c["clause"])
        rows.append(
            {
                "id": c["id"],
                "claim": c["claim"],
                "expected": c["expected"],
                "disposition": vd.disposition,
                "state": _state(vd.disposition),
                "detail": vd.detail,
            }
        )

    false_greens = [r for r in rows if r["state"] == "supported" and r["expected"] != "supported"]
    false_accusations = [
        r for r in rows if r["state"] == "contradicted" and r["expected"] != "contradicted"
    ]

    # Bar 3 = specificity: a refusal must name at least one figure from its own
    # statement, so it can never be the content-free wall. (A statement with no
    # figure at all is exempt: there is nothing to name.)
    nonspecific = []
    for r in rows:
        if r["state"] != "could_not_verify":
            continue
        claim_nums = set(re.findall(r"\d+", r["claim"]))
        detail_nums = set(re.findall(r"\d+", r["detail"]))
        if claim_nums and not (claim_nums & detail_nums):
            nonspecific.append(r)

    definite_expected = [r for r in rows if r["expected"] in ("supported", "contradicted")]
    definite_hit = [r for r in definite_expected if r["state"] == r["expected"]]
    definite_rate = (len(definite_hit) / len(definite_expected)) if definite_expected else 1.0

    # ---- scorecard ----
    print(f"\nCachet acceptance gate  |  corpus: {corpus_path}  ({len(rows)} cases)\n")
    print(f"  {'id':40} {'expected':16} {'engine':16} {'disposition'}")
    print(f"  {'-' * 40} {'-' * 16} {'-' * 16} {'-' * 24}")
    for r in rows:
        mark = (
            "ok"
            if (
                r["state"] == r["expected"]
                or (r["expected"] == "could_not_verify" and r["state"] == "could_not_verify")
            )
            else "XX"
        )
        print(f"  {r['id']:40} {r['expected']:16} {r['state']:16} {r['disposition']}  [{mark}]")

    b1 = not false_greens
    b2 = not false_accusations
    b3 = not nonspecific
    b4 = definite_rate >= bar
    print("\n  bars:")
    print(
        f"    1. zero false greens .......... {'PASS' if b1 else 'FAIL (' + str(len(false_greens)) + ')'}"
    )
    print(
        f"    2. zero false accusations ..... {'PASS' if b2 else 'FAIL (' + str(len(false_accusations)) + ')'}"
    )
    print(
        f"    3. refusals are specific ...... {'PASS' if b3 else 'FAIL (' + str(len(nonspecific)) + ' content-free)'}"
    )
    print(
        f"    4. definite-rate >= {bar:.2f} ...... {'PASS' if b4 else 'FAIL'}  ({len(definite_hit)}/{len(definite_expected)} = {definite_rate:.2f})"
    )

    if nonspecific:
        print("\n  content-free refusals (name no figure from their own statement):")
        for r in nonspecific:
            print(f"    - {r['id']}: {r['detail'][:110]}")

    passed = b1 and b2 and b3 and b4
    print(f"\n  RESULT: {'GREEN - demo bar met' if passed else 'RED - not demo-ready'}\n")
    return 0 if passed else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    default_corpus = (
        Path(__file__).resolve().parents[1] / "evals" / "cachet_acceptance" / "corpus.jsonl"
    )
    ap.add_argument("--corpus", type=Path, default=default_corpus)
    ap.add_argument("--bar", type=float, default=0.70)
    ap.add_argument(
        "--labeler",
        choices=("off", "regex"),
        default="off",
        help="subject labeler mode; 'regex' exercises the subject-bound percent/polarity path",
    )
    args = ap.parse_args()
    # get_subject_labeler() reads CARREL_SUBJECT_LABELER per call, so setting it here
    # is enough to flip the whole run between the figure-scope-out path and the labeled
    # path. 'off' clears it so the run matches the shipped default exactly.
    if args.labeler == "off":
        os.environ.pop("CARREL_SUBJECT_LABELER", None)
    else:
        os.environ["CARREL_SUBJECT_LABELER"] = args.labeler
    return run(args.corpus, args.bar)


if __name__ == "__main__":
    raise SystemExit(main())
