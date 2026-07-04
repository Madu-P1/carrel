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

### D1 — DONE (92713c1df, 2026-06-15) — EU magnitude abbreviations, no catch regression
- Shipped: mln/mn/bn/bln/mld recognized; `_canonical_figures` skips uncanonical
  comma-decimals so the altered-figure pre-pass fires on multi-figure lines.
  Live BIM: total=3, verified=1 (Result line), unsupported=2 (60bn + 20% France).
  Regression guard in test_contract_verify.AlteredFigureNearCopyRegressionTests.
- Original spec below (kept for the record):
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

### D2 — DONE (5ebd96ba1, 2026-06-15, supervised + council) — solved via subject-bound percents
- Shipped together with D3 as ONE principled change (council verdict: subject-binding
  as a comparison KEY, not a topicality gate, so it does not weaken the
  conflicting-clauses guard). A clean "10% France" line no longer conflicts with an
  unrelated "16% profitability" clause. Live BIM: clean allocation line now VERIFIED.
- Original spec below.
### D2 — [REVIEW, STAGED 2026-06-15] Stop conflicting-clauses over-refusal on distinct-fact figures
- ANALYSIS (2026-06-15): reproduced. A clean "Allocation key: …10% France…" line
  reads could-not-check because retrieval also pulls an unrelated "16% profitability
  threshold" clause; that clause yields a spurious percent contradiction (10% vs
  16%) alongside the true clause's present (10%), and the adjudicator's rule 1
  refuses (conflicting_clauses) rather than take the present. The refusal is the
  DELIBERATE guard against false-greening an amended-contract conflict (the worst
  failure class), so a correct fix needs subject/section topicality on the
  contradiction (only conflict when the two clauses concern the SAME subject), not
  a blanket "prefer present". Real work + real false-green risk. NOT demo-critical:
  D1 already gives acceptance on the tampered slide. Do supervised with both-
  direction fixtures (clean line passes; a real amended-value conflict still refuses).
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

### D3 — DONE (5ebd96ba1, 2026-06-15, supervised + council) — percent subject binding
- Shipped with D2. anchors.py percents carry an optional subject (conservative
  proper-noun adjacency); contract_verify._subject_aware_percent makes a
  same-subject value mismatch a direct contradiction ("20% France" vs "10% France"),
  more general than the near-verbatim figure pre-pass. Fixtures both directions;
  mis-bind fails to could-not-check. Original spec below.
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

### S1 — DONE (59eac7bd2, forge run) — property-style slide/bullet coverage
- Shipped: `SlideBulletSegmentationTests` in tests/test_legal_sentences.py covers
  all six bullet glyphs, leading tabs, CRLF/blank-line runs, and the single-line
  paste as the documented known limitation. 27/27 green. Queue entry was never
  marked done; reconciled 2026-07-01.
- Original spec below (kept for the record):
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

## SI — Structural Integrity pillar (2026-06-24, REVIEW)

New intra-document verification surface: a document checked against ITSELF, no source,
no DB, no model, no network. Full spec + held-out test list in
`docs/plans/2026-06-24-structural-integrity-pillar.md`. New module
`services/legal/structural_integrity.py` + new tests `tests/test_structural_integrity.py`.
All REVIEW (new truth-feeding module; SI-4 edits `deterministic_envelope.py`). Land SI-1
first; it is the demo hero on its own. Each task is additive and independently shippable.

### SI-1 — [REVIEW] Dangling intra-document cross-reference detection (demo hero)
- STATUS 2026-06-24: BUILT + adversary-hardened in worktree peaceful-kilby-70f12c
  (UNCOMMITTED). `services/legal/structural_integrity.py` +
  `tests/test_structural_integrity.py` (14 tests). cachet-adversary closed 4
  false-flag cracks (subsection/parent, markup heading, Roman numeral, quoted
  external); report at `.claude/adversary/report-2026-06-24-si1.md`. Pending
  human review + commit. Do not re-pick.
- Deps: none. New `structural_integrity.py`. Reuses `anchors._SECTION` + `_normalize_section`.
- Why: "...set forth in Section 12.3..." when the document declares only Sections 1-9 is an
  undeniable, zero-false-green catch a lawyer sees instantly. Highest demo-per-build.
- Acceptance (ALL hold, pure functions, no DB, fixtures only):
  - `StructuralFinding` dataclass per the spec (kind/disposition/detail/span/start/end/target).
  - A referenced `Section`/`Clause`/`Article` number with no start-of-line declaration in the
    same text reads `flagged` `dangling_cross_reference` with normalized `target`.
  - A reference whose target IS declared reads silent (no finding, no green card).
  - `Exhibit`/`Schedule` refs with no in-document declaration read `could_not_check`, NEVER
    `flagged` (may be external attachments).
  - FRAGMENT GUARD: a text with fewer than the declaration threshold reads every reference
    `could_not_check`, never `flagged`.
  - Range form ("Sections 4 through 9") does not false-flag interior numbers.
  - New `tests/test_structural_integrity.py` pins every case above. Every existing assertion
    in `test_anchors`, `test_contract_verify`, `test_deterministic_envelope` stays green
    UNCHANGED. Zero-egress holds.

### SI-2 — [REVIEW] Defined-term-defined-but-never-used detection
- STATUS 2026-06-24: BUILT + adversary-hardened in worktree peaceful-kilby-70f12c
  (UNCOMMITTED). `check_defined_terms` in structural_integrity.py; conservative
  use-counting (case-insensitive + trailing-s) so plural/lowercase/possessive uses
  never false-flag. adversary pass found 0 cracks (all controls held). Pending
  review + commit. Do not re-pick.
- Deps: SI-1 (shares the module + finding type). Reuses `build_alias_table` +
  `_defined_term_anchors`.
- Why: a defined term that is never used is a real, deterministic drafting defect with low
  false-green risk.
- Acceptance:
  - A term in `build_alias_table` whose only occurrence is its definition site reads
    `flagged` `defined_term_unused`.
  - A defined term used elsewhere reads silent.
  - USED-BUT-UNDEFINED is NOT flagged in v1 (false-accuse risk on capitalized words);
    documented recall gap, `could_not_check` at most. Pin that it never `flagged`.
  - Fixtures both directions; existing suites green unchanged; zero-egress holds.

### SI-3 — [REVIEW] Internal single-document contradiction (subject-bound, ADR-0013-constrained)
- STATUS 2026-06-24: BUILT + adversary-hardened in worktree peaceful-kilby-70f12c
  (UNCOMMITTED). `check_internal_contradictions`, PERCENT-ONLY (reuses D3 subject).
  adversary found the predicted crack: a bare proper-noun subject conflates "10%
  France tax" with "20% France tariff" (different facts). DECISION: SI-3 emits
  `could_not_check` ("possible inconsistency, review"), NEVER `flagged` - a confident
  intra-document contradiction needs stronger (T1) binding. Money/duration never
  compared. Safety-invariant test pins "SI-3 never flags". Pending review + commit.
  Do not re-pick.
- Deps: SI-1. Reuses subject-bound anchors (the D3 conservative percent subject).
- Why: "10% to France ... 20% to France" inside one document is a real contradiction.
- Acceptance:
  - Two same-type anchors bound to the SAME subject with different canonical values read
    `flagged` `internal_contradiction`, both spans named.
  - INHERITS ADR-0013: no new figure green path. Unbound / weakly-bound pairs (incl. the
    "$1,000,000 ... $1,200,000" different-subject case) read `could_not_check`, never
    `flagged`.
  - A `cachet-adversary` pass runs first; each surviving crack becomes a held-out test.
  - Fixtures both directions; existing suites green unchanged; zero-egress holds.
- Note: most false-green-prone of the pillar. Supervised only; do not ship unattended.

### SI-4 — [REVIEW] Source-free entry point + additive envelope wiring
- STATUS 2026-06-24: BUILT in worktree peaceful-kilby-70f12c (UNCOMMITTED).
  `check_structural_integrity` aggregates SI-1+SI-2; `build_deterministic_envelope`
  gains an additive `structural_findings` key (only return path). All existing
  envelope/verify/zero-egress assertions green unchanged (447-test subset). Pending
  review + commit. Do not re-pick.
- Deps: SI-1 (SI-2/SI-3 optional). Edits `deterministic_envelope.py` (truth surface).
- Why: structural integrity must run on one document with no source uploaded, and the tray
  must see the findings.
- Acceptance:
  - `check_structural_integrity(text: str) -> list[StructuralFinding]` runs SI-1..SI-3 with
    no `conn`/`doc_ids`.
  - `build_deterministic_envelope` gains an ADDITIVE `structural_findings` key (serialized
    findings over the draft); `claims`, `unsupported_spans`, `provider`, `model` keys
    unchanged in shape and value for existing fixtures.
  - A draft with a dangling ref yields a non-empty `structural_findings` AND an unchanged
    `claims` shape. Every existing `test_deterministic_envelope` assertion green unchanged.
  - Zero-egress holds.

### SI-5 — [REVIEW] Render structural findings in the tray (FRONTEND, separate track)
- Deps: SI-4. `*.tsx`/`*.css`. NOT part of the engine contract; queued for visibility.
- Why: surface the catch to the lawyer in the existing 3-state tray.
- Acceptance: `structural_findings` render in the flagged + could-not-check registers; no
  green badge; honest empty state; matches `DESIGN.md` (Libre Caslon, ink/paper/oxblood);
  RTL test; route to /design-review.

---

## NOT queued (operator / validation gated — never Forge-shippable)
- Role-aligned clause matching (after T66 validation).
- T1 labeled legal corpus (data task).
- Clean-prose coverage wording (validate with real lawyers first).
- Any change to the no-green-badge / honest-refusal brand stance (council + Madu).


---

## Mythos engine scan (2026-06-22) — services/legal false-green hunt
Filed by Mythos ACTION mode. 8 fresh-context Opus finders + 4 cross-model (Sonnet) refuters
over the verify engine. ALL are truth/verdict surfaces -> **[REVIEW]** (drafts for a human/
council read, NEVER auto-shipped). Ledger: /tmp/mythos-cachet-scan/.mythos/findings-cachet-engine-scan.md

### Q1 [REVIEW] (critical) — Quote-framing false green: a verbatim quote greens inside a rejected/attributed frame
- Status: DRAFT on branch claude/vibrant-wu-d6c9fc (2026-07-04) — awaiting human read.
  The quote leg greened on verbatim PRESENCE even when the quoted words live only
  inside an adverse frame ("Appellant argued that '<quote>'; the court rejected
  that contention." -> verified). Fix: new pure
  `services/legal/quote_check.py::quote_adverse_framed` + the frame lexicon;
  `cachet_verify/adapter.py::_quote_checks` demotes a present quote to
  could_not_check when EVERY located occurrence in a confident source is
  adverse-framed. Refuse-leaning, NO new green path; a clean-source verbatim quote
  stays verified (ADR-0013 provably-safe anchor). `combine` floors the whole
  verdict. cachet-adversary round ran FIRST on the refuse-vs-over-refuse tradeoff:
  HELD 15/15 (10 adverse demotions + 5 clean-quote preservations). A follow-up
  independent /mythos report round found 5 real defects in the first pass and ALL
  were reproduced + FIXED in-change: C1/C2 over-refusal (adopted contention /
  non-merits rejection word) via `_ADOPTION` veto + `_ARG_NOUN` requirement;
  S1/S2 quadratic DoS (54KB -> 22s) via `_FRAME_WINDOW` bound + `_MAX_OCCURRENCES`
  budget (3.4MB now ~1.1s); C3 abbreviation split via `_ABBREVIATIONS`-aware
  sentence boundaries. Report:
  `.claude/adversary/report-2026-07-04-quote-framing.md`. Held-out tests:
  `tests/test_quote_check.py::AdverseFrameDemotionTests` (22) +
  `tests/test_cachet_verify_seam.py::QuoteFramingHonestyTests` (4). Gate: 590
  engine tests + ruff (check + format) + zero-egress green.
- Deps: none. Touches `quote_check.py` + `adapter.py` (truth surfaces).
- Acceptance (met): the rejected-argument repro resolves to could_not_check; a
  faithful bare verbatim quote against a clean source still reads verified;
  existing quote_check + cachet_verify suites green unchanged; zero-egress holds.
- Follow-up (separate REVIEW, NOT in this change): the clause leg
  (`contract_verify.py::verify_claim_against_clause`) emits an internal `verified`
  sub-check for the same quote. It is floored by `combine` (verdict is honest),
  but the twin should be neutralized without touching the figure/percent catches.
  See the report's "documented residual". The truncation variant
  ("...runs with the land, provided the owner consents...") is a separate
  documented residual (the clause leg already refuses it); not part of Q1.
- Residual (Mythos C3, safe direction — a MISSED demotion, never a new green): a
  comma parenthetical splitting a negation ("did not, per Corp. Inc., hold that
  '<quote>'") loses "did not" to `_governing_prefix` comma-splitting, so it stays
  verified. Closing it re-introduces a real over-refusal, so it is left as a
  recall gap.

### M1 [REVIEW] (critical) — Caption acronym false-green: fabricated ALL-CAPS initials read as match
- Status: todo
- Deps: none
- Source: mythos cachet-engine-scan @ services/legal/citations_eyecite.py:228
- Grounding: repro: caption_match_state(NLR v. JLS, 'National Labor Relations Board v. Jones Laughlin Steel') == 'match' (cross-model refuted, survived)
- Goal: _acronym_forms emits an initialism for every contiguous word-run of the WHOLE case name; restrict credit to a side's own words.
- Acceptance: held-out: a fabricated ALL-CAPS-initials caption (NLR v. JLS) on a real reporter number resolves to caption_unconfirmed/mismatch, NOT match; existing caption tests stay green.

### M2 [REVIEW] (critical) — Acronym forms span the v. separator
- Status: todo
- Deps: none
- Source: mythos cachet-engine-scan @ services/legal/citations_eyecite.py:223
- Grounding: repro: _acronym_forms keeps 'v' and spans both parties, emitting cross-party forms ('bvj','vjls')
- Goal: Split the name on the v. separator BEFORE generating acronym forms; never cross it.
- Acceptance: held-out: no acronym form produced by _acronym_forms contains a token from both parties.

### M3 [REVIEW] (critical) — Case-existence on the tutor path has NO caption cross-check
- Status: todo
- Deps: none
- Source: mythos cachet-engine-scan @ services/legal/case_verification.py:429
- Grounding: cite:services/legal/case_verification.py:429+false-green-caption-gate-bypass (cross-model refuted, survived)
- Goal: The caption gate runs only in deterministic_envelope; the tutor path emits exists=True+case_name from the CourtListener echo with no caption cross-check. Apply the caption gate here too.
- Acceptance: held-out: a fabricated caption on a real reporter number, via the tutor/case_verification path, yields could-not-confirm, not exists=True.

### M4 [REVIEW] (high) — European-comma money parsed 10x wrong
- Status: todo
- Deps: none
- Source: mythos cachet-engine-scan @ services/legal/anchors.py:691
- Grounding: repro: extract_anchors('$1,2 billion') -> $12B (10x); _money_cents naive .replace(',','') vs _MAGNITUDE's parse_grouped_number refusal (cross-model refuted, survived)
- Goal: Route $-money through parse_grouped_number's European-comma refusal so $1,2 cannot become $12.
- Acceptance: held-out: '$1,2 billion' refuses / is flagged ambiguous, never canonicalizes to 12e9.

### M5 [REVIEW] (high) — Two-party fabricated caption matches a one-party name
- Status: todo
- Deps: none
- Source: mythos cachet-engine-scan @ services/legal/citations_eyecite.py:322
- Grounding: repro: caption_match_state(IBM v. BMC, 'International Business Machines Corporation') == 'match'
- Goal: Require each populated draft side to match a DISTINCT span of the resolved name.
- Acceptance: held-out: a two-party draft caption against a single-party resolved name resolves to mismatch.

### M6 [REVIEW] (high) — Date locale ambiguity silently month-first
- Status: DRAFT on branch claude/modest-engelbart-7b2328 (2026-07-01) — awaiting human security read.
  `_date_iso` now refuses N/N/YYYY where both fields are 1..12 and differ (returns
  None -> no date anchor); unambiguous (one field >12), equal-field, ISO, and
  textual forms unaffected. Both-direction fixtures in tests/test_anchors.py.
  Gate: 504 engine tests + ruff + zero-egress green; forge-rater SHIP
  (.forge/scores/date-locale-ambiguity-20260701T203050Z.json). anchors.py is a
  security truth surface -> logged to .claude/logs/operator-followups.jsonl.
  Original spec below.
- Deps: none
- Source: mythos cachet-engine-scan @ services/legal/anchors.py:759
- Grounding: repro: _date_iso('03/04/2024')->2024-03-04 but '13/04/2024'->2024-04-13 (dateutil dayfirst=False)
- Goal: Refuse N/N/YYYY where both fields <= 12 (ambiguous), or carry the source locale.
- Acceptance: held-out: an ambiguous DD/MM vs MM/DD date is flagged ambiguous, not silently resolved.

### M7 [REVIEW] (high) — Empty case_name still reads exists=True
- Status: todo
- Deps: none
- Source: mythos cachet-engine-scan @ services/legal/case_verification.py:430
- Grounding: repro: status==200 with empty case_name -> CaseVerdict(exists=True, case_name=None)
- Goal: Treat an empty/None case_name as could-not-confirm.
- Acceptance: held-out: a 200 response with no case_name yields could-not-confirm, not exists=True.

### M8 [REVIEW] (high) — holding_match trusts the model's supports=True
- Status: todo
- Deps: none
- Source: mythos cachet-engine-scan @ services/legal/case_verification.py:309
- Grounding: cite:services/legal/case_verification.py:309+OWASP-LLM09
- Goal: Gate holding_match on a verbatim-excerpt-in-opinion check before trusting model supports=True.
- Acceptance: held-out: a model supports=True with no verbatim grounding does NOT set holding_match=True.

### M9 [REVIEW] (high) — CourtListener 200 + empty clusters reads as existing
- Status: todo
- Deps: none
- Source: mythos cachet-engine-scan @ services/legal/courtlistener.py:266
- Grounding: repro: _coerce_hit({'status':200,'clusters':[]}) -> exists=True, case_name=None (cross-model refuted, survived)
- Goal: Require status==200 AND a non-empty cluster before exists=True.
- Acceptance: held-out: a 200 with clusters:[] yields exists=False/could-not-confirm.

### M10 [REVIEW] (high) — exists = status==200 with no cluster requirement
- Status: todo
- Deps: none
- Source: mythos cachet-engine-scan @ services/legal/courtlistener.py:128
- Grounding: cite:services/legal/courtlistener.py:128+CWE-345
- Goal: Define exists to require a present cluster, not merely a 200.
- Acceptance: held-out: CitationHit.exists is False when no cluster is present.

### M11 [REVIEW] (high) — Amount partial-confirmation can green (latent)
- Status: todo
- Deps: none
- Source: mythos cachet-engine-scan @ services/legal/contract_verify.py:733
- Grounding: cite:services/legal/contract_verify.py:733+partial-confirmation-false-green
- Goal: Mirror the percent path's all_confirmed gate for amounts (latent today; a future caller trusting the disposition inherits a false green).
- Acceptance: held-out: a partially-confirmed amount set does not produce a confirmed disposition.

### M12 [REVIEW] (high) — Floating quote rides the co-cite union
- Status: todo
- Deps: none
- Source: mythos cachet-engine-scan @ services/legal/deterministic_envelope.py:559
- Grounding: repro: a fabricated quote verbatim in a co-cited opinion rides group_opinions via the floating-phrase fallback (documented accepted residual)
- Goal: Fail floating phrases toward could-not-check, not the union of every co-cited opinion.
- Acceptance: held-out: a floating quote whose grounding cite is positionally unclear refuses, not greens.

### M13 [REVIEW] (medium) — Holding window head-clip biases the model
- Status: todo
- Deps: none
- Source: mythos cachet-engine-scan @ services/legal/case_verification.py:470
- Grounding: cite:services/legal/case_verification.py:470+holding-window-truncation
- Goal: Record the 8000-char clip in the verdict so a truncated head can't silently push toward non-False.
- Acceptance: held-out: the verdict surfaces when the opinion was truncated for the holding check.

### M14 [REVIEW] (medium) — Displayed citation anchored to server echo
- Status: todo
- Deps: none
- Source: mythos cachet-engine-scan @ services/legal/courtlistener.py:269
- Grounding: cite:services/legal/courtlistener.py:269+CWE-345
- Goal: Anchor the displayed citation to the submitted substring, not the server echo.
- Acceptance: held-out: the surfaced citation string equals the user-submitted span, not the API echo.

### M15 [REVIEW] (medium) — Subject setdefault drops same-subject multi-figure contradiction
- Status: todo
- Deps: none
- Source: mythos cachet-engine-scan @ services/legal/contract_verify.py:691
- Grounding: cite:services/legal/contract_verify.py:691+subject-key-collision
- Goal: Key by figure span, not subject string, so same-subject multi-figure contradictions are not dropped.
- Acceptance: held-out: two figures under the same subject both reach the contradiction check.

### M16 [REVIEW] (low) — _MIN_KEY_CHARS is dead code
- Status: todo
- Deps: none
- Source: mythos cachet-engine-scan @ services/legal/align.py:41
- Grounding: repro: align_claims_to_draft pins 'the statute' as exact despite the _MIN_KEY_CHARS docstring; the constant is never referenced
- Goal: Enforce _MIN_KEY_CHARS or delete the docstring promise.
- Acceptance: held-out: a sub-threshold key is not pinned as exact (or the docstring no longer claims a floor).

### M17 [REVIEW] (low) — Money None-canonical not dropped
- Status: todo
- Deps: none
- Source: mythos cachet-engine-scan @ services/legal/anchors.py:855
- Grounding: cite:services/legal/anchors.py:855+null-canonical-collision
- Goal: Mirror the date loop's None-drop for money anchors.
- Acceptance: held-out: a money anchor with a None canonical value is dropped, not collided.

