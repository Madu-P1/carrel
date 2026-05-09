"""Generate the PDF fixtures consumed by test_docling_pdf_ingest.py.

Run: `./.venv/bin/python -m tests.fixtures.generate`

Outputs:
- tests/fixtures/single_column.pdf  — heading + two body paragraphs, one column
- tests/fixtures/two_column.pdf     — two-column layout, body-1 left, body-2 right

These are deliberately tiny so Docling's OCR fallback isn't triggered
(reportlab emits a real text layer). They exercise the walker's reading
order and char-offset accounting, not Docling's vision pipeline.

reportlab is a test-only dependency (see requirements-dev.txt).
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)
from reportlab.platypus.doctemplate import PageTemplate

FIXTURES_DIR = Path(__file__).resolve().parent

SINGLE_COLUMN_HEADING = "Photosynthesis Overview"
SINGLE_COLUMN_BODY_1 = (
    "Plants convert sunlight into chemical energy through photosynthesis. "
    "The process begins when chlorophyll absorbs photons and uses their energy "
    "to split water molecules in the thylakoid membranes."
)
SINGLE_COLUMN_BODY_2 = (
    "The Calvin cycle then fixes atmospheric carbon dioxide into glucose. "
    "Each turn of the cycle consumes three molecules of carbon dioxide and "
    "produces one three-carbon sugar called glyceraldehyde-3-phosphate."
)

TWO_COLUMN_HEADING = "Cell Division"
TWO_COLUMN_LEFT_BODY = (
    "Mitosis produces two genetically identical daughter cells from a single "
    "parent cell. The process is divided into prophase, metaphase, anaphase, "
    "and telophase. Mitosis is responsible for growth and tissue repair in "
    "multicellular organisms."
)
TWO_COLUMN_RIGHT_BODY = (
    "Meiosis produces four genetically distinct gametes from a single parent "
    "cell. Crossing over during prophase one creates new combinations of "
    "alleles. The result is increased genetic variation in sexually "
    "reproducing populations."
)


def _styles() -> tuple[ParagraphStyle, ParagraphStyle]:
    sheet = getSampleStyleSheet()
    heading = ParagraphStyle(
        name="FixtureHeading",
        parent=sheet["Heading1"],
        fontSize=18,
        spaceAfter=12,
    )
    body = ParagraphStyle(
        name="FixtureBody",
        parent=sheet["BodyText"],
        fontSize=11,
        leading=14,
        spaceAfter=10,
    )
    return heading, body


def write_single_column(path: Path) -> None:
    heading_style, body_style = _styles()
    doc = SimpleDocTemplate(
        str(path),
        pagesize=LETTER,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    doc.build(
        [
            Paragraph(SINGLE_COLUMN_HEADING, heading_style),
            Paragraph(SINGLE_COLUMN_BODY_1, body_style),
            Spacer(1, 0.1 * inch),
            Paragraph(SINGLE_COLUMN_BODY_2, body_style),
        ]
    )


def write_two_column(path: Path) -> None:
    heading_style, body_style = _styles()
    page_width, page_height = LETTER
    margin = 0.75 * inch
    gutter = 0.25 * inch
    column_width = (page_width - 2 * margin - gutter) / 2

    heading_frame = Frame(
        margin,
        page_height - margin - 1.0 * inch,
        page_width - 2 * margin,
        0.9 * inch,
        showBoundary=0,
        leftPadding=0,
        rightPadding=0,
    )
    left_frame = Frame(
        margin,
        margin,
        column_width,
        page_height - 2 * margin - 1.1 * inch,
        showBoundary=0,
    )
    right_frame = Frame(
        margin + column_width + gutter,
        margin,
        column_width,
        page_height - 2 * margin - 1.1 * inch,
        showBoundary=0,
    )

    doc = BaseDocTemplate(str(path), pagesize=LETTER)
    doc.addPageTemplates(
        [PageTemplate(id="two_col", frames=[heading_frame, left_frame, right_frame])]
    )
    doc.build(
        [
            Paragraph(TWO_COLUMN_HEADING, heading_style),
            Paragraph(TWO_COLUMN_LEFT_BODY, body_style),
            Paragraph(TWO_COLUMN_RIGHT_BODY, body_style),
        ]
    )


def write_all() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    write_single_column(FIXTURES_DIR / "single_column.pdf")
    write_two_column(FIXTURES_DIR / "two_column.pdf")


if __name__ == "__main__":
    write_all()
    print(f"Wrote fixtures to {FIXTURES_DIR}")
