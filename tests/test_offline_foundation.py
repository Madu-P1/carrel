"""Phase 2: offline-foundation guards.

Two demo-blocking behaviors:
  - sqlite-vec must FAIL LOUD in demo mode (CACHET_REQUIRE_SQLITE_VEC) rather
    than silently degrading to BM25-only.
  - the fastembed weights cache must be pinnable via CARREL_FASTEMBED_CACHE_DIR
    so it can be pre-cached at build time and served offline.
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

import db
import services.retrieval.embeddings as embeddings


class SqliteVecFailLoudTests(unittest.TestCase):
    def setUp(self) -> None:
        db._SQLITE_VEC_WARNING_KEYS.clear()

    def test_demo_mode_raises_when_vec_unavailable(self) -> None:
        with mock.patch.dict(os.environ, {"CACHET_REQUIRE_SQLITE_VEC": "1"}, clear=False):
            with self.assertRaises(RuntimeError):
                db._sqlite_vec_unavailable("sqlite_vec_load_failed", error="boom")

    def test_default_degrades_quietly(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CACHET_REQUIRE_SQLITE_VEC", None)
            self.assertFalse(db._sqlite_vec_unavailable("sqlite_vec_load_failed"))

    def test_required_flag_accepts_truthy_values(self) -> None:
        for value in ("1", "true", "TRUE", "yes"):
            with mock.patch.dict(os.environ, {"CACHET_REQUIRE_SQLITE_VEC": value}, clear=False):
                self.assertTrue(db._sqlite_vec_required())


class FastembedCachePinTests(unittest.TestCase):
    def test_cache_dir_from_env_is_passed_through(self) -> None:
        with (
            mock.patch("fastembed.TextEmbedding") as text_embedding,
            mock.patch.dict(
                os.environ, {"CARREL_FASTEMBED_CACHE_DIR": "/tmp/cachet-models"}, clear=False
            ),
        ):
            embeddings.FastembedEmbedder()
        text_embedding.assert_called_once_with(
            model_name="BAAI/bge-small-en-v1.5", cache_dir="/tmp/cachet-models"
        )

    def test_no_env_passes_none(self) -> None:
        with (
            mock.patch("fastembed.TextEmbedding") as text_embedding,
            mock.patch.dict(os.environ, {}, clear=False),
        ):
            os.environ.pop("CARREL_FASTEMBED_CACHE_DIR", None)
            embeddings.FastembedEmbedder()
        text_embedding.assert_called_once_with(model_name="BAAI/bge-small-en-v1.5", cache_dir=None)


class OfflineEnvFloorTests(unittest.TestCase):
    def test_offline_forced_even_when_preset_off(self) -> None:
        # An inherited HF_HUB_OFFLINE=0 must NOT survive in deterministic mode: the
        # floor uses unconditional assignment, not setdefault, so the embedder cannot
        # download while the cert attests "no data left this device".
        with mock.patch.dict(
            os.environ,
            {
                "CACHET_DETERMINISTIC_VERIFY": "1",
                "HF_HUB_OFFLINE": "0",
                "TRANSFORMERS_OFFLINE": "0",
            },
            clear=False,
        ):
            embeddings._enforce_offline_env()
            self.assertEqual("1", os.environ["HF_HUB_OFFLINE"])
            self.assertEqual("1", os.environ["TRANSFORMERS_OFFLINE"])

    def test_offline_not_touched_when_flag_off(self) -> None:
        with mock.patch.dict(os.environ, {"HF_HUB_OFFLINE": "0"}, clear=False):
            os.environ.pop("CACHET_DETERMINISTIC_VERIFY", None)
            embeddings._enforce_offline_env()
            self.assertEqual("0", os.environ["HF_HUB_OFFLINE"])


if __name__ == "__main__":
    unittest.main()
