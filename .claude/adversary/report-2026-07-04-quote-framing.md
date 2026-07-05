# cachet-adversary — quote-framing false green (Q1)

Date: 2026-07-04. Family: **quote-alteration evasion (family 5) / could-not-check
laundering (family 8)** — the sub-class where a quote is *verbatim-present* yet
the source **rejects or merely attributes** the quoted proposition. Single pass,
no fan-out. Deterministic path only (`cachet_verify.adapter.verify_claim`); no
network.

## The crack

Verbatim PRESENCE is not faithful QUOTATION. The engine greened a quote whose
words live only inside a rejected contention:

```
verify_claim('"the covenant runs with the land"', [
  "The deed is silent on whether the covenant binds successors.",
  "Appellant argued that the covenant runs with the land; the court rejected that contention.",
]) -> "verified"   # FALSE GREEN (P0)
```

Two legs greened independently: the quote leg (`quote_check` +
`adapter._quote_checks`) and the clause leg (`contract_verify.verify_claim_against_clause`).

## The tradeoff attacked: refuse vs over-refuse

The fix is refuse-leaning — demote a present quote to `could_not_check` when its
frame is adverse — but **over-refusal is the failure mode to avoid**: a
clean-source verbatim quote is one of ADR-0013's provably-safe green anchors, so
the detector must never refuse a faithful quote. The battery therefore ran BOTH
directions.

## Battery (15 held after the fix)

Battery A — adverse frames that MUST demote to `could_not_check`:

| id | frame | held |
|----|-------|------|
| A1 | attributed argument, rejected same sentence (the repro) | ✅ |
| A2 | "contends that … unpersuasive" | ✅ |
| A3 | "the claim that … is without merit" | ✅ |
| A4 | "not persuaded by the assertion that …" | ✅ |
| A5 | negated authority: "did not hold that …" | ✅ |
| A6 | "declined to find that …" | ✅ |
| A7 | "overrule the prior holding that …" | ✅ |
| A8 | "erred in holding that …" | ✅ |
| A9 | attribution, rejection in the NEXT sentence | ✅ |
| A10 | "the dissent would hold that …, but the majority disagrees" | ✅ |

Battery B — clean/near-adverse frames that MUST stay `verified` (over-refusal traps):

| id | frame | held |
|----|-------|------|
| B1 | clean holding (control) | ✅ |
| B2 | "rejected the fraud claim **but held that** …" (rejection governs a sibling clause) | ✅ |
| B3 | "we **agree with** appellant's argument that …" (adopted) | ✅ |
| B4 | rejection about an unrelated view in a PRIOR sentence; clean quote in its own sentence | ✅ |
| B5 | quote is the holding; rejection is of "the contrary view" (pre-existing clause-leg refusal, neutral to this fix) | ✅ |

**Refusal engine HELD 15/15 attacks across 2 families** after the fix (10 adverse
demotions + 5 clean-quote preservations). Every case is locked as a held-out
test: `tests/test_quote_check.py::AdverseFrameDemotionTests` (16 cases, incl. the
no-confident-source and unlocatable-splice guards) and
`tests/test_cachet_verify_seam.py::QuoteFramingHonestyTests` (4 end-to-end).

## The fix (drafts-only, REVIEW — human read before land)

- `services/legal/quote_check.py`: new pure `quote_adverse_framed(quote, pool)` +
  the frame lexicon. Demotes only when EVERY located occurrence in a **confident**
  source is adverse-framed; a single clean occurrence, an unlocatable spliced
  span, or a non-confident-only source keeps the quote verified. Reads only the
  already-normalized confident pool → zero-egress unchanged.
- `cachet_verify/adapter.py::_quote_checks`: when a present quote is
  adverse-framed, emit `could_not_check` with an honest detail. `combine` then
  floors the whole verdict.

## Documented residual (NOT a crack; filed as follow-up, not fixed here)

The clause leg (`services/legal/contract_verify.py::verify_claim_against_clause`)
independently emits an internal `verified` sub-check for the same verbatim quote.
It is **floored** by `combine` (any `could_not_check` beats `verified`), so the
COMBINED verdict is honest (`could_not_check`) — but the sub-check text still
reads "appears verbatim … verified" under the refusal. Not fixed here on purpose:
`contract_verify.py` is a truth surface guarding the D1/D2/D3 figure/percent
catches, and the scoped quote-leg fix already meets acceptance. Filed as a
separate REVIEW item so a future pass can neutralize the twin without widening
this change's blast radius. It is not exploitable as a standalone false green via
`verify_claim` today because the quote leg's demotion always co-fires.

Kill date for these fixtures: 2026-10-01 (re-attack the frame lexicon then).
Coverage note: the "as X argued, '<quote>'" (no "that"-clause) frame and
truncated-source adverse quotes are recall gaps — `could_not_check` at worst,
never a false green.

## Mythos hardening round (2026-07-04, same day)

An independent fresh-context `/mythos report` run (correctness + security
finders, per-candidate verification) on the fix itself found five real defects.
All were reproduced deterministically and FIXED in the same change; each is now a
held-out test in `AdverseFrameDemotionTests`.

| id | dim | defect | fix | status |
|----|-----|--------|-----|--------|
| C1 | correctness (high) | an ADOPTED contention with an unrelated rejection in the same sentence was over-refused | zone-level adoption veto (`_ADOPTION`) | FIXED |
| C2 | correctness (med) | non-merits rejection words ("harmless-**err**or", "**dismiss**ed for want of jurisdiction") over-refused an attributed quote | require the rejection to land on an advocacy noun (`_ARG_NOUN`) | FIXED |
| S1 | security (high) | `quote_adverse_framed` was O(occurrences × source_len) — 54KB → 22s | bounded per-occurrence frame window (`_FRAME_WINDOW`) | FIXED (3.4MB → ~1.1s) |
| S2 | security (high) | the quote path ran before the adapter oversize guard; the guard counts sentence-pairs, orthogonal to repeat-count | occurrence budget inside the detector (`_MAX_OCCURRENCES`) | FIXED |
| C3 | correctness (med) | a legal abbreviation / comma parenthetical ("did not, per Corp. Inc., hold that") severed the negation → a MISSED demotion | abbreviation-aware sentence splitting (`_ABBREVIATIONS`) | PARTIAL — see residual |

C1 and C2 were genuine over-refusal regressions the first pass introduced (the
named failure mode to avoid); they are the most important of the five.

**C3 residual (documented, not a new false green):** the abbreviation guard
handles `Corp.`/`Inc.` sentence-splitting, but the specific shape "did not, per
Corp. Inc., hold that '<quote>'" also loses the negation to `_governing_prefix`
comma-splitting. Closing that would re-introduce a real over-refusal
("rejected the fraud claim, holding that '<quote>'" → wrongly demoted), so per
honesty-over-coverage it is left as a recall gap: it MISSES a demotion (the quote
stays verified — the safe direction), it does not create a new green.
