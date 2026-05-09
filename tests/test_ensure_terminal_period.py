"""Unit tests for ``_ensure_terminal_period``.

Pinning the fix for run-on takeaway text in the Concept Atlas, where
bullet-point evidence sentences were joined with a single space and no
terminal periods, producing output like::

    "...what they do Meta analysis shows roughly 154 different traits..."

instead of two cleanly bounded sentences.
"""

from services.ingestion.topics import _ensure_terminal_period


class TestEnsureTerminalPeriod:
    def test_adds_period_when_missing(self):
        assert _ensure_terminal_period("focus of who are leaders") == (
            "focus of who are leaders."
        )

    def test_idempotent_on_terminated_sentence(self):
        # Re-running the function must never double-up punctuation.
        assert _ensure_terminal_period("Already done.") == "Already done."
        assert _ensure_terminal_period("Already done?") == "Already done?"
        assert _ensure_terminal_period("Already done!") == "Already done!"

    def test_preserves_colon_and_semicolon(self):
        # Treat clause-internal terminators as already-terminated; the
        # downstream join is fine with a colon ending.
        assert _ensure_terminal_period("Three rules:") == "Three rules:"
        assert _ensure_terminal_period("Two parts;") == "Two parts;"

    def test_strips_trailing_whitespace(self):
        assert _ensure_terminal_period("trailing  ") == "trailing."

    def test_empty_returns_empty(self):
        assert _ensure_terminal_period("") == ""
        assert _ensure_terminal_period(None) == ""

    def test_join_produces_two_sentences(self):
        # The actual integration shape: two bullet-text strings joined
        # with a space produce two cleanly bounded sentences instead of
        # a run-on.
        a = _ensure_terminal_period("focus of who are leaders")
        b = _ensure_terminal_period("Meta analysis shows 154 traits")
        assert (
            f"{a} {b}"
            == "focus of who are leaders. Meta analysis shows 154 traits."
        )
