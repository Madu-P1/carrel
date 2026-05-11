"""Tests for services.extraction.text_artifacts.strip_extraction_artifacts."""

from __future__ import annotations

import unittest

from services.extraction.text_artifacts import strip_extraction_artifacts

USER_CHUNK_FIXTURE = (
    "Variance and Standard Deviation\n\n"
    "Variance\n\n"
    "The expected squared deviation from the mean R Var R E R E R P R E R "
    "  = − = × −     ∑\n\n"
    "Standard Deviation\n\n"
    "The square root of the variance\n\n"
    "( ) ( ) SD R Var R=\n\n"
    "Both are measures of the risk of a probability distribution"
)


class StripExtractionArtifactsTests(unittest.TestCase):
    def test_single_pua_char_stripped(self) -> None:
        self.assertEqual(strip_extraction_artifacts("hello  world"), "hello world")

    def test_multiple_pua_chars_stripped(self) -> None:
        text = "abcdef"
        self.assertEqual(strip_extraction_artifacts(text), "abcdef")

    def test_pua_range_boundaries(self) -> None:
        # U+E000 is the start of PUA, U+F8FF is the end. Both must go.
        text = "xyz"
        self.assertEqual(strip_extraction_artifacts(text), "xyz")

    def test_empty_parens_stripped(self) -> None:
        self.assertEqual(strip_extraction_artifacts("foo ( ) bar"), "foo bar")

    def test_nested_empty_parens_collapse_to_empty(self) -> None:
        self.assertEqual(strip_extraction_artifacts("( ) ( )"), "")

    def test_user_chunk_fixture_preserves_prose(self) -> None:
        out = strip_extraction_artifacts(USER_CHUNK_FIXTURE)
        self.assertIn("The expected squared deviation from the mean", out)
        self.assertIn("Standard Deviation", out)
        self.assertIn("Both are measures of the risk of a probability distribution", out)
        # No PUA chars survive.
        for codepoint in out:
            self.assertFalse(
                0xE000 <= ord(codepoint) <= 0xF8FF,
                f"PUA char U+{ord(codepoint):04X} leaked into output",
            )
        # No empty parens survive.
        self.assertNotIn("( )", out)
        self.assertNotIn("()", out)

    def test_idempotent_on_user_chunk(self) -> None:
        once = strip_extraction_artifacts(USER_CHUNK_FIXTURE)
        twice = strip_extraction_artifacts(once)
        self.assertEqual(once, twice)

    def test_none_input_returns_empty_string(self) -> None:
        self.assertEqual(strip_extraction_artifacts(None), "")  # type: ignore[arg-type]

    def test_empty_string_returns_empty_string(self) -> None:
        self.assertEqual(strip_extraction_artifacts(""), "")

    def test_clean_prose_unchanged(self) -> None:
        text = "Mitosis is the process by which a single cell divides into two daughter cells."
        self.assertEqual(strip_extraction_artifacts(text), text)

    def test_unicode_math_symbols_preserved(self) -> None:
        text = "Var(R) = ∑ p × (r - μ)²"
        out = strip_extraction_artifacts(text)
        for symbol in ("∑", "×", "²", "μ"):
            self.assertIn(symbol, out)

    def test_greek_letters_preserved(self) -> None:
        text = "The α and β parameters control the model."
        self.assertEqual(strip_extraction_artifacts(text), text)

    def test_paragraph_break_preserved(self) -> None:
        self.assertEqual(strip_extraction_artifacts("line1\n\nline2"), "line1\n\nline2")

    def test_idempotent_on_clean_text(self) -> None:
        text = "Mitosis is the process by which a single cell divides into two daughter cells."
        once = strip_extraction_artifacts(text)
        twice = strip_extraction_artifacts(once)
        self.assertEqual(once, twice)

    def test_orphan_operator_tail_stripped(self) -> None:
        # Real chunk from production 2026-05-11 Ask Library: after PUA
        # stripping, operator skeleton remained. Should be cleaned.
        self.assertEqual(
            strip_extraction_artifacts("BFI Var R = × − − + × −"),
            "BFI Var R",
        )

    def test_repeated_equals_stripped(self) -> None:
        self.assertEqual(
            strip_extraction_artifacts("0.045 21.2% SD R Var R= = ="),
            "0.045 21.2% SD R Var R",
        )
        self.assertEqual(
            strip_extraction_artifacts("8.59% 29.30% SD R Var R= = ="),
            "8.59% 29.30% SD R Var R",
        )

    def test_legitimate_math_preserved(self) -> None:
        # Regression: cleanup MUST NOT touch real equations.
        for expr in [
            "2 + 2 = 4",
            "Var(R) = E[(R - E[R])^2]",
            "a = b",
            "x − y = z",
        ]:
            self.assertEqual(strip_extraction_artifacts(expr), expr, msg=expr)

    def test_idempotent_on_operator_soup(self) -> None:
        text = "BFI Var R = × − − + × −\nSD R Var R= = ="
        once = strip_extraction_artifacts(text)
        twice = strip_extraction_artifacts(once)
        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()
