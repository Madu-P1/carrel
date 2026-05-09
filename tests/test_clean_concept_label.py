"""Unit tests for ``clean_concept_label``.

Pinning the fix for the doubled-phrase bug. The first-user demo surfaced
chips reading "Contingency Approach Contingency Approach (5%)" because
the cleaner only deduped adjacent identical words; a phrase-level repeat
slipped through.
"""

from services.documents import clean_concept_label


class TestCleanConceptLabel:
    def test_adjacent_word_dedup_preserved(self):
        # The pre-existing behaviour: collapse "foo foo bar" -> "foo bar".
        assert clean_concept_label("foo foo bar") == "foo bar"

    def test_phrase_level_dedup_two_words(self):
        # The bug: an LLM emitting "X / X" or "X — X" got normalised to
        # "X X X X" by the separator collapse, and the adjacent-word
        # loop couldn't see it as a duplicate phrase.
        assert (
            clean_concept_label("Contingency Approach Contingency Approach")
            == "Contingency Approach"
        )

    def test_phrase_level_dedup_three_words(self):
        assert clean_concept_label("A B C A B C") == "A B C"

    def test_phrase_level_dedup_case_insensitive(self):
        assert (
            clean_concept_label("Transformational Leadership transformational leadership")
            == "Transformational Leadership"
        )

    def test_separator_normalises_then_dedups(self):
        # Reproduces the upstream LLM shape: "X — X" or "X / X" becomes
        # "X X X X" after separator collapse, which the new phrase-level
        # check then folds back to "X X".
        assert (
            clean_concept_label("Contingency Approach / Contingency Approach")
            == "Contingency Approach"
        )
        assert (
            clean_concept_label("Contingency Approach - Contingency Approach")
            == "Contingency Approach"
        )

    def test_non_duplicate_phrase_unchanged(self):
        # Negative case: the cleaner must not over-fold genuine phrases.
        assert clean_concept_label("Foo Bar Baz") == "Foo Bar Baz"
        assert clean_concept_label("Bottom Line") == "Bottom Line"

    def test_three_word_non_duplicate_unchanged(self):
        # Odd word count cannot be a clean duplicate; left alone.
        assert clean_concept_label("Theory of Mind") == "Theory of Mind"

    def test_empty_returns_fallback(self):
        assert clean_concept_label("") == "Study concept"
        assert clean_concept_label(None) == "Study concept"

    def test_camelcase_split_then_dedup(self):
        # Pre-existing camelCase split path still works alongside the
        # new phrase dedup.
        assert clean_concept_label("FooBar FooBar") == "Foo Bar"
