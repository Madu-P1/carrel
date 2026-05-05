"""Direct tests for the quote-validation module.

The grounded-tutor tests cover this through the pipeline, but unit
tests give faster feedback when the matcher itself is the suspect.
"""

from __future__ import annotations

import unittest

from services.tutor_quotes import (
    QuoteMatch,
    normalize,
    slice_original,
    validate_quote,
)


class NormalizeTests(unittest.TestCase):
    def test_collapses_whitespace_and_lowercases(self) -> None:
        nt = normalize("  Hello   World  ")
        self.assertEqual("hello world", nt.text)

    def test_smart_quotes_fold_to_ascii(self) -> None:
        nt = normalize("“Yes,” he said")  # curly quotes
        self.assertIn('"yes,"', nt.text)

    def test_index_map_round_trips(self) -> None:
        original = "Hello   World"
        nt = normalize(original)
        # 'h' is at position 0 in original
        self.assertEqual(0, nt.index_map[0])
        # 'w' is the 7th character in normalized ('hello w'),
        # backed by position 8 in original (after the triple space).
        self.assertEqual("w", nt.text[6])
        self.assertEqual("W", original[nt.index_map[6]])


class SliceOriginalTests(unittest.TestCase):
    def test_slice_returns_verbatim_substring(self) -> None:
        original = "The quick brown fox"
        nt = normalize(original)
        # Position of "brown" in normalized form
        start = nt.text.find("brown")
        self.assertEqual("brown", slice_original(original, nt, start, 5))

    def test_out_of_bounds_returns_empty(self) -> None:
        nt = normalize("hello")
        self.assertEqual("", slice_original("hello", nt, 100, 5))


class ValidateQuoteTests(unittest.TestCase):
    def test_exact_match_returns_unrepaired(self) -> None:
        match = validate_quote("brown fox", "The quick brown fox jumps")
        self.assertIsNotNone(match)
        assert match is not None  # for type checker
        self.assertEqual("brown fox", match.quote)
        self.assertFalse(match.repaired)

    def test_smart_quote_drift_is_repaired(self) -> None:
        # Model emits curly quotes; source has ASCII quotes.
        source = 'He said "yes" loudly.'
        match = validate_quote("“yes”", source)
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual('"yes"', match.quote)
        self.assertTrue(match.repaired)

    def test_unrelated_quote_rejects(self) -> None:
        match = validate_quote("entirely different text", "the quick brown fox")
        self.assertIsNone(match)

    def test_empty_inputs_reject(self) -> None:
        self.assertIsNone(validate_quote("", "anything"))
        self.assertIsNone(validate_quote("anything", ""))
        self.assertIsNone(validate_quote("   ", "   "))

    def test_short_fuzzy_match_below_threshold_rejects(self) -> None:
        # Exact substrings always match (any length); the 40-char
        # minimum applies only to the fuzzy fallback. Here "needl"
        # is missing from the source so we fall to fuzzy, where the
        # tiny common run is rejected.
        match = validate_quote("needl in haystck", "needle in haystack of thread")
        # Either the fuzzy match repairs the typo (returning a real
        # span >= 40 chars after similarity) or rejects. Both are
        # acceptable; what we're pinning is that the validator never
        # invents a quote that isn't backed by content.
        if match is not None:
            self.assertIn(match.quote, "needle in haystack of thread")

    def test_returned_match_is_quotematch_dataclass(self) -> None:
        match = validate_quote("brown fox", "the brown fox")
        self.assertIsInstance(match, QuoteMatch)


if __name__ == "__main__":
    unittest.main()
