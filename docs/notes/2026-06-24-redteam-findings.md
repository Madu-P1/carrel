# Red-team findings — cachet-adversary confession battery (2026-06-24)

Produced by the read-only adversarial discovery harness (`evals/adversary/`). The
battery ran **493 adversarial probes across 22 families** through the REAL
deterministic engine, under a socket ban that proves zero egress. Every probe
carries a provable honest expectation by construction.

- **490 HELD** · **0 false accusations** · **0 laundering** · **2 false greens (P0)** ·
  **1 honest-direction observation**
- Ledger: `.claude/adversary/confession-ledger-*.md` (+ `.json`, + crack fixtures).
- Locking tests: `tests/test_redteam_findings.py` (open findings `expectedFailure`;
  the day the engine is fixed they flip to unexpected-success and flag the reviewer).

**Constitution note.** The harness is read-only: it imports the engine and reads
its verdict back, editing no truth-surface file. The fixes below touch gated truth
surfaces (`contract_verify.py` / `anchors.py`) and are therefore DRAFTED + queued
for REVIEW per `.claude/forge.contract.yaml`. Nothing here is merged.

---

## RT1 — Single-value percent affirmed subject-blind (P0 false green, REVIEW)

**What the engine did.** A single-value percent clause affirms (`disposition=present`
-> `supported`) ANY claim that carries that percent value, even when the claim's
subject never appears in the clause.

```
verify_claim_against_clause(
    "The audit fee is 10% of Net Sales.",
    "Licensee shall pay Licensor a royalty of 10% of Net Sales",
).disposition == "present"   # <- false green; 10% is the ROYALTY, not an audit fee

verify_claim_against_clause(
    "The early-payment discount is 8%.",
    "overdue amounts shall bear interest at a rate of 8% per annum",
).disposition == "present"   # <- false green; 8% is the INTEREST rate, not a discount
```

**Why it matters.** This is the exact AI-summary failure the product exists to
catch: a draft re-attributes a contract's number to the wrong subject, and the
engine greens it. The detail string even reads "8% appears in the loaded source;
review the full passage for context" — an affirmation, not a refusal.

**Root cause (the asymmetry).** Money and duration are scoped out by ADR-0013: a
bare value match there resolves to `not_found` (could-not-verify), never
`present`. Percent (and date, and governing-law) are NOT scoped out — they affirm
on a bare single-value match. Confirmed: the behavior is identical with
`CARREL_SUBJECT_LABELER=off` and `=regex`, so the existing subject labeler does not
close it (the labeler disambiguates multiple subjects *within* a clause; here the
claim's subject is simply absent from a single-value clause).

**Distinct from the already-fixed class.** The multi-value subject-collision
(`10% France` vs `10% Germany` in one clause) HOLDS now — the `subject-swap` family
ran 7/7 to could-not-verify. RT1 is the *single-value subject-absence* case, which
is still open.

**This reproduces a KNOWN operator-gated item**, not a novel surprise: it is the
"Role-aligned clause matching (after T66 validation)" entry in the NOT-queued
section of `.claude/forge.engine.tasks.md`. The value of this finding is a
deterministic, minimal, test-locked reproduction that the eventual fix can be
graded against.

**Candidate fixes (operator/REVIEW decision — do NOT merge unattended).**
1. Extend the ADR-0013 figure scope-out to percent in the default path: a matching
   percent resolves to could-not-verify (could-not-check), never `present`. Simplest,
   consistent with money/duration, costs the (rare) honest single-subject percent
   affirmation.
2. Gate percent affirmation on the claim's subject token appearing in (or aligning
   with) the matched clause — the "role-aligned clause matching" work, which needs
   the subject labeler to bind a subject to a single-value clause. Higher fidelity,
   larger change, validation-gated.

**Locking test.** `tests/test_redteam_findings.py::PercentSubjectBindingTests`
(`expectedFailure` until fixed) + the money/duration positive controls that must
not regress. The harness also pins it as a tripwire
(`tests/test_adversary_harness.py::...subject_binding_false_green_is_present`).

---

## RT2 — Verbatim quote missed on sentence-start case difference (P3, honest-direction)

**What the engine did.** A quote that is present verbatim in the clause but differs
only in case at a sentence start is left could-not-verify instead of supported.

```
verify_claim_against_clause(
    'The contract states that "time is of the essence" for all deadlines.',
    "Time is of the essence with respect to each obligation under this Agreement.",
).disposition == "not_found"   # <- missed; the clause says "Time is of the essence"
```

**Why it is only P3.** This is the SAFE direction — under-affirmation, never a false
green. But it is a real coverage gap: a lawyer who pastes a quote lowercase will not
get the confirmation they should. The other three quote controls (mid-sentence,
already-lowercase) confirm correctly, so the trigger is specifically the leading
capital.

**Candidate fix (REVIEW).** Case-insensitive (or case-folded) quote-anchor matching
in the quote path. Locking test:
`tests/test_redteam_findings.py::QuoteCaseSensitivityTests` (`expectedFailure`).

---

## What HELD (the moat's strengths, confirmed under fire)

- **Money & duration scope-out**: 120 money + 111 near-miss-duration + 12
  unit-confusion + 5 magnitude-scaling + 5 word-form contradictions all caught or
  honestly refused; 0 false greens.
- **Fabricated & misattributed citations**: 8 caption-mismatch, 3 year, 3 court all
  flagged; 8 fabricated cites refused; the real cite still affirmed. The 2026
  sanctions-frontier surface holds.
- **Quote alteration**: 16 fabricated quotes, 0 affirmed.
- **Multi-value subject-collision**: 7/7 honest refusal (the previously-fixed class).
- **Format robustness**: date/percent format variants and equivalent durations are
  not falsely accused.
