# Cachet deterministic extraction engine: what to verify, what to skip, without an LLM

Date: 2026-06-05
Method: ~24-agent fan-out (code inventory + 2026 NLP/legal-tech research + adversarial verification of
load-bearing determinism/coverage/licensing claims). Companion to
`docs/notes/2026-06-05-cachet-local-architecture.md`. Honesty tiers used throughout:
- T0 = pure deterministic, NO AI (regex / grammar / string / table lookup, no learned weights)
- T1 = local classical ML, no LLM, no cloud (spaCy NER, a small NLI cross-encoder, Docling layout/OCR)
- T2 = local LLM
"No cloud" is met by T0/T1/T2 on-device. "No AI" is met ONLY by T0. A T1/T2 step is never called deterministic.

## The verdict: extract by ANCHOR, not by claim

Cachet should decide what to verify by detecting ANCHORS, not by detecting claims. An anchor is a
deterministically findable token/span that makes a statement independently checkable: a legal citation,
a quotation-marked run, a money amount, a date/duration, a defined term, a section reference, a party
name. This replaces the ML-hard question "is this sentence a check-worthy claim?" with the T0 question
"does this span carry a verifiable artifact?" The LLM that today decides what to verify
(`services/tutor.py` grounded-answer tool call) is removed from that decision entirely.

Steelman of the opposing view (taken seriously): anchors miss the highest-value claims. "Defendant
maliciously refused to pay" (verifiable vs the record, no anchor), "best efforts" clauses (the
most-litigated contract provision, no anchor), implicit citations (regex recall 0.22 vs ML 0.66), and
Omission-class discrepancies (a missing clause has no surface token). A skeptic says anchors miss exactly
what a lawyer most needs caught.

This sharpens the design but does not kill it. Anchor extraction is a PRECISION gate, not a recall gate.
The missed claims are precisely the set no deterministic tool should claim to verify. The product
guarantee is "grounding attested, never truth or soundness." So the engine's job is high-confidence checks
on what carries an anchor, plus a LOUD, itemized refusal tray for what it skipped and why. The
cross-professional discovery independently found the loud first-class refusal is the single strongest
finding. The tray is the saleable object, not a gap. A system that silently passes anchor-free claims is
the disqualifying failure mode; this design never does.

The verdict space has THREE terminal states, never two:
`checked_supported_or_present`, `checked_contradicted_or_not_found`, `could_not_check_no_anchor`.
Collapsing the third into "clean" is the lulling failure mode and is forbidden.

## A tested bug found this run (independently shippable fix)

`_CITATION_SHAPE` at `services/legal/case_verification.py:59` silently misses every reporter with an
embedded digit: F.2d, F.3d, F.4th, F.Supp.2d, F.Supp.3d, L.Ed.2d, Cal.4th, N.Y.2d. The character class
`[A-Za-z\.\s\(\)]{1,40}` excludes digits. Live-tested this run: on a real 7-citation brief it found 4/7
(57%); a pure-circuit brief (all F.3d) scores 0/N. It is the ONLY gate for `_looks_like_legal_text()`, so a
false negative silently skips the CourtListener lookup with no fallback. Fix: replace with
`eyecite.get_citations()` (found 7/7). Eyecite is already installed in the venv.

## Anchor taxonomy (each a deterministic detector)

1. Citation (case/statute/reg) - eyecite [T0]
2. Slip-op / unreported - dedicated regex `\bNo\.\s+\d{1,4}-\d{1,6}\b` + `\bslip\s+op\.` [T0]
3. Quoted-run - existing `_QUOTED_SPAN` (`services/legal/quote_check.py`) [T0]
4. Money / amount - clean-room regex [T0]
5. Date / duration - narrow regex + `dateutil.parse(fuzzy=False)` [T0]
6. Section / Article / Exhibit ref - extended `_SECTION_NUMBERED_PREFIX` [T0]
7. Defined-term occurrence - alias table built at ingest [T0]
8. Party name - parenthetical-alias + entity-suffix regex [T0] (statistical NER for un-aliased names is T1, optional, off)

Scanner: a single new `extract_anchors(span) -> list[Anchor]` (the architectural gap; it does not exist
today). Each `Anchor(type, text, char_start, char_end, canonical_value)`; `canonical_value` is populated
only for parametric types (money to cents, duration to days, date to ISO) to enable the T0 contradiction
check.

## Litigator engine (Surface A, the offline opener) - genuinely T0 end to end

- L0 ingest the draft as-is [T0]: the draft is the unit source; do not Docling it. Replace the block at
  `services/verify.py:250-252` (`grounded_tutor_envelope`) with `build_deterministic_envelope(cleaned)`.
- L1 anchor detection over the raw draft [T0]: eyecite for citations (`.span()` gives offsets), the
  quoted-run regex, the new slip-op regex.
- L2 quote<->citation association [T0, NEW]: eyecite captures a quote only inside a parenthetical; the
  dominant brief pattern is `held that "X," Smith, 326 U.S. 310`. For each quoted run, scan within a
  120-char window for the nearest citation anchor and bind them as one checkable unit. Unbound quotes still
  get a source-pool verbatim check; unbound citations get existence-only.
- L3 existence check [T0 logic, network is external infra, no model]: call
  `verify_claims_for_cases(..., client=adapter, enable_holding_match=False)`
  (`case_verification.py:500`; the `client=` seam and `enable_holding_match` opt-out already exist). For the
  offline demo, inject a bundled-SQLite CourtListener snapshot behind the same seam. Fabricated cite -> no
  hit -> `cite_not_found`. The visceral catch.
- L4 verbatim quote check [T0]: `verbatim_run_present(run, opinion_text)` after `split_runs` on edit marks.
  Absent -> `quote_altered`. Present -> `language_present` (NOT "claim true").
- L5 skip/refuse routing [T0]: every anchor-free sentence (legal-aware splitter) goes to the itemized tray,
  split into `checked_no_support` vs `could_not_check_no_anchor`. Never collapsed.
- L6 emit envelope [T0]: pack into the exact dict `_verify_result_from_envelope` (`verify.py:282`) already
  consumes; `align_claims_to_draft`, verdict cards, serialization all reuse verbatim.
- Optional assistive, OFF in demo: holding-match (does the opinion SUPPORT the proposition?) stays T2 at
  `case_verification.py:206`, gated by `enable_holding_match`. A local T1 NLI substitute is roadmap.

## Contract engine (Surface B, the business close) - T0 gold case, honest coverage limit

- C0 ingest (one-time, at upload): Docling structural typing is T1 (no T0 substitute for layout); for a
  clean digital DOCX/text-PDF the TEXT is T0 and only typing is T1. Scanned-PDF OCR is T1, so a "verbatim"
  check against OCR output is an approximation: surface an OCR banner and downgrade the verdict. Tables are
  not yet walked (`typed_walker.py:159`), so payment-schedule cells are out of scope until a table-walk PR.
- C1 defined-term + party table build (at ingest) [T0, NEW]: two regexes (definition pattern + parenthetical
  alias) build an alias->canonical map. Must run BEFORE any structural drop, because the existing
  `is_banner_shape` heuristic would wrongly suppress Title-Case defined terms.
- C2 anchor detection over the AI summary [T0]: money, duration, date (narrow regex + dateutil, NOT LexNLP),
  section-ref, defined-term occurrence.
- C3 retrieve the contract span [T0 FTS5 arm / T1 vector arm]: `search_typed_hybrid`; expand the query with
  the canonical form when a defined-term alias is present.
- C4 match decision:
  - not-found [T0]: verbatim absent for all nodes AND retrieval score below a floor -> `cannot_verify`.
  - present [T0]: anchor value appears verbatim -> `language_present_in_Section_X` (attests language, not
    correctness; UI must say "review full clause for context" so a carve-out is never hidden).
  - PARAMETRIC CONTRADICTION [T0, the gold case]: for money/duration, extract the clause's number with the
    same regex, normalize both to a canonical unit, compare. "$1M" vs "$500,000", "5 years after execution"
    vs "after termination" -> `parametric_contradiction`. Pure arithmetic, zero ML. Beats the litigator path
    (no NLI needed). Recall on word-form values is UNKNOWN until corpus-tested.
  - paraphrase support [T1, OFF in demo]: `cross-encoder/nli-deberta-v3-xsmall` (~70MB; torch+transformers+
    onnxruntime already installed), premise=clause, hypothesis=summary sentence, confidence-gated so
    sub-threshold -> "cannot determine".
- C5 skip routing + envelope [T0]: anchor-free claims ("governing law favors the buyer", "best efforts")
  -> loud `could_not_check_no_anchor` tray. Same envelope dict, reuse `_verify_result_from_envelope`.

## Coverage reality (the number most likely to be over-optimistic)

Anchor coverage on real contract claims is roughly 25-35%, not the 46-54% an early agent guessed (that
figure was refuted: no primary source, synthetic test). Grounded in CUAD (510 real commercial contracts, 41
clause categories): only ~32% are surface-detectable; LegalBench puts it at 10-15% of tasks. The no-anchor
majority includes anti-assignment, IP ownership, liability caps, termination-for-convenience, and
Omission-class discrepancies (a material clause simply absent, invisible to any anchor method). The
litigator path has much higher anchor coverage because briefs structurally require a citation for every
non-obvious assertion. Treat anchors as precision, not recall, and let the loud tray + roadmap T1 NLI carry
the rest.

## Honesty tier map (demo posture)

Litigator demo: T0 end to end (eyecite + quote + existence + verbatim + 3-state routing). Holding-match OFF.
Contract demo: T0 except the one-time ingest (Docling structural typing T1, unavoidable) and the optional
vector-recall arm (T1; FTS5 arm alone is T0 and can carry the demo). NLI OFF. Net: the only irreducible
non-T0 in either demo is local structural typing and optional vector recall, both no-cloud, neither no-AI.

## Build delta (additive, test-gated)

Dependencies:
- eyecite + reporters-db + courts-db: VERIFIED already installed, all BSD-2-Clause, pure Aho-Corasick + JSON
  lookup, zero learned weights, fully offline, T0. Pin as a first-class dep. Transitive lxml carries an
  LGPL-2.1 iconv binary (dynamic-linked); clear before first distribution, not a blocker.
- DO NOT add LexNLP. VERIFIED AGPL-3.0 (copyleft trap for a closed product) AND its `amounts.py` calls
  nltk's perceptron tagger (T1) on the default path, `dates.py` loads an sklearn classifier (T1). The prior
  "pure T0" assumption was wrong. Re-implement money/duration patterns clean-room as MIT regex (1-2 days;
  patterns are not copyrightable). OpenIE is also out: T1 (statistical parse + LinearClassifier) and GPL-3.
- python-dateutil for T0 date parse. Roadmap-only NLI reuses the already-installed torch/transformers/onnx.

New files (all T0 unless noted): `services/legal/anchors.py` (the 8 detectors + clean-room regexes),
`services/legal/citations_eyecite.py` (eyecite adapter replacing `_CITATION_SHAPE`),
`services/legal/sentences.py` (legal-aware splitter; existing splitters fragment "U.S.", "F.3d", "v.",
"Fed. R. Civ. P."), `services/legal/deterministic_envelope.py` (`build_deterministic_envelope` orchestrating
L1-L6 / C1-C5, emitting the exact envelope shape).

Changed: `verify.py:250-252` swap behind env flag `CACHET_DETERMINISTIC_VERIFY=true` (default off, no silent
change); `_verify_result_from_envelope` + `api_models.py` add the 3-state verdict + coverage-summary fields;
`case_verification.py:59` deprecate `_CITATION_SHAPE` to a fallback.

Storage: no new migration required. `evidence_references` already has `anchor_text/anchor_start/anchor_end`
(`migrations/0001_initial.sql:186-188`).

PR slicing (each keeps the full verify chain green): PR-A anchors.py + tests; PR-B eyecite adapter (fixes
the F.3d bug, independently shippable visible win); PR-C defined-term table; PR-D deterministic_envelope
behind the flag; PR-E coverage-summary UI + 3-state tray.

## The 3 decisions most likely to be wrong

1. "Anchor coverage is complete, so no-anchor -> skip is safe." It is not: ~65-75% of contract claims and
   the highest-value litigator factual assertions have no anchor. Fallback: anchor is a precision gate; the
   skip set is a loud itemized tray with a mandatory coverage summary, split into checked-no-support vs
   could-not-check; one-click "check this anyway" delegates scope to the human. The tray is the product.
2. "The contract path is no-AI end to end." Two breaks: ingest is T1 (Docling typing; OCR for scans), and the
   parametric-contradiction recipe is an original, medium-confidence claim with unknown recall on word-form
   values, while verbatim-present still does not equal proposition-support (a "$1M cap EXCLUDING gross
   negligence" carve-out passes a naive presence check). Fallback: for digital contracts say "text is T0,
   typing is T1"; OCR banner + "approximate" verdict for scans; print "review full clause for context" on
   every present-verdict; demo parametric contradiction only on a pre-vetted clean-mismatch corpus.
3. "Cachet can determine proposition support without an LLM." Holding-match and paraphrase entailment are
   semantic; no T0 method resolves them; the code correctly uses a T2 call. Fallback: keep holding-match OFF
   in the demo (the flag exists); ship on existence + verbatim + parametric contradiction (genuinely T0 and
   visceral); offer support-checking only as a labeled assistive tier (local NLI T1, confidence-gated, or
   AFM/MLX T2). Never print a support verdict as deterministic.

## Verification ledger (assert only the confirmed column)

CONFIRMED: eyecite 2.7.6 is T0 (Aho-Corasick + reporters-db, zero weights), BSD-2-Clause, offline, already
installed directly in the venv, gives char offsets; `_CITATION_SHAPE` misses digit-bearing reporters (live
4/7 vs eyecite 7/7); LexNLP is AGPL-3.0 and its amounts/dates paths are T1; Stanford OpenIE is T1 and GPL-3;
verbatim presence does not imply proposition support; WestCheck/Shepard's BriefCheck are anchor-first
(citation pattern then lookup); Thomson Reuters Deal Proof checks defined-terms/dates/amounts/cross-refs
deterministically (validates the contract anchor taxonomy); BriefCatch RealityCheck and Clearbrief are
cloud-bound (validates the local differentiation; Clearbrief factual scoring is T1, not T0).

UNCERTAIN / REFUTED: the 46-54% contract anchor-coverage figure (refuted; CUAD-grounded ~25-35%); whether
parametric-contradiction recall holds on word-form values (unknown, untested); spaCy statistical NER is T1
not T0; scare-quote false positives in quoted-run detection are unbounded without calibration.

UNKNOWN: on-device NLI single-pair latency on the target Mac; parametric-contradiction recall on real NDAs;
exact bundled citation-index size (carried from the architecture note).
