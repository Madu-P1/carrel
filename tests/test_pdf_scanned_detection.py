"""Unit tests for the scanned-PDF detection helpers in
``services.extraction.parsers.pdf``.

Pins the threshold logic that decides when the Docling/RapidOCR
fallback should fire. Real first-user case: Daft & Lengel 1986
"Organizational Information Requirements" — a ProQuest scan whose
only native text layer is a per-page "Reproduced with permission..."
watermark (~9 chars/page of body content). Without the fallback, the
Reader rendered a single 170-char chunk for an 18-page paper.
"""

from services.extraction.parsers.pdf import (
    _SCANNED_PDF_USABLE_CHARS_PER_PAGE,
    _looks_like_scanned_pdf,
    _usable_chars,
)
from services.extraction.types import ExtractedElement, SourceSpan


def _element(text: str, normalized: str | None = None) -> ExtractedElement:
    return ExtractedElement(
        id="x",
        kind="paragraph",
        text=text,
        normalized_text=text if normalized is None else normalized,
        span=SourceSpan(file_name="x", file_id="x"),
    )


class TestUsableChars:
    def test_counts_normalized_text(self):
        elements = [_element("hello", "hello"), _element("world", "world")]
        assert _usable_chars(elements) == 10

    def test_excludes_classified_noise(self):
        # Watermark / footer lines are zeroed out via normalized_text="" in
        # the _pdf_page_elements pass; _usable_chars must respect that.
        elements = [
            _element("real body text here", "real body text here"),
            _element("Reproduced with permission...", ""),
        ]
        assert _usable_chars(elements) == len("real body text here")


class TestLooksLikeScannedPdf:
    def test_dense_native_text_does_not_trigger(self):
        # 18 pages of academic content with realistic body density.
        elements = [_element("a" * 800, "a" * 800) for _ in range(18)]
        assert _looks_like_scanned_pdf(elements, page_count=18) is False

    def test_watermark_only_triggers(self):
        # Daft & Lengel shape: bridge filtered the per-page watermark
        # to normalized_text="", so usable_chars across 18 pages is the
        # cover-page heading only.
        elements = [
            _element("Daft, Richard L;Lengel, Robert H", "Daft, Richard L;Lengel, Robert H")
        ]
        assert _looks_like_scanned_pdf(elements, page_count=18) is True

    def test_threshold_is_per_page_not_total(self):
        # Exactly the threshold, all on one page.
        elements = [
            _element(
                "a" * (_SCANNED_PDF_USABLE_CHARS_PER_PAGE * 3),
                "x" * (_SCANNED_PDF_USABLE_CHARS_PER_PAGE * 3),
            )
        ]
        # 3 pages worth of usable text spread across 3 pages = at threshold,
        # but boundary is "<" so equal-density does not trigger.
        assert _looks_like_scanned_pdf(elements, page_count=3) is False

    def test_single_page_pdf_skipped(self):
        # One-page PDFs are too small a sample for the density heuristic
        # — a typed memo with 5 chars of body shouldn't be misclassified.
        elements = [_element("hi", "hi")]
        assert _looks_like_scanned_pdf(elements, page_count=1) is False

    def test_unknown_page_count_skipped(self):
        elements = [_element("hi", "hi")]
        assert _looks_like_scanned_pdf(elements, page_count=None) is False
