"""T1 calibration gate (ADR-0012): the false-affirmative-rate gate that keeps the T1
recall tier dark until it is proven safe on a labeled, held-out legal corpus.

T1 may only ever be enabled when this gate passes. The gate is a pure metric over two
files plus operator-owned thresholds, modeled on ``benchmarks/phase0.py``: it does NOT
run the NLI model (that happens in the corpus-blocked tuning step), so it stays fast and
deterministic in CI. It reads:

  - the gold corpus test split (``data/calibration/corpus/test.jsonl``), each row
    ``{id, surface, doc, sentence, clause, gold_label}``;
  - the model's predictions on that split (``predictions.jsonl``), each row
    ``{id, surface, predicted}`` where ``predicted`` is support / contradict / refused;
  - operator thresholds (``thresholds.json``): the verdict confidence epsilon and a
    per-surface false-affirmative ceiling.

It computes, per surface, the **false-affirmative rate** = (affirmative verdicts whose
gold disagrees) / (affirmative verdicts), and PASSES only when every surface's FAR is at
or under its ceiling, the affirmative count clears a vacuous-pass floor, and (if a
baseline exists) FAR has not regressed. On pass it writes ``gate-pass.json`` with five
hashes (corpus, thresholds, guideline, model, features); the runtime ``t1_permitted()``
guard re-checks those hashes, so a stale or forged artifact can never enable T1.

Two modes:
  - default (CI guard): if T1 is DARK (thresholds unset and no gate-pass artifact) the
    gate is not required and exits 0. This keeps CI green through the dark scaffold while
    still failing loudly the moment someone sets thresholds to enable T1 without a
    passing corpus.
  - ``--fail-on-gate`` (the operator's enabling run / the unit tests): always runs the
    gate strictly, so a missing corpus or null thresholds exits 1.

Blocking errors (B1-B8): B1 thresholds missing/null; B2 corpus missing/empty; B3
predictions missing/empty; B4 vacuous pass (affirmatives below the floor; 0/0 is not a
pass); B5 corpus schema violation; B6 a ceiling above the sanity cap (no loose ceiling
for demo optics); B7 prediction/corpus id misalignment; B8 document-level split leakage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# One labeled / prediction / threshold record. The gate reads JSON, so values are
# arbitrary; the keys the gate relies on are validated by the B-checks, not the type.
JsonDict = dict[str, Any]

ROOT_DIR = Path(__file__).resolve().parent.parent
CALIBRATION_DIR = ROOT_DIR / "data" / "calibration"
DEFAULT_THRESHOLDS = CALIBRATION_DIR / "thresholds.json"
DEFAULT_CORPUS = CALIBRATION_DIR / "corpus" / "test.jsonl"
DEFAULT_PREDICTIONS = CALIBRATION_DIR / "predictions.jsonl"
DEFAULT_MANIFEST = CALIBRATION_DIR / "manifest.json"
DEFAULT_GATE_PASS = CALIBRATION_DIR / "gate-pass.json"
DEFAULT_GUIDELINE = CALIBRATION_DIR / "GUIDELINE-v1.md"

# One confident wrong T1 verdict in front of a lawyer is product-ending, so the
# affirmative-verdict error ceiling stays near zero. A committed far_ceiling above this
# is itself a blocking error: the operator cannot loosen it for demo optics.
FAR_CEILING_SANITY_CAP = 0.05
# A gate computed over too few affirmative verdicts is not a pass (0/0 would sail under
# any ceiling). Each gated surface's affirmative count must clear this floor.
MIN_AFFIRMATIVES = 30

# Fail-closed interlock for the best-of-K equivalence (ADR-0012 "Implementation notes").
# The runtime runs best-of-K, but this gate measures a per-pair FAR and does NOT yet perform
# the best-of-K reduction itself, so a top-1 predictions file would certify a FAR the runtime
# exceeds. Until that reduction lands (the enable-PR checklist), the gate stamps False into
# every artifact and services.legal.t1_gate.t1_permitted() REFUSES to enable T1 on a False
# artifact. Flip to True ONLY in the PR that makes the gate reduce best-of-K and adds a test
# that a top-1 / wrong-K predictions file fails. This is the one code-enforced reason T1
# cannot go live yet; do not flip it to make a demo work.
BEST_OF_K_GATE_ENFORCED = False

AFFIRMATIVE = frozenset({"support", "contradict"})
GOLD_LABELS = frozenset({"support", "contradict", "cannot_determine"})
PREDICTED_LABELS = frozenset({"support", "contradict", "refused"})
_CORPUS_FIELDS = ("id", "surface", "doc", "sentence", "clause", "gold_label")


@dataclass
class GateResult:
    passed: bool
    dark: bool
    blocking_errors: list[str] = field(default_factory=list)
    far_by_surface: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _read_jsonl(path: Path) -> list[JsonDict] | None:
    if not path.exists():
        return None
    rows: list[JsonDict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    except (json.JSONDecodeError, OSError):
        return None
    return rows


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def thresholds_complete(thresholds: JsonDict | None) -> bool:
    """True only when the operator has set every threshold the gate needs."""
    if not isinstance(thresholds, dict):
        return False
    if thresholds.get("threshold_epsilon") is None:
        return False
    # rank_cutoff is the top-K candidacy floor the runtime runs best-of. It rides this
    # file's hash, so requiring it here is what makes the gate certify the same K the
    # runtime uses: a gate that passed without it would measure an undefined strategy.
    if thresholds.get("rank_cutoff") is None:
        return False
    ceilings = thresholds.get("far_ceiling")
    if not isinstance(ceilings, dict) or not ceilings:
        return False
    return all(v is not None for v in ceilings.values())


def is_enabled(thresholds: JsonDict | None, gate_pass_path: Path) -> bool:
    """T1 is in scope for gating once the operator has set thresholds or a gate-pass
    artifact exists. Until then it is dark by construction."""
    return thresholds_complete(thresholds) or gate_pass_path.exists()


def check_thresholds(thresholds: JsonDict | None) -> list[str]:
    errors: list[str] = []
    if not thresholds_complete(thresholds):
        errors.append("B1: thresholds.json is missing or carries null placeholders.")
        return errors
    assert isinstance(thresholds, dict)  # narrowed by thresholds_complete
    for surface, ceiling in thresholds["far_ceiling"].items():
        if not isinstance(ceiling, (int, float)) or ceiling > FAR_CEILING_SANITY_CAP:
            errors.append(
                f"B6: far_ceiling[{surface}]={ceiling} exceeds the sanity cap "
                f"{FAR_CEILING_SANITY_CAP}; a loose ceiling cannot be committed."
            )
    return errors


def validate_corpus(rows: list[JsonDict] | None) -> list[str]:
    if not rows:
        return ["B2: the corpus test split is missing or empty."]
    errors: list[str] = []
    for i, row in enumerate(rows):
        missing = [f for f in _CORPUS_FIELDS if f not in row]
        if missing:
            errors.append(f"B5: corpus row {i} is missing fields {missing}.")
            continue
        if row["gold_label"] not in GOLD_LABELS:
            errors.append(f"B5: corpus row {i} has invalid gold_label {row['gold_label']!r}.")
    return errors


def validate_predictions(preds: list[JsonDict] | None, corpus: list[JsonDict] | None) -> list[str]:
    if not preds:
        return ["B3: the predictions file is missing or empty."]
    errors: list[str] = []
    for i, row in enumerate(preds):
        if "id" not in row or "predicted" not in row:
            errors.append(f"B7: prediction row {i} is missing id/predicted.")
            continue
        if row["predicted"] not in PREDICTED_LABELS:
            errors.append(f"B7: prediction row {i} has invalid predicted {row['predicted']!r}.")
    if corpus:
        corpus_ids = {r.get("id") for r in corpus}
        pred_ids = {r.get("id") for r in preds if "id" in r}
        if corpus_ids != pred_ids:
            errors.append("B7: prediction ids do not align 1:1 with the corpus ids.")
    return errors


def check_split_leakage(manifest: JsonDict | None) -> list[str]:
    """B8: a document must live in exactly one split. ``manifest['splits']`` maps each
    split name to a list of doc ids; any doc in more than one split is leakage."""
    if not isinstance(manifest, dict):
        return []  # no manifest provided; corpus-only runs are checked by B2/B5
    splits = manifest.get("splits")
    if not isinstance(splits, dict):
        return []
    seen: dict[str, str] = {}
    errors: list[str] = []
    for split_name, docs in splits.items():
        for doc in docs or []:
            if doc in seen and seen[doc] != split_name:
                errors.append(
                    f"B8: document {doc!r} appears in both {seen[doc]!r} and {split_name!r} splits."
                )
            seen[doc] = split_name
    return errors


def compute_far(corpus: list[JsonDict], preds: list[JsonDict]) -> dict[str, JsonDict]:
    """Per-surface affirmative count, false-affirmative count, and rate.

    An affirmative is a support/contradict prediction; it is a false affirmative when the
    gold label disagrees. ``refused`` predictions are not affirmatives and never count.
    """
    gold = {r["id"]: r for r in corpus}
    stats: dict[str, JsonDict] = {}
    for pred in preds:
        row = gold.get(pred.get("id"))
        if row is None:
            continue
        surface = row.get("surface", "unknown")
        bucket = stats.setdefault(surface, {"affirmatives": 0, "false_affirmatives": 0})
        predicted = pred.get("predicted")
        if predicted in AFFIRMATIVE:
            bucket["affirmatives"] += 1
            if row.get("gold_label") != predicted:
                bucket["false_affirmatives"] += 1
    for bucket in stats.values():
        n = bucket["affirmatives"]
        bucket["far"] = bucket["false_affirmatives"] / n if n else 0.0
    return stats


def run_gate(
    *,
    thresholds_path: Path = DEFAULT_THRESHOLDS,
    corpus_path: Path = DEFAULT_CORPUS,
    predictions_path: Path = DEFAULT_PREDICTIONS,
    manifest_path: Path = DEFAULT_MANIFEST,
    baseline_path: Path | None = None,
    gate_pass_path: Path = DEFAULT_GATE_PASS,
    fail_on_gate: bool = False,
) -> GateResult:
    thresholds = _read_json(thresholds_path)
    thresholds = thresholds if isinstance(thresholds, dict) else None

    if not fail_on_gate and not is_enabled(thresholds, gate_pass_path):
        return GateResult(
            passed=True,
            dark=True,
            notes=["T1 dark: thresholds unset and no gate-pass artifact; gate not required."],
        )

    errors: list[str] = []
    errors += check_thresholds(thresholds)
    corpus = _read_jsonl(corpus_path)
    errors += validate_corpus(corpus)
    preds = _read_jsonl(predictions_path)
    errors += validate_predictions(preds, corpus)
    manifest = _read_json(manifest_path)
    errors += check_split_leakage(manifest if isinstance(manifest, dict) else None)

    # Without clean inputs the rate is meaningless; fail on the blocking set alone.
    if errors:
        return GateResult(passed=False, dark=False, blocking_errors=errors)

    assert thresholds is not None and corpus is not None and preds is not None
    stats = compute_far(corpus, preds)
    far_by_surface = {s: round(v["far"], 6) for s, v in stats.items()}
    ceilings = thresholds["far_ceiling"]
    baseline = _read_json(baseline_path) if baseline_path else None
    baseline_far = baseline.get("far_by_surface", {}) if isinstance(baseline, dict) else {}

    for surface, ceiling in ceilings.items():
        bucket = stats.get(surface, {"affirmatives": 0, "far": 0.0})
        if bucket["affirmatives"] < MIN_AFFIRMATIVES:
            errors.append(
                f"B4: surface {surface!r} has {bucket['affirmatives']} affirmative verdicts, "
                f"below the {MIN_AFFIRMATIVES} floor; a near-empty denominator is not a pass."
            )
            continue
        if bucket["far"] > ceiling:
            errors.append(
                f"surface {surface!r} FAR {bucket['far']:.4f} exceeds its ceiling {ceiling}."
            )
        prior = baseline_far.get(surface)
        if isinstance(prior, (int, float)) and bucket["far"] > prior:
            errors.append(
                f"surface {surface!r} FAR {bucket['far']:.4f} regressed against baseline {prior}."
            )

    return GateResult(
        passed=not errors, dark=False, blocking_errors=errors, far_by_surface=far_by_surface
    )


def write_gate_pass(
    *,
    model_sha256: str,
    feature_version: str,
    thresholds_path: Path = DEFAULT_THRESHOLDS,
    corpus_path: Path = DEFAULT_CORPUS,
    predictions_path: Path = DEFAULT_PREDICTIONS,
    guideline_path: Path = DEFAULT_GUIDELINE,
    gate_pass_path: Path = DEFAULT_GATE_PASS,
    far_by_surface: dict[str, float] | None = None,
) -> Path:
    """Write the gate-pass artifact the runtime guard re-checks. Caller writes this ONLY
    after a passing run; the hashes bind the pass to an exact model/corpus/predictions/
    threshold tuple, so any later drift invalidates it. ``best_of_k_enforced`` carries the
    fail-closed interlock (see BEST_OF_K_GATE_ENFORCED): while False the runtime refuses to
    enable T1, so an artifact minted by this code today cannot turn the tier on."""
    artifact = {
        "passed": True,
        "corpus_sha256": _sha256_file(corpus_path),
        "predictions_sha256": _sha256_file(predictions_path),
        "thresholds_sha256": _sha256_file(thresholds_path),
        "guideline_version": _sha256_file(guideline_path),
        "model_sha256": model_sha256,
        "feature_version": feature_version,
        "best_of_k_enforced": BEST_OF_K_GATE_ENFORCED,
        "far_by_surface": far_by_surface or {},
    }
    gate_pass_path.parent.mkdir(parents=True, exist_ok=True)
    gate_pass_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    return gate_pass_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="T1 calibration gate (ADR-0012).")
    parser.add_argument("--thresholds", type=Path, default=DEFAULT_THRESHOLDS)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--baseline", type=Path, default=None)
    parser.add_argument(
        "--fail-on-gate",
        action="store_true",
        help="Run the gate strictly even when T1 is dark; exit 1 unless it fully passes.",
    )
    return parser.parse_args(argv)


def main_cli(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_gate(
        thresholds_path=args.thresholds,
        corpus_path=args.corpus,
        predictions_path=args.predictions,
        manifest_path=args.manifest,
        baseline_path=args.baseline,
        fail_on_gate=args.fail_on_gate,
    )
    if result.dark:
        print("T1 calibration gate: DARK (not required). " + "; ".join(result.notes))
        return 0
    if result.passed:
        print("T1 calibration gate: PASS. " + json.dumps(result.far_by_surface))
        return 0
    print("T1 calibration gate: FAIL.")
    for err in result.blocking_errors:
        print(f"  - {err}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main_cli())
