# Cachet verify: the unit-of-grounding limitation (2026-06-09)

## What

The deterministic verify engine grounds at the **sentence** level: the draft is
split into sentences (`services/legal/sentences.py::split_sentences`), and each
sentence becomes one claim card scored by its strongest anchor.

Two real consequences surface from this, found while validating the engine
end-to-end against a real uploaded source (Loving v. Virginia excerpt):

1. **A paragraph of multiple QUOTED holdings with NO inline citations collapses
   into one claim.** Example: `The Court held that "A." It then held that "B."`
   stays a single sentence, because the splitter deliberately does **not** treat
   a closing-quote boundary (`."`) as a sentence end. So both quotes land on one
   claim, and if any one quote can't be confirmed, the whole claim reads
   could-not-check, leaving the accurate quotes uncredited (it under-claims; it
   never over-claims).

2. **It is deliberate, not a bug.** The conservative splitter exists because the
   litigator pattern puts a citation immediately after a quoted holding:
   `... "Separate educational facilities are inherently unequal." Brown v. Board
   of Education, 347 U.S. 483.` Splitting on the `."` there would sever the
   holding from the citation that grounds it, breaking same-sentence quote
   attribution (and `tests/test_deterministic_envelope.py::test_correct_quote_is_verified`).
   Keeping holding+citation together is worth more than crediting the rarer
   no-citation quoted-holding case. Pinned by
   `tests/test_legal_sentences.py::test_quoted_holding_keeps_its_following_citation`.

## Why we did not "fix" it tonight

A naive fix (let `."` end a sentence) was tried and reverted: it split holdings
from their citations. The correct fix is **citation-aware** sentence splitting:
allow a `."` boundary only when the text that follows is NOT a citation. eyecite
gives citation spans, but they typically start at the reporter ("347 U.S. 483"),
not the party name ("Brown"), so the lookahead needs party-name detection too.
That is real work and was out of scope for the correctness pass.

## Impact

- Briefs **with** inline citations split fine (the `. ` after the citation is a
  normal boundary). This is the common litigator shape.
- Briefs of **bare quoted holdings without citations** (or contract summaries
  that quote clause language without a section anchor) under-credit. Safe
  direction (could-not-check, never a false present), but a worse experience.

## If/when we build the real fix

Make `_BOUNDARY` citation-aware: a `[.!?]["')\]]*\s+` boundary becomes a split
point only when the following token does not begin a citation (eyecite span OR a
`<Party> v. <Party>` / reporter pattern). Add cases to `test_legal_sentences.py`
for: quoted holding + new sentence (split), quoted holding + citation (no split),
quoted holding + party-name citation (no split).
