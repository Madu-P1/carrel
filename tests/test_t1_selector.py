"""PR-4 (T1 recall tier, ADR-0012): the local NLI selector, dark / unwired.

Exercises the selection LOGIC through the ``EntailmentScorer`` Protocol stub so no model
loads, plus one integration check that the real ``TransformersEntailment`` fails LOUD on a
cold cache and opens no socket. The tier produces a verdict only for an above-threshold
support/contradict; everything else returns None (the could-not-check tray), never a
guessed verdict.
"""

from __future__ import annotations

import socket
import unittest
from unittest import mock

from services.legal.t1_selector import (
    CANNOT_DETERMINE,
    CONTRADICT,
    SUPPORT,
    T1Candidate,
    TransformersEntailment,
    _build_label_map,
    assess,
)


class _StubScorer:
    """Returns fixed probabilities; never loads a model."""

    def __init__(self, probs: dict[str, float]) -> None:
        self._probs = probs

    def score(self, premise: str, hypothesis: str) -> dict[str, float]:
        return dict(self._probs)


class _RaisingScorer:
    def score(self, premise: str, hypothesis: str) -> dict[str, float]:
        raise RuntimeError("model load failed")


def _candidate(rank: int = 1) -> T1Candidate:
    return T1Candidate(
        sentence="The term is two years.",
        clause="This Agreement continues for a confidentiality term of two (2) years.",
        rank=rank,
    )


class _FakeConfig:
    def __init__(self, id2label: dict[int, str]) -> None:
        self.id2label = id2label


class AssessTests(unittest.TestCase):
    def test_support_above_threshold_is_an_assessment(self) -> None:
        a = assess(
            _candidate(),
            scorer=_StubScorer({SUPPORT: 0.9, CONTRADICT: 0.05, CANNOT_DETERMINE: 0.05}),
            verdict_threshold=70.0,
            rank_cutoff=3,
        )
        assert a is not None
        self.assertEqual(SUPPORT, a.label)
        self.assertAlmostEqual(90.0, a.confidence, places=4)
        # rationale is an extractive template that echoes the clause, never generated prose.
        self.assertIn("two (2) years", a.rationale)

    def test_contradict_above_threshold_is_an_assessment(self) -> None:
        a = assess(
            _candidate(),
            scorer=_StubScorer({SUPPORT: 0.1, CONTRADICT: 0.85, CANNOT_DETERMINE: 0.05}),
            verdict_threshold=70.0,
            rank_cutoff=3,
        )
        assert a is not None
        self.assertEqual(CONTRADICT, a.label)

    def test_cannot_determine_returns_none(self) -> None:
        self.assertIsNone(
            assess(
                _candidate(),
                scorer=_StubScorer({SUPPORT: 0.2, CONTRADICT: 0.2, CANNOT_DETERMINE: 0.6}),
                verdict_threshold=50.0,
                rank_cutoff=3,
            )
        )

    def test_below_threshold_returns_none(self) -> None:
        # support is the argmax but under the threshold -> the tray, not a verdict.
        self.assertIsNone(
            assess(
                _candidate(),
                scorer=_StubScorer({SUPPORT: 0.55, CONTRADICT: 0.25, CANNOT_DETERMINE: 0.2}),
                verdict_threshold=70.0,
                rank_cutoff=3,
            )
        )

    def test_below_rank_cutoff_short_circuits_before_scoring(self) -> None:
        # A non-candidate (rank worse than the cutoff) never reaches the model: the
        # raising scorer would blow up if it were called.
        self.assertIsNone(
            assess(
                _candidate(rank=9), scorer=_RaisingScorer(), verdict_threshold=50.0, rank_cutoff=3
            )
        )

    def test_scorer_failure_is_fail_closed_none(self) -> None:
        self.assertIsNone(
            assess(_candidate(), scorer=_RaisingScorer(), verdict_threshold=50.0, rank_cutoff=3)
        )


class LabelMapTests(unittest.TestCase):
    def test_reads_id2label_not_position(self) -> None:
        # A permuted order still maps correctly, proving label order is read, not assumed.
        m = _build_label_map(_FakeConfig({0: "contradiction", 1: "entailment", 2: "neutral"}))
        self.assertEqual({0: CONTRADICT, 1: SUPPORT, 2: CANNOT_DETERMINE}, m)
        m2 = _build_label_map(_FakeConfig({0: "entailment", 1: "neutral", 2: "contradiction"}))
        self.assertEqual({0: SUPPORT, 1: CANNOT_DETERMINE, 2: CONTRADICT}, m2)

    def test_unknown_label_is_cannot_determine_safe(self) -> None:
        self.assertEqual({0: CANNOT_DETERMINE}, _build_label_map(_FakeConfig({0: "LABEL_0"})))


def _forbid_sockets():
    def _raise(*_a, **_k):
        raise AssertionError("the T1 selector attempted to open a real socket")

    return mock.patch.object(socket, "socket", _raise)


class OfflineLoadTests(unittest.TestCase):
    def test_missing_model_fails_loud_without_a_socket(self) -> None:
        # The real scorer loads via the offline harness: a cold cache raises a clear
        # error and opens no socket (the no-network contract on the model path).
        scorer = TransformersEntailment("cachet-nonexistent/fake-nli-model-xyz")
        with _forbid_sockets():
            with self.assertRaises(RuntimeError):
                scorer.score("a premise clause", "a hypothesis sentence")


if __name__ == "__main__":
    unittest.main()
