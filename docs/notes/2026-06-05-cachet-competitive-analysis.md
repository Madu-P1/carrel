# Cachet — Competitive Analysis of the AI-Output Verification Market

**Date:** 2026-06-05
**Prepared as:** a multi-team engagement (landscape mapping, competitor dossiers, adversarial fact-check, metric scoring, partner synthesis, honesty red-team)
**Coverage:** 33 players mapped across 3 rings, 16 deep-dived, scored on an 11-metric rubric under two weightings
**Method:** 54 research/analysis agents, web-grounded, each claim fact-checked by an independent adversarial pass; Cachet's own claims independently verified against the `main` branch of the codebase

---

## 0. How to read this report (methodology and honesty caveats)

This is a decision document, not a brochure. Four caveats govern every number below. Read them first or you will over-trust the ranking.

1. **Competitor scores are this analysis's estimates, not a published benchmark.** Only Cachet was scored against primary evidence (its own source code). Every competitor score is built from web research plus an adversarial fact-check, on the same rubric. Treat the ladder as **directional**, not as a measured leaderboard. The single most load-bearing caveat in the document: the headline "Cachet 5.3, below every serious incumbent" is a hand-built comparison, not a lab result.

2. **Two weightings, on purpose.** The **thesis-weighted** score tilts toward the four dimensions Cachet is betting on (independence, determinism, locality, refusal). The **market-neutral** score weights all 11 dimensions equally. Where they diverge, the gap is the size of Cachet's bet. The executive summary leads with the **neutral** number because it is the less self-serving one.

3. **The same product appears three times.** Thomson Reuters CoCounsel / Westlaw was profiled by all three ring-analysts under slightly different names (research, legal-research, contracts). The effective distinct-competitor count is **14**, not 16. The three rows are kept in the raw scorecard for faithfulness and bracketed in the narrative.

4. **Cachet's codebase claims were verified against `main` on 2026-06-05.** Several differentiators in the pitch are partly promissory. What is actually true today is in Section 6. This correction is the most important output of the engagement.

**Rubric (0-10 each):** independent verification, deterministic grounding, data locality / no-cloud, legal-domain depth, honest refusal, catch accuracy, workflow integration, use-case breadth, traction, price/accessibility, moat.

**Thesis weights:** independence .15, determinism .13, locality .13, catch .12, legal-depth .10, refusal .10, workflow .06, traction .06, moat .06, breadth .05, price .04.

---

## 1. Executive summary

Cachet's honest market-neutral score is **5.3**. On this analysis's estimated ladder that sits below every serious legal-native incumbent in the set: Free Law Project (6.3), Lexis+ Protégé (6.1), the Thomson Reuters CoCounsel family (5.4 to 6.0), BriefCatch RealityCheck (5.8), Clearbrief and vLex (5.7). That is what fighting on commoditized ground looks like.

The totals understate one real asset and overstate another. Cachet genuinely owns **refusal honesty** (9, the highest in the set) and is the only player with a structural path to **true on-device locality**, because every incumbent is cloud-locked (0 to 1 on locality) and cannot move without abandoning its business model. But the **deterministic, LLM-off engine the whole pitch leans on is not on `main`**, and one of the three "deterministic" checks (holding-match) is itself an LLM call. So independence and determinism are *partly* promissory today.

The strategic picture resolves cleanly:

- **The litigator cite-check wedge is commoditized.** Existence-checking is free from Free Law Project, sold cheaply by CourtListener-class tools, and bundled free inside the Word-native products AmLaw firms already pay for. The capability gap that does exist (incumbents' substance verdicts are LLM-as-judge) is *invisible at the point of purchase*. You do not win a commoditized category with a better engine the buyer cannot perceive.

- **The in-house no-cloud contract wedge is the only defensible ground on the board.** Every serious incumbent scores 0 to 1 on locality and is architecturally frozen there. The regulated in-house buyer who legally cannot egress data is a customer **no cloud incumbent can follow without re-architecting its business**. Exactly one credible competitor (SpotDraft VerifAI) is moving toward this ground, and its "local" is not yet real, has no independent authority check, and has no refusal state.

- **The strategy is not better cite-checking.** It is to be the verifier that can honestly say *no* and that never lets the document leave the building, sold to the buyers a cloud incumbent cannot legally serve. **Everything depends on shipping the local path and merging the deterministic path before validation interviews turn into a sales cycle.**

---

## 2. The metric framework

| # | Dimension | What a 10 looks like | Why it is on the rubric |
|---|---|---|---|
| 1 | Independent verification | A true third-party check, independent of the generator | Cachet's core posture vs self-grading copilots |
| 2 | Deterministic grounding | Citation lookup / verbatim quote-match / holding-match, not an LLM judge | The "trust the check, not the vibe" thesis |
| 3 | Data locality / no-cloud | Nothing egresses; on-device or on-prem | The in-house regulated wedge lives or dies here |
| 4 | Legal-domain depth | Deep authority sources (KeyCite, Shepard's, CourtListener, executed contracts) | Verification needs ground truth |
| 5 | Honest refusal | A loud, designed "cannot verify" state | Cachet's signature product stance |
| 6 | Catch accuracy | Measured accuracy on the failure it targets | The number a sophisticated buyer will demand |
| 7 | Workflow integration | Native in Word / iManage / NetDocuments / browser | Lawyers live in these surfaces |
| 8 | Use-case breadth | Wide range of verification jobs | Cachet is deliberately narrow here |
| 9 | Traction | Customers, revenue, logos, deployment proof | Cachet's weakest dimension |
| 10 | Price / accessibility | Cheap, self-serve, no platform lock-in | Cachet's wedge against enterprise incumbents |
| 11 | Moat | Data, distribution, switching costs, regulatory positioning | Defensibility of the whole thesis |

---

## 3. Master scorecard

Sorted by **market-neutral** score (the less self-serving metric). Scores are analyst estimates (caveat 1). Abbreviations: Indep, Det(erminism), Local, Legal, Refuse, Catch, Wflow, Breadth, Tract(ion), Price, Moat.

| Player | Indep | Det | Local | Legal | Refuse | Catch | Wflow | Breadth | Tract | Price | Moat | **Neutral** | **Thesis** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Free Law Project (eyecite / CourtListener) | 9 | 8 | 4 | 6 | 8 | 6 | 2 | 3 | 8 | 9 | 6 | **6.3** | 6.5 |
| Lexis+ / Protégé (Shepard's) | 7 | 6 | 1 | 10 | 5 | 5 | 7 | 6 | 9 | 2 | 9 | **6.1** | 5.9 |
| TR CoCounsel / Westlaw (Legal) ¹ | 3 | 4 | 0 | 10 | 3 | 4 | 10 | 10 | 10 | 2 | 10 | **6.0** | 5.1 |
| BriefCatch RealityCheck | 9 | 5 | 1 | 8 | 5 | 5 | 7 | 5 | 8 | 4 | 7 | **5.8** | 5.8 |
| TR CoCounsel (research) ¹ | 3 | 5 | 1 | 10 | 3 | 5 | 9 | 8 | 10 | 1 | 9 | **5.8** | 5.3 |
| Clearbrief | 8 | 6 | 2 | 6 | 5 | 5 | 7 | 6 | 7 | 5 | 6 | **5.7** | 5.6 |
| vLex Vincent AI | 2 | 3 | 1 | 8 | 8 | 5 | 8 | 8 | 9 | 3 | 8 | **5.7** | 5.0 |
| TR CoCounsel (contracts) ¹ | 2 | 4 | 0 | 10 | 2 | 3 | 9 | 9 | 9 | 2 | 9 | **5.4** | 4.5 |
| **CACHET (verified)** | **8** | **8** | **5** | **7** | **9** | **5** | **2** | **3** | **1** | **6** | **4** | **5.3** | **5.9** |
| Midpage | 3 | 5 | 1 | 8 | 3 | 5 | 5 | 6 | 6 | 9 | 5 | **5.1** | 4.6 |
| SpotDraft VerifAI | 4 | 3 | 3 | 5 | 1 | 4 | 7 | 6 | 8 | 7 | 5 | **4.8** | 4.2 |
| Vectara (HHEM) | 6 | 6 | 5 | 1 | 3 | 6 | 2 | 3 | 5 | 7 | 6 | **4.5** | 4.7 |
| Luminance | 2 | 2 | 4 | 8 | 1 | 4 | 5 | 6 | 9 | 1 | 7 | **4.5** | 4.1 |
| CiteCheck AI (LawDroid) class | 9 | 7 | 1 | 5 | 2 | 5 | 2 | 2 | 3 | 9 | 2 | **4.3** | 4.6 |
| Paxton AI (AI Citator) | 2 | 2 | 1 | 8 | 2 | 4 | 4 | 7 | 6 | 3 | 5 | **4.0** | 3.5 |
| JurisCheck | 6 | 5 | 1 | 5 | 4 | 5 | 5 | 2 | 1 | 7 | 2 | **3.9** | 4.0 |
| Private legal-LLM vendors (LLM.co class) | 1 | 1 | 6 | 3 | 1 | 2 | 3 | 7 | 2 | 2 | 3 | **2.8** | 2.6 |

¹ Same Thomson Reuters CoCounsel / Westlaw family, profiled three times by three ring-analysts. Effective distinct competitors = 14.

**Reading the two columns:** Cachet's thesis score (5.9) sits well above its neutral score (5.3) because the thesis weighting rewards exactly the four dimensions it leads on. That 0.6 gap *is* the bet. If the bet (independence + determinism + locality + refusal actually matter to buyers) is right, Cachet rises. If buyers price on legal depth, workflow, and traction, the neutral number is the truth and Cachet is mid-pack.

---

## 4. Market structure: three rings

The dangerous competition is not where the original seed list pointed.

**Ring 1 — Legal-AI incumbents with built-in cite-checking** (Clearbrief, BriefCatch RealityCheck, the TR CoCounsel/Westlaw family, Lexis+ Protégé, vLex Vincent, Paxton, Midpage). This is where the most direct competition actually lives, and it was almost entirely missing from the founders' seed names. These players own the Microsoft Word surface, AmLaw distribution, citator depth (KeyCite, Shepard's), and the buyer's default trust.

**Ring 2 — Standalone hallucination detection and LLM-trust tooling** (Vectara HHEM, the LawDroid CiteCheck class, developer-facing eval vendors). One ring out: cheap or free, independent, but existence-only and developer-facing. Useful to Cachet mostly as **commoditized ingredients**, not rivals.

**Ring 3 — Contract AI and no-cloud tools for regulated counsel** (SpotDraft VerifAI, Luminance, the private legal-LLM vendors, CoCounsel for contracts). This is where Cachet's defensible wedge sits and where competition is thinnest on the dimensions that matter.

**The structural fact that organizes the whole map:** a deterministic existence primitive (Free Law Project's eyecite plus CourtListener, neutral 6.3) is free and already embedded inside the paid incumbents. The entire cite-existence layer is a **dependency, not a market**. Real competition is therefore two narrower contests:

1. **Who can verify substance** (quote, holding, contract clause) deterministically rather than with an LLM judge? On this, the incumbents are quietly LLM-as-judge despite deterministic marketing (this is inferred across several, not proven for each).
2. **Who can do it with nothing leaving the device?** On this, every incumbent scores 0 to 1 and is architecturally frozen.

Those two gaps are the only uncontested ground on the board.

---

## 5. What each competitor does best

**Free Law Project (eyecite / CourtListener)** — Independent, deterministic, free screening of whether a US citation resolves to a real opinion: the hallucination-existence check the rest of the market quietly builds on. *This is Cachet's dependency, not its rival, and a commoditizer of bare existence-checking.*

**Lexis+ / Protégé (Shepard's)** — Authoritative US citation existence plus good-law/treatment validation at scale, against the deepest proprietary case-law + Shepard's graph, wired into both AI-generated and human-drafted content.

**Thomson Reuters CoCounsel / Westlaw** — Defensible, citation-grounded answers and agentic work product fused to the largest first-party legal-authority graph in the industry (Westlaw + Practical Law + KeyCite), native in Word and the DMS. Best at *trusted generation*, not independent verification.

**BriefCatch RealityCheck** — Argument-level authority verification of third-party/AI-drafted briefs, distributed at the point of maximum leverage by putting the checker in courts' hands to screen filed briefs. Tell: its substance verdict is LLM-as-judge.

**Clearbrief** — Catching mischaracterization inside Word: flagging where a cited case or record document does not support the sentence it is attached to, binding assertions to record evidence across large document sets, with a partner-facing Cite Check Report audit trail. One of only two players partly occupying *independent adjudication of a third-party work product*.

**vLex Vincent AI** — Cross-border, multi-jurisdiction research grounded in a citation-linked ~1B-doc global corpus (plausibly best-in-class on non-US coverage), with honest refusal when authority is missing as a genuine secondary strength.

**Midpage** — Cheap, genuinely source-grounded US case-law research delivered natively inside general-purpose LLMs (Claude/ChatGPT) via MCP, so a generalist model stops inventing cases.

**SpotDraft VerifAI** — Fast in-Word review of unfamiliar third-party contracts against the customer's own plain-English playbook, with a genuinely distinctive first-mover on-device demo on Qualcomm Snapdragon NPUs. **The single most direct threat to Cachet's wedge.**

**Vectara (HHEM)** — Cheap, fast, non-LLM-judge entailment/grounding scoring: whether a generated claim is supported by a passage you already hold, via a tiny CPU-runnable open model. Arguably the best off-the-shelf RAG factual-consistency primitive (a possible *ingredient* for Cachet).

**Luminance** — High-volume contract review and M&A diligence at enterprise scale, with reusable negotiation "institutional memory," heavy capital, blue-chip logos.

**CiteCheck AI (LawDroid) class** — Dead-cheap, zero-setup independent existence-screening of citations in any document against CourtListener in under two minutes. Anchors the buyer's price and mental model.

**Paxton AI (AI Citator)** — Generative case-treatment analysis with unusually transparent self-published benchmark samples versus black-box incumbents.

**JurisCheck** — Cheap, vendor-independent existence-plus-Bluebook-format smoke test that runs outside whatever tool drafted the brief.

**Private legal-LLM vendors (LLM.co / LAW.co class)** — The widest sovereign-deployment matrix in the set (on-prem, VPC, air-gapped, edge, appliances), model-agnostic. A *deployment/sovereignty* story, not a verification one. **The closest analog to Cachet's locality pitch, and a reminder that "local" alone is not a moat.**

---

## 6. Cachet, honestly (verified against `main`, 2026-06-05)

This section supersedes the pitch wherever they conflict. Verified by reading the source.

**What ships deterministically today:**
- **Verbatim quote-match** (`services/legal/quote_check.py`). Pure and deterministic: no network, no model call. Header states it is the "deterministic cry-wolf surface" and degrades to `could_not_check`, never to a false flag. **Real, shipped, defensible.**
- **Case-existence** via CourtListener API lookup. Authoritative, but requires a network call and a free API token (so it is not "no network," it is "no AI cloud").

**What is NOT deterministic (disclose, do not sell as deterministic):**
- **Holding-match** (`services/legal/case_verification.py::check_holding_match`) runs the **Claude verifier** (`request_tool_call`, returns supports/ambiguous). This is **LLM-as-judge, the exact approach the analysis dings competitors for.** Cachet's defensible deterministic claim is narrower than the pitch: verbatim quote-match + case-existence. Holding-match is a real, disclosable limitation.

**What is not on `main`:**
- The **fully LLM-off orchestration** (`CACHET_DETERMINISTIC_VERIFY` / `deterministic_envelope.py`) lives only in unmerged worktrees. The shipped `verify.py` is a thin coordinator on top of an LLM claim-extraction spine. So independence (8) and determinism (8) are scored a notch below the pitch's ~9 to reflect merge-state reality.
- **eyecite** is importable in the venv but is **not in `requirements.txt` and not wired into the shipped detector**, which is still the `_CITATION_SHAPE` regex. Statements like "we consume eyecite as a free dependency" describe a roadmap, not the shipped system.

**Where Cachet honestly competes:**
1. **Refusal honesty (9, highest in the set).** The three-state loud tray (verified / cannot-verify / altered) makes "I cannot honestly check this" a first-class outcome, no streak or green-badge gamification. Every incumbent surfaces uncertainty as a soft flag the lawyer must interpret. *Caveat: this is a designed-but-unshipped stance and a UX a competitor could copy in a sprint. It is a lead, not yet a moat.*
2. **True data locality as the only credible trajectory.** Every serious incumbent is frozen at 0 to 1. Cachet at 5 today (cloud asterisk) is the only player that can reach 8 to 9 via the Apple Foundation Models path. This is a business-model moat for the regulated buyer, *conditional on shipping it.*
3. **Deterministic substance verification (the quote leg only).** Verbatim quote-match against the actual document is sharper and more defensible than an LLM judge.
4. **Independence from the generating model.** Cachet verifies output regardless of which tool drafted it; CoCounsel, Lexis, Paxton, Midpage, vLex, Luminance verify their own generation as a side effect.
5. **Price and self-serve posture** for solos and individuals, against sales-gated six-figure incumbents.

**Where Cachet loses:**
- **Traction: 1**, the lowest in the set. Pre-product, pre-incorporation, zero paying customers, validation interviews only scheduled for mid-June to July 2026. Six lawyers' concept-love is not paid-demand validation.
- **The deterministic engine is unmerged** and holding-match is LLM-based (see above).
- **Workflow integration: 2**, tied for worst. macOS-only, no Word add-in, no iManage, no NetDocuments, no browser extension. The localhost-browser path is a standalone island.
- **Locality has a cloud asterisk today.** The moat is currently a slide.
- **Catch accuracy: 5**, with no published benchmark on any labeled set. "Demo-ready over adversarial rounds" is an argument, not a number. Sophisticated buyers will ask for the number.
- **Authority breadth is narrow** (legal depth 7 vs KeyCite/Shepard's 10; contract-anchor coverage self-assessed at 25 to 35 percent).
- **Moat: 4.** No data moat, no distribution, no switching costs yet.

---

## 7. Wedge strategy

### Litigator (fake-citation pre-check) — do not lead

**Verdict:** Commoditized and not viable as a standalone business. The existence primitive is free, embedded in the paid incumbents, and is a tool Cachet itself must call. The genuine capability gap (incumbents' substance verdicts are LLM-as-judge) is **invisible at the point of purchase**: to a buyer, the catch looks identical.

**Recommendation:** Never compete on bare cite-existence. Consume CourtListener (and eventually eyecite) as a free dependency, not a differentiator. If the litigator surface is kept, reposition it narrowly onto the **one verified-deterministic axis: verbatim quote-match against the actual source** (the exact failure that sanctioned a CoCounsel brief in *U.S. v. Farris*, 6th Cir., Apr 2026), paired with the loud cannot-verify state. **Do not anchor the litigator pitch on holding-match, which is LLM-based.** Treat the litigator wedge as a **top-of-funnel credibility demo and a wedge into the firm, not the revenue engine.**

### In-house no-cloud contract verification — lead here

**Verdict:** This is the defensible wedge and the one place a cloud incumbent structurally cannot follow. Regulated in-house counsel who legally cannot send data to a model cloud are served by no serious incumbent (all 0 to 1 on locality). The single credible threat is **SpotDraft VerifAI** (Word-native, Qualcomm on-device demo, strong traction), but its "local" is laptop-NPU local that still calls the cloud for login/licensing/collaboration, it is not GA or self-hosted, and it has no external legal-authority check and (per this analysis's estimate) no designed refusal state. Cachet's three differentiators map exactly onto VerifAI's three gaps: deterministic source-grounded checks, a loud honest refusal, and true on-prem locality.

**Recommendation:** Make **"the AI contract-claim verifier where the document never leaves the building, and which tells you when it cannot be sure"** the primary position. The verdict is **conditional and the condition is non-negotiable: ship the fully-local Apple Foundation Models path before validation interviews convert to a sales cycle.** Today locality is 5 with a cloud asterisk. The window is open only until SpotDraft VerifAI's on-device build reaches GA. Run the litigator demo alongside for credibility, but let **paid-demand data, not concept-love, decide resource allocation.**

---

## 8. Top threats (ranked)

1. **SpotDraft VerifAI** — the only player that can occupy Cachet's exact positioning before Cachet ships. Race it on independence, refusal, and true air-gapped locality, the three things it lacks. The threat closes the moment its on-device build reaches GA.
2. **TR CoCounsel / Westlaw / Lexis+ Protégé** — they own the buyer relationship, the Word/DMS surfaces, and a citation ledger that *looks like* verification to buyers. They can crowd Cachet out of the buyer's mind before evaluation, even though they cannot match independence, a deterministic quote gate, honest refusal, or locality.
3. **BriefCatch RealityCheck** — court-screening distribution and AmLaw reach effectively commoditize hallucinated-cite detection at the top of the market. Its LLM-as-judge substance verdict is the opening for Cachet's deterministic quote claim.
4. **Free Law Project (eyecite / CourtListener)** — commoditization from below. More dependency than rival, but it makes "we verify cites exist" a losing standalone position against a free standard.
5. **Commoditization perception generally** (LawDroid CiteCheck class, JurisCheck, Paxton) — cheap tools that loudly claim to catch hallucinated cites anchor the buyer's assumption that the job is already covered. Cachet's exposure here is *perception*, not capability.
6. **Cachet's own merge-state and validation gap (internal)** — the unmerged deterministic engine and the absence of any paid-demand signal are the most likely reasons the strategy stalls, independent of any competitor move.

---

## 9. Whitespace (uncontested ground)

- **The honest-refusal verifier.** No competitor ships a designed, loud cannot-verify state. "The verifier that tells you when it cannot be sure" is unclaimed and is Cachet's strongest single dimension.
- **True local-first verification for regulated counsel.** "Nothing leaves the device" is confirmed unoccupied by any legal verifier found; all are cloud plus external-database-grounded. The regulatory constraint is a moat a cloud incumbent cannot follow without re-architecting.
- **Deterministic substance verification as the headline, not existence.** A verifier whose verbatim quote-match is genuinely deterministic and *benchmarked* occupies ground the incumbents only gesture at. (Keep this honest to the quote leg.)
- **Independent, generator-agnostic adjudication of a finished third-party work product.** Almost everyone verifies their own generation; only Clearbrief and BriefCatch partly occupy this, and neither does it locally.
- **The grounding-to-refusal bridge for in-house contract claims:** comparing an AI assertion against the actual executed contract on-device, with a designed abstention when the anchor is not found. This precise intersection (local + deterministic + contract-grounded + honest-refusal) is what the entire competitor set leaves open.

---

## 10. Recommendations (the partner's call)

1. **Stop selling the cite-checker.** Reframe the company around the in-house no-cloud contract wedge. The litigator surface is the hook, not the business.
2. **Merge the LLM-off deterministic path and ship the on-device path before the validation interviews become a sales cycle.** Until then the pitch is ahead of the product, and a sharp buyer or competitor will find the gap in the first demo.
3. **Put a measured catch-accuracy number on the board.** Build a labeled set of hallucinated cites and bad contract claims, benchmark the deterministic checks, publish it. "Sound by construction" loses to a number.
4. **Tell the truth about holding-match.** It is LLM-as-judge. Either keep it and disclose it, or build a deterministic holding-support check. Do not let the determinism story rest on a leg that does not bear weight.
5. **Pick one frame for Free Law Project:** critical infrastructure Cachet depends on and a commoditizer of existence-checking. Not a head-to-head rival.
6. **Use *U.S. v. Farris* precisely.** It validates both Cachet checks, but it cuts the determinism story on one leg: the false quotations are caught deterministically by quote-match; the misrepresented holdings are exactly what Cachet checks with an LLM. Motivate the **quote-match** wedge with Farris, not holding-match.
7. **Let paid demand, not six lawyers' applause, allocate resources.** Run both wedges into the validation interviews; weight the build toward whichever produces a paid-demand signal first.

---

## Appendix A: Red-team honesty log

The synthesis was passed through an independent adversarial honesty pass. Its material catches, all folded into the report above:

- **Competitor scores are analyst-generated, not benchmarked.** The grounding profile scored only Cachet. The entire competitor ladder is this analysis's estimate. (Caveat 1.)
- **"Only player with a path to locality" rests on self-scored competitor numbers.** On-device inference is a feature an incumbent *can* add (SpotDraft is doing it); the "business-model impossibility" is asserted, not proven. Treat locality as a *lead time* advantage, not a permanent moat.
- **Refusal honesty (9) is a self-assigned score on an unshipped product** and a UX a competitor could copy. Real edge, not yet a defensible asset.
- **Holding-match is LLM-based** — Cachet is partly the thing it accuses competitors of being. (Verified against source; Section 6.)
- **eyecite is roadmap, not a shipped dependency.** (Verified: in venv, not in `requirements.txt`, not in the shipped detector.)
- **SpotDraft VerifAI's "1" on refusal and authority is too harsh** — scored against an untested product on a dimension Cachet invented. Softened to "no publicly evident refusal state or external-authority check (untested)."
- **Specific competitive-intel figures are unsourced** ("$25/mo," "Series A," "AmLaw-200," "Qualcomm on-device," "traction 8"). Directionally plausible, individually unverified. Do not repeat as fact in external materials.
- **Internal inconsistency on Free Law Project** (highest-scoring competitor yet called "a non-threat dependency") reconciled: it is a dependency that constrains Cachet's litigator pricing, not a product rival.

## Appendix B: Engagement parameters

- Universe mapped: 33 players. Deep-dived: 16 (14 distinct). Rings: 3. Wedges: 2.
- Agents: 54. Tool calls: 684. Subagent tokens: ~4.18M. Duration: ~63 min.
- Pipeline: landscape mapping (3 ring-analysts) → per-competitor dossier → adversarial fact-check → 11-metric scoring → partner synthesis → honesty red-team.
- Cachet self-scoring grounded in `CLAUDE.md`, memory, and direct source verification of `services/legal/quote_check.py`, `services/legal/case_verification.py`, and `requirements.txt` on `main` at 2026-06-05.

---

## Appendix C: Harvey legal red-team — pressure-test of the in-house no-cloud wedge

The senior-lawyer persona (a composite BigLaw litigation partner plus in-house GC) web-grounded in 2026 sources and stress-tested Section 7's lead recommendation. Verdict, condensed. He carries his own caveat: this is priors, not validation.

**Verdict: real but narrow, and the part that sells is not the part Cachet leads with.**

- **The blanket "regulated counsel can't use cloud AI" claim is largely dead.** ABA Formal Opinion 512 plus the state bars settled that cloud generative AI is permissible with competence, supervision, and confidentiality; the vendor ecosystem now ships SOC 2 Type II, zero-retention contracts, and "we never train on your data" as table stakes. For the median regulated company a BAA plus a zero-retention DPA inside the Microsoft 365 / Azure OpenAI boundary already satisfies the duty. There, no-cloud is a preference, not a requirement, and preferences do not clear procurement.

- **Two segments where the line is genuinely hard:** (1) **defense / ITAR / EAR / CUI / classified**, where no-egress is a literal compliance posture, and (2) **EU-sovereign regulated finance and insurance**, where the US CLOUD Act means a hyperscaler's EU region gives residency but not sovereignty, and DORA / NIS2 / the EU AI Act are actively pushing inference on-prem. **Paris domicile makes the EU-sovereign segment Cachet's natural beachhead.** HIPAA is the weakest driver (a BAA cures it); drop it from the lead.

- **The real status-quo competitor is Microsoft**, not the legal-AI incumbents. Copilot is marketed for contract review, keeps data in the M365 boundary, and is already licensed and security-reviewed. You do not beat it on a better privacy story; you beat it only where the boundary itself is the problem (EU sovereignty) or on **independence** ("who checks Copilot's own output?"). The other status quo is "we just don't use AI for contracts," which has zero procurement cost and is brutal to dislodge.

- **The strongest wedge is procurement-friction collapse, not privacy.** If nothing leaves the device there is no DPA to negotiate, no sub-processor to assess, no external-transfer DPIA. A CISO's review can collapse from a six-week cloud-vendor assessment to a one-week "assess a desktop binary that makes no outbound calls." For a pre-incorporation solo vendor that would otherwise be auto-rejected, the local architecture is what lets it clear the gate at all. **Reframe the pitch from "you'll be safer" (a value claim) to "you can actually buy me next week" (a cost claim). Cost claims close.** Caveat: "no DPA" is real; "no review at all" is optimistic, since a CISO can still demand a DPIA on a local tool that processes personal data at scale.

- **Biggest risk that it is not a business: the macOS / Windows-VDI mismatch sits directly on the only hard-requirement segments.** Defense and EU-bank counsel run managed Windows or Citrix/VDI. On a virtual desktop the "device" is a data-center VM, so "nothing leaves the device" is both unbuildable on their endpoint and partly meaningless. The elegant macOS-native story is aimed at a population that mostly is not in the regulated segments that need it. This must be resolved before committing to the wedge.

**Painkiller trigger:** the first time an AI-generated contract claim is about to be relied on where it bites (a board answer on an indemnity cap, a rep in a financing, a covenant calc). The buyer is the GC or AI-governance chair who has *already* deployed a legal AI assistant and had a near-miss. If the company has not adopted an assistant yet, there is no pain to kill.

**The eight falsifying interview questions (spine in bold):**
1. Walk me through the last time someone relied on an AI summary of a contract for something that mattered. What was the claim, who relied on it, what would have happened if it was wrong?
2. **Today, can your lawyers put the text of an executed contract into a cloud AI tool? Yes or no, and what exact policy or clause says so?**
3. When you brought in your current AI tool, how long did security and procurement take, and what held it up?
4. **If a tool ran entirely on the lawyer's machine and sent nothing out, would your CISO still require a full vendor security review and DPIA, or a reduced one? Has that actually happened here?**
5. **Do your lawyers work on Windows or Mac, and is it a physical laptop or a Citrix/VDI desktop?**
6. Would you trust verification software from a vendor with no SOC 2 and no operating history to touch your executed contracts? What would it take, concretely, to make that a yes?
7. If your AI says the MSA caps liability at $1M, what do you do right now to check it, and how long does it take?
8. Who has to sign off to spend real money: you, security, compliance, the business? Walk me through the last sub-$50k legal-tech purchase and who said no.

Answers to 2, 4, and 5 alone are enough to call go/no-go before August: is the cloud ban real for them, does local actually shorten procurement, and are they even on a machine Cachet supports.

**Key sources (2026):** ABA Opinion 512 and zero-retention vendor norms (GC AI, Wordsmith); Microsoft 365 Copilot privacy boundary (Microsoft Learn, Microsoft Adoption); ITAR / air-gapped requirements (ITAR Consultant, iternal.ai); CLOUD Act / sovereignty under DORA, NIS2, EU AI Act (SoftwareSeni, SysArt); local inference as DPA-free privacy-by-design (GDPR Local, Seresa); corporate legal as a Windows / Citrix-VDI world (V2 Cloud). Full URLs in the engagement transcript.

**How this changes the report:** it does not overturn Section 7's "lead with the in-house wedge" call; it sharpens it. Relocate the positioning from *privacy* to *procurement-friction collapse + independence*, name the EU-sovereign and defense segments explicitly, and treat the macOS/VDI platform question as a gating risk to resolve in the first interviews rather than a detail.
