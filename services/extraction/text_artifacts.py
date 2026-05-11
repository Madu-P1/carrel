"""Strip extraction artifacts from chunk text before LLM / user surfaces.

Some PDFs encode mathematical expressions with custom fonts whose glyphs
fall in the Unicode Private-Use Area (PUA, U+E000 to U+F8FF). When those
PDFs are parsed with a plain text extractor, the math glyphs come through
as PUA codepoints that render as boxes downstream and confuse LLM
providers. The same extractors often leave empty parentheses where an
equation was supposed to be rendered (e.g. "SD R Var R=" followed by
"( )" on its own line).

The long-term fix is Docling-based structured extraction
(see services/ingestion/docling_parser.py), which understands math and
tables natively. This module is a stopgap that cleans up existing
chunks at read time so the tutor and review surfaces stop showing PUA
boxes and stray empty parens.

Two SAFE rules only:

1. Strip all Private-Use Area codepoints. These never legitimately
   appear in academic prose; they are always font-specific glyphs.
2. Strip empty parentheses, which are template skeletons left behind
   by failed equation extraction.

Note: Unicode Mathematical Operators (U+2200 to U+22FF) and Greek
letters (U+0370 to U+03FF) are intentionally preserved because they
are real characters that authors write in prose (Var(R) = sigma p
times ...).
"""

from __future__ import annotations

import re

# U+E000 to U+F8FF is the Basic Multilingual Plane Private-Use Area.
# Custom math fonts in PDFs commonly map glyphs into this range, and
# nothing in standard academic prose belongs here.
_PUA_RE = re.compile(r"[-]+")

# Empty parens left by failed equation extraction. Allow internal
# whitespace because PDFs often emit "( )" with a stray space.
_EMPTY_PARENS_RE = re.compile(r"\(\s*\)")

# Orphan math operator runs left over after PUA glyph stripping.
# Real chunk seen in production (2026-05-11):
#     "BFI Var R = × − − + × −"
#     "0.045 21.2% SD R Var R= = ="
# The operands lived in PUA-mapped font glyphs; once we strip those,
# only operator skeletons remain. Real expressions never contain 2+
# math operators in a row separated by whitespace ("× −" or "= ="),
# so a run of 2+ is a reliable signal of post-strip junk.
#
# Two patterns:
#  1. End-of-line operator tail: "... = × − − + × −" at $ -> strip
#  2. Repeated equals interior: "R= = =" -> strip the chain
#
# Both anchored to whitespace boundaries so legitimate math like
# "2 + 2 = 4" or "Var(R) = E[(R - E[R])^2]" survives.
_TRAILING_OP_RUN_RE = re.compile(r"\s*[×−+÷=](?:\s+[×−+÷=])+\s*$", re.MULTILINE)
_INTERIOR_OP_RUN_RE = re.compile(r"\s+[×−+÷=](?:\s+[×−+÷=]){1,}(?=\s|$)")

# Collapse runs of spaces / tabs inside a single line, but preserve
# newlines so paragraph structure survives.
_INLINE_WS_RE = re.compile(r"[ \t]{2,}")

# Collapse 3+ consecutive newlines down to 2 (paragraph break).
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def strip_extraction_artifacts(text: str) -> str:
    """Return text with PDF math extraction artifacts removed.

    Idempotent: applying the function twice yields the same result as
    applying it once. Handles None by returning the empty string.
    """
    if not text:
        return ""
    cleaned = _PUA_RE.sub("", text)
    cleaned = _EMPTY_PARENS_RE.sub("", cleaned)
    # Run trailing-tail FIRST so it can match the operator soup at the
    # end of a line; otherwise interior collapse would leave a single
    # operator stranded that trailing wouldn't catch (needs 2+).
    cleaned = _TRAILING_OP_RUN_RE.sub("", cleaned)
    cleaned = _INTERIOR_OP_RUN_RE.sub("", cleaned)
    # Re-run trailing once more in case the interior collapse exposed
    # a fresh tail. Cheap; keeps the function idempotent.
    cleaned = _TRAILING_OP_RUN_RE.sub("", cleaned)
    cleaned = _INLINE_WS_RE.sub(" ", cleaned)
    cleaned = _BLANK_LINES_RE.sub("\n\n", cleaned)
    # Trim trailing spaces on each line so " \n" does not become a
    # stable artifact across repeated runs.
    cleaned = "\n".join(line.rstrip() for line in cleaned.split("\n"))
    return cleaned.strip()
