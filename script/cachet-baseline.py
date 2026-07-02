#!/usr/bin/env python
"""Cachet deterministic-engine baseline: the committed, byte-reproducible ledger.

Measurement only. This script touches NO engine module and re-implements NONE of
the verdict logic: it imports ``script/cachet-acceptance.py`` and reuses that
file's exact engine entry (``verify_claim_against_clause``) and disposition ->
state mapper (``_state``). If the acceptance gate's verdict machinery ever moves,
this baseline moves with it automatically.

It runs the deterministic clause-level verifier over the six FROZEN acceptance
corpora, in a fixed order, and emits a single machine-checkable artifact
(default ``evals/cachet_acceptance/baseline.json``) recording:

  (a) per-corpus auto-resolution: ``total`` cases, ``definite`` verdicts (the
      engine reached supported/contradicted rather than refusing), and
      ``definite_rate`` = definite / total.
  (b) ``catastrophic_errors``: a flat list, in corpus-then-line order, of every
      catastrophic disagreement, each as ``{corpus, line_id, engine_verdict,
      gold_label, kind}``. ``kind`` is exactly:
        - "false_green"      when state == supported AND gold != supported
                             (the engine vouched for a non-supported claim), and
        - "false_accusation" when state == contradicted AND gold == supported
                             (the engine accused a clean, supported claim).
      Both classifications use the state enum from cachet-acceptance.py
      (supported / contradicted / could_not_verify), never a hardcoded guess.
  (c) ``totals``: {false_greens, false_accusations}.

Determinism is load-bearing: the engine is deterministic, so this JSON must
regenerate byte-for-byte. The output carries NO timestamp, NO absolute path, NO
host / random / run-id field; corpora iterate in the fixed order below and lines
in file order; every float is rounded to 6 places; the file is written with
``json.dump(..., sort_keys=True, indent=2, ensure_ascii=False)`` plus a trailing
newline. The subject labeler is pinned to the shipped default ("off") regardless
of ambient env so an inherited ``CARREL_SUBJECT_LABELER`` cannot perturb the run.

Usage:
    ./.venv/bin/python script/cachet-baseline.py [--out PATH]

Verify (from the product root):
    ./.venv/bin/python script/cachet-baseline.py --out /tmp/cachet-baseline-check.json \\
      && cmp /tmp/cachet-baseline-check.json evals/cachet_acceptance/baseline.json \\
      && echo CACHET_BASELINE_REPRODUCIBLE
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

# The fixed, ordered acceptance corpora. Order is part of the artifact contract:
# the per-corpus list and the catastrophic_errors flat list both follow it.
_CORPORA_ORDER = [
    "corpus",
    "contract_corpus",
    "collision_corpus",
    "injection_corpus",
    "polarity_collision_corpus",
    "recall_corpus",
]

_CORPUS_DIR = _ROOT / "evals" / "cachet_acceptance"


def _load_acceptance():
    """Import script/cachet-acceptance.py by path (its name has a hyphen).

    Importing only runs module-level code (imports + constant/function defs);
    ``main()`` stays behind the ``__name__ == "__main__"`` guard, so nothing
    executes here. We reuse ``verify_claim_against_clause`` (the engine entry the
    acceptance gate already binds) and ``_state`` (its disposition -> state map).
    """
    path = Path(__file__).resolve().parent / "cachet-acceptance.py"
    spec = importlib.util.spec_from_file_location("cachet_acceptance", path)
    if spec is None or spec.loader is None:  # pragma: no cover - import wiring
        raise RuntimeError(f"could not load acceptance module at {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_cases(corpus_path: Path):
    """Reuse the acceptance gate's exact corpus-loading: one JSON object per
    non-blank line."""
    return [
        json.loads(line)
        for line in corpus_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def build_baseline(acc) -> dict:
    """Run the engine over every corpus and assemble the baseline payload."""
    corpora_rows = []
    catastrophic_errors = []

    for name in _CORPORA_ORDER:
        corpus_path = _CORPUS_DIR / f"{name}.jsonl"
        cases = _load_cases(corpus_path)

        total = len(cases)
        definite = 0

        for idx, c in enumerate(cases):
            # Field names discovered from cachet-acceptance.py: gold label is
            # "expected", id field is "id". Per spec, fall back to the 0-based
            # line index when a line carries no explicit id.
            line_id = c.get("id", idx)
            gold_label = c["expected"]

            vd = acc.verify_claim_against_clause(c["claim"], c["clause"])
            engine_verdict = acc._state(vd.disposition)

            if engine_verdict in ("supported", "contradicted"):
                definite += 1

            # Catastrophic-error classification using the state enum from the
            # acceptance gate (supported / contradicted / could_not_verify).
            kind = None
            if engine_verdict == "supported" and gold_label != "supported":
                kind = "false_green"
            elif engine_verdict == "contradicted" and gold_label == "supported":
                kind = "false_accusation"

            if kind is not None:
                catastrophic_errors.append(
                    {
                        "corpus": name,
                        "line_id": line_id,
                        "engine_verdict": engine_verdict,
                        "gold_label": gold_label,
                        "kind": kind,
                    }
                )

        definite_rate = round(definite / total, 6) if total else 0.0
        corpora_rows.append(
            {
                "name": name,
                "total": total,
                "definite": definite,
                "definite_rate": definite_rate,
            }
        )

    totals = {
        "false_greens": sum(1 for e in catastrophic_errors if e["kind"] == "false_green"),
        "false_accusations": sum(1 for e in catastrophic_errors if e["kind"] == "false_accusation"),
    }

    return {
        "corpora": corpora_rows,
        "catastrophic_errors": catastrophic_errors,
        "totals": totals,
    }


def _summary_lines(baseline: dict) -> list[str]:
    lines = ["Cachet engine baseline", "", "definite_rate (auto-resolution) by corpus:"]
    for row in baseline["corpora"]:
        lines.append(
            f"  {row['name']:28} {row['definite_rate']:.6f}  ({row['definite']}/{row['total']})"
        )
    t = baseline["totals"]
    lines.append("")
    lines.append(f"false_greens:      {t['false_greens']}")
    lines.append(f"false_accusations: {t['false_accusations']}")
    return lines


def _write_json(baseline: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(baseline, f, sort_keys=True, indent=2, ensure_ascii=False)
        f.write("\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Emit the Cachet engine baseline JSON.")
    ap.add_argument(
        "--out",
        type=Path,
        default=_CORPUS_DIR / "baseline.json",
        help="output path (default: evals/cachet_acceptance/baseline.json)",
    )
    args = ap.parse_args()

    # Pin the subject labeler to the shipped default so the baseline is
    # reproducible regardless of an inherited CARREL_SUBJECT_LABELER. This
    # mirrors cachet-acceptance.py's default ("off") path.
    os.environ.pop("CARREL_SUBJECT_LABELER", None)

    acc = _load_acceptance()
    baseline = build_baseline(acc)

    _write_json(baseline, args.out)

    # Human-readable companion: a sibling .md next to the JSON, plus the same
    # summary to stderr. The machine check (byte-identity of the JSON) is the
    # sole gate; this is for reading only.
    summary = "\n".join(_summary_lines(baseline)) + "\n"
    md_path = args.out.with_suffix(".md")
    md_path.write_text(summary, encoding="utf-8")
    sys.stderr.write(summary)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
