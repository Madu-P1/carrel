# Answer key — civil-equal-protection-memo.md

Ground truth for the seeded memo. Internal only (not shown to T66 participants). The memo
carries **10 unique case citations** in the planted distribution 7 / 2 / 1 = 70% accurate /
20% holding-mismatched / 10% fabricated. For each, the expected verify-surface disposition is
listed so the validator's catch rate and false-positive rate are exactly measurable.

## Per-citation ground truth

| # | Citation | Class | Why | Expected verdict (verify surface) |
|---|---|---|---|---|
| 1 | Romer v. Evans, 517 U.S. 620 (1996) | real + accurate | Animus is not a legitimate interest; correctly characterized. | supported (case found, holding supports) |
| 2 | United States v. Windsor, 570 U.S. 744 (2013) | real + accurate | Law whose purpose/effect imposes inequality on a class. | supported |
| 3 | City of Cleburne v. Cleburne Living Center, 473 U.S. 432 (1985) | real + accurate | Irrational prejudice fails rational basis. | supported |
| 4 | Loving v. Virginia, 388 U.S. 1 (1967) | real + accurate | Family/marriage as basic civil right; strict scrutiny for the classification at issue there. | supported |
| 5 | Obergefell v. Hodges, 576 U.S. 644 (2015) | real + accurate | Fundamental right to marry not deniable to a disfavored class. | supported |
| 6 | Plyler v. Doe, 457 U.S. 202 (1982) | real + accurate | No denial of benefit based on unchosen status. | supported |
| 7 | Brown v. Board of Education, 347 U.S. 483 (1954) | real + accurate | Rejected separate-but-equal; state separation can inflict injury. | supported |
| 8 | Lochner v. New York, 198 U.S. 45 (1905) | **real, HOLDING-MISMATCH** | Cited for "courts should not second-guess economic line-drawing." Lochner did the **opposite** (it struck the law, second-guessing the legislature) and is repudiated. The opinion does not support the proposition it is marshaled for. | **proposition_unsupported** (case found, holding does NOT support) |
| 9 | Tinker v. Des Moines Indep. Cmty. Sch. Dist., 393 U.S. 503 (1969) | **real, HOLDING-MISMATCH** | Cited for "equal-protection challenges to benefit programs get only minimal scrutiny." Tinker is a First Amendment student-speech case; it says nothing about EP scrutiny tiers. | **proposition_unsupported** |
| 10 | Hargrove v. Board of Regents, 571 U.S. 312 (2014) | **FABRICATED** | No such case exists at this cite (571 U.S. is a real volume; the case is invented). | **citation_not_found** |

**The memo must NOT false-flag #1-#7.** Catching #8 and #9 (holding mismatch) and #10 (fabrication) while leaving #1-#7 as supported is the pass condition.

## Acceptance (T65 Deliverable 1)
- All three planted errors caught: #10 surfaces as `citation_not_found`, #8 and #9 as `proposition_unsupported`.
- Zero false positives on the seven accurate cites.
- Any miss is itself a signal: if a fabrication slips through, that is a corpus/coverage gap (CourtListener); if a holding-mismatch slips through, that is a holding-match-verifier gap. Either becomes its own engine task (do NOT patch code under T65); iterate the memo only if the miss is a memo-construction artifact.

## How to run it end-to-end (operator step; needs a keyed instance)
This dev worktree has `ANTHROPIC_API_KEY` set but **no `COURTLISTENER_API_TOKEN`**, so the case-existence + holding-match checks (the crux of this memo) cannot run here; CourtListener degrades to "verification unavailable" without the token. Run on a configured instance:

1. Set `ANTHROPIC_API_KEY` and `COURTLISTENER_API_TOKEN` (and optionally `COURTLISTENER_BASE_URL`).
2. Start the backend; ensure a corpus is loaded if you also want to exercise the grounding dimension (the case checks do not require ingested sources, but the per-claim grounding verdict does).
3. POST the memo body to `/api/verify` (the same path the verify-as-hero surface uses), e.g. the `draft` field = the memo's Discussion text.
4. Compare each returned case verdict against the table above. Record catch rate (caught planted errors / 3) and false-positive rate (accurate cites wrongly flagged / 7).

## Notes
- The grounding-against-your-own-corpus dimension is secondary for a legal memo: the "sources" here are the cited opinions, which the case-verifier handles. Don't read a low grounding score (from an empty corpus) as a citation-check failure.
- Next artifact: a parallel **criminal** seed memo (e.g., a Fourth Amendment suppression memo using Terry / Katz / Mapp accurately, with a planted holding-mismatch + a fabrication) to span practice areas, per the T65 plan.
