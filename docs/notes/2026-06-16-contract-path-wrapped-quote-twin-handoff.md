# Handoff: contract-path twin of the hard-wrapped-quote attribution fix

Date: 2026-06-16
For: a fresh session that will do the contract-path port
Owner branch to start from: `main` once this PR lands (commits `4b04374db`, `46bd1d69f`, `bc4c7bca0`)

## One-line summary

The litigator altered-quote pass was just fixed to attribute a quote across a hard
line wrap (logical-sentence grouping). The contract clause-quote check has the same
shape and the same latent gap, but it is a **recall** gap, not a false-green gap
(empirically confirmed below). This is the follow-up to apply the same reflow to the
contract path and lock it with a committed regression test.

## Why this exists

`split_sentences` (commit `3374549af`) splits drafts on every hard newline so slide /
bullet drafts segment per line. That stranded a hard-wrapped quote from the citation
on the next line, silently killing the litigator doctored-quote refusal. The fix
(`46bd1d69f`, refined by `bc4c7bca0`) added
`services/legal/sentences.py::split_sentences_with_groups`, and the litigator
altered-quote pass in `services/legal/deterministic_envelope.py` now pools opinions by
**logical sentence** and checks the reflowed text. See memory
`cachet-line-split-breaks-quote-attribution` and
`docs/notes` history for the full root-cause.

The **contract** clause-quote check did NOT get that treatment.

## Where the contract gap lives

`services/legal/deterministic_envelope.py`, in `_contract_claim`, the **C2
anchor-laundering guard** (around line 743-756 as of this PR):

```python
if (
    verdict.disposition == "present"
    and verdict.anchor_type != "quote"
    and matched_clause is not None
):
    quote_reason = _quote_unverified_reason(sentence, [matched_clause])
    if quote_reason:
        claim["quote_could_not_check_reason"] = quote_reason
```

`sentence` here is the **per-line surface segment** from the build loop's
`for i, sentence in enumerate(sentences)` (where `sentences, sentence_groups =
split_sentences_with_groups(draft)`). It is NOT the reflowed logical text. So when a
contract claim hard-wraps a quoted holding across two physical lines, the quote's own
words sit in a different segment than the presenting anchor, and the C2 guard cannot
re-check the wrapped quote against the matched clause.

The other contract quote site, `services/legal/contract_verify.py:951`
(`if anchor.type == "quote" and verbatim_run_present(anchor.text, clause)`), is
whitespace-blind via `verbatim_run_present` -> `normalize_for_verbatim`, so it is NOT
at risk from segmentation. Leave it; it is documented as safe.

## What it is and is NOT (empirically established 2026-06-16)

It is **NOT a false green.** A throwaway probe ran the full contract envelope over the
50%-royalty clause with a fabricated holding that is absent from the clause, in both a
same-line and a hard-wrapped layout, and checked every card via
`services.verify._verify_result_from_envelope`:

- same-line: one card -> `unknown` (the C2 guard fires; the fabricated quote
  downgrades the percent-present to could-not-check).
- wrapped: two cards -> line 1 `verified` (legitimately about the 50%, holds no
  fabricated quote) + line 2 `unknown` (the fabricated holding, not verified against
  the clause).

In neither layout does the fabricated holding appear in a `verified` card. The
inviolable promise (never green a fabricated/altered claim) holds on the contract path
after the per-line split. This is why this PR merges safely without the port.

It IS a **recall / coverage** gap: a hard-wrapped contract quote becomes its own
could-not-check card instead of being re-checked against the matched clause as part of
the laundering guard. That is the safe direction (could-not-check, never a false
accusation), but it is less coverage than the litigator path now has.

## The task

1. Apply the same logical-sentence reflow the litigator pass got to the contract C2
   guard. The build loop already computes `sentence_groups`; pool the C2 quote check by
   logical group and run `_quote_unverified` on the reflowed logical text, then attach
   any reason to the surface segment that holds the flagged phrase (reuse
   `_segment_holding_quoted_phrase`, added in `bc4c7bca0`). Mirror the litigator
   altered-quote pass at the bottom of `build_deterministic_envelope`; do not duplicate
   the reflow logic, factor the shared piece if it reads cleanly.
2. Keep the C2 guard's precondition intact (only `present`, non-`quote`, with a
   `matched_clause`). After the money/duration scope-out (`4b04374db`), the live
   `present` anchor types reaching the guard are percent / date / governing_law /
   polarity, not money/duration. Confirm that against the current `verify_claim_against_clause`.
3. Decide the matched-clause set when pooling: the litigator pass pools opinions across
   a group; the contract C2 guard re-checks against the SINGLE `matched_clause` of the
   presenting segment. When the quote is stranded on a sibling segment, you need the
   presenting segment's `matched_clause` available at the point you check the reflowed
   text. This is the one piece of real design here. Do not regress the same-line case.

## Tests to bring / write (the trip-wire)

A sibling session left `ContractWrappedQuoteTests` on branch
`friendly-khayyam-55ec9d` (commit `221b31be7`, pushed, no PR) — 5 tests that fail
loudly under a per-line split, verified non-vacuous by monkeypatch. Pull those over
and make them pass for real (not by monkeypatch). Add at minimum:

- a wrapped contract quote that IS verbatim in the clause -> not flagged;
- a wrapped contract quote that is ABSENT from the clause, riding a percent/date
  present -> the present downgrades to could-not-check (the coverage the port adds);
- the same-line case stays unchanged (regression guard);
- the no-false-green property: assert no `verified` card ever contains a fabricated
  wrapped holding (the probe from this handoff, made into a committed test). The probe
  harness is `tests/test_contract_verify_integration.py` (`_DeterministicEmbedder`,
  `_node`, `build_deterministic_envelope`, `verify_service._verify_result_from_envelope`).

## Acceptance

- The new contract-wrapped-quote tests pass for real.
- `script/cachet-acceptance.py` over the collision / injection / contract corpora stays
  at zero false greens.
- The full Python verify chain stays green (the canonical unittest list in `CLAUDE.md`,
  plus ruff, phase0 no-regression, t1_calibration).
- No false accusation introduced: a wrapped quote that cannot be checked must read
  could-not-check, never "altered" / "fabricated".

## Pointers

- Litigator fix commits: `46bd1d69f` (grouping) + `bc4c7bca0` (target the quoted span).
- Memory: `cachet-line-split-breaks-quote-attribution`, `cachet-money-duration-false-green`,
  `cachet-verify-three-failure-layers`, `cachet-verify-segmentation-fix`.
- Sibling trip-wire branch: `origin/claude/friendly-khayyam-55ec9d` (`221b31be7`).
