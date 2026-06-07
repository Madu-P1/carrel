"""PR-5 (T1 recall tier, ADR-0012): the calibration gate.

The gate keeps T1 dark until it passes on a labeled held-out corpus. These tests lock the
two modes (dark-guard vs --fail-on-gate), every blocking error (B1-B8), the vacuous-pass
floor, the sanity cap, a synthetic PASS, and the gate-pass artifact's five hashes. No
corpus or model is involved: the gate is a pure metric over files.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from benchmarks import t1_calibration as gate
from benchmarks.t1_calibration import MIN_AFFIRMATIVES


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _write_json(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj), encoding="utf-8")


def _corpus(n: int, *, surface: str = "litigator", gold: str = "support") -> list[dict]:
    return [
        {
            "id": f"c{i}",
            "surface": surface,
            "doc": f"d{i}",
            "sentence": "a draft sentence",
            "clause": "a source clause",
            "gold_label": gold,
        }
        for i in range(n)
    ]


def _preds(n: int, *, surface: str = "litigator", predicted: str = "support") -> list[dict]:
    return [{"id": f"c{i}", "surface": surface, "predicted": predicted} for i in range(n)]


class CalibrationGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.thresholds = self.dir / "thresholds.json"
        self.corpus = self.dir / "test.jsonl"
        self.preds = self.dir / "predictions.jsonl"
        self.manifest = self.dir / "manifest.json"
        self.gate_pass = self.dir / "gate-pass.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self, *, fail_on_gate: bool = True, baseline: Path | None = None):
        return gate.run_gate(
            thresholds_path=self.thresholds,
            corpus_path=self.corpus,
            predictions_path=self.preds,
            manifest_path=self.manifest,
            baseline_path=baseline,
            gate_pass_path=self.gate_pass,
            fail_on_gate=fail_on_gate,
        )

    def _complete_thresholds(self, ceiling: float = 0.02, surfaces=("litigator",)) -> None:
        _write_json(
            self.thresholds,
            {
                "schema_version": 1,
                "threshold_epsilon": 80.0,
                "rank_cutoff": 3,
                "far_ceiling": {s: ceiling for s in surfaces},
            },
        )

    # --- modes ---

    def test_dark_default_passes_when_thresholds_null_and_no_artifact(self) -> None:
        _write_json(
            self.thresholds, {"threshold_epsilon": None, "far_ceiling": {"litigator": None}}
        )
        result = self._run(fail_on_gate=False)
        self.assertTrue(result.passed)
        self.assertTrue(result.dark)

    def test_fail_on_gate_with_no_corpus_trips_loudly(self) -> None:
        _write_json(
            self.thresholds, {"threshold_epsilon": None, "far_ceiling": {"litigator": None}}
        )
        result = self._run(fail_on_gate=True)
        self.assertFalse(result.passed)
        joined = " ".join(result.blocking_errors)
        self.assertIn("B1", joined)  # null thresholds
        self.assertIn("B2", joined)  # no corpus
        self.assertIn("B3", joined)  # no predictions

    # --- blocking errors ---

    def test_b6_ceiling_above_sanity_cap_is_blocking(self) -> None:
        self.assertTrue(
            any(
                "B6" in e
                for e in gate.check_thresholds(
                    {"threshold_epsilon": 80.0, "rank_cutoff": 3, "far_ceiling": {"litigator": 0.2}}
                )
            )
        )

    def test_b5_corpus_schema_violation(self) -> None:
        errs = gate.validate_corpus([{"id": "c0", "surface": "litigator"}])  # missing fields
        self.assertTrue(any("B5" in e for e in errs))

    def test_b7_prediction_misalignment(self) -> None:
        corpus = _corpus(2)
        preds = [{"id": "c0", "surface": "litigator", "predicted": "support"}]  # missing c1
        self.assertTrue(any("B7" in e for e in gate.validate_predictions(preds, corpus)))

    def test_b8_split_leakage(self) -> None:
        errs = gate.check_split_leakage({"splits": {"train": ["d1", "d2"], "test": ["d2"]}})
        self.assertTrue(any("B8" in e for e in errs))

    def test_b4_vacuous_pass_is_blocking(self) -> None:
        # A handful of perfect affirmatives must NOT pass: 0/0 or a tiny denominator is
        # not certifiable. Below the floor -> B4.
        self._complete_thresholds()
        few = max(1, MIN_AFFIRMATIVES // 6)
        _write_jsonl(self.corpus, _corpus(few))
        _write_jsonl(self.preds, _preds(few))
        result = self._run()
        self.assertFalse(result.passed)
        self.assertTrue(any("B4" in e for e in result.blocking_errors))

    # --- FAR + pass ---

    def test_passing_gate_writes_nothing_by_itself_but_reports_pass(self) -> None:
        self._complete_thresholds(ceiling=0.05)
        _write_jsonl(self.corpus, _corpus(MIN_AFFIRMATIVES))
        _write_jsonl(self.preds, _preds(MIN_AFFIRMATIVES))  # all correct support -> FAR 0
        result = self._run()
        self.assertTrue(result.passed, result.blocking_errors)
        self.assertEqual(0.0, result.far_by_surface["litigator"])

    def test_far_over_ceiling_fails(self) -> None:
        self._complete_thresholds(ceiling=0.02)
        corpus = _corpus(MIN_AFFIRMATIVES, gold="support")
        # 5 of the affirmatives are wrong (gold contradict) -> FAR ~0.167 > 0.02.
        for row in corpus[:5]:
            row["gold_label"] = "contradict"
        _write_jsonl(self.corpus, corpus)
        _write_jsonl(self.preds, _preds(MIN_AFFIRMATIVES, predicted="support"))
        result = self._run()
        self.assertFalse(result.passed)
        self.assertTrue(any("exceeds its ceiling" in e for e in result.blocking_errors))

    def test_compute_far_counts_only_affirmatives(self) -> None:
        corpus = [
            {"id": "a", "surface": "contract", "gold_label": "support"},
            {"id": "b", "surface": "contract", "gold_label": "contradict"},
            {"id": "c", "surface": "contract", "gold_label": "support"},
            {"id": "d", "surface": "contract", "gold_label": "support"},
        ]
        preds = [
            {"id": "a", "predicted": "support"},  # correct affirmative
            {"id": "b", "predicted": "support"},  # FALSE affirmative (gold contradict)
            {"id": "c", "predicted": "refused"},  # not an affirmative
            {"id": "d", "predicted": "support"},  # correct affirmative
        ]
        stats = gate.compute_far(corpus, preds)["contract"]
        self.assertEqual(3, stats["affirmatives"])
        self.assertEqual(1, stats["false_affirmatives"])
        self.assertAlmostEqual(1 / 3, stats["far"], places=4)

    def test_gate_pass_artifact_records_input_hashes_and_interlock(self) -> None:
        self._complete_thresholds()
        gate.write_gate_pass(
            model_sha256="deadbeef",
            feature_version="feat-v1",
            thresholds_path=self.thresholds,
            corpus_path=self.corpus,  # missing file -> hash None, still recorded
            predictions_path=self.preds,  # missing file -> hash None, still recorded
            guideline_path=self.dir / "GUIDELINE.md",
            gate_pass_path=self.gate_pass,
            far_by_surface={"litigator": 0.0},
        )
        artifact = json.loads(self.gate_pass.read_text(encoding="utf-8"))
        for key in (
            "corpus_sha256",
            "predictions_sha256",
            "thresholds_sha256",
            "guideline_version",
            "model_sha256",
            "feature_version",
            "best_of_k_enforced",
        ):
            self.assertIn(key, artifact)
        self.assertEqual("deadbeef", artifact["model_sha256"])
        self.assertEqual("feat-v1", artifact["feature_version"])
        # The interlock ships False: an artifact minted today cannot enable T1 at runtime.
        self.assertFalse(artifact["best_of_k_enforced"])


if __name__ == "__main__":
    unittest.main()
