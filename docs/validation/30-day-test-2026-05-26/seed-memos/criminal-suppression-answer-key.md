# Answer key — criminal-suppression-memo.md

Ground truth for the criminal seed memo. Internal only. **10 unique citations**, planted
distribution 7 / 2 / 1 = 70% accurate / 20% holding-mismatched / 10% fabricated.

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
| 9 | Gideon v. Wainwright, 372 U.S. 335 (1963) | **real, HOLDING-MISMATCH** | Cited for "physical evidence seized without a warrant must be excluded." Gideon is the Sixth Amendment right-to-counsel case; the exclusionary rule is Mapp/Weeks, not Gideon. | **proposition_unsupported** |
| 10 | Delgado v. United States, 593 U.S. 401 (2021) | **FABRICATED** | No such case at this cite (593 U.S. is a plausible recent volume; the case is invented). | **citation_not_found** |

**Must NOT false-flag #1-#7.** Pass = catch #8, #9 (mismatch) and #10 (fabrication); leave the seven accurate cites supported.

## Acceptance + run procedure
Same as the civil memo (see `civil-equal-protection-answer-key.md`): set `ANTHROPIC_API_KEY` + `COURTLISTENER_API_TOKEN`, POST each memo's Discussion to `/api/verify`, compare per-cite verdicts to the table, record catch rate (/3) and false-positive rate (/7). The case-existence + holding checks require the CourtListener token (absent in the dev worktree), so the catch-test runs on a keyed instance.

## Cite-accuracy caveat
All seven "accurate" cites are long-settled, famous U.S. Reports citations the author is confident are correct; the keyed run is also the moment to confirm each resolves in CourtListener (a real cite that fails to resolve would be a false negative of the test, not of the tool, and means the memo cite needs correction, not the engine).

## Span achieved
With the civil equal-protection memo, this gives the two-practice-area pair the T65 plan calls for (civil + criminal), each a ground-truthed 7/2/1 artifact.
