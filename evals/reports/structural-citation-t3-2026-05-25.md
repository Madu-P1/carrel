# Chunks-path structural-citation T3 report (2026-05-25)

Gate 1 T3 acceptance artifact. Documents the signal tightening that
T3 lands on top of T2's runtime filter, the unit-test coverage that
pins each new pattern, and the empirical situation on the smoke
corpus (still zero traps, per the T2.0 baseline finding).

## What T3 lands

Two narrow extensions to `services/retrieval/quote_heuristics.py`,
no new public functions, no flag change. Behind the existing
`RETRIEVAL_CHUNKS_HEURISTIC` (default `false` until T4).

### Four new bare-reference patterns

Added to `_BARE_REFERENCE_PATTERNS` alongside T2's numeric-only,
author-year, bracketed, and see-figure patterns.

1. **Chapter / section / part labels**:
   `^(?:chapter|chap|section|sec|part|pt|ch|§)\.?\s+(?:\d+(?:\.\d+)*[a-z]?|[ivxlcdm]+)\.?$`
   Catches: `Chapter 3`, `Sec. 4.2`, `Part IV`, `§ 7`, `Ch. 5a`.
   Misses (intentionally): the longer "Chapter 3: Contract Formation"
   form. That one falls through to `is_heading_shape` instead.

2. **Page ranges**:
   `^(?:pp?|pages)\.?\s*\d+\s*[\-–—]\s*\d+\.?$`
   Catches: `pp. 22-25`, `pages 100-105`, `pp. 22–25` (en-dash),
   `pp. 22—25` (em-dash). The dash character class is the only
   intentional dash usage in this module; em-dashes elsewhere are
   prose-banned per CLAUDE.md voice rule.

3. **Equation / formula references**:
   `^(?:eq(?:uation)?|formula)\.?\s+\d+(?:\.\d+)*[a-z]?\.?$`
   Catches: `Eq. 3`, `Equation 12`, `Formula 4.2a`.

4. **Appendix / exhibit references**:
   `^(?:appendix|app|exhibit|exh)\.?\s+(?:[A-Z]|\d+(?:\.\d+)*)\.?$`
   Catches: `Appendix A`, `App. B`, `Exhibit 3`, `Exh. 4.2`.

Each pattern has positive subtests in
`tests/test_retrieval_quote_heuristics.py::BareReferenceTests` and a
negative subtest in `test_real_sentence_does_not_fire` using prose
that opens with the same vocabulary
(`"Chapter 3 covers contract formation in detail"`,
`"Pages 22 to 25 cover the methodology"`, etc.) to guard against
false-drops.

### Length-cap bypass for section-numbered headings

`is_heading_shape` previously rejected any quote longer than
`HEADING_MAX_CHARS` (default 80). The T3 extension recognises a
section-numbered opening (Chapter/Section/Part/§ + number) and
allows such quotes through the length gate, while still applying
the other gates (non-heading characters, terminal punctuation,
finite verb). The implementation lives in `_starts_with_section_number`
and is called only when the quote already failed the length cap.

Caught (new):

- `"Chapter 14: Modern Trial Procedure In Contemporary American Courts"`
  (over 80 chars, no period, no finite verb → fires)
- `"Section 4.2: Definitions And Their Practical Application In Federal Litigation"`

Not caught (existing gates still apply on the bypass path):

- `"Chapter 3 covers contract formation across the major common-law
  jurisdictions in detail."` (terminal period → keeps)
- `"Chapter 3 has many sections on contract formation across the
  major common-law jurisdictions worldwide"` (finite verb `has` →
  keeps)

## Empirical measurement on smoke corpus

```
suite:                smoke (the canonical full-mode eval set)
mode:                 full
RETRIEVAL_USE_NODES:  false  (chunks branch)
total cases:          15
quote_total:          36
structural_citation_count: 0  (same as T2.0 baseline)
structural_citation_rate:  0.0
groundedness@8:       unchanged from T2.0 baseline
quote_validity:       unchanged from T2.0 baseline
```

The T3 additions do not move `structural_citation_count` because
the smoke corpus has no LLM-cited quote shaped like a chapter / page
range / equation / appendix reference (and zero long
section-numbered headings). The corpus is four small pedagogical
sources whose retrievable chunks rarely contain such structures.
This is the same situation T2 hit at landing and the same fact the
T2.0 baseline already documented.

## What this report says

- The T3 additions are surgical regex + a length-cap bypass.
- Unit-test coverage pins both directions: each new pattern fires
  on its target shape AND keeps a real sentence using the same
  vocabulary. The `tests/test_retrieval_quote_heuristics.py` suite
  grows from 39 to 49 test methods (4 new
  `BareReferenceTests` methods, 4 new `HeadingShapeTests` methods,
  2 new `StructuralQuoteIntegrationTests` methods).
- The closed-class verb detector is intentionally narrow (irregular
  list + `-ed/-ing/-en` suffix; `-s` / `-es` excluded so plural
  nouns don't false-positive). It does NOT catch all third-person-
  singular verbs ("covers", "offers", "explains"). The plan's
  documented kill condition for the verb detector (false-drop
  rate > 5% on the eventual labeled slice → spaCy ADR) is the
  empirical gate, not the unit-test bench.

## What this report does NOT say

It does NOT empirically demonstrate a drop in
`structural_citation_rate` against the T2.0 baseline. The smoke
corpus has zero structural traps in the first place; there is no
non-zero baseline to drop from. The slot-1 TODOS T3 acceptance text
("second-round drop measured") cannot be honestly satisfied without
either a labeled slice or a real-user corpus. The labeled slice
(`evals/cases/structural-citation.jsonl`) is escalated to operator
follow-up per ADR 0004 and per the T2.0 baseline report's
recommendation; T4's >=30% drop gate is gated on that slice landing.

## Implication for T4

T4 (default-on flip) was already pending on the labeled slice per
the T2.0 baseline report. T3 does not change that. T4 will run
full-mode evals with the flag explicitly off then on; the gating
metric remains
`structural_citation_rate drops >= 30% from the post-T2.0 baseline
AND groundedness@8 stays within 0.02 of baseline`. With the smoke
corpus alone, both numbers will be `0 → 0` and the test is vacuous;
with the labeled slice, the off-run produces the trap rate and the
on-run measures the heuristic's catch.

## Reproduce

```bash
RETRIEVAL_USE_NODES=false ./.venv/bin/python -m evals.run_evals \
  --mode full --suite smoke --report-dir /tmp/eval-t3/
```

Expected: same counts as the T2.0 baseline. Unit test bench:

```bash
PYTHONPATH=. ./.venv/bin/python -m unittest \
  tests.test_retrieval_quote_heuristics -v
```

Expected: 49 OK (T2's 39 + T3's 10 new methods across
`BareReferenceTests`, `HeadingShapeTests`, and
`StructuralQuoteIntegrationTests`).
