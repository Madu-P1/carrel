# Answer key — civil-equal-protection-memo.md

Ground truth for the seeded memo. Internal only (not shown to T66 participants). The memo
carries **10 unique case citations**. The original design called it a 7 / 2 / 1 split
(accurate / holding-mismatch / fabricated). The **2026-05-29 catch-test run corrected the
ground truth** (see `../catch-test-results-2026-05-29.md`): cite #10 is not a pure
fabrication — it is a **phantom** (a real citation carrying a confabulated case name). The
corrected classes are **7 accurate / 2 named-real holding-mismatch / 1 phantom**. The
pure-fabrication (404) class is exercised by the criminal memo (`Delgado`, 593 U.S. 401,
confirmed 404), not here.

For each cite the expected verify-surface disposition is listed so the validator's catch rate
and false-positive rate are exactly measurable.

## Per-citation ground truth

| # | Citation (as drafted) | Class | Why | Expected verdict (verify surface) |
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
| 10 | "Hargrove v. Board of Regents," 571 U.S. 312 (2014) | **PHANTOM** (real cite, confabulated name + holding-mismatch) | 571 U.S. 312 is a **real** citation — it resolves to ***Fernandez v. California*** (a Fourth Amendment consent-to-search case), **not** "Hargrove v. Board of Regents." So the *citation exists* (it will NOT surface as `citation_not_found`); the *case name is fabricated*; and the *real* opinion (Fernandez) does not support the equal-protection proposition the memo marshals it for. This is the most realistic LLM hallucination shape: a confident, well-formed cite to a real reporter slot under an invented name. Existence-checking alone passes it — **only holding-match catches it.** | **case found, but as *Fernandez v. California* (name does not match the drafted "Hargrove"); holding does NOT support → proposition_unsupported** |

**The memo must NOT false-flag #1-#7.** Catching #8 and #9 (holding mismatch) and #10 (phantom) while leaving #1-#7 as supported is the pass condition.

## What the 2026-05-29 catch-test run confirmed (and what is still pending)

Run recorded in full at `../catch-test-results-2026-05-29.md`. Summary as it bears on this key:

- **Existence — confirmed for all 10.** Every accurate cite (#1-#7) resolved `exists=True / status 200` to its correct case name. #8 Lochner and #9 Tinker also resolved `200`. **#10 resolved `200` to *Fernandez v. California*** — the empirical confirmation that #10 is a phantom, not a 404.
- **Holding-match — confirmed on #8 (Lochner) only, and it works.** With the AI provider actually on (`ClaudeRouter`, `ai_enabled=True`), Lochner returned `holding_match=False` with correct reasoning ("Lochner actually stands for the opposite"). This is the proof-of-life for the holding-match dimension — the hardest thing the engine does, and it was right.
- **Holding-match on #9, #10, and the #1-#7 "supports" verdicts is EXPECTED but NOT yet independently confirmed.** The first paced run had the provider resolved *off* (`holding_error=ai_disabled`, a harness gap — the standalone runner didn't load `.env`/`EINSTEIN_AI_PROVIDER=claude`), and the corrected provider-on run only had budget for #8 before the CourtListener rate limit. #9/#10 holding catches and the seven "supports" verdicts are the validated mechanism applied by analogy; **confirm each in the full T66 paced run on an upgraded CourtListener tier.** Do not report them as confirmed until then.

## Acceptance (T65 Deliverable 1)
- All three planted errors caught: **#8 and #9 as `proposition_unsupported`; #10 as case-found-under-the-wrong-name + `proposition_unsupported`** (holding-match is the catch path for the phantom, since existence passes).
- Zero false positives on the seven accurate cites.
- **Implicit name-mismatch caveat (#10).** The engine surfaces the *true* name (Fernandez) next to the cite but does not parse the drafted name ("Hargrove") to assert "you called this Fernandez but cited it as Hargrove." So the phantom's name fabrication is caught *implicitly* (the operator eyeballs true-name vs draft) plus *explicitly* via holding-match. Explicit name-mismatch flagging is a candidate engine improvement (logged in the results doc), not a T65 patch.
- Any miss is itself a signal: if a holding-mismatch slips through, that is a holding-match-verifier gap and becomes its own engine task (do NOT patch code under T65); iterate the memo only if the miss is a memo-construction artifact.

## How to run it end-to-end (operator step; needs a keyed instance)
The case-existence + holding-match checks require **both** `ANTHROPIC_API_KEY` **and** `COURTLISTENER_API_TOKEN`, **and** the AI provider must actually resolve on (load `.env` / set `EINSTEIN_AI_PROVIDER=claude`; a bare script that skips `.env` resolves the provider *off* and silently no-ops holding-match with `holding_error=ai_disabled` — that was the 2026-05-29 false-zero). On a configured instance:

1. Export `ANTHROPIC_API_KEY` + `COURTLISTENER_API_TOKEN` (and optionally `COURTLISTENER_BASE_URL`); confirm the provider resolves to `claude` (`ai_enabled=True`), not `off`.
2. Start the backend; ensure a corpus is loaded if you also want to exercise the grounding dimension (the case checks do not require ingested sources, but the per-claim grounding verdict does).
3. POST the memo body to `/api/verify` (the same path the verify-as-hero surface uses), `draft` = the memo's Discussion text.
4. Pace requests under the CourtListener limit (free tier: 5/min, 50/hour, 125/day — too low for a full multi-cite brief; an upgraded tier or opinion caching is a T66 prerequisite). Compare each returned case verdict against the table above. Record catch rate (caught planted errors / 3) and false-positive rate (accurate cites wrongly flagged / 7).

## Notes
- The grounding-against-your-own-corpus dimension is secondary for a legal memo: the "sources" here are the cited opinions, which the case-verifier handles. Don't read a low grounding score (from an empty corpus) as a citation-check failure.
- Companion artifact: the **criminal** Fourth-Amendment suppression memo (`criminal-suppression-answer-key.md`) — it carries the pure-404 fabrication (`Delgado`, confirmed) and a separately-noted ambiguous-existence finding (`Gideon`, 372 U.S. 335 → status 300).
