# Handoff: fix the false greens an xhigh code-review found in PR #179

Date: 2026-06-16
For: a fresh session doing a focused correctness fix pass
Branch to work on: `claude/crazy-brahmagupta-301932` (HEAD `bedd143a1` at time of writing). These
defects live on the BRANCH, not on `main` — `main` (`efbac6c3b`) does not have any of these
commits yet. Fix here so PR [carrel#179](https://github.com/Madu-P1/carrel/pull/179) becomes
mergeable; do NOT merge #179 until every CONFIRMED false green below is closed and locked by a test.

## Status / why this exists

An extra-high-effort `/code-review` (9 finder angles + verifiers) over `git diff origin/main...HEAD`
(15 commits of Cachet deterministic-verify work) found **multiple reproduced false greens** — the
engine rendering a `verified` card over a fabricated/altered claim. That is the one inviolable
failure ("never green a fabricated/altered claim"). The merge was BLOCKED and #179 is held.

Important correction recorded for whoever picks this up: an earlier single-probe check in this
session declared the branch "verified safe, no false green." That was wrong — the probe was too
narrow (one layout) and missed everything below. Trust the adversarial corpus + per-defect repros,
not a single hand-built example.

Two of the false greens (3, 5 below) are in the litigator passes from commits `46bd1d69f` /
`bc4c7bca0`; one (4) is in the contract laundering port `bedd143a1`; the percent ones (1, 2) are in
`5ebd96ba1`. They were missed by the earlier per-commit reviews because no test exercised
multi-quote groups, multi-present groups, union pooling, or partial subject matches.

## Root causes (fix these patterns, not just the instances)

- **A. Union pooling.** The new logical-group passes check a quoted phrase against the UNION of a
  group's clauses/opinions, instead of against the single source the quote actually rides. A union
  is strictly more lenient: a fabricated quote that is verbatim in an unrelated co-grouped source is
  treated as present -> false green. Affects findings 3, 4, 5; widened by 6.
- **B. Partial-match precedence.** `present` is returned when only SOME of a claim's subjects/keys
  match the clause, ignoring the ones the clause is silent on. `present` then outranks the
  `not_found`/`multi_value` the unmatched part should have produced -> the unconfirmed part rides a
  green. Affects findings 1, 2, 13. The safe rule: return `present` only when EVERY subject/key the
  claim asserts is matched; otherwise could-not-check (`not_found` / `multi_value_unverifiable`).

## Findings (ranked; CONFIRMED = reproduced end-to-end this session)

Line numbers are approximate — grep the named symbol.

### False greens (block the merge)

1. **`_subject_aware_percent` partial-match -> `verified`.** `services/legal/contract_verify.py`
   ~line 593 (the `matched = [...]; if matched: return ClauseVerdict("present", ...)` branch).
   Repro: clause "The royalty rate is 10% France."; draft "The royalty rate is 10% France and 20%
   Germany." -> card `verified` ("10% appears in Section 5"); the fabricated 20% Germany rides green.
   Was `multi_value_unverifiable` (safe) for the subject-less equivalent. CONFIRMED e2e.
   Fix (pattern B): `present` only if `set(claim_subj) <= set(clause_subj)` (every claim subject
   matched); else `not_found`/`multi_value_unverifiable`. The function's own docstring already
   promises this ("a claim subject the clause is silent on is not_found, never a green") — the
   `matched` branch violates it.

2. **Subject-aware percent present skips a sibling subject-LESS altered percent.**
   `services/legal/contract_verify.py` ~line 796 (the percent branch of
   `verify_claim_against_clause` that does `present_verdict = present_verdict or sa; continue`).
   A subject-less percent is excluded from `claim_subj`, so when one subject-bound percent agrees the
   function returns present and the caller `continue`s past the value-only multi-value gate; an
   altered/absent subject-less percent in the same sentence is never checked. Repro: source "10%
   France ... surtax of 7%", draft "Band 10% France holds; the surtax is 20%." -> present. CONFIRMED.
   Fix: same as 1 — do not green when there are unmatched percents on either side (subject-bound or
   not). Re-converge with the value-only multi-value path instead of short-circuiting it.

3. **Litigator altered-quote pass flags only the FIRST bad phrase per group.**
   `services/legal/deterministic_envelope.py` ~line 1048 (the post-loop calling `_quote_unverified`,
   which returns on the first miss ~line 443) + `_segment_holding_quoted_phrase` attaching ONE reason
   to ONE segment. Repro: one hard-wrapped logical sentence with two ALTERED quotes, each a real
   cite (Brown 347 U.S. 483 + Obergefell 576 U.S. 644); only the first segment downgrades, the second
   reads `verified` by case-existence. CONFIRMED e2e.
   Fix (pattern A-adjacent): collect ALL unverified phrases in the group (not just the first) and
   attach a reason to each phrase-holding segment. Keep `_quote_unverified`'s single-return contract
   for its other caller, or add a variant that yields all misses.

4. **Contract laundering pass pools ALL present-clauses (union).**
   `services/legal/deterministic_envelope.py` ~line 1087 (`_quote_unverified(logical_text,
   present_clauses)` over the pooled `present_clauses`). A fabricated quote absent from its own
   present's clause but verbatim in an unrelated co-grouped present's clause -> not flagged -> both
   cards `verified`. CONFIRMED e2e. This is in the port `bedd143a1`.
   Fix (pattern A): check each present member's wrapped quotes against ONLY that member's own
   `clause_text`, not the union. Mirror the per-segment C2 guard's precision the comment claims.

5. **Litigator pass pools ALL opinions (union).** `services/legal/deterministic_envelope.py`
   ~line 1051 (`pooled = [op for i in members for op in opinions_by_sentence.get(i, [])]`). A
   fabricated quote attributed to cite-A but verbatim in pooled cite-B's opinion -> not flagged.
   CONFIRMED (function level). Fix (pattern A): attribute each quoted phrase to the opinion(s) of the
   cite in its OWN segment/clause, not the group union. This is the harder design piece — wrapping
   means a quote and its cite can be on different segments of one logical sentence, so "its own cite"
   = the cite(s) within the same logical sentence whose span the quote belongs to. Decide the
   attribution unit deliberately; do not regress the wrapped-quote-with-its-own-cite case (the
   original litigator fix this session shipped).

6. **`_split_line_sentences` merges separate sentences on a lowercase continuation.**
   `services/legal/sentences.py` ~line 70, the `_BOUNDARY` regex requires `[A-Z0-9]` after the
   terminator, so "...holding.\nbrown 347 U.S. 483 confirms it." never splits in the whole-draft
   logical splitter and groups as ONE logical sentence. Breaks "proximity is not attribution" and
   enlarges the pools feeding 3-5. CONFIRMED (`split_sentences_with_groups` returns repeated group
   ids). Fix: treat a real terminator + whitespace as a boundary regardless of the next char's case
   (or at least for newline-separated lines), without regressing the abbreviation / citation
   suppression already in `_split_line_sentences`. This interacts with the documented `."`
   closing-quote rule — keep that, fix only the lowercase-continuation merge.

### False accusations / weakened catches (secondary invariant)

7. **`_canonical_figures` asymmetric skip -> faithful figure accused.**
   `services/legal/contract_verify.py` ~line 146 + the near-copy altered-figure pass. Claim "1.2
   billion" vs source "1,2 billion" (ambiguous comma-decimal, same intended value): the function
   skips the comma-decimal on the clause side only, so the claim figure reads "not found in the
   source" -> `parametric_contradiction` accusing a faithful figure. CONFIRMED e2e. Fix: make the
   skip symmetric — if either side has an uncanonical/ambiguous figure at the same position, bail to
   could-not-check rather than accuse.

8. **Fabricated-caption catch masked to `unknown`.** `services/verify.py:351` — in
   `_claim_dict_to_verdict` the `quote_could_not_check_reason` branch is checked BEFORE the
   case-verdict caption-mismatch branch. A fabricated caption on a real number ("Smith v. Jones, 347
   U.S. 483") that also carries an unverifiable quote reads `unknown` ("could not verify the quote")
   instead of `unsupported` ("resolves to a different case") — softening a core litigator catch.
   CONFIRMED e2e. Fix: a hard `unsupported` (caption mismatch / fabricated section) must outrank a
   could-not-check quote reason in the precedence chain.

9. **Contract laundering stamps the reason on EVERY present member.**
   `services/legal/deterministic_envelope.py` ~line 1091 (`for i in present_members: ...
   setdefault(...)`). A clean present-A (its own quote verbatim in its own clause) gets downgraded to
   `unknown` with a reason naming a DIFFERENT member's fabricated quote. Over-refusal + wrong
   attribution. CONFIRMED. Fixed naturally by the per-member (not union) rewrite in 4: attach the
   reason only to the member whose own clause lacks its own quote.

10. **`_segment_holding_quoted_phrase` falls back to `members[0]`.**
    `services/legal/deterministic_envelope.py` ~line 475. When a fabricated quote's words wrap across
    two segments (whole in neither quoted span and not a substring of any single segment), the reason
    lands on `members[0]` — possibly a quote-free line — while the quote-bearing segments stay green.
    CONFIRMED via direct call. Fix: when no single segment holds the phrase, attach the reason to the
    segment(s) that hold the quoted SPAN fragments, or to all members of the group, not the first.

### Test-integrity / latent

11. **Collision gate (387 cases) passes with the labeler OFF.** `script/cachet-acceptance.py` ~line
    48. The gate runs `verify_claim_against_clause` without `CARREL_SUBJECT_LABELER`, and figures are
    scoped out (ADR-0013), so all 387 read could-not-verify even with the labeler removed — it
    validates the scope-out, not the labeler it advertises. CONFIRMED. Fix: run the collision/recall
    corpora with the labeler ON (`CARREL_SUBJECT_LABELER=regex` at least) so the gate actually
    exercises the labeled path; keep a labeler-OFF run too. ALSO add percent + polarity collisions
    (different-subject same-value, partial-match) so finding 1/2/13 are locked by the gate, not just
    unit tests.

12. **`_subject_aware_amount` has no claim-side verbatim post-check.**
    `services/legal/contract_verify.py` ~line 648-673 — only the clause side gets the local-proximity
    window. Latent today (regex floor makes the claim subject verbatim by construction) but a
    false-accusation hole once the AFM labeler is wired. Add a symmetric claim-side verbatim
    post-check before trusting any model-proposed claim subject.

13. **`_polarity_pass` likely has the same partial-match hole as 1.**
    `services/legal/contract_verify.py` ~line 516 — a present on one (stem, noun) key can win over a
    `not_found` on a second key the clause is silent on. Lower confidence (noun-binding makes a clean
    trigger fragile) but the precedence is the same gap. Apply pattern B here too.

14. **Subject-aware percent downgrades a real contradiction to `not_found` when subject phrasing
    differs** (lost catch, fails safe). Claim "20% France" vs source "10% under the French method":
    on `main` value-only -> contradiction; here subject-bound claim + subject-less clause -> matched
    empty -> `not_found`. No false green/accusation, but a lost catch. Lower priority; consider
    folding the subject path back to the value-only contradiction when subjects don't bind on both
    sides.

15. **Dead `None`-guard after `_canonical_figures` now always returns a list.**
    `services/legal/contract_verify.py` ~line 179 (`if claim_canon is None or clause_canon is None:
    return None` is unreachable). Cleanup; remove it and handle the real asymmetric-length case from
    finding 7 explicitly.

## Acceptance (the bar to clear before #179 can merge)

- Each CONFIRMED false green (1-6) has a committed regression test whose adversarial case fails on
  the current branch and passes after the fix. The `cachet-adversary` skill is built to generate
  exactly these (claim, source) pairs; use it to mint the cases, then commit the surviving ones.
- `script/cachet-acceptance.py` over ALL five corpora: zero false greens AND zero false accusations,
  with the labeler both OFF and `=regex` (fix finding 11 so the gate is non-vacuous), and with new
  percent/polarity partial-match + union-pooling collisions added.
- Full Python verify chain green: the canonical unittest list in `CLAUDE.md`, ruff check + format,
  `benchmarks.phase0 --compare ... --fail-on-regression`, `benchmarks.t1_calibration`.
- No new false accusation: a quote/figure that cannot be checked reads could-not-check, never
  "altered"/"fabricated"; findings 7, 9, 10 specifically verified clean.
- Re-run `/code-review --xhigh` (or `/mythos`) on the fix diff; it must come back clean on the
  false-green dimension.

## How to reproduce / harness

- Contract path end-to-end: `tests/test_contract_verify_integration.py` helpers
  (`_DeterministicEmbedder`, `_node`, `build_deterministic_envelope`) +
  `services.verify._verify_result_from_envelope(draft, env, 0.0).claim_verdicts`; a card with
  `verdict == "verified"` whose `claim_text` contains the fabricated/unconfirmed value/quote is a
  false green.
- Litigator path: `build_deterministic_envelope(draft, conn=None, doc_ids=None, client=<offline
  corpus>)`; cited cases with opinion text live in `services/legal/local_caselaw.py` (Brown 347 U.S.
  483, Obergefell 576 U.S. 644 both have opinion text — use two distinct cites for the multi-quote
  case).
- Grouping: `services.legal.sentences.split_sentences_with_groups(draft)` returns `(segments,
  group_ids)`; repeated ids = merged into one logical sentence.
- Always run with the abs venv: `/Users/madu/Desktop/Codex/.venv/bin/python`, cwd = the worktree.

## Pointers

- PR: [carrel#179](https://github.com/Madu-P1/carrel/pull/179) (held, do not merge until green).
- Defect-bearing commits: `5ebd96ba1` (percent), `46bd1d69f` + `bc4c7bca0` (litigator passes),
  `bedd143a1` (contract laundering port).
- Skill: `cachet-adversary` (generate the adversarial cases and route each into a locking test).
- Memory: `cachet-money-duration-false-green`, `cachet-line-split-breaks-quote-attribution`,
  `cachet-verify-three-failure-layers`, `cachet-clean-prose-coverage-decision`.
- Companion handoff (already resolved): `docs/notes/2026-06-16-contract-path-wrapped-quote-twin-handoff.md`.
