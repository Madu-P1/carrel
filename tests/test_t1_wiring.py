"""PR-6 (T1 recall tier, ADR-0012): wiring the local NLI selector into the verify path.

Covers the three surfaces this PR adds, all DARK by default:
  - the runtime guard ``t1_gate.t1_permitted`` (fail-closed: opt-in env AND a still-valid
    gate-pass artifact) and ``load_runtime_thresholds``;
  - Site A (``deterministic_envelope``): an anchor-free contract claim gets a local-model
    assessment ONLY when permitted, and the verdict never changes;
  - Site B (``verify._claim_dict_to_verdict``): a ``t1_assessment`` maps onto the
    ``assessed_*`` card fields, strictly subordinate to an unknown could-not-check verdict.

No model loads (the selector is exercised through a stub scorer) and no network is opened.
"""

from __future__ import annotations

import hashlib
import math
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import db
from services import verify as verify_service
from services.ingestion.persistence import embed_and_index_nodes, insert_typed_nodes
from services.ingestion.typed_walker import TypedNode
from services.legal import deterministic_envelope as det_env
from services.legal import t1_gate
from services.legal.t1_gate import FEATURE_VERSION
from services.verify import _claim_dict_to_verdict

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_SOURCE = REPO_ROOT / "migrations"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _StubScorer:
    """Fixed probabilities; never loads a model."""

    def __init__(self, probs: dict[str, float]) -> None:
        self._probs = probs

    def score(self, premise: str, hypothesis: str) -> dict[str, float]:
        return dict(self._probs)


class GateGuardTests(unittest.TestCase):
    """t1_permitted is fail-closed and re-validates the artifact against the live files."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        d = Path(self._tmp.name)
        self.thresholds = d / "thresholds.json"
        self.corpus = d / "test.jsonl"
        self.guideline = d / "GUIDELINE.md"
        self.gate_pass = d / "gate-pass.json"
        self.thresholds.write_text(
            '{"threshold_epsilon": 80.0, "rank_cutoff": 3, "far_ceiling": {"contract": 0.02}}',
            encoding="utf-8",
        )
        self.corpus.write_text('{"id": "c0"}\n', encoding="utf-8")
        self.guideline.write_text("# guideline v1\n", encoding="utf-8")
        for attr, path in (
            ("_THRESHOLDS", self.thresholds),
            ("_CORPUS", self.corpus),
            ("_GUIDELINE", self.guideline),
            ("_GATE_PASS", self.gate_pass),
        ):
            patcher = mock.patch.object(t1_gate, attr, path)
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write_artifact(self, **overrides: object) -> None:
        import json

        artifact = {
            "passed": True,
            "corpus_sha256": _sha(self.corpus),
            "thresholds_sha256": _sha(self.thresholds),
            "guideline_version": _sha(self.guideline),
            "model_sha256": "deadbeef",
            "feature_version": FEATURE_VERSION,
            # Simulates a future enable-PR artifact where best-of-K is gate-enforced; today's
            # write_gate_pass stamps False, which the interlock test below exercises.
            "best_of_k_enforced": True,
        }
        artifact.update(overrides)
        self.gate_pass.write_text(json.dumps(artifact), encoding="utf-8")

    def test_dark_when_env_unset(self) -> None:
        self._write_artifact()
        with mock.patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("CACHET_T1_RECALL", None)
            self.assertFalse(t1_gate.t1_permitted())

    def test_dark_when_opted_in_but_no_artifact(self) -> None:
        with mock.patch.dict("os.environ", {"CACHET_T1_RECALL": "1"}, clear=False):
            self.assertFalse(t1_gate.t1_permitted())

    def test_permitted_when_opted_in_and_artifact_valid(self) -> None:
        self._write_artifact()
        with mock.patch.dict("os.environ", {"CACHET_T1_RECALL": "1"}, clear=False):
            self.assertTrue(t1_gate.t1_permitted())

    def test_fail_closed_on_thresholds_drift(self) -> None:
        self._write_artifact()
        # Operator widens thresholds AFTER the gate passed: the recorded hash no longer
        # matches, so the pass is invalid.
        self.thresholds.write_text(
            '{"threshold_epsilon": 1.0, "rank_cutoff": 9, "far_ceiling": {"contract": 0.99}}',
            encoding="utf-8",
        )
        with mock.patch.dict("os.environ", {"CACHET_T1_RECALL": "1"}, clear=False):
            self.assertFalse(t1_gate.t1_permitted())

    def test_fail_closed_on_stale_feature_version(self) -> None:
        self._write_artifact(feature_version="t1-v0-old")
        with mock.patch.dict("os.environ", {"CACHET_T1_RECALL": "1"}, clear=False):
            self.assertFalse(t1_gate.t1_permitted())

    def test_fail_closed_when_passed_flag_false(self) -> None:
        self._write_artifact(passed=False)
        with mock.patch.dict("os.environ", {"CACHET_T1_RECALL": "1"}, clear=False):
            self.assertFalse(t1_gate.t1_permitted())

    def test_fail_closed_until_best_of_k_enforced(self) -> None:
        # The spine interlock: even a fully valid artifact must not enable T1 while the
        # gate has not mechanically enforced best-of-K. False and missing both fail closed.
        for value in (False, None):
            self._write_artifact(best_of_k_enforced=value)
            with mock.patch.dict("os.environ", {"CACHET_T1_RECALL": "1"}, clear=False):
                self.assertFalse(t1_gate.t1_permitted())

    def test_fail_closed_on_corrupt_artifact_never_raises(self) -> None:
        # A non-UTF-8 / partially-written artifact must resolve to dark, not raise
        # (UnicodeDecodeError is a ValueError, not an OSError): the "never raises" contract.
        self.gate_pass.write_bytes(b"\xff\xfe\x00not utf-8")
        with mock.patch.dict("os.environ", {"CACHET_T1_RECALL": "1"}, clear=False):
            self.assertFalse(t1_gate.t1_permitted())

    def test_load_runtime_thresholds_fail_closed_on_corrupt(self) -> None:
        self.thresholds.write_bytes(b"\xff\xfe\x00not utf-8")
        self.assertIsNone(t1_gate.load_runtime_thresholds())

    def test_load_runtime_thresholds_reads_values(self) -> None:
        self.assertEqual((80.0, 3), t1_gate.load_runtime_thresholds())

    def test_load_runtime_thresholds_none_when_unset(self) -> None:
        self.thresholds.write_text(
            '{"threshold_epsilon": null, "rank_cutoff": null, "far_ceiling": {}}',
            encoding="utf-8",
        )
        self.assertIsNone(t1_gate.load_runtime_thresholds())


class _DeterministicEmbedder:
    dim = 384

    def _vec(self, text: str) -> list[float]:
        tokens = [t.lower() for t in text.split() if t]
        if not tokens:
            return [0.0] * self.dim
        accum = [0.0] * self.dim
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            for i in range(self.dim):
                accum[i] += ((digest[i % len(digest)] / 255.0) * 2.0) - 1.0
        norm = math.sqrt(sum(v * v for v in accum)) or 1.0
        return [v / norm for v in accum]

    def embed_passages(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


def _node(order: int, text: str) -> TypedNode:
    return TypedNode(
        node_type="body",
        heading_path="Agreement",
        page=1,
        char_start=order * 200,
        char_end=order * 200 + len(text),
        verbatim_text=text,
        parent_block_id=None,
        reading_order=order,
    )


class SiteAEnvelopeTests(unittest.TestCase):
    """Site A: the anchor-free contract branch attaches an assessment only when permitted."""

    # A draft sentence with no surface anchor (no citation / money / date / party / quote).
    ANCHOR_FREE = "The supplier must behave reasonably in every circumstance."

    def setUp(self) -> None:
        self._original = (db.BASE_DIR, db.DATA_DIR, db.UPLOAD_DIR, db.DB_PATH, db.SCHEMA_PATH)
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        data_dir = root / "data"
        upload_dir = data_dir / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        (root / "schema.sql").write_text("-- test\n", encoding="utf-8")
        shutil.copytree(MIGRATIONS_SOURCE, root / "migrations", dirs_exist_ok=True)
        db.configure_paths(
            base_dir=root,
            data_dir=data_dir,
            upload_dir=upload_dir,
            db_path=data_dir / "test.db",
            schema_path=root / "schema.sql",
        )
        self._conn = db.get_db()
        db.apply_migrations(self._conn)
        self._embedder = _DeterministicEmbedder()
        self._conn.execute(
            "INSERT INTO documents (id, filename, file_type, status, source_kind, subject_name) "
            "VALUES ('contract-1', 'msa.pdf', 'pdf', 'ready', 'upload', 'Agreement')"
        )
        nodes = [
            _node(0, "The parties shall cooperate in good faith on all matters."),
            _node(1, "Each party will use commercially reasonable efforts to perform."),
        ]
        ids = insert_typed_nodes(self._conn, "contract-1", nodes)
        embed_and_index_nodes(self._conn, nodes, ids, embedder=self._embedder)
        self._conn.commit()

    def tearDown(self) -> None:
        self._conn.close()
        self._tmp.cleanup()
        db.configure_paths(
            base_dir=self._original[0],
            data_dir=self._original[1],
            upload_dir=self._original[2],
            db_path=self._original[3],
            schema_path=self._original[4],
        )

    def _build(self) -> dict:
        return det_env.build_deterministic_envelope(
            self.ANCHOR_FREE, conn=self._conn, doc_ids=["contract-1"], embedder=self._embedder
        )

    def test_dark_by_default_no_assessment(self) -> None:
        # No env opt-in and no gate-pass artifact: the anchor-free claim stays UNTREATED
        # (no card, no assessed-tier provenance). T1 only promotes it to an assessed
        # could-not-check card when the gate is honestly open.
        env = self._build()
        claim = env["claims"][0]
        self.assertTrue(claim.get("untreated"))
        self.assertNotIn("could_not_check_reason", claim)
        self.assertNotIn("t1_assessment", claim)

    def test_permitted_attaches_assessment_without_changing_the_verdict(self) -> None:
        with (
            mock.patch.object(det_env, "t1_permitted", return_value=True),
            mock.patch.object(det_env, "load_runtime_thresholds", return_value=(70.0, 3)),
            mock.patch.object(
                det_env,
                "default_scorer",
                return_value=_StubScorer(
                    {"support": 0.9, "contradict": 0.05, "cannot_determine": 0.05}
                ),
            ),
        ):
            env = self._build()
        claim = env["claims"][0]
        self.assertIn("t1_assessment", claim)
        self.assertEqual("support", claim["t1_assessment"]["label"])
        self.assertAlmostEqual(90.0, claim["t1_assessment"]["confidence"], places=4)
        # End to end: the card carries assessed_* but the verdict is still unknown.
        card = verify_service._verify_result_from_envelope(
            self.ANCHOR_FREE, env, 0.0
        ).claim_verdicts[0]
        self.assertEqual("unknown", card.verdict)
        self.assertEqual("support", card.assessed_label)
        self.assertAlmostEqual(90.0, card.assessed_confidence or 0.0, places=4)

    def test_below_threshold_leaves_no_assessment(self) -> None:
        with (
            mock.patch.object(det_env, "t1_permitted", return_value=True),
            mock.patch.object(det_env, "load_runtime_thresholds", return_value=(70.0, 3)),
            mock.patch.object(
                det_env,
                "default_scorer",
                return_value=_StubScorer(
                    {"support": 0.55, "contradict": 0.25, "cannot_determine": 0.2}
                ),
            ),
        ):
            env = self._build()
        # argmax is support but under the 70 threshold -> stays untreated (no card),
        # no assessment.
        self.assertNotIn("t1_assessment", env["claims"][0])


class SiteBMappingTests(unittest.TestCase):
    """Site B: assessed_* is mapped only under an unknown could-not-check verdict."""

    def test_assessment_maps_onto_assessed_fields(self) -> None:
        claim = {
            "text": "The supplier must behave reasonably.",
            "citations": [],
            "case_verdicts": [],
            "could_not_check_reason": "No verifiable anchor was found.",
            "t1_assessment": {"label": "support", "confidence": 88.0, "model": "nli-x"},
        }
        card = _claim_dict_to_verdict(claim, 0)
        self.assertEqual("unknown", card.verdict)
        self.assertEqual("support", card.assessed_label)
        self.assertEqual(88.0, card.assessed_confidence)
        self.assertEqual("nli-x", card.assessed_model)

    def test_assessment_ignored_on_a_verified_card(self) -> None:
        # A stray assessment on a card that earns a T0 verdict must never override it:
        # the assessed_* fields stay None so a guess can't paint over a deterministic fact.
        claim = {
            "text": "Brown v. Board, 347 U.S. 483.",
            "citations": [{"chunk_index": 1}],
            "case_verdicts": [],
            "t1_assessment": {"label": "support", "confidence": 99.0, "model": "nli-x"},
        }
        card = _claim_dict_to_verdict(claim, 0)
        self.assertEqual("verified", card.verdict)
        self.assertIsNone(card.assessed_label)
        self.assertIsNone(card.assessed_confidence)

    def test_no_assessment_leaves_assessed_none(self) -> None:
        claim = {
            "text": "The supplier must behave reasonably.",
            "citations": [],
            "case_verdicts": [],
            "could_not_check_reason": "No verifiable anchor was found.",
        }
        card = _claim_dict_to_verdict(claim, 0)
        self.assertEqual("unknown", card.verdict)
        self.assertIsNone(card.assessed_label)
        self.assertIsNone(card.assessed_confidence)
        self.assertIsNone(card.assessed_model)


if __name__ == "__main__":
    unittest.main()
