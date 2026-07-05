"""Held-out paraphrase-recall test for the on-device encoder (EinsteinEncodeBridge).

Proves the semantic encoder retrieves the correct source span when the wording
differs from the claim — the low-lexical-overlap cases the FTS/shingle index
misses, where the engine currently refuses because it cannot locate the source.
Each case pairs the true paraphrase against a distractor that shares surface
words but not meaning, so a purely lexical ranker would mis-rank it and only
semantic recall gets it right.

The encoder is a PROPOSER (candidate retrieval); the deterministic verify engine
still disposes. No negation cases here: negation-flip is the encoder's known
weakness and belongs to the deterministic layer, not this recall gate.

macOS 14+ arm64 with the bridge built only; auto-skips on CI / non-macOS
(mirrors tests/integration/test_afm_real_bridge.py).
"""

from __future__ import annotations

import platform
import sys
import unittest

from ai.native_bridge_paths import ENCODE_BRIDGE_CANDIDATES, find_binary

skip_reason = (
    "Run on macOS arm64 with the encoder bridge built: "
    "swift build --package-path macos-app --product EinsteinEncodeBridge"
)


def _on_macos_with_bridge() -> bool:
    if sys.platform != "darwin" or platform.machine() != "arm64":
        return False
    return find_binary(ENCODE_BRIDGE_CANDIDATES) is not None


# (claim, [sources], index of the true paraphrase). Source 1 in each case is a
# same-topic, higher-lexical-overlap distractor.
CASES = [
    (
        "The covenant binds later owners of the property.",
        [
            "Successors in title are bound by the restrictive covenant.",
            "The covenant was drafted by the property developer's counsel.",
        ],
        0,
    ),
    (
        "The company's revenue grew last year.",
        [
            "Annual turnover rose over the prior fiscal year.",
            "The company moved its headquarters last year.",
        ],
        0,
    ),
    (
        "The agreement may be terminated with thirty days notice.",
        [
            "Either party can end the contract on 30 days written notice.",
            "The agreement was executed in March by both parties.",
        ],
        0,
    ),
]


def _cosine(a: list[float], b: list[float]) -> float:
    # Encoder L2-normalizes, so cosine is a dot product.
    return sum(x * y for x, y in zip(a, b))


@unittest.skipUnless(_on_macos_with_bridge(), skip_reason)
class EncoderParaphraseRecallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from services.retrieval.embeddings import AppleContextualEmbedder

        cls.embedder = AppleContextualEmbedder()

    def test_dimension_and_shape(self) -> None:
        self.assertEqual(self.embedder.dim, 512)
        vec = self.embedder.embed_query("hello world")
        self.assertEqual(len(vec), 512)

    def test_paraphrase_source_outranks_lexical_distractor(self) -> None:
        for claim, sources, correct in CASES:
            with self.subTest(claim=claim):
                vectors = self.embedder.embed_passages([claim, *sources])
                claim_vec, source_vecs = vectors[0], vectors[1:]
                scores = [_cosine(claim_vec, sv) for sv in source_vecs]
                best = max(range(len(scores)), key=lambda i: scores[i])
                self.assertEqual(
                    best,
                    correct,
                    msg=(
                        f"ranked source {best} over the paraphrase {correct}; "
                        f"scores={[round(s, 3) for s in scores]}"
                    ),
                )


if __name__ == "__main__":
    unittest.main()
