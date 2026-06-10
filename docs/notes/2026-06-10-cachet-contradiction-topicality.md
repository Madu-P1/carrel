# Decision: should parametric contradictions carry the on-topic gate?

Status: DECIDED 2026-06-10 (operator delegated the call; built the same day).
Ruling: option 3, refined. Contradictions stay ungated by topicality, but the
clause loop no longer breaks on the first contradiction: ALL top-k clauses are
evaluated, and a contradiction stands only when NO retrieved clause carries the
claim's value for that anchor type. When both signals exist (a present and a
contradiction for the same type, different clauses), the engine cannot
deterministically know which clause governs, so it REFUSES with both clauses
and both values named ("conflicting clauses, review both") — certainty is
manufactured in neither direction (ADR-0012 invariant 2). Off-topic presents
never earn a green (C3 unchanged) but DO veto an accusation: a value verbatim
anywhere in the retrieved clauses makes accusing from a different clause a
guess.

Rejected alternatives, with reasons:
- Option 1 (status quo): the false accusation is live-demonstrated and grows
  with every value-dense anchor type; it also blocked the parametric roadmap.
- Option 2 (symmetric topicality gate): a falsified value LOWERS overlap with
  its true clause, so the gate preferentially suppresses exactly the catches
  the product exists for, and invisibly (could-not-check instead of a visible,
  dismissible accusation).
- Present-wins (the intent of the old code comment "clause B's $600k must not
  contradict a claim whose $500k clause A confirmed" — which the rank-order
  break never actually delivered): a value coincidence in any on-topic-ish
  clause would mask a TRUE contradiction with a green, the worst failure
  class. The amended-contract scenario decides it: two clauses governing the
  same subject with different values; present-wins paints green on the
  superseded value, the conflict refusal surfaces both.

Known cost, accepted (both directions, per the adversarial review of the
build): the conflict refusal demotes a green when the contradicting clause is
noise, AND demotes a true contradiction when the coinciding present is noise
(a $1M insurance minimum beside the $1M-vs-$500K cap catch). The second is the
sharper case. Gating the VETO on the C3 relevance signal was considered and
rejected: the two cases are symmetric to the machine (the relevance floor is
too weak to say which clause governs), and an on-topic-gated veto would let an
off-topic accusation fire while the claim's value sits verbatim one clause
over — the exact manufactured-accusation shape this decision kills. The
refusal names both clauses and both values, so a demoted catch is surfaced,
not hidden; the cost is salience, not truth. Follow-ups: a demotion counter in
the eval harness so the validation interviews measure the real rate, and a
recorded subordination — when an uncontested contradiction of one type wins,
a contested conflict of another type in the same sentence is not separately
reported. If the measured rate is too high, the revisit is recorded here,
with evidence, not by reverting to a guess.

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
