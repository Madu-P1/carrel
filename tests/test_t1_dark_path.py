"""PR-7 (T1 recall tier, ADR-0012): the dark-path integration, end to end.

PR-6 wired the selector behind ``t1_permitted()`` and tested it with the guard
*stubbed* (``mock.patch.object(det_env, "t1_permitted", return_value=True)``). This
suite instead drives the **real** guard through its real inputs - the
``CACHET_T1_RECALL`` env flag and a synthetic ``gate-pass.json`` whose hashes match
the (patched) calibration files on disk - so the gate, the threshold load, the
candidacy floor, and the selector all run as they would in production. Every case
runs under a socket ban, turning two ADR-0012 promises into executable invariants:

  - "on-device even when live": with the gate honestly open, the selector engages and
    attaches an assessment without opening a single socket;
  - "cannot ship live before the gate passes": with the flag ON but no valid artifact
    (or an honestly-minted one, which today stamps ``best_of_k_enforced: False``), the
    selector is never even constructed and the envelope is byte-identical to flag-off.

No model weights load here (the engage case injects a stub scorer); the companion
proof that the *real* model-load path is offline-by-construction lives in
``tests/test_zero_egress.py``.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import socket
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

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_SOURCE = REPO_ROOT / "migrations"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _forbid_sockets():
    """Patch socket.socket so any real connection attempt fails loudly."""

    def _raise(*_args, **_kwargs):
        raise AssertionError("the T1 verify path attempted to open a real socket")

    return mock.patch.object(socket, "socket", _raise)


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


class _StubScorer:
    """Fixed probabilities; never loads a model and never touches the network."""

    def __init__(self, probs: dict[str, float]) -> None:
        self._probs = probs

    def score(self, premise: str, hypothesis: str) -> dict[str, float]:
        return dict(self._probs)


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


class T1DarkPathBase(unittest.TestCase):
    """Real-gate harness: a temp contract DB plus a temp calibration dir wired into
    ``t1_gate`` so the production ``t1_permitted`` / ``load_runtime_thresholds`` read
    our synthetic files. Subclasses choose which artifact (if any) to write."""

    # A draft sentence with no surface anchor (no citation / money / date / party /
    # section / defined-term / quote), so it lands in the anchor-free branch where T1
    # lives. Proven anchor-free by the PR-6 wiring suite.
    ANCHOR_FREE = "The supplier must behave reasonably in every circumstance."

    def setUp(self) -> None:
        # --- temp contract DB (mirrors the PR-6 Site A harness) ---
        self._original = (db.BASE_DIR, db.DATA_DIR, db.UPLOAD_DIR, db.DB_PATH, db.SCHEMA_PATH)
        self._db_tmp = tempfile.TemporaryDirectory()
        root = Path(self._db_tmp.name)
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

        # --- temp calibration dir, wired into the real gate ---
        self._cal_tmp = tempfile.TemporaryDirectory()
        cal = Path(self._cal_tmp.name)
        self.thresholds = cal / "thresholds.json"
        self.corpus = cal / "test.jsonl"
        self.guideline = cal / "GUIDELINE.md"
        self.gate_pass = cal / "gate-pass.json"
        # Real committed values (the gate's outputs) so load_runtime_thresholds returns
        # (epsilon, K); the gate-pass artifact is what each test writes or withholds.
        self.thresholds.write_text(
            '{"threshold_epsilon": 70.0, "rank_cutoff": 3, "far_ceiling": {"contract": 0.02}}',
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
        self._conn.close()
        self._db_tmp.cleanup()
        self._cal_tmp.cleanup()
        db.configure_paths(
            base_dir=self._original[0],
            data_dir=self._original[1],
            upload_dir=self._original[2],
            db_path=self._original[3],
            schema_path=self._original[4],
        )

    def _write_artifact(self, **overrides: object) -> None:
        artifact = {
            "passed": True,
            "corpus_sha256": _sha(self.corpus),
            "thresholds_sha256": _sha(self.thresholds),
            "guideline_version": _sha(self.guideline),
            "model_sha256": "deadbeef",
            "feature_version": FEATURE_VERSION,
            # A future enable-PR artifact: best-of-K gate-enforced. Today's real
            # write_gate_pass stamps False; the "honestly minted" test below uses that.
            "best_of_k_enforced": True,
        }
        artifact.update(overrides)
        self.gate_pass.write_text(json.dumps(artifact), encoding="utf-8")

    def _build(self) -> dict:
        return det_env.build_deterministic_envelope(
            self.ANCHOR_FREE, conn=self._conn, doc_ids=["contract-1"], embedder=self._embedder
        )


class FlagOnValidArtifactTests(T1DarkPathBase):
    def test_real_gate_engages_selector_and_opens_no_socket(self) -> None:
        # The honest live path: env opt-in + a valid gate-pass that matches the files on
        # disk. The REAL t1_permitted() opens the tier, the REAL load_runtime_thresholds
        # supplies (70, 3), the candidacy floor and selector run (with a stub scorer so
        # no weights load), and an assessment is attached - all without a single socket.
        self._write_artifact()
        with mock.patch.dict(os.environ, {"CACHET_T1_RECALL": "1"}, clear=False):
            self.assertTrue(t1_gate.t1_permitted(), "synthetic artifact should open the real gate")
            with (
                mock.patch.object(
                    det_env,
                    "default_scorer",
                    return_value=_StubScorer(
                        {"support": 0.9, "contradict": 0.05, "cannot_determine": 0.05}
                    ),
                ),
                _forbid_sockets(),
            ):
                env = self._build()
        claim = env["claims"][0]
        self.assertIn("t1_assessment", claim)
        self.assertEqual("support", claim["t1_assessment"]["label"])
        self.assertAlmostEqual(90.0, claim["t1_assessment"]["confidence"], places=4)
        # End to end: the card carries assessed_* provenance but the verdict is unchanged.
        card = verify_service._verify_result_from_envelope(
            self.ANCHOR_FREE, env, 0.0
        ).claim_verdicts[0]
        self.assertEqual("unknown", card.verdict)
        self.assertEqual("support", card.assessed_label)
        self.assertAlmostEqual(90.0, card.assessed_confidence or 0.0, places=4)


class FlagOnButInertTests(T1DarkPathBase):
    """Flag ON but the gate is not honestly open: the selector is never constructed and
    the envelope is byte-identical to a flag-off build. A flag flip alone cannot ship a
    live T1 verdict (the physically-inert guard)."""

    def _flag_off_envelope(self) -> dict:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CACHET_T1_RECALL", None)
            return self._build()

    def test_no_artifact_is_byte_identical_to_flag_off_and_never_builds_scorer(self) -> None:
        # No gate-pass file at all: the real gate is closed, so default_scorer is never
        # called and the output is indistinguishable from T1 being absent.
        reference = self._flag_off_envelope()
        scorer = mock.Mock()
        with (
            mock.patch.object(det_env, "default_scorer", scorer),
            mock.patch.dict(os.environ, {"CACHET_T1_RECALL": "1"}, clear=False),
            _forbid_sockets(),
        ):
            self.assertFalse(t1_gate.t1_permitted())
            env_on = self._build()
        scorer.assert_not_called()
        for claim in env_on["claims"]:
            self.assertNotIn("t1_assessment", claim)
        self.assertEqual(
            json.dumps(reference, sort_keys=True),
            json.dumps(env_on, sort_keys=True),
            "flag-on-without-a-valid-artifact must be byte-identical to flag-off",
        )

    def test_honestly_minted_artifact_today_stays_dark(self) -> None:
        # The spine interlock: a real, fully-hash-valid passing artifact that records
        # best_of_k_enforced=False (what the gate stamps today) must NOT enable T1. Even
        # the genuine artifact a passing run produces leaves the tier dark.
        reference = self._flag_off_envelope()
        self._write_artifact(best_of_k_enforced=False)
        scorer = mock.Mock()
        with (
            mock.patch.object(det_env, "default_scorer", scorer),
            mock.patch.dict(os.environ, {"CACHET_T1_RECALL": "1"}, clear=False),
            _forbid_sockets(),
        ):
            self.assertFalse(t1_gate.t1_permitted())
            env_on = self._build()
        scorer.assert_not_called()
        self.assertNotIn("t1_assessment", env_on["claims"][0])
        self.assertEqual(json.dumps(reference, sort_keys=True), json.dumps(env_on, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
