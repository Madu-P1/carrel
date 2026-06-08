# Answer key — criminal-suppression-memo.md

Ground truth for the criminal seed memo. Internal only. **10 unique citations**, original
design 7 / 2 / 1 = accurate / holding-mismatch / fabricated. The **2026-05-29 catch-test run**
(see `../catch-test-results-2026-05-29.md`) confirmed the fabrication and surfaced one
correction: cite #9 (`Gideon`) returns an **ambiguous** existence result (status 300), not a
clean match, so it never reaches holding-match — it is a poor mismatch-test cite and should be
swapped. Details below.

## Per-citation ground truth

| # | Citation | Class | Why | Expected verdict |
|---|---|---|---|---|
| 1 | Terry v. Ohio, 392 U.S. 1 (1968) | real + accurate | Frisk limited to a weapons patdown on reasonable suspicion. | supported |
| 2 | Chimel v. California, 395 U.S. 752 (1969) | real + accurate | Search incident limited to the arrestee's wingspan. | supported |
| 3 | Katz v. United States, 389 U.S. 347 (1967) | real + accurate | Reasonable expectation of privacy. | supported |
| 4 | Mapp v. Ohio, 367 U.S. 643 (1961) | real + accurate | Exclusionary rule applies to the States. | supported |
| 5 | Weeks v. United States, 232 U.S. 383 (1914) | real + accurate | Federal exclusionary rule. | supported |
| 6 | Wong Sun v. United States, 371 U.S. 471 (1963) | real + accurate | Fruit of the poisonous tree. | supported |
| 7 | Miranda v. Arizona, 384 U.S. 436 (1966) | real + accurate | Custodial-interrogation warnings. | supported |
| 8 | Brown v. Mississippi, 297 U.S. 278 (1936) | **real, HOLDING-MISMATCH** | Cited for "search incident to arrest may extend to the whole premises." Brown v. Mississippi is a coerced-confession / due-process case; it says nothing about search scope (and Chimel holds the opposite). | **proposition_unsupported** |
| 9 | Gideon v. Wainwright, 372 U.S. 335 (1963) | **real, HOLDING-MISMATCH — but existence is AMBIGUOUS** | Cited for "physical evidence seized without a warrant must be excluded." Gideon is the Sixth Amendment right-to-counsel case; the exclusionary rule is Mapp/Weeks, not Gideon. **However:** the 2026-05-29 run showed 372 U.S. 335 returns **status 300 (ambiguous / multiple matches)** from the CourtListener citation lookup, deterministically (both passes) → `exists=False`. Because holding-match only runs on a clean `200`, the real holding-mismatch is **never reached**. The engine surfaces this as **"Ambiguous (multiple matches)" → could_not_check**, not `proposition_unsupported`. | **could_not_check (ambiguous existence)** — and see swap recommendation below |
| 10 | Delgado v. United States, 593 U.S. 401 (2021) | **FABRICATED (confirmed 404)** | No such case at this cite; 593 U.S. 401 returned `status 404 / exists=False` on the 2026-05-29 run. A genuine dead cite. | **citation_not_found** ✓ confirmed |

**Must NOT false-flag #1-#7.** Pass = catch #8 (mismatch) and #10 (fabrication); #9 is reclassified (see below).

## What the 2026-05-29 catch-test run confirmed
Full record at `../catch-test-results-2026-05-29.md`.
- **Existence confirmed for #1-#8** (`exists=True / 200`, correct names) and **#10** (`404`, the valid fabrication).
- **#9 (Gideon) → status 300 ambiguous**, deterministic across both passes. A real, famous case whose *existence lookup* is ambiguous — a false-negative-on-existence shape that blocks the holding dimension.
- **Holding-match was not run provider-on for any criminal cite** (the provider-on budget went to the civil Lochner proof before the rate limit). #8's holding catch is expected by the validated mechanism (see the civil Lochner result) but **not yet independently confirmed** — confirm in T66.

### Swap recommendation for #9
Gideon is a bad holding-mismatch test cite: its existence is ambiguous, so the engine correctly stops at "could_not_check" and never evaluates the holding. To keep a clean second mismatch in the criminal memo, **replace Gideon with a famous case that resolves to a single `200`** (e.g. another suppression-adjacent opinion cited for a proposition it does not hold), so the holding-match dimension is actually exercised. This is a memo-construction fix (a future memo revision), not an engine bug — the engine's ambiguous-existence handling is correct behavior. Until swapped, score #9 as `could_not_check` (a non-error, non-catch), not as a missed mismatch.

## Acceptance + run procedure
Same as the civil memo (`civil-equal-protection-answer-key.md`): export `ANTHROPIC_API_KEY` + `COURTLISTENER_API_TOKEN`, **confirm the AI provider resolves on** (not `off`/`ai_disabled`), POST each memo's Discussion to `/api/verify`, pace under the CourtListener rate limit, compare per-cite verdicts to the table, record catch rate and false-positive rate. With #9 reclassified, the criminal memo's catch targets are **#8 (mismatch) + #10 (fabrication)**; #9 is a known `could_not_check` until the cite is swapped.

## Cite-accuracy caveat
All seven "accurate" cites resolved cleanly on 2026-05-29. The `Gideon` ambiguity is the live example of why this caveat matters: a real cite that fails to resolve cleanly is a false negative *of the test cite*, not of the tool — fix the memo cite, not the engine.

## Span achieved
With the civil equal-protection memo, this gives the two-practice-area pair the T65 plan calls for (civil + criminal). Post-correction the pair spans all four real verdict shapes: **supported** (the 14 accurate cites), **proposition_unsupported / holding-mismatch** (Lochner, Tinker, Brown v. Mississippi), **phantom / real-cite-wrong-name** (civil #10 = Fernandez-as-"Hargrove"), and **citation_not_found** (criminal #10 = Delgado, confirmed), plus the **could_not_check / ambiguous-existence** edge (Gideon).
