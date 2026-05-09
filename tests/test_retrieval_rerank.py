"""Unit tests for the cross-encoder rerank module.

The fastembed-backed `FastembedReranker` is exercised with a stub
TextCrossEncoder so the test suite never downloads the 1 GB model.
A separate manual smoke (not run in CI) verifies the live path.
"""

from __future__ import annotations

import math
import unittest
from unittest import mock

from services.retrieval.rerank import (
    DEFAULT_RERANKER_MODEL,
    FastembedReranker,
    _sigmoid,
    default_reranker,
    normalize_scores,
)


class SigmoidTests(unittest.TestCase):
    def test_zero_maps_to_one_half(self) -> None:
        self.assertEqual(_sigmoid(0.0), 0.5)

    def test_large_positive_maps_close_to_one(self) -> None:
        self.assertGreater(_sigmoid(10.0), 0.9999)

    def test_large_negative_maps_close_to_zero(self) -> None:
        self.assertLess(_sigmoid(-10.0), 0.0001)

    def test_extreme_values_do_not_overflow(self) -> None:
        # Naive 1 / (1 + exp(-x)) overflows at x ~= -710 on float64.
        # Our two-branch implementation must stay finite.
        for x in (-1e6, 1e6):
            with self.subTest(x=x):
                value = _sigmoid(x)
                self.assertTrue(math.isfinite(value))
                self.assertGreaterEqual(value, 0.0)
                self.assertLessEqual(value, 1.0)


class NormalizeScoresTests(unittest.TestCase):
    def test_empty_input_returns_empty(self) -> None:
        self.assertEqual(normalize_scores([]), [])

    def test_min_max_normalises_to_unit_interval(self) -> None:
        self.assertEqual(normalize_scores([1.0, 3.0, 5.0]), [0.0, 0.5, 1.0])

    def test_flat_input_falls_back_to_one_for_every_score(self) -> None:
        # All scores equal → span is zero. Returning all-zeros would
        # collapse the blended formula; returning all-ones preserves
        # ordering from the other side of the blend.
        self.assertEqual(normalize_scores([2.5, 2.5, 2.5]), [1.0, 1.0, 1.0])

    def test_single_value_input_normalises_to_one(self) -> None:
        self.assertEqual(normalize_scores([7.0]), [1.0])

    def test_negative_scores_handled(self) -> None:
        self.assertEqual(normalize_scores([-2.0, 0.0, 2.0]), [0.0, 0.5, 1.0])


class FastembedRerankerTests(unittest.TestCase):
    def test_default_model_name(self) -> None:
        reranker = FastembedReranker()
        self.assertEqual(reranker.model_name, DEFAULT_RERANKER_MODEL)

    def test_explicit_model_name(self) -> None:
        reranker = FastembedReranker("Xenova/ms-marco-MiniLM-L-6-v2")
        self.assertEqual(reranker.model_name, "Xenova/ms-marco-MiniLM-L-6-v2")

    def test_empty_documents_short_circuits_without_loading_model(self) -> None:
        reranker = FastembedReranker()
        # If empty input triggered the model load, the import below
        # would happen — but rerank_pairs must short-circuit first.
        with mock.patch("fastembed.rerank.cross_encoder.TextCrossEncoder") as patched:
            self.assertEqual(reranker.rerank_pairs("anything", []), [])
            patched.assert_not_called()

    def test_rerank_pairs_sigmoids_raw_scores(self) -> None:
        # Stand in for fastembed's TextCrossEncoder. Returns raw logits;
        # the wrapper must apply sigmoid before handing scores back.
        class _StubEncoder:
            def __init__(self, *_: object, **__: object) -> None:
                pass

            def rerank(self, query: str, documents):  # noqa: ARG002
                return iter([0.0, 5.0, -5.0])

        reranker = FastembedReranker()
        with mock.patch(
            "fastembed.rerank.cross_encoder.TextCrossEncoder",
            new=_StubEncoder,
        ):
            scores = reranker.rerank_pairs("q", ["a", "b", "c"])

        self.assertEqual(len(scores), 3)
        self.assertAlmostEqual(scores[0], 0.5, places=4)
        self.assertGreater(scores[1], 0.99)
        self.assertLess(scores[2], 0.01)

    def test_rerank_pairs_lazy_loads_only_once_across_calls(self) -> None:
        load_count = 0

        class _StubEncoder:
            def __init__(self, *_: object, **__: object) -> None:
                nonlocal load_count
                load_count += 1

            def rerank(self, query: str, documents):  # noqa: ARG002
                return iter([1.0] * len(list(documents)))

        reranker = FastembedReranker()
        with mock.patch(
            "fastembed.rerank.cross_encoder.TextCrossEncoder",
            new=_StubEncoder,
        ):
            reranker.rerank_pairs("q", ["a"])
            reranker.rerank_pairs("q", ["b", "c"])
            reranker.rerank_pairs("q", ["d"])

        self.assertEqual(load_count, 1)


class DefaultRerankerTests(unittest.TestCase):
    def test_caches_singleton_per_process(self) -> None:
        # Reset the cached instance so this test doesn't leak between runs.
        import services.retrieval.rerank as rerank_module

        rerank_module._default = None
        with mock.patch("fastembed.rerank.cross_encoder.TextCrossEncoder"):
            first = default_reranker()
            second = default_reranker()
        self.assertIs(first, second)
        rerank_module._default = None

    def test_explicit_model_name_overrides_cache(self) -> None:
        import services.retrieval.rerank as rerank_module

        rerank_module._default = None
        with mock.patch("fastembed.rerank.cross_encoder.TextCrossEncoder"):
            first = default_reranker("Xenova/ms-marco-MiniLM-L-6-v2")
            second = default_reranker("BAAI/bge-reranker-base")
        # Passing an explicit model_name forces a fresh instance.
        self.assertIsNot(first, second)
        rerank_module._default = None


if __name__ == "__main__":
    unittest.main()
