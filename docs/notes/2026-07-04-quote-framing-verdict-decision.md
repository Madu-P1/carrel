# Quote-framing verdict decision (Q1)

2026-07-04. Engineering note recording the decision behind the Q1 fix:
demoting a verbatim quote that greens inside a rejected or attributed frame.
Authored alongside the fix (branch `claude/vibrant-wu-d6c9fc`), not a
pre-existing spec.

## The defect

The deterministic engine greened a quote on verbatim PRESENCE alone:

```
verify_claim('"the covenant runs with the land"', [
  "The deed is silent on whether the covenant binds successors.",
  "Appellant argued that the covenant runs with the land; the court rejected that contention.",
]) -> "verified"
```

The quoted words are real, but they live only inside a rejected contention.
Verbatim presence is not faithful quotation.

## F-A. The refuse-vs-over-refuse decision

**Recommendation:** demote a present quote to `could_not_check` when its source
frame is adverse (attributed-and-rejected, or negated authority), never to a new
green.

**Steelman against:** verbatim quotes are one of ADR-0013's provably-safe green
anchors. A frame detector is a heuristic; the moment it over-refuses a faithful
quote ("the court rejected the fraud claim **but held that** '<quote>'"), it
poisons the single most trustworthy green the engine has. Better to leave the
quote leg alone and accept the false green as a known residual than to bolt an
NLP-ish frame classifier onto a trust surface.

**Test against it, and where it lands:** the counter is right that over-refusal is
the worse error here, so the fix is built to fail SAFE toward *verified*, not
toward refusal:

1. It demotes only when EVERY located occurrence in a **confident** source is
   adverse-framed. One clean occurrence keeps the quote verified.
2. The adverse signal is tied to the clause that **governs** the quote (the tail
   after the last clause-break before the quote), so a rejection of a sibling
   clause ("rejected the fraud claim **but held that** '<quote>'") does not taint
   it. This is what keeps B2/B3/B4 verified.
3. If the span cannot be located contiguously (a spliced / ellipsis-bridged
   quote), it does NOT demote — it cannot read the frame, so it declines to
   refuse rather than guess.

The counter changes the *construction* (governing-clause binding + confident-only
+ locate-or-abstain), not the direction. A `cachet-adversary` round ran FIRST on
exactly this tradeoff and the detector HELD 15/15: 10 adverse frames demoted, 5
clean-quote traps preserved. Report:
`.claude/adversary/report-2026-07-04-quote-framing.md`.

## Scope decision: quote leg only, clause leg left floored

Two legs greened the repro independently: the quote leg and the clause leg
(`contract_verify.py::verify_claim_against_clause`). `combine` floors the whole
verdict to `could_not_check` as soon as the quote leg refuses, so fixing the
quote leg alone meets acceptance. The clause leg's twin verbatim-quote green is
left in place on purpose — `contract_verify.py` guards the D1/D2/D3 figure and
percent catches, and widening the change there is unjustified risk when the
verdict is already honest. Filed as a separate REVIEW follow-up (see the queue
entry and the report's "documented residual").

## What shipped

- `services/legal/quote_check.py`: `quote_adverse_framed` + frame lexicon (pure,
  reads only the normalized confident pool; zero-egress unchanged).
- `cachet_verify/adapter.py::_quote_checks`: the demotion + honest detail.
- Held-out tests: `tests/test_quote_check.py::AdverseFrameDemotionTests`,
  `tests/test_cachet_verify_seam.py::QuoteFramingHonestyTests`.

Gate: 590 engine tests, ruff check + format, zero-egress — all green.
Drafts-only; REVIEW; human read before land.

## Mythos hardening round (same day)

An independent `/mythos report` pass (correctness + security finders) on this fix
found five real defects; all reproduced and were fixed in-change:

- **Over-refusal (C1/C2, the primary mandate):** the first pass bound the
  attribution to the governing clause but scanned the WHOLE sentence for a
  rejection, so an ADOPTED contention with an unrelated rejection, or an
  incidental "harmless-error"/"dismissed" token, wrongly demoted a faithful
  quote. Fixed with a zone-level adoption veto (`_ADOPTION`) and a requirement
  that the rejection land on an advocacy noun (`_ARG_NOUN`).
- **Quadratic DoS (S1/S2):** `_sentence_and_next` re-scanned the whole source per
  occurrence (54KB → 22s) and ran before the adapter's sentence-pair oversize
  guard. Fixed with a bounded per-occurrence frame window (`_FRAME_WINDOW`) and an
  occurrence budget (`_MAX_OCCURRENCES`); a 3.4MB repeat-pad now returns in ~1.1s.
- **Abbreviation split (C3):** `Corp.`/`Inc.` mid-sentence broke the frame. Fixed
  the sentence splitter to be abbreviation-aware (`_ABBREVIATIONS`). One narrow
  shape — a comma parenthetical splitting a negation ("did not, per Corp. Inc.,
  hold that '<quote>'") — remains a documented residual: it MISSES a demotion
  (stays verified, the safe direction), and closing it would re-introduce a real
  over-refusal, so honesty-over-coverage keeps it as a recall gap.

Every finding is now a held-out test in `AdverseFrameDemotionTests`.
