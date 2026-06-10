# Percent anchors: the next deterministic engine build

Decided 2026-06-10 by an adversarially-arbitrated research round (5 ground-truth
maps, ranked candidates, proponent vs adversary with every load-bearing claim
re-executed live in the worktree, cold synthesis). The verdict's full text lives
in the session workflow journal; this plan is its executable form.

## Why percent, and why now

Two live-verified defects drive the scope:

1. **The percent gap mints an affirmative false "present" today.** Percent is
   absent from `_PARAMETRIC_TYPES` (services/legal/contract_verify.py:33), so
   "capped at 99% of fees paid in the prior 12 months" checked against a clause
   that says 50% returns `present` — the matching 12-month duration carries the
   verdict and the engine renders a green "Present in your sources" card for a
   falsified cap. The C2 laundering guard re-checks only quotes
   (deterministic_envelope.py:505-519), not sibling values. An affirmative false
   green in the moat wedge (liability caps, interest rates, revenue shares,
   indemnity baskets) is the product's worst failure class, and it is in the
   engine now.

2. **The word-form money guard leaks compounds.** `_MONEY_WORD`'s `(?<![\w-])`
   guard (services/legal/anchors.py:71) blocks "twenty-five million" but not
   "twenty five million": the detector matches the tail ("five million dollars")
   and canonicalizes $5,000,000 out of a twenty-five-million sentence. Verified
   live: this mints both a false `present` against a $5M clause and a false
   `parametric_contradiction` (a manufactured accusation, the forbidden
   direction) against the correct $25M clause. The comment claiming out-of-scope
   forms "stay an honest could-not-check" is also stale: since the 2026-06-08
   untreated split, an anchor-free sentence renders as plain text, not a card.

The word-form GRAMMAR EXTENSION (compound money words, spelled-out durations)
was argued as candidate #1 and REJECTED: it is ADR-0012's rejected Alternative C
("do not chase fractal regex edges"), its recall value is a corpus-test unknown
flagged twice by the 2026-06-05 extraction note, every wrong canonical value is
a manufactured accusation, and the live leak above is evidence the existing
bounded grammar already over-reaches. The remedy for a leaking boundary is to
seal it, not enlarge it.

## PR-0 (mandatory rider, ships first): seal the word-form money boundary

- Reject a `_MONEY_WORD` match whose preceding text ends with a number word
  (space-separated compound the bounded grammar cannot represent): no anchor,
  never a wrong value.
- Pin with tests: "twenty five million dollars" → no money anchor;
  "one hundred twenty five million dollars" → no money anchor; the simple forms
  ("five million dollars", "a billion dollars", "five hundred thousand
  dollars") keep their exact canonicals.
- Correct the stale "stay an honest could-not-check" comment: such sentences
  render UNTREATED (no card) post-2026-06-08 split; the gap is pinned, not
  hidden.

## PR-1 (the build): digit-form percent/rate parametric anchors

Detector (services/legal/anchors.py):
- `percent` anchor type, DIGIT forms only with the unit marker in-span:
  `5%`, `12.5 percent`, `12 per cent`, `50 bps`, `50 basis points`.
- Canonical value: basis points, exact decimal arithmetic (5% → 500; 12.5% →
  1250; 0.01% → 1; 50 bps → 50). Exact equality, no tolerance.
- Refusals, pinned by tests, never a guessed value: word-form percent ("five
  percent" — same lesson as PR-0), range forms ("5-10%" — guessing either end
  manufactures a verdict), "percentage points" (different semantics from
  percent; deferred), bare numbers without an in-span unit.
- "fifty percent (50%)" yields exactly ONE anchor (the digit form).

Wiring:
- `_PARAMETRIC_TYPES` += "percent" (contract_verify.py:33); `_values_match`
  exact-equality branch already covers it.
- `_CLAUSE_CHECKABLE` += "percent" (deterministic_envelope.py:58) so a
  percent-only sentence routes to the clause check.
- Zero wire/UI changes: anchor internals are server-side; the verdict mapping
  (services/verify.py:173-180) already renders all four dispositions.

Tests (the established pattern, tests/test_anchors.py + test_contract_verify.py
+ one integration case):
- Canonical sweep, false-positive sweep, offset integrity, overlap guard.
- Clause dispositions: present (5% vs 5%), THE laundering case (99% + matching
  12-month duration vs a 50% clause flips present → parametric_contradiction),
  not_found, multi-value refusal (two percents on one side).
- Integration: a percent contradiction through real retrieval over seeded
  contract nodes, plus card↔reason consistency.

## Explicitly out of scope (each with a reason)

- Word-form percent and any word-form money/duration grammar extension:
  corpus-tested recall question per ADR-0012 Alternative C; re-enters only with
  data.
- Percentage-point vs percent semantics: deferred, pinned by a no-anchor test.
- "X% of Y" predicate matching (the value matches but the base differs):
  value-only matching is the deterministic contract; the C3 on-topic gate
  (deterministic_envelope.py:469-477) is the existing mitigation.
- Contradiction topicality / sibling-value laundering in general (requiring ALL
  carried types to match before `present`): verdict-logic redesign. REQUIRED
  FOLLOW-UP: a decision note weighing false-accusation exposure against
  contradiction-masking before any parametric type beyond percent ships. The
  residual class the percent build does not close (e.g. word-form money riding a
  matching duration) belongs to that note.

## Gate

ruff check + format on touched paths; the engine unittest suites
(test_anchors, test_legal_sentences, test_citations_eyecite, test_local_caselaw,
test_deterministic_envelope, test_contract_verify,
test_contract_verify_integration, test_align, test_demo_corpus,
test_zero_egress) — 188 green at baseline in this worktree; adversarial code
review on the diff; then commit and push.
