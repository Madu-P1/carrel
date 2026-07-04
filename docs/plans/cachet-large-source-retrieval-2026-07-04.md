# Plan — Lift the O(draft×source) ceiling: deterministic candidate retrieval for large sources

**Date:** 2026-07-04
**Owner task:** `L1` in `.claude/forge.engine.tasks.md` (`[REVIEW]`, drafts-only)
**Surface:** `cachet_verify/adapter.py` (the packaged kernel; a verdict truth surface)
**Invariant that must never break:** no false green. A `could_not_check` is always
preferred to a false "verified" or a false "no such value."

## Problem (grounded)

`verify_claim` compares each claim against **every** source sentence
(`cachet_verify/adapter.py:402`, `for entry in index.sentences`). The bound
`_too_large(claim_sentences, source_sentences) = product > 4_000`
(`adapter.py:83-87`) refuses whenever the product exceeds the ceiling; the
single-claim path evaluates `_too_large(1, index.sentence_count)`
(`adapter.py:394`), so **any source past ~4,000 sentences refuses outright**
with "too large to attest deterministically in bounded time." A ~1,000-page
document is tens of thousands of sentences and trips instantly. This makes
Cachet structurally unable to verify against large sources — the core product
promise.

Observed: a 7-sentence draft against a large source returns
`0 verified · 0 altered · 1 could_not_check` because the *source* blew the
ceiling. (Separately, the Lectern surface sends the whole draft as ONE claim by
calling `/verify` instead of `/attest`; that frontend wiring is a separate task,
`L0`, not this one.)

## The design — a superset FILTER, not a top-K ranker

Top-K ranking is where a false `could_not_check` (or a dropped contradiction →
false green) sneaks in. The safe design retrieves **all** source sentences that
share an exact key with the claim — a provable superset of what each exact-match
leg could ever compare — then runs the existing legs against that candidate set.

Two independent key namespaces, unioned before comparison:

1. **Quote leg — shingle index (provably complete).** Index every source
   sentence by its `w`-word shingles, where `w` is the SAME minimum n-gram width
   the verbatim quote matcher uses (`_quote_checks` / the quote pool). Any
   verbatim quote of length ≥ `w` shares ≥1 shingle with the source sentence
   containing it, so "all source sentences sharing ≥1 shingle with the claim" is
   a superset of every sentence the quote matcher could match. No threshold, no
   score, no K.

2. **Contradiction / residue / clause leg — anchor+topic index.** A contradicting
   sentence ("counter-offer of £950" vs a claim's "£850") shares the *subject/topic*
   vocabulary, not the value. Index every source sentence under its residue
   anchors AND its content-topic tokens (reuse the existing
   `_topic_tokens`/stopword helper). The residue/clause legs retrieve any source
   sentence sharing a topic token with the claim's residue/service span. This
   guarantees the `same_fact_disagreement` veto (`adapter.py:448`) still sees the
   contradicting sentence — the candidate set can never silently omit a
   same-subject different-value sentence.

**Candidate set fed to the legs = union(quote candidates, residue/clause
candidates).** Never an intersection.

## Granularity — stay per-sentence

Per-sentence, matching `split_sentences` and the existing per-sentence legs.
Chunking is rejected: a verbatim quote could straddle a chunk boundary and break
the superset guarantee. The index is sentence-keyed.

## The ceiling changes meaning (does not vanish)

Replace "source too big" with "this CLAIM matched too many candidates." After
filtering, if a claim's candidate set exceeds a per-claim bound (e.g. the same
4,000, but now candidates-per-claim, not total source), refuse THAT claim as
`could_not_check` — honest, and only a stopword-only/degenerate claim hits it.
Cost becomes O(draft_sentences × candidates_per_claim), independent of source
size.

## The ship gate — a recall-completeness PROPERTY TEST (the crux)

The whole no-false-green safety rides on "the candidate set is a superset of what
brute force would compare." That is a testable property, and it is the ship
authority for this task:

- **P1 (equivalence):** for a corpus of randomized `(claim, sources)` pairs
  (varying quote overlaps, altered figures, contradictions, negation flips,
  proper-noun swaps, and no-match cases), the NEW indexed `verify_claim` returns
  a byte-identical `Attestation.state` and check set to the OLD brute-force
  `verify_claim` on the same input. Same for `attest_draft`. This proves the
  index changes cost, never verdict.
- **P2 (superset, direct):** for randomized `(claim, source_sentences)`, the
  retrieved candidate index set ⊇ the set of source sentences the brute-force
  scan would have compared and produced a non-None leg outcome for. Assert
  superset directly, not just equal verdicts.
- **P3 (scale):** a source with >100k sentences and a small draft attests every
  claim (no oversize refusal from source size alone) within the wall-clock bound;
  a genuinely degenerate stopword-only claim still refuses as `could_not_check`.
- **P4 (no catch weakened):** the existing altered-figure / fabricated-quote /
  contradiction fixtures across the cachet_verify suites still catch. Add a
  fixture reproducing the real behavior this change touches (per the contract's
  REAL-WORLD REGRESSION RULE): a large source where an altered quote still reads
  altered and a fabricated case still reads could_not_check.

If P1–P4 cannot all be made deterministic fixtures, the task stays REVIEW-gated
(it already is) and does not auto-ship.

## Constraints preserved

Zero-egress (pure in-process exact-token index, no socket), no embeddings, no new
runtime dependency, fully deterministic (exact keys, no scoring). The index is
built ONCE per request inside the existing `SourceIndex`/`build_source_index`
seam — extend it, do not add a parallel structure.

## Steps (small, reversible)

1. Extend `SourceIndex` with two inverted maps built during
   `build_source_index`: `shingle -> {sentence_ids}` and
   `topic_or_anchor_token -> {sentence_ids}`. Pure addition; nothing reads them
   yet. Green.
2. Add `candidate_ids(claim) -> frozenset[int]` on `SourceIndex` = union of the
   two lookups. Unit-test it against brute force (P2). Green.
3. Route `verify_claim`'s per-sentence loop and the quote leg through
   `candidate_ids` instead of `index.sentences` / full pool. Behind the P1
   equivalence test. Green.
4. Change `_too_large` at the call sites to bound candidates-per-claim, not
   source size. Add P3. Green.
5. Add the large-source real-behavior fixture (P4). Green.

## Acceptance → see task `L1` in the queue. Verify with the cachet_verify suites
(the Forge contract's default `engine-suites` do NOT cover `cachet_verify/`; the
task adds them explicitly), ruff over `cachet_verify`, and `tests.test_zero_egress`.
