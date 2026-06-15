# Forge armada — Cachet (2026-06-15)

The prioritized goal set for Cachet. Each task is deterministic, test-gated,
additive, and independently shippable as one draft (the contract is
`drafts_only: true` — Forge never pushes/merges/deploys).

**Ship-authority tags (read before running unattended):**
- `[AUTO]` — behavior-PRESERVING (perf, refactor, added test coverage). Cannot
  regress a catch. Safe for the unattended watchdog IFF an operator-owned
  held-out copy of the engine suites is staged in `<cage>/held-out/` (the
  unattended driver ships on the held-out gate ALONE; an empty held-out = no
  ship). These are the only ids the overnight `<cage>/queue.txt` should contain.
- `[REVIEW]` — changes a verdict/register, a truth surface (`anchors.py`,
  `contract_verify.py`, `sentences.py`, `deterministic_envelope.py`,
  `case_verification.py`, `local_caselaw.py`), or any frontend (`*.tsx`/`*.css`).
  The 2026-06-14 `mln` regression proved the in-repo fixtures miss real-slide
  failures here, so these are built as drafts for a HUMAN/council read, never
  autonomously shipped. Run supervised (in-session `/forge`, or by hand).

`pick: lowest-eligible` runs in number order.

---

## P0 — Demo readiness (the BIM-slide / Wedge-2 hero path)

### D1 — [REVIEW] Recognize EU-finance magnitude abbreviations WITHOUT regressing the figure catch
- Deps: none. Touches `anchors.py` + `contract_verify.py` (truth surfaces).
- Why: `mln`/`mn`/`bn`/`bln`/`mld` are standard in EU tax/finance decks (the BIM
  lecture uses `mln` throughout). They are not recognized, so the "Result: 30 mln
  …" line is UNTREATED and no supported card appears beside the flagged ones.
  The naive add (2026-06-14) recognized them BUT downgraded the live "60 billion"
  catch to could-not-check: the extra magnitude made bullet 1 multi-value and the
  cross-clause adjudicator demoted the near-verbatim figure contradiction.
- Acceptance (ALL hold, with fixtures, no DB):
  - `mln/mn/bn/bln/mld` canonicalize correctly (`anchors._MONEY_SCALE`, `_MAGNITUDE`).
  - REGRESSION GUARD (the mln failure): a near-verbatim sentence with MULTIPLE
    magnitudes where exactly one is altered still reads `parametric_contradiction`
    naming the altered figure — NOT `multi_value_unverifiable` — even when a
    sibling retrieved clause carries a different magnitude. Add a unit test on
    `verify_claim_against_clause` AND on `adjudicate_clause_candidates`
    reproducing "60 billion vs source 20 billion, with 300 mln + 1,2 billion also
    present" and assert the catch stands.
  - The "Result: 30 mln ×4" all-equal line reads supported (single deduped value
    matching the source) — synthetic clause fixture.
  - Every existing assertion in `test_contract_verify`, `test_anchors`,
    `test_deterministic_envelope` stays green unchanged. Zero-egress holds.
- Note: REVIEW-gated. Do not re-ship without the regression guard above.

### D2 — [REVIEW] Stop conflicting-clauses over-refusal on distinct-fact figures
- Deps: none. Touches `contract_verify.py` (adjudicator).
- Why: a CLEAN "Allocation key: turnover (10% Italy, 10% France …)" line reads
  could-not-check because retrieval also pulls bullet 1's "16%" and the
  conflicting-clauses rule refuses. 10% and 16% are DIFFERENT facts (different
  subjects), not two versions of one fact, so the refusal is over-conservative and
  starves the demo of any supported card.
- Acceptance:
  - A clean line whose value is present in its true clause reads supported even
    when an unrelated sibling clause carries a different percent for a different
    subject. Distinguish "same fact, conflicting values" (refuse) from "different
    facts" (do not refuse) — by subject/section topicality, not bare value presence.
  - The REAL contradiction cases (amended-contract conflict, the live $360M case)
    still refuse with both clauses named — pin them. Honesty-over-coverage holds.
  - Fixtures both directions. Zero-egress holds.

### D3 — [REVIEW] Percent-anchor subject binding ("20% France" vs source "10% France")
- Deps: none. Touches `anchors.py` / `contract_verify.py`.
- Why: a direct percent→subject binding is a stronger, more general catch than the
  near-verbatim figure pre-pass (works when the sentence is not a near-copy).
- Acceptance: a percent bound to a subject contradicts the source's percent for
  the same subject; an unbound percent never false-accuses; fixtures; existing
  percent tests green; zero-egress holds.

### D4 — [REVIEW] Verified/supported count renders beside the refusal (acceptance visible)
- Deps: D1/D2. Frontend.
- Why: the operator's core ask — "the refusal shines when acceptance is visible."
  The `Supported` stat + headline already exist in `VerifyVerdictSummary`; verify
  end-to-end that they render on a mixed verdict, council-approved register (count,
  muted ink, no green badge, no score).
- Acceptance: a 3-statement mixed result (2 unsupported + 1 supported) renders the
  supported count beside the flagged count; no green badge; RTL test pins it.

---

## P1 — Engine correctness (truth surfaces, REVIEW)

### E2 — [REVIEW] Corpus-completeness attestation: cross-check size/hash before honoring scope="complete"
- (carried) Touches `local_caselaw.py` / `case_verification.py`.
- Acceptance: `scope="complete"` honored only when the manifest's declared size
  (and content hash when available) matches the loaded corpus; on mismatch a miss
  folds to bounded could-not-check, never the loud "no such case". Demo manifest
  unchanged. Both directions pinned. Zero-egress holds.

### E3 — [REVIEW] Gate 1: deterministic low-information / heading filter on the legacy chunks path
- (carried) Touches retrieval / `node_type_router` import.
- Acceptance: a model-free heuristic flags heading-shaped / low-info lines on the
  chunks path; import (do not re-derive) `NON_CITABLE_NODE_TYPES`; answer-bearing
  prose unaffected; pure; zero-egress holds.

### E4 — [REVIEW] Comma-decimal magnitude hardening sweep ("1,2 billion" vs "1.200 billion")
- Touches `anchors.py`. Audit every magnitude/money path for comma-decimal vs
  comma-thousands ambiguity and refuse (could-not-check) rather than guess.
- Acceptance: ambiguous comma forms never produce a confident verdict; unambiguous
  ones still parse; fixtures; zero-egress holds.

---

## P2 — Safe backend (behavior-preserving, AUTO)

### E1 — [AUTO] Hoist per-node tokenization out of the deterministic verify hot path
- (carried) Behavior byte-identical. Acceptance: the sentence token set is derived
  ONCE per sentence and reused across candidate clauses; the brief-level quote
  pool / alias table materialized once per request; every assertion in
  `test_deterministic_envelope`, `test_contract_verify`, `test_quote_check` stays
  green UNCHANGED; a focused test pins the new shape; zero-egress holds.

### S1 — [AUTO] Property-style coverage for `split_sentences` slide/bullet inputs
- New tests only, no src change. Acceptance: tests for bullet glyphs (•, -, *, ◦,
  –, —) at line starts, leading tabs, mixed CRLF/blank-line runs, and a no-newline
  single-line slide paste; assert current splitter behavior on each (document the
  no-newline single-line case as the known limitation). Suite stays green.

### S2 — [AUTO] Extract the shared content-token / trailing-s-fold helper used in 3+ places
- Behavior byte-identical refactor. Acceptance: one shared helper, all call sites
  updated, every engine assertion green unchanged, a test pins identical output to
  the pre-refactor baseline.

---

## P3 — Frontend (taste, REVIEW)

### F1 — [REVIEW] Visual QA on the segmented verdict + examination drawer + token highlight
- `*.tsx`/`*.css`. Acceptance: screenshot at 1440/1920; `.markToken` reads as one
  accent (no second color); the drawer no longer collapses the document column;
  supported cards stay unmarked-pass; matches `DESIGN.md` (Libre Caslon,
  ink/paper/oxblood, no green). Route to /design-review.

### F2 — [REVIEW] Examination drawer: show the matched source clause beside a flagged figure
- `*.tsx`. A flagged "60 billion" should let the lawyer see the source's
  "20 billion" clause inline, not just the reason string. Acceptance: render the
  matched clause under the "Grounded" check when present; honest fallback when
  absent; RTL test.

---

## NOT queued (operator / validation gated — never Forge-shippable)
- Role-aligned clause matching (after T66 validation).
- T1 labeled legal corpus (data task).
- Clean-prose coverage wording (validate with real lawyers first).
- Any change to the no-green-badge / honest-refusal brand stance (council + Madu).
