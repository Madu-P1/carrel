# Cachet confession ledger — 2026-06-23T23:18:05.319451Z

Cachet attacked its own deterministic verify engine. Every probe below was run through the REAL engine (no mock of verdict logic), under a socket ban that proves zero network egress, and carries a PROVABLE honest expectation by construction. A divergence from that expectation is a real crack, not a guess.

## Headline

- **493** adversarial probes across **22** families
- **490** HELD (engine answered honestly)
- **2** crack(s) surfaced — listed first, each with its locking test
  - FALSE GREEN (P0): 2  |  LAUNDERING (P0): 0  |  FALSE ACCUSATION (P1): 0
- composition: 47 hand-crafted hard cases, 446 systematic value-space probes

## Cracks (the confession)

Each crack is where the engine was caught being wrong. The repro line reproduces it against the real engine; the locking test is the held-out regression that would prevent it. Fixes are DRAFTED + queued for review, never merged unattended (engine truth surfaces are human-gated).

### Crack 1: FALSE GREEN (P0 — affirmed the unsupportable)
- **family**: `subject-mismatch-single`  ·  **case**: `subjmismatch.percent_interest`
- **claim**: The early-payment discount is 8%.
- **source**: overdue amounts shall bear interest at a rate of 8% per annum
- **engine said**: `supported` (disposition `present`)  ·  **honest expectation**: {contradicted | could_not_verify}
- **why it is a crack**: 8% is the default interest rate; the claim re-attributes it to a discount. Affirming it (supported) would be subject-blind: a false green.
- **repro**: `probe_contract('The early-payment discount is 8%.', 'overdue amounts shall bear interest at a rate of 8% per annum').state == 'supported'  # honest expectation: {contradicted | could_not_verify}`
- **locking test**: `test_redteam_subject_mismatch_single_001`

### Crack 2: FALSE GREEN (P0 — affirmed the unsupportable)
- **family**: `subject-mismatch-single`  ·  **case**: `subjmismatch.percent_royalty`
- **claim**: The audit fee is 10% of Net Sales.
- **source**: Licensee shall pay Licensor a royalty of 10% of Net Sales
- **engine said**: `supported` (disposition `present`)  ·  **honest expectation**: {contradicted | could_not_verify}
- **why it is a crack**: 10% is the royalty rate; the claim re-attributes it to an audit fee. Affirming it (supported) would be subject-blind: a false green.
- **repro**: `probe_contract('The audit fee is 10% of Net Sales.', 'Licensee shall pay Licensor a royalty of 10% of Net Sales').state == 'supported'  # honest expectation: {contradicted | could_not_verify}`
- **locking test**: `test_redteam_subject_mismatch_single_002`

## Honest-direction observations (coverage gaps, not cracks)

Here the engine REFUSED a claim that was honestly supportable — it failed to confirm a true positive. This is the SAFE direction (never a false green), but a coverage gap worth a fix.

- `quote-verbatim-control` · The contract states that "time is of the essence" for all deadlines.
  - engine: `could_not_verify`; honest expectation: {supported}
  - Verbatim quote "time is of the essence" is present in the clause; must stay supported.
  - repro: `probe_contract('The contract states that "time is of the essence" for all deadlines.', 'Time is of the essence with respect to each obligation under this Agreement.').state == 'could_not_verify'  # honest expectation: {supported}`

## Per-family coverage

| Family | Tier | Probes | Held | Cracks | State distribution |
|---|---|---|---|---|---|
| `citation-caption-mismatch` | proven | 8 | 8 | 0 | contradicted:8 |
| `citation-court-mismatch` | proven | 3 | 3 | 0 | contradicted:3 |
| `citation-fabricated` | proven | 8 | 8 | 0 | could_not_verify:8 |
| `citation-verbatim-control` | proven | 1 | 1 | 0 | supported:1 |
| `citation-year-mismatch` | proven | 3 | 3 | 0 | contradicted:3 |
| `clean-control` | proven | 20 | 20 | 0 | could_not_verify:13, supported:7 |
| `equivalent-duration` | proven | 3 | 3 | 0 | could_not_verify:3 |
| `format-variant-date` | proven | 4 | 4 | 0 | supported:4 |
| `format-variant-percent` | proven | 6 | 6 | 0 | supported:6 |
| `governing-law-lookalike` | exploratory | 8 | 8 | 0 | contradicted:8 |
| `magnitude-scaling-money` | proven | 5 | 5 | 0 | contradicted:5 |
| `near-miss-duration` | proven | 111 | 111 | 0 | contradicted:111 |
| `polarity-flip` | exploratory | 4 | 4 | 0 | could_not_verify:4 |
| `quote-alteration` | proven | 16 | 16 | 0 | could_not_verify:16 |
| `quote-verbatim-control` | proven | 4 | 3 | 0 | could_not_verify:1, supported:3 |
| `subject-mismatch-single` | proven | 4 | 2 | 2 | could_not_verify:2, supported:2 |
| `subject-swap` | proven | 7 | 7 | 0 | could_not_verify:7 |
| `unit-confusion-duration` | proven | 12 | 12 | 0 | contradicted:12 |
| `value-contradiction-date` | proven | 24 | 24 | 0 | contradicted:24 |
| `value-contradiction-money` | proven | 120 | 120 | 0 | contradicted:120 |
| `value-contradiction-percent` | proven | 117 | 117 | 0 | contradicted:117 |
| `word-form-money` | proven | 5 | 5 | 0 | contradicted:5 |

### Exploratory-family catch-rate (honest coverage, not cracks)

Polarity and governing-law contradiction-catching is NOT asserted as a hard expectation, so an honest could-not-verify there is HELD, not a crack. The catch-rate below is a coverage signal: how often the engine actively flagged the contradiction vs honestly refused.

- `governing-law-lookalike`: caught (contradicted) 8 / honest-refusal (could-not-verify) 0 of 8
- `polarity-flip`: caught (contradicted) 0 / honest-refusal (could-not-verify) 4 of 4

## Methodology

- **Read-only**: the harness imports the engine and reads its verdict back; it edits no truth-surface file (`contract_verify.py`, `deterministic_envelope.py`, `anchors.py`, `sentences.py`, `case_verification.py`, `local_caselaw.py`).
- **Zero-egress**: the entire battery runs inside a socket ban; any real socket construction raises. No network, no model download.
- **Deterministic**: the battery is reproducible run-to-run; only the ledger timestamp varies.
- **By design, not a crack**: money and duration are scoped out — a matching figure there resolves to could-not-verify, never supported (ADR-0013). Percent, date, and governing-law instead affirm a genuine single-value match as `supported` (as does a verbatim quote). The clean-control and format-variant families confirm the engine does not ACCUSE these clean claims. The subject-mismatch cracks above show the cost of that asymmetry: the percent affirmation path greens on the bare value alone, so it also greens a value re-attributed to a different subject.
- **Engine entry points**: contract path `verify_claim_against_clause(claim, clause)`; litigator path `build_deterministic_envelope(draft, client=local_caselaw_client())`.

