"""Tests for the citation-quote validation surface.

PR-D1 hardens two layers of the no-fabrication contract:

1. ``services/tutor.py:_normalize_match_text`` now NFKC-normalizes
   each character before lowercasing + whitespace-collapse, so a
   chunk containing the `ﬁ` ligature matches an LLM-emitted quote of
   `"finance"`. Both sides normalize to the same canonical form.

2. ``services/tutor.py:_fuzzy_quote_match`` raises the similarity
   floor from 0.7 to 0.95. Sub-95% fuzzy "repairs" were silently
   substituting a model-emitted quote with a different chunk
   substring; the user's mental model ("this is the source span")
   survived but the substituted quote no longer literally backed
   the claim. PR-D1 drops looser matches into ``unsupported_spans``
   instead of rewriting them.

3. ``services/extraction/utils.py:normalize_space`` also NFKCs at
   write time so new chunks are visually consistent in storage with
   the compare-time canonical form. Existing un-normalized chunks
   keep working because the compare-time NFKC normalizes both sides.
"""

from __future__ import annotations

import unittest

from services.extraction.utils import normalize_space
from services.tutor import (
    _fuzzy_quote_match,
    _normalize_match_text,
    _validated_citation_quote,
)


class NfkcCompareTimeNormalizationTests(unittest.TestCase):
    """`_normalize_match_text` must NFKC-normalize so ligature-bearing
    chunk content matches ASCII LLM quotes."""

    def test_fi_ligature_normalizes_to_ascii(self) -> None:
        result = _normalize_match_text("ﬁnance")  # ﬁnance
        # NFKC expands U+FB01 to "fi"; the rest passes through.
        self.assertEqual(result.text, "finance")

    def test_fl_ligature_normalizes_to_ascii(self) -> None:
        result = _normalize_match_text("reﬂection")  # reﬂection
        self.assertEqual(result.text, "reflection")

    def test_index_map_handles_ligature_expansion(self) -> None:
        # ﬁnance is 6 source chars (ﬁ, n, a, n, c, e). After NFKC the
        # normalized form is "finance" (7 chars). Both `f` and `i`
        # must map back to source index 0 so `_slice_original_span`
        # returns the original ﬁ ligature.
        result = _normalize_match_text("ﬁnance")
        self.assertEqual(result.text, "finance")
        # f and i both came from source index 0 (the ﬁ ligature).
        self.assertEqual(result.index_map[0], 0)
        self.assertEqual(result.index_map[1], 0)
        # The rest map 1:1 to source positions 1..5.
        self.assertEqual(result.index_map[2], 1)
        self.assertEqual(result.index_map[6], 5)

    def test_validator_finds_ascii_quote_in_ligature_chunk(self) -> None:
        # The real audit-flagged regression: chunk has ﬁnance, LLM
        # emits "finance". Pre-PR-D1 the substring find fails and the
        # citation is dropped. Post-PR-D1 NFKC makes both sides equal.
        chunk = "Variance is central to ﬁnance and risk modeling."
        llm_quote = "central to finance and risk modeling"
        match = _validated_citation_quote(llm_quote, chunk)
        self.assertIsNotNone(match, msg="NFKC normalization must let ASCII match ligature chunk.")
        # The returned quote is sliced from the ORIGINAL chunk, so it
        # preserves the ﬁ ligature for verbatim rendering.
        assert match is not None  # for type checker
        self.assertIn("ﬁ", match.quote)

    def test_benign_ascii_round_trip(self) -> None:
        # No false positives: pure ASCII text round-trips unchanged.
        result = _normalize_match_text("The capital of Bolivia is La Paz.")
        self.assertEqual(result.text, "the capital of bolivia is la paz.")


class FuzzyQuoteThresholdTests(unittest.TestCase):
    """`_fuzzy_quote_match` floor raised from 0.7 to 0.95."""

    def test_high_similarity_quote_still_accepted(self) -> None:
        # An LLM quote that's character-for-character identical to a
        # chunk substring (after normalization) must still pass.
        chunk = "Variance is the expected value of squared deviations from the mean."
        llm_quote = "Variance is the expected value of squared deviations"
        match = _validated_citation_quote(llm_quote, chunk)
        self.assertIsNotNone(match)

    def test_loose_70_percent_match_now_rejected(self) -> None:
        # REGRESSION test (audit-flagged). Pre-PR-D1 a ~70% similar
        # quote was silently substituted for the real chunk substring.
        # The model emits a paraphrase; the fuzzy matcher used to
        # "repair" it to whatever 70%-similar span existed in the
        # chunk. After PR-D1 the loose match is rejected and the
        # claim drops to unsupported_spans.
        chunk = "Variance is the expected value of squared deviations."
        # ~70% similar but materially different phrasing: shared
        # words "variance", "the", "value", "of" but the actual
        # mechanism described ("mean of squared deviations from the
        # average") differs from the chunk's "expected value of".
        llm_quote = "Variance equals the mean of squared values"
        match = _fuzzy_quote_match(
            llm_quote,
            chunk,
            _normalize_match_text(llm_quote),
            _normalize_match_text(chunk),
        )
        self.assertIsNone(
            match,
            msg="Loose ~70% fuzzy match must be rejected post-PR-D1.",
        )

    def test_high_similarity_via_whitespace_difference_accepted(self) -> None:
        # Whitespace divergence is the kind of "fuzzy repair" we want
        # to keep: model emits "...the expected   value..." (double
        # space); chunk has "...the expected value...". Normalization
        # collapses whitespace, similarity stays at 1.0.
        chunk = "Variance is the expected value of squared deviations from the mean."
        llm_quote = "Variance is the expected  value of squared deviations"
        match = _fuzzy_quote_match(
            llm_quote,
            chunk,
            _normalize_match_text(llm_quote),
            _normalize_match_text(chunk),
        )
        self.assertIsNotNone(
            match,
            msg="Whitespace-only divergence must still match after PR-D1.",
        )


class NormalizeSpaceNfkcTests(unittest.TestCase):
    """`normalize_space` adds NFKC at the write-side so storage is
    visually consistent with the compare-time canonical form."""

    def test_ligatures_decomposed_in_extracted_text(self) -> None:
        # PDFKit emits the ﬁ ligature; normalize_space should hand the
        # downstream chunker an ASCII "fi" string.
        result = normalize_space("efﬁcient ﬂow")  # eﬁcient ﬂow
        self.assertEqual(result, "efficient flow")

    def test_fullwidth_digits_decomposed(self) -> None:
        # NFKC also collapses fullwidth ASCII (common in OCR of CJK
        # documents) to the regular ASCII range.
        result = normalize_space("page １２３")
        self.assertEqual(result, "page 123")

    def test_benign_ascii_text_unchanged(self) -> None:
        # No false positives on already-clean text.
        result = normalize_space("Variance is the expected value of squared deviations.")
        self.assertEqual(result, "Variance is the expected value of squared deviations.")

    def test_whitespace_collapsing_still_applies(self) -> None:
        # The existing whitespace-collapse behavior must coexist with
        # the new NFKC pass.
        result = normalize_space("hello   world\r\nsecond\tline")
        self.assertEqual(result, "hello world\nsecond line")


if __name__ == "__main__":
    unittest.main()
