# Catch-test results — 2026-05-29

First end-to-end run of the seeded-memo catch test against the Cachet verification engine
(`services/legal/case_verification.py::verify_claims_for_cases` — CourtListener case-existence
plus the Claude holding-match verifier). This is the empirical record for **T65 Deliverable 1**
and the ground-truth source that corrected both answer keys
(`seed-memos/civil-equal-protection-answer-key.md`, `seed-memos/criminal-suppression-answer-key.md`).

## TL;DR
The engine works on the hard case. With the AI provider actually on, holding-match caught the
Lochner mismatch (`holding_match=False`) **with correct legal reasoning** — the single most
important thing this product claims to do. An earlier "0 of 6 caught" pass was **not** an engine
failure: it was (a) a harness gap that left the AI provider resolved *off*, (b) one seed-memo
cite mislabeled, and (c) the CourtListener rate limit. All three are explained below; none is a
defect in the verification logic. Full per-cite confirmation is deferred to T66 because the free
CourtListener tier cannot pace a complete two-memo run in one sitting.

## What was run
A throttled diagnostic over the 20 seeded cites (10 civil + 10 criminal), in two passes plus a
decisive single-cite probe:

1. **PASS 1 — existence.** One batched CourtListener citation lookup per memo, holding-match off.
2. **PASS 2 — holding-match, paced.** Six diagnostic cites, one at a time, ~42 s apart to respect
   the 5/min limit. (This pass ran with the provider mistakenly *off* — see Finding 7.)
3. **Provider-on probe.** A single mismatch cite (Lochner) re-run with `.env` sourced so the
   provider resolved to `ClaudeRouter` (`ai_enabled=True`), to answer the one question the prior
   passes could not: *does holding-match produce a real verdict when it actually runs?*

## Results — existence (PASS 1)
18 of 20 cites resolved cleanly to the correct case name. The two non-`200` results are both
informative, not failures.

| Cite | Result | Note |
|---|---|---|
| 517 U.S. 620 / 570 U.S. 744 / 473 U.S. 432 / 388 U.S. 1 / 576 U.S. 644 / 457 U.S. 202 / 347 U.S. 483 | `200` ✓ | civil accurate cites — all correct names (Romer, Windsor, Cleburne, Loving, Obergefell, Plyler, Brown v. Board) |
| 392 U.S. 1 / 395 U.S. 752 / 389 U.S. 347 / 367 U.S. 643 / 232 U.S. 383 / 371 U.S. 471 / 384 U.S. 436 | `200` ✓ | criminal accurate cites — all correct (Terry, Chimel, Katz, Mapp, Weeks, Wong Sun, Miranda) |
| 198 U.S. 45 (Lochner) / 393 U.S. 503 (Tinker) / 297 U.S. 278 (Brown v. Miss.) | `200` ✓ | the three named-real holding-mismatch cites — exist, correct names |
| **571 U.S. 312** | `200` → ***Fernandez v. California*** | **phantom confirmed.** The civil memo drafts this as "Hargrove v. Board of Regents." Real cite, fabricated name. Existence passes; only holding-match can catch it. |
| **372 U.S. 335** (Gideon) | **`300` ambiguous → `exists=False`** | a real, famous case returning **ambiguous (multiple matches)**, deterministically (both passes). Blocks holding-match. See Finding 5. |
| **593 U.S. 401** (Delgado) | **`404` → `exists=False`** | the criminal memo's planted fabrication — a genuine dead cite. Correctly caught. |

## Results — holding-match (provider-on probe)
```
provider: ClaudeRouter | ai_enabled: True
LOCHNER 198 U.S. 45: exists=True status=200 holding_match=False holding_error=None
  concern: "...cites Lochner for the proposition that 'courts should not second-guess a
            legislature's economic line-drawing.' Lochner actually stands for the opposite..."
  excerpt: "The statute necessarily interferes with the right of contract between the
            employer and employes..."
```
The verifier did not just return a boolean — it identified *why* the cite is misused (Lochner
struck the law; it is cited as if it counseled deference). That is the behavior the litigation
wedge is sold on.

## Findings

### Engine validated
1. **Existence checking works.** 18/20 clean resolutions to correct names; the planted 404
   (Delgado) caught; ambiguous and not-found states distinguished by status code.
2. **Holding-match works (the hard dimension).** Provider-on Lochner probe returned
   `holding_match=False` with correct reasoning. Proof-of-life for the dimension that catches
   "real case, wrong proposition."

### Ground-truth corrections to the seed memos (applied to the answer keys)
3. **Civil #10 is a phantom, not a fabrication.** 571 U.S. 312 = *Fernandez v. California*; the
   memo's "Hargrove v. Board of Regents" is a confabulated name on a real cite. Reclassified from
   `citation_not_found` to *case-found-under-wrong-name + proposition_unsupported*. This is the
   most realistic LLM hallucination shape and the best single test case in the set — existence
   cannot catch it; only holding-match can.
4. **Criminal #10 is a confirmed 404.** 593 U.S. 401 (Delgado) is genuinely non-existent. The
   answer-key classification was correct; now empirically confirmed.
5. **Criminal #9 (Gideon, 372 U.S. 335) is a poor mismatch-test cite.** It returns `300
   ambiguous` deterministically, so the engine correctly stops at `could_not_check` and never
   reaches the holding mismatch. Reclassified to `could_not_check`; **recommend swapping the cite**
   for one that resolves to a single `200` so the holding dimension is actually exercised. The
   engine's ambiguous-existence handling is *correct behavior*, not a bug.

### Operational
6. **CourtListener free tier is the binding constraint.** 5 req/min · 50/hour · 125/day. Fine for
   a paced diagnostic; far too low for a real 20-40-cite brief, where each cite costs a lookup
   plus an opinion fetch. An upgraded membership tier and/or opinion-text caching is a **T66
   prerequisite**, and itself a product requirement for the litigation wedge (a finding, not a
   blocker for the test).
7. **Harness gap (caused the false 0/6).** The standalone runner did not load `.env`, so
   `EINSTEIN_AI_PROVIDER` defaulted away from `claude` and the provider resolved *off*. Every
   holding-match call then no-opped with `holding_error=ai_disabled`. The fix is purely in the
   test harness: source `.env` (or export `EINSTEIN_AI_PROVIDER=claude`) so the provider resolves
   on. The app already does this; the bare script did not. Not an engine defect.

### Product-improvement candidates (file as engine tasks; do NOT patch under T65)
8. **Fail loud when holding-match is unavailable.** When the provider is off or below the quality
   bar, the verify surface renders a soft gray "Holding check unavailable" sub-line under a green
   "Case found." A hurried litigator could read the green as full validation when the holding was
   never checked. The T64 fail-loud gate already covers the *answer* path; holding-match
   availability deserves the same prominence. Candidate engine task, adjacent to T64.
9. **Explicit name-mismatch flagging.** For the phantom (#10) the engine surfaces the *true* name
   (Fernandez) beside the cite but does not compare it to the *drafted* name ("Hargrove") and
   assert the discrepancy. The catch currently leans on holding-match plus an operator's eye.
   Explicit draft-name-vs-resolved-name comparison would make the phantom catch unambiguous.

## Confirmed vs pending (do not overclaim)
- **Confirmed 2026-05-29:** all 20 existence results; the Delgado 404 catch; the
  571-is-Fernandez phantom; the Gideon 300-ambiguous behavior; holding-match works (Lochner,
  provider-on).
- **Pending T66 (provider-on, full paced run on an upgraded tier):** per-cite holding catches for
  Tinker, Brown v. Mississippi, and the Fernandez phantom; the fourteen "supports" verdicts on the
  accurate cites; the end-to-end catch-rate and false-positive-rate numbers that gate the
  COMMIT/FALLBACK/KILL decision rule. The mechanism is validated; the full census is not yet run.

## Next steps (T66)
1. **Founder:** upgrade the CourtListener tier (or confirm opinion-text caching) so a full two-memo
   run fits the rate budget; rotate the API token used for this diagnostic.
2. Run both memos end-to-end through `/api/verify` with the provider confirmed on; record
   catch-rate and false-positive-rate against the corrected answer keys.
3. Swap the Gideon cite (Finding 5) for a clean-resolving second criminal mismatch.
4. Optionally add a self-contained 404 to the civil memo, or accept that the criminal memo covers
   the pure-fabrication class.
5. File Findings 8 and 9 as engine tasks (fail-loud holding-unavailable; explicit name-mismatch).

## Reproduce
Run on a configured instance, provider confirmed on, paced under the rate limit:
```bash
set -a; source .env; set +a            # loads EINSTEIN_AI_PROVIDER=claude + ANTHROPIC_API_KEY
export COURTLISTENER_API_TOKEN=...      # never commit this; rotate after use
# then drive services.legal.case_verification.verify_claims_for_cases over the memo windows,
# pacing one request every ~12s (5/min) with backoff on courtlistener_rate_limited.
```
Confirm `get_default_provider()` reports `ClaudeRouter` / `ai_enabled=True` before trusting any
holding-match result. A reported `holding_error=ai_disabled` means the provider is off — the
result is not a real verdict.

## Token handling
The CourtListener token used for this diagnostic was passed only inline at runtime and is **not**
present in any tracked file (verified). It must be **rotated** on the CourtListener account, and
never committed or logged.
