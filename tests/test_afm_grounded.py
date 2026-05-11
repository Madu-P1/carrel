"""Tests for `ai/afm_grounded.py` — server-side span extraction."""

from __future__ import annotations

import unittest

from ai.afm_grounded import extract_best_span


class ExtractBestSpanTests(unittest.TestCase):
    def test_picks_sentence_with_highest_overlap(self) -> None:
        chunk = (
            "Mitosis is the process of cell division. "
            "During metaphase, chromosomes align at the cell equator. "
            "In anaphase, sister chromatids are pulled to opposite poles of the cell. "
            "Telophase concludes the process."
        )
        answer = "Sister chromatids are pulled to opposite poles during anaphase."
        span = extract_best_span(chunk, answer)
        self.assertGreater(span.score, 0.10)
        self.assertFalse(span.is_full_chunk)
        # The picked sentence should mention the keywords from the answer.
        self.assertIn("anaphase", span.text.lower())
        self.assertIn("opposite poles", span.text.lower())
        # And it must be a verbatim substring of the chunk.
        self.assertIn(span.text.rstrip("…").rstrip(), chunk)

    def test_falls_back_to_full_chunk_when_no_sentence_clears_threshold(self) -> None:
        chunk = "Photosynthesis happens in chloroplasts. ATP is the energy currency."
        answer = "The mitochondria is the powerhouse of the cell."
        span = extract_best_span(chunk, answer, min_score=0.5)
        self.assertTrue(span.is_full_chunk)
        self.assertLess(span.score, 0.5)
        # The fallback must still be a verbatim substring of the chunk.
        truncated = span.text.rstrip("…").rstrip()
        self.assertTrue(
            truncated in chunk or chunk.startswith(truncated),
            f"fallback span '{truncated}' not in chunk",
        )

    def test_truncates_at_word_boundary_verbatim(self) -> None:
        # Codex P2: the returned span MUST be a verbatim substring of
        # the source chunk. The old behaviour appended an ellipsis on
        # truncation, which broke that invariant and let citations
        # render text that doesn't exist in the source.
        long_chunk = ("word " * 200).strip()
        span = extract_best_span(long_chunk, "word", max_chars=80)
        self.assertLessEqual(len(span.text), 80)
        self.assertFalse(span.text.endswith("…"))
        self.assertIn(span.text, long_chunk)

    def test_handles_empty_chunk(self) -> None:
        span = extract_best_span("", "anything")
        self.assertEqual(span.score, 0.0)
        self.assertTrue(span.is_full_chunk)

    def test_handles_empty_answer(self) -> None:
        span = extract_best_span("Some chunk text.", "")
        self.assertEqual(span.score, 0.0)
        self.assertTrue(span.is_full_chunk)

    def test_short_sentences_skipped(self) -> None:
        # Fragments below 20 chars should not be returned as the best span.
        chunk = (
            "Yes. No. Maybe. Mitosis is a process of cell division that produces daughter cells."
        )
        answer = "Mitosis produces daughter cells."
        span = extract_best_span(chunk, answer)
        self.assertNotEqual(span.text.strip().rstrip("."), "Yes")
        self.assertNotEqual(span.text.strip().rstrip("."), "No")


if __name__ == "__main__":
    unittest.main()
