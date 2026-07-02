# Kernel-residue parity report (ADR-0015, revisit-trigger #3)

The kernel adapter (cachet_verify: legal-engine parametrics + kernel residue detectors + quote check) against non-legal AI fabrications. No citation or caselaw pack in play.

## Headline numbers

- **Altered-catch rate: 15/15 (100%)** on anchored, near-verbatim fabrications
- **False greens: 0** (floor: 0)
- **False accusations: 0** (floor: 0)
- Faithful confirmed: 5/5
- Honest refusal on uncheckable/blind-spot cases: 5/5

## Per-case results

| id | domain | truth | outcome | engine says | note |
|---|---|---|---|---|---|
| F1 | finance | altered | flagged | `altered` | transposed money figure on a near-verbatim sentence |
| F2 | finance | faithful | supported | `verified` | faithful restatement, both figures intact |
| F3 | finance | altered | flagged | `altered` | digit-swapped percent on a near-verbatim sentence |
| F4 | finance | uncheckable | refused | `could_not_check` | pure semantic claim, no anchor: must refuse, never rule |
| F5 | finance | altered | flagged | `altered` | magnitude alteration, EU-finance shape (the live BIM catch, non-legal framing) |
| C1 | consulting | altered | flagged | `altered` | 10x magnitude drift (million -> billion) |
| C2 | consulting | faithful | supported | `verified` | faithful duration |
| C3 | consulting | altered | flagged | `altered` | dropped-digit duration drift |
| C4 | consulting | altered | flagged | `altered` | physical-unit drift (tons): CLOSED by the kernel residue detector, batch A |
| M1 | medical | altered | flagged | `altered` | drug-dosage drift (mg): the highest-stakes blind spot, CLOSED in batch A |
| M2 | medical | altered | flagged | `altered` | duration drift in a clinical narrative |
| M3 | medical | faithful | supported | `verified` | faithful clinical percent |
| M4 | medical | altered | flagged | `altered` | date drift (textual, unambiguous form) |
| T1 | tax | altered | flagged | `altered` | order-of-magnitude money drift on a threshold |
| T2 | tax | faithful | supported | `verified` | faithful threshold |
| T3 | tax | altered | flagged | `altered` | dropped-zero percent drift |
| P1 | operations | altered | flagged | `altered` | payment-terms duration drift beside a faithful price |
| P2 | operations | altered | flagged | `altered` | grouped-count drift: CLOSED by the kernel residue detector, batch A |
| G1 | operations | uncheckable | refused | `could_not_check` | ratio notation is NOT an anchored type yet: documented gap, must refuse |
| G2 | medical | uncheckable | refused | `could_not_check` | word-form frequency is NOT an anchored type yet: documented gap, must refuse |
| G4 | finance | uncheckable | refused | `could_not_check` | synonym-subject alteration (fine/penalty): the token gate cannot tell it from a cross-fact figure without reopening the break-fee false accusation (mythos batchD, refuted). Deliberate over-refusal; documented gap. |
| G3 | medical | uncheckable | refused | `could_not_check` | temperature units are NOT anchored yet (unit ambiguity risk): documented gap |
| Q1 | journalism | altered | flagged | `altered` | quote with a swapped tail: invented words attributed to a speaker |
| Q2 | journalism | faithful | supported | `verified` | verbatim quoted phrase |
| Q3 | journalism | altered | flagged | `altered` | wholly fabricated quote, nothing close in the source |

## Details (flagged cases)

- **F1**: The summary states $4.2 billion; the loaded source states $2.4 billion.
- **F3**: The summary states 64%; the loaded source states 46%.
- **F5**: The summary states 60 billion; the loaded source states 20 billion.
- **C1**: The summary states 3 billion; the loaded source states 300 million.
- **C3**: The summary states 8 months; the loaded source states 18 months.
- **C4**: The summary states 620 tons; the loaded source states 120 tons.
- **M1**: The summary states 50 mg; the loaded source states 5 mg.
- **M2**: The summary states 14 days; the loaded source states 7 days.
- **M4**: The summary states March 1, 2026; the loaded source states March 11, 2026.
- **T1**: The summary states $25,000; the loaded source states $2,500.
- **T3**: The summary states 2%; the loaded source states 20%.
- **P1**: The summary states 45 days; the loaded source states 30 days.
- **P2**: The summary states 2,140; the loaded source states 1,240.
- **Q1**: quoted words absent from every source
- **Q3**: quoted words absent from every source
