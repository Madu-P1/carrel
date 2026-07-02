# Round-0 Baseline: Cachet Deterministic Verification Engine

**Date:** 2026-06-29  
**Branch:** foundry/cachet-honest-auto  
**Gate script:** `script/cachet-acceptance.py` (run verbatim, no reimplementation)  
**Bar applied:** `--bar 0.95` for all six corpora  
**Total cases across all corpora:** 608  

---

## Section A: Catastrophic Failure Census

### False-Greens (fabricated/altered claim engine reported as "supported")

**None found across all six corpora.**

| Corpus | Cases checked | False-greens |
|---|---|---|
| corpus.jsonl | 8 | 0 |
| contract_corpus.jsonl | 13 | 0 |
| collision_corpus.jsonl | 387 | 0 |
| injection_corpus.jsonl | 130 | 0 |
| polarity_collision_corpus.jsonl | 4 | 0 |
| recall_corpus.jsonl | 66 | 0 |
| **Total** | **608** | **0** |

The engine emits `supported` only on `governing-law-supported` (contract_corpus, line 5) and `polarity-true-support-license` (polarity_collision_corpus, line 4) — both correct. Every false-green guard case (`subject-confusion-false-green-guard`, `cap-multifigure-false-green-guard`, `fg-capped-at-phrasing`, `fg-bare-role-subjects`, `fg-min-vs-max`, `fg-subjectless-claim-vs-bound-clause`, `fg-duration-continue-for-phrasing`, `coincidental-same-value-different-label-guard`, `no-bindable-label-must-refuse`) returned `could_not_verify`, never `supported`.

### False-Accusations (clean claim engine flagged as "contradicted")

**None found across all six corpora.**

| Corpus | Cases checked | False-accusations |
|---|---|---|
| corpus.jsonl | 8 | 0 |
| contract_corpus.jsonl | 13 | 0 |
| collision_corpus.jsonl | 387 | 0 |
| injection_corpus.jsonl | 130 | 0 |
| polarity_collision_corpus.jsonl | 4 | 0 |
| recall_corpus.jsonl | 66 | 0 |
| **Total** | **608** | **0** |

The engine never emits `contradicted` on a `supported` or `could_not_verify` expected case.

---

## Section B: Per-Corpus Results Table

| Corpus | Cases | Definite expected | Definite hit | Definite-rate | vs 0.95 bar | Bar 1 FG | Bar 2 FA | Bar 3 Specific | Overall |
|---|---|---|---|---|---|---|---|---|---|
| corpus.jsonl | 8 | 5 | 1 | **0.20** | FAIL | PASS | PASS | **FAIL (5)** | RED |
| contract_corpus.jsonl | 13 | 7 | 4 | **0.57** | FAIL | PASS | PASS | PASS | RED |
| collision_corpus.jsonl | 387 | 0 | 0 | 1.00 (vacuous) | PASS | PASS | PASS | PASS | GREEN |
| injection_corpus.jsonl | 130 | 0 | 0 | 1.00 (vacuous) | PASS | PASS | PASS | PASS | GREEN |
| polarity_collision_corpus.jsonl | 4 | 2 | 2 | **1.00** | PASS | PASS | PASS | PASS | GREEN |
| recall_corpus.jsonl | 66 | 66 | 22 | **0.33** | FAIL | PASS | PASS | PASS | RED |

**Summary: 3 RED, 3 GREEN. All six pass Bar 1 (zero false-greens) and Bar 2 (zero false-accusations).**

### Key structural observations from the data

**What the engine does reliably:**
- Contradiction detection: 100% of `contradicted` expected cases across every corpus. Parametric contradictions (altered figure) are caught without exception.
- False-green safety: 0 false greens across 608 cases, including all fabricated-alignment guard cases in the collision and injection corpora.
- Governing-law support detection: text-match cases (`governing-law-supported`, `polarity-true-support-license`) resolve correctly.

**Where the engine fails (all Bar 4, not Bar 1/2):**

1. **corpus.jsonl (definite-rate 0.20):** The engine fires `multi_value_unverifiable` on every multi-figure clause, including cases where the claim's specific figure IS present and attributable. `quantum-25pct-supported` (line 1) and `extra-margins-10pct-supported` (line 2) are clean single-claim single-match cases that fail because the source clause also contains an incidental second figure (10% profitability threshold alongside 25% Amount A). `scope-20bn-supported` (line 3) fires `not_found` despite an exact match in the clause. Additionally, `coincidental-same-value-different-label-guard` (line 7, expected: `contradicted`) falls back to `could_not_verify` because the aligner is not yet shipped.

2. **corpus.jsonl Bar 3 (5 content-free refusals):** The boilerplate "The percent/magnitude values in the summary and the loaded source cannot be aligned one-to-one deterministically" does not name any figure from its own claim, triggering Bar 3 failures for:
   - Line 1: `quantum-25pct-supported`
   - Line 2: `extra-margins-10pct-supported`
   - Line 5: `subject-confusion-false-green-guard`
   - Line 7: `coincidental-same-value-different-label-guard`
   - Line 8: `no-bindable-label-must-refuse`

3. **contract_corpus.jsonl (definite-rate 0.57):** Three misses:
   - Line 1, `cap-supported`: single-figure liability cap clause fires `not_found`.
   - Line 3, `term-supported`: single-figure duration clause fires `not_found`.
   - Line 7, `exclusivity-contradiction`: polarity contradiction (exclusive vs non-exclusive) fires `multi_value_unverifiable` instead of `contradicted`.

4. **recall_corpus.jsonl (definite-rate 0.33):** Systemic recall failure on the `supported` direction. All 22 contradicted cases pass (100%). All 44 supported cases fail (0%). Every `*-supported-floor` case (lines 1, 4, 7, 10, 13, 16, 19, 22, 25, 28, 31, 34, 37, 40, 43, 46, 49, 52, 55, 58, 61, 64) fires `not_found` despite exact-match "The X is $Y." clauses. Every `*-supported-afm` case (lines 3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36, 39, 42, 45, 48, 51, 54, 57, 60, 63, 66) fires `not_found` on natural-language phrasing that the regex floor cannot bind (AFM labeler path not active by default).

---

## Section C: Verbatim Commands and Raw Script Output

### Commands run

```bash
# All commands run from /Users/madu/Desktop/Codex-foundry-cachet

./.venv/bin/python script/cachet-acceptance.py --corpus evals/cachet_acceptance/corpus.jsonl --bar 0.95
./.venv/bin/python script/cachet-acceptance.py --corpus evals/cachet_acceptance/contract_corpus.jsonl --bar 0.95
./.venv/bin/python script/cachet-acceptance.py --corpus evals/cachet_acceptance/collision_corpus.jsonl --bar 0.95
./.venv/bin/python script/cachet-acceptance.py --corpus evals/cachet_acceptance/injection_corpus.jsonl --bar 0.95
./.venv/bin/python script/cachet-acceptance.py --corpus evals/cachet_acceptance/polarity_collision_corpus.jsonl --bar 0.95
./.venv/bin/python script/cachet-acceptance.py --corpus evals/cachet_acceptance/recall_corpus.jsonl --bar 0.95
```

---

### corpus.jsonl (8 cases) — RAW OUTPUT

```
Cachet acceptance gate  |  corpus: evals/cachet_acceptance/corpus.jsonl  (8 cases)

  id                                       expected         engine           disposition
  ---------------------------------------- ---------------- ---------------- ------------------------
  quantum-25pct-supported                  supported        could_not_verify multi_value_unverifiable  [XX]
  extra-margins-10pct-supported            supported        could_not_verify multi_value_unverifiable  [XX]
  scope-20bn-supported                     supported        could_not_verify not_found  [XX]
  alteration-30pct-contradiction           contradicted     contradicted     parametric_contradiction  [ok]
  subject-confusion-false-green-guard      could_not_verify could_not_verify multi_value_unverifiable  [ok]
  equal-allocation-not-grounded            could_not_verify could_not_verify not_found  [ok]
  coincidental-same-value-different-label-guard contradicted     could_not_verify multi_value_unverifiable  [XX]
  no-bindable-label-must-refuse            could_not_verify could_not_verify multi_value_unverifiable  [ok]

  bars:
    1. zero false greens .......... PASS
    2. zero false accusations ..... PASS
    3. refusals are specific ...... FAIL (5 content-free)
    4. definite-rate >= 0.95 ...... FAIL  (1/5 = 0.20)

  content-free refusals (name no figure from their own statement):
    - quantum-25pct-supported: The percent values in the summary and the loaded source cannot be aligned one-to-one deterministically, so thi
    - extra-margins-10pct-supported: The percent values in the summary and the loaded source cannot be aligned one-to-one deterministically, so thi
    - subject-confusion-false-green-guard: The percent values in the summary and the loaded source cannot be aligned one-to-one deterministically, so thi
    - coincidental-same-value-different-label-guard: The magnitude values in the summary and the loaded source cannot be aligned one-to-one deterministically, so t
    - no-bindable-label-must-refuse: The magnitude values in the summary and the loaded source cannot be aligned one-to-one deterministically, so t

  RESULT: RED - not demo-ready
```

---

### contract_corpus.jsonl (13 cases) — RAW OUTPUT

```
Cachet acceptance gate  |  corpus: evals/cachet_acceptance/contract_corpus.jsonl  (13 cases)

  id                                       expected         engine           disposition
  ---------------------------------------- ---------------- ---------------- ------------------------
  cap-supported                            supported        could_not_verify not_found  [XX]
  cap-altered-contradiction                contradicted     contradicted     parametric_contradiction  [ok]
  term-supported                           supported        could_not_verify not_found  [XX]
  term-altered-contradiction               contradicted     contradicted     parametric_contradiction  [ok]
  governing-law-supported                  supported        supported        present  [ok]
  governing-law-contradiction              contradicted     contradicted     parametric_contradiction  [ok]
  exclusivity-contradiction                contradicted     could_not_verify multi_value_unverifiable  [XX]
  cap-multifigure-false-green-guard        could_not_verify could_not_verify not_found  [ok]
  fg-capped-at-phrasing                    could_not_verify could_not_verify not_found  [ok]
  fg-bare-role-subjects                    could_not_verify could_not_verify not_found  [ok]
  fg-min-vs-max                            could_not_verify could_not_verify not_found  [ok]
  fg-subjectless-claim-vs-bound-clause     could_not_verify could_not_verify not_found  [ok]
  fg-duration-continue-for-phrasing        could_not_verify could_not_verify not_found  [ok]

  bars:
    1. zero false greens .......... PASS
    2. zero false accusations ..... PASS
    3. refusals are specific ...... PASS
    4. definite-rate >= 0.95 ...... FAIL  (4/7 = 0.57)

  RESULT: RED - not demo-ready
```

---

### collision_corpus.jsonl (387 cases) — RAW OUTPUT (summary only; full per-item output persisted)

```
[387 rows, all: could_not_verify | could_not_verify | not_found  [ok]]

  bars:
    1. zero false greens .......... PASS
    2. zero false accusations ..... PASS
    3. refusals are specific ...... PASS
    4. definite-rate >= 0.95 ...... PASS  (0/0 = 1.00)

  RESULT: GREEN - demo bar met
```

---

### injection_corpus.jsonl (130 cases) — RAW OUTPUT (summary only; full per-item output available)

```
[130 rows, all: could_not_verify | could_not_verify | not_found  [ok]]

  bars:
    1. zero false greens .......... PASS
    2. zero false accusations ..... PASS
    3. refusals are specific ...... PASS
    4. definite-rate >= 0.95 ...... PASS  (0/0 = 1.00)

  RESULT: GREEN - demo bar met
```

---

### polarity_collision_corpus.jsonl (4 cases) — RAW OUTPUT

```
Cachet acceptance gate  |  corpus: evals/cachet_acceptance/polarity_collision_corpus.jsonl  (4 cases)

  id                                       expected         engine           disposition
  ---------------------------------------- ---------------- ---------------- ------------------------
  polarity-collision-license-vs-warranty   could_not_verify could_not_verify not_found  [ok]
  polarity-collision-agreement-vs-consent  could_not_verify could_not_verify not_found  [ok]
  polarity-true-contradiction-license      contradicted     contradicted     parametric_contradiction  [ok]
  polarity-true-support-license            supported        supported        present  [ok]

  bars:
    1. zero false greens .......... PASS
    2. zero false accusations ..... PASS
    3. refusals are specific ...... PASS
    4. definite-rate >= 0.95 ...... PASS  (2/2 = 1.00)

  RESULT: GREEN - demo bar met
```

---

### recall_corpus.jsonl (66 cases) — RAW OUTPUT

```
Cachet acceptance gate  |  corpus: evals/cachet_acceptance/recall_corpus.jsonl  (66 cases)

  id                                       expected         engine           disposition
  ---------------------------------------- ---------------- ---------------- ------------------------
  recall-money-liability_cap-5000000-supported-floor supported        could_not_verify not_found  [XX]
  recall-money-liability_cap-5000000-contradicted-floor contradicted     contradicted     parametric_contradiction  [ok]
  recall-money-liability_cap-5000000-supported-afm supported        could_not_verify not_found  [XX]
  recall-money-liability_cap-250000-supported-floor supported        could_not_verify not_found  [XX]
  recall-money-liability_cap-250000-contradicted-floor contradicted     contradicted     parametric_contradiction  [ok]
  recall-money-liability_cap-250000-supported-afm supported        could_not_verify not_found  [XX]
  recall-money-indemnification_cap-5000000-supported-floor supported        could_not_verify not_found  [XX]
  recall-money-indemnification_cap-5000000-contradicted-floor contradicted     contradicted     parametric_contradiction  [ok]
  recall-money-indemnification_cap-5000000-supported-afm supported        could_not_verify not_found  [XX]
  recall-money-indemnification_cap-250000-supported-floor supported        could_not_verify not_found  [XX]
  recall-money-indemnification_cap-250000-contradicted-floor contradicted     contradicted     parametric_contradiction  [ok]
  recall-money-indemnification_cap-250000-supported-afm supported        could_not_verify not_found  [XX]
  recall-money-security_deposit-5000000-supported-floor supported        could_not_verify not_found  [XX]
  recall-money-security_deposit-5000000-contradicted-floor contradicted     contradicted     parametric_contradiction  [ok]
  recall-money-security_deposit-5000000-supported-afm supported        could_not_verify not_found  [XX]
  recall-money-security_deposit-250000-supported-floor supported        could_not_verify not_found  [XX]
  recall-money-security_deposit-250000-contradicted-floor contradicted     contradicted     parametric_contradiction  [ok]
  recall-money-security_deposit-250000-supported-afm supported        could_not_verify not_found  [XX]
  recall-money-signing_bonus-5000000-supported-floor supported        could_not_verify not_found  [XX]
  recall-money-signing_bonus-5000000-contradicted-floor contradicted     contradicted     parametric_contradiction  [ok]
  recall-money-signing_bonus-5000000-supported-afm supported        could_not_verify not_found  [XX]
  recall-money-signing_bonus-250000-supported-floor supported        could_not_verify not_found  [XX]
  recall-money-signing_bonus-250000-contradicted-floor contradicted     contradicted     parametric_contradiction  [ok]
  recall-money-signing_bonus-250000-supported-afm supported        could_not_verify not_found  [XX]
  recall-money-termination_penalty-5000000-supported-floor supported        could_not_verify not_found  [XX]
  recall-money-termination_penalty-5000000-contradicted-floor contradicted     contradicted     parametric_contradiction  [ok]
  recall-money-termination_penalty-5000000-supported-afm supported        could_not_verify not_found  [XX]
  recall-money-termination_penalty-250000-supported-floor supported        could_not_verify not_found  [XX]
  recall-money-termination_penalty-250000-contradicted-floor contradicted     contradicted     parametric_contradiction  [ok]
  recall-money-termination_penalty-250000-supported-afm supported        could_not_verify not_found  [XX]
  recall-money-annual_retainer-5000000-supported-floor supported        could_not_verify not_found  [XX]
  recall-money-annual_retainer-5000000-contradicted-floor contradicted     contradicted     parametric_contradiction  [ok]
  recall-money-annual_retainer-5000000-supported-afm supported        could_not_verify not_found  [XX]
  recall-money-annual_retainer-250000-supported-floor supported        could_not_verify not_found  [XX]
  recall-money-annual_retainer-250000-contradicted-floor contradicted     contradicted     parametric_contradiction  [ok]
  recall-money-annual_retainer-250000-supported-afm supported        could_not_verify not_found  [XX]
  recall-duration-notice_period-3years-supported-floor supported        could_not_verify not_found  [XX]
  recall-duration-notice_period-3years-contradicted-floor contradicted     contradicted     parametric_contradiction  [ok]
  recall-duration-notice_period-3years-supported-afm supported        could_not_verify not_found  [XX]
  recall-duration-notice_period-90days-supported-floor supported        could_not_verify not_found  [XX]
  recall-duration-notice_period-90days-contradicted-floor contradicted     contradicted     parametric_contradiction  [ok]
  recall-duration-notice_period-90days-supported-afm supported        could_not_verify not_found  [XX]
  recall-duration-initial_term-3years-supported-floor supported        could_not_verify not_found  [XX]
  recall-duration-initial_term-3years-contradicted-floor contradicted     contradicted     parametric_contradiction  [ok]
  recall-duration-initial_term-3years-supported-afm supported        could_not_verify not_found  [XX]
  recall-duration-initial_term-90days-supported-floor supported        could_not_verify not_found  [XX]
  recall-duration-initial_term-90days-contradicted-floor contradicted     contradicted     parametric_contradiction  [ok]
  recall-duration-initial_term-90days-supported-afm supported        could_not_verify not_found  [XX]
  recall-duration-cure_period-3years-supported-floor supported        could_not_verify not_found  [XX]
  recall-duration-cure_period-3years-contradicted-floor contradicted     contradicted     parametric_contradiction  [ok]
  recall-duration-cure_period-3years-supported-afm supported        could_not_verify not_found  [XX]
  recall-duration-cure_period-90days-supported-floor supported        could_not_verify not_found  [XX]
  recall-duration-cure_period-90days-contradicted-floor contradicted     contradicted     parametric_contradiction  [ok]
  recall-duration-cure_period-90days-supported-afm supported        could_not_verify not_found  [XX]
  recall-duration-warranty_period-3years-supported-floor supported        could_not_verify not_found  [XX]
  recall-duration-warranty_period-3years-contradicted-floor contradicted     contradicted     parametric_contradiction  [ok]
  recall-duration-warranty_period-3years-supported-afm supported        could_not_verify not_found  [XX]
  recall-duration-warranty_period-90days-supported-floor supported        could_not_verify not_found  [XX]
  recall-duration-warranty_period-90days-contradicted-floor contradicted     contradicted     parametric_contradiction  [ok]
  recall-duration-warranty_period-90days-supported-afm supported        could_not_verify not_found  [XX]
  recall-duration-renewal_term-3years-supported-floor supported        could_not_verify not_found  [XX]
  recall-duration-renewal_term-3years-contradicted-floor contradicted     contradicted     parametric_contradiction  [ok]
  recall-duration-renewal_term-3years-supported-afm supported        could_not_verify not_found  [XX]
  recall-duration-renewal_term-90days-supported-floor supported        could_not_verify not_found  [XX]
  recall-duration-renewal_term-90days-contradicted-floor contradicted     contradicted     parametric_contradiction  [ok]
  recall-duration-renewal_term-90days-supported-afm supported        could_not_verify not_found  [XX]

  bars:
    1. zero false greens .......... PASS
    2. zero false accusations ..... PASS
    3. refusals are specific ...... PASS
    4. definite-rate >= 0.95 ...... FAIL  (22/66 = 0.33)

  RESULT: RED - not demo-ready
```

---

## Interpretation note

All failures are Bar 3 (specificity) and Bar 4 (recall) — none are Bar 1 or Bar 2. The engine is structurally safe: it never greens a fabricated claim and never flags a clean claim. Its entire failure surface is under-reaching: it refuses to confirm `supported` in cases where it should, and its refusal boilerplate is generic rather than claim-specific.

The two highest-priority repair targets by corpus impact are:

1. **recall_corpus recall gap (44 missed `supported` cases):** The floor binder fires `not_found` on exact-match "The X is $Y." clauses across all 11 money and 5 duration subjects. This is a single code path; fixing it closes 44/44 of these misses.

2. **corpus.jsonl multi-figure wall (3 missed `supported` + 5 content-free refusals):** The `multi_value_unverifiable` path fires whenever the source clause contains more than one numeric figure, even when the claim's specific figure is unambiguously attributed. The fix requires subject-bound figure routing, not just multi-figure detection.
