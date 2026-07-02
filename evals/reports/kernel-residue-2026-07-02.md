# Kernel-residue parity report (ADR-0015, revisit-trigger #3)

Domain-agnostic residue (quote, money, percent, duration, magnitude, date) against non-legal AI fabrications. No legal pack in play.

## Headline numbers

- **Altered-catch rate: 12/12 (100%)** on anchored, near-verbatim fabrications
- **False greens: 0** (floor: 0)
- **False accusations: 0** (floor: 0)
- Faithful confirmed: 1/5
- Honest refusal on uncheckable/blind-spot cases: 4/4

## Per-case results

| id | domain | truth | outcome | engine says | note |
|---|---|---|---|---|---|
| F1 | finance | altered | flagged | `parametric_contradiction` | transposed money figure on a near-verbatim sentence |
| F2 | finance | faithful | refused | `not_found` | faithful restatement, both figures intact |
| F3 | finance | altered | flagged | `parametric_contradiction` | digit-swapped percent on a near-verbatim sentence |
| F4 | finance | uncheckable | refused | `not_found` | pure semantic claim, no anchor: must refuse, never rule |
| F5 | finance | altered | flagged | `parametric_contradiction` | magnitude alteration, EU-finance shape (the live BIM catch, non-legal framing) |
| C1 | consulting | altered | flagged | `parametric_contradiction` | 10x magnitude drift (million -> billion) |
| C2 | consulting | faithful | refused | `not_found` | faithful duration |
| C3 | consulting | altered | flagged | `parametric_contradiction` | dropped-digit duration drift |
| C4 | consulting | uncheckable | refused | `not_found` | physical-unit figure (tons) is NOT an anchored type: blind spot, must refuse |
| M1 | medical | uncheckable | refused | `not_found` | drug dosage (mg) is NOT an anchored type: the highest-stakes blind spot, must refuse |
| M2 | medical | altered | flagged | `parametric_contradiction` | duration drift in a clinical narrative |
| M3 | medical | faithful | refused | `not_found` | faithful clinical percent |
| M4 | medical | altered | flagged | `parametric_contradiction` | date drift (textual, unambiguous form) |
| T1 | tax | altered | flagged | `parametric_contradiction` | order-of-magnitude money drift on a threshold |
| T2 | tax | faithful | refused | `not_found` | faithful threshold |
| T3 | tax | altered | flagged | `parametric_contradiction` | dropped-zero percent drift |
| P1 | operations | altered | flagged | `parametric_contradiction` | payment-terms duration drift beside a faithful price |
| P2 | operations | uncheckable | refused | `not_found` | bare grouped count is NOT an anchored type: blind spot, must refuse |
| Q1 | journalism | altered | flagged | `altered` | quote with a swapped tail: invented words attributed to a speaker |
| Q2 | journalism | faithful | supported | `verbatim` | verbatim quoted phrase |
| Q3 | journalism | altered | flagged | `altered` | wholly fabricated quote, nothing close in the source |

## Details (flagged cases)

- **F1**: The summary states $4.2 billion; the loaded source states $2.4 billion.
- **F3**: The summary states 64%; the loaded source states 46%.
- **F5**: The summary states 60 billion; the loaded source states 20 billion.
- **C1**: The summary states 3 billion; the loaded source states 300 million.
- **C3**: The summary states 8 months; the loaded source states 18 months.
- **M2**: The summary states 14 days; the loaded source states 7 days.
- **M4**: The summary states March 1, 2026; the loaded source states March 11, 2026.
- **T1**: The summary states $25,000; the loaded source states $2,500.
- **T3**: The summary states 2%; the loaded source states 20%.
- **P1**: The summary states 45 days; the loaded source states 30 days.
- **Q1**: year
- **Q3**: merger / create ten thousand new jobs
