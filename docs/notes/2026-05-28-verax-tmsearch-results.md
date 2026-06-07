# USPTO TMSearch results: VERAX in Class 9 + Class 42

**Search date:** 2026-05-28
**Tool:** USPTO Trademark Search (`tmsearch.uspto.gov`)
**Query:** Wordmark contains `VERAX`, filtered International Class 009 and International Class 042
**Source files:** `tmSearchResults2026-05-28.xlsx` (Class 9, 13 results) + `tmSearchResults2026-05-28-2.xlsx` (broader, 10 results)
**Verdict:** **BLOCKED in IC 009 + IC 042.** Recommend fallback to VOUCH per [ADR-0010](../adr/ADR-0010-v2-monorepo-second-frontend.md) backup ladder, or operator engages IP counsel for a preliminary opinion before committing to VERAX.

## Blockers identified

### Tier 1 — likely blocking (do not file without counsel)

**1. DSM IP Assets B.V. (Netherlands) — two registered VERAX marks in IC 009 + IC 042**

| | |
|---|---|
| Marks | VERAX (Reg 7081161, Serial 90231215) + VERAX (Reg 7081155, Serial 90201048) |
| Status | LIVE, registered 2023-06-13 |
| Class | IC 009 + IC 042 |
| Goods | Downloadable + non-downloadable software for monitoring animal feed ingredients, animal health, welfare and nutrition, environmental impact. Animal-management domain. |
| Concern | Identical wordmark in identical class. Goods are narrower than ours (animal mgmt vs. legal/professional verification) but USPTO 2(d) refusal applies when marks are identical and goods are related — counsel call on whether "software for monitoring X" and "software for verifying Y" are related enough to refuse. |

DSM also owns **VERAX KNOW MORE, SOONER** (Reg 6896408) in IC 009 + IC 042 — slogan + brand combination, same domain. Confirms DSM is actively branding under VERAX in software classes.

**2. APODEX US, Inc. (Delaware) — recent intent-to-use filing, broad claims**

| | |
|---|---|
| Mark | VERAX (Serial 99818726) |
| Status | LIVE, filed 2026-05-12 (two weeks before this search), Basis 1b (intent to use) |
| Classes | IC 009 + IC 010 + IC 041 + IC 042 + IC 044 (five classes) |
| Goods | Includes "downloadable computer software programs for use in database management, use as a spreadsheet, word processing," "downloadable smartphone software," AI humanoid robots, surgical robots, medical apparatus, and more. |
| Concern | This is the worst blocker. Priority date 2026-05-12. Broad general-purpose software claims directly in IC 009 + IC 042. Five-class filing indicates a strategy of locking down VERAX across a wide surface. Even if APODEX never demonstrates real use, the pending 1b application sits as a blocker for new filings during the statutory window. |

### Tier 2 — navigable but adds noise

| Mark | Owner | Class | Goods |
|---|---|---|---|
| VERAX, VERAX CTX, VERAX IMX, VERAX ISX | JP3 Measurement, LLC (Texas) | IC 009 | Hardware: instruments and apparatus for oil-and-gas hydrocarbon composition monitoring |
| VERAX BIOMEDICAL × 2 | Verax Biomedical Inc. (Delaware) | IC 010, IC 016 | Medical immunoassay test kits; printed health/safety materials |
| VERAX FILMS × 2 | Verax Group, LLC (Alabama) | IC 041 | Motion picture / TV production |
| VERAX | Donald R. Kelley | IC 036 | Private equity / hedge fund investment services |
| VERAX, VERAX COMMODITIES, V (stylized) | Verax Commodities LLC (Florida) | IC 036 | Sugar commodity brokerage |
| WARRIOR BEER WORKS CRAFT BREW SEMPER VERAX EST CERVISIA | Christopher Couture | IC 016, IC 021 | Stickers, drinkware |

These are LIVE marks containing "VERAX" but in unrelated classes or for unrelated goods. A USPTO examiner would not refuse based on these alone for a software application. They become relevant only if counsel needs to argue the linguistic surface is unusually crowded.

## Why this verdict

Standard USPTO refusal under §2(d) "likelihood of confusion": refuses a new mark if it is similar to a registered mark AND the goods/services are related. Here:

- **Marks are identical.** Both DSM and APODEX have registered/filed the literal string "VERAX." No similarity argument needed; it's the same word.
- **Goods/services are in the same class.** Both DSM (registered, narrower goods) and APODEX (pending, broader goods) are in IC 009 + IC 042 — the exact classes we'd file in.

Counsel could argue the goods are narrow enough (animal-mgmt software vs. AI legal verification software) to escape refusal under DSM alone. But APODEX's broad pending claims in general software for database management and electronic storage make that argument harder. And APODEX's priority date (May 12, 2026) is two weeks ago — they're newer than our intent and got there first.

## Options the operator now has

1. **Fall back to VOUCH** (the priority-1 backup per ADR-0010 and the V2-name design doc). Re-run TMSearch on VOUCH in IC 009 + IC 042; almost certainly more crowded (common English word) but the blockers will be easier to interpret because most "VOUCH" marks are likely for unrelated services.
2. **Engage IP counsel for a 1-hour preliminary opinion on VERAX** (~$300-500). Counsel reviews DSM + APODEX and tells you whether the combination is genuinely fatal or whether a narrow filing (claiming "software specifically for AI citation verification in legal documents" or similar tight goods description) could thread the needle. Decision deadline: 1-2 weeks.
3. **Skip VERAX permanently and commit to VOUCH or PROVA.** Highest velocity. Lowest brand-ownership ceiling.

## Recommended next action

Run TMSearch on **VOUCH** in IC 009 + IC 042 today. If clear or near-clear, commit to VOUCH and update ADR-0010 + draft ADR-0011 (rename strategy). If VOUCH is also blocked, run **PROVA** next.

Engage IP counsel only if there's a strong product/marketing reason to fight for VERAX specifically — and only after the operator has read this note and the underlying xlsx files end-to-end.

## Files referenced

- `/Users/madu/Downloads/tmSearchResults2026-05-28.xlsx` (Class 9 search, 13 results)
- `/Users/madu/Downloads/tmSearchResults2026-05-28-2.xlsx` (broader VERAX search, 10 results)
- [ADR-0010](../adr/ADR-0010-v2-monorepo-second-frontend.md) — V2 monorepo + second frontend, follow-up #1a (this search)
- V2 name design doc at `/Users/madu/.gstack/projects/Madu-P1-carrel/madu-claude-practical-mestorf-ee78c3-design-20260528-153625.md`
