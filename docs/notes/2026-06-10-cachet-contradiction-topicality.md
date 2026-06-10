# Decision needed: should parametric contradictions carry the on-topic gate?

Status: OPEN. Required before any parametric anchor type beyond percent ships
(per docs/plans/2026-06-10-cachet-percent-anchor.md). Operator call: the two
failure directions trade off against each other and the right balance is a
product judgment, not an engineering one.

## The asymmetry, live-demonstrated (2026-06-10 adversarial review)

`_contract_claim` (services/legal/deterministic_envelope.py:467-484) applies
the C3 `_clause_on_topic` relevance gate ONLY to `present` verdicts; a
`parametric_contradiction` is accepted from ANY retrieved top-3 clause, and the
loop breaks on the first one. Reproduced live: with a corpus containing only
"The executive's annual bonus equals 40% of base salary.", the draft "The
aggregate liability is capped at 50% of fees paid." reads
`parametric_contradiction` — "The summary states 50%; your loaded sources
states 40%." A liability-cap claim accused with an executive-bonus clause.
Sibling shapes: "The late fee is 2%." accused with an 8%-interest clause;
"The licensee retains 95% of net revenues." accused with the licensor's
mutually consistent "5% of net revenues" complement.

Percent materially widens the exposure: percent values collide across
unrelated clauses far more often than exact dollar figures (5%/10%/50% recur
in interest, bonus, royalty, and basket clauses).

## Why it was built this way (the argument for the status quo)

Gating contradictions on topicality MASKS real contradictions: the relevance
signal is the same retrieval that ranked the clause; a falsified value tends to
LOWER lexical/semantic overlap with its true clause, so a topicality gate would
preferentially suppress exactly the catches the product exists for. A false
accusation is recoverable in the UI register (the lawyer reads both quoted
values and the named section, sees the mismatch is about a different subject);
a masked contradiction is the silent green, the worst direction. ADR-0012
invariant 2 prefers refusing to guessing, but a contradiction is not a guess —
both values are real extractions; what is uncertain is only whether they refer
to the same predicate.

## The candidate positions

1. **Status quo** (contradictions ungated): maximum catch rate; the
   false-accusation class above persists and grows with each value-dense
   anchor type.
2. **Symmetric gate** (contradictions need on-topic too): kills the class but
   demonstrably suppresses true catches whose clause ranks low; the failure
   becomes invisible (could-not-check) instead of visible (a wrong accusation
   a lawyer can dismiss).
3. **Middle path**: keep contradictions ungated but stop breaking on the first
   one — scan all top-k; if ANY clause yields `present` for the same anchor
   type, prefer the refusal (`multi_value_unverifiable`-style "conflicting
   clauses, review both") over either verdict. Honest in both directions, at
   the cost of a new disposition nuance.
4. **Residual sibling-laundering**: whatever is decided, the class the percent
   build does not close (e.g. a word-form money value riding a matching
   duration into `present`) belongs to this same decision.

## Decision inputs to gather

Real false-accusation rate on representative AI contract summaries (the
Lebanon/GCC validation interviews can carry a fixture set), and whether lawyers
read an off-topic accusation as a tolerable nuisance or a credibility kill —
the Harvey prior says a wrong accusation burns trust almost as fast as a wrong
green, which argues for option 3 over 1.
