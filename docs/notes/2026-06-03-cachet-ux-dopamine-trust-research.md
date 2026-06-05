# Cachet UX research: honest dopamine for a trust instrument

Date: 2026-06-03
Provenance: `/deep-research` workflow (24 sources, 113 extracted claims, 25 adversarially verified, 15 confirmed at 2-0 / 3-0, 10 killed). Workflow synthesis step failed; this document is the hand-synthesis, grounded in the live `DESIGN.md` and the shipped `frontend/src/features/verify/` implementation.
Audience: founder, designer, engineer. Hand-off artifact.

---

## 0. How to read this (evidence ledger)

A report for a verification product should model the calibration it preaches. So every empirical claim below is tagged:

- **[confirmed N-0 / N-1]** survived 2-3 independent adversarial verifiers reading the primary source.
- **[refuted 0-3]** was actively killed. I report these because two of them sharpen the thesis.
- **[unverified]** is real, citable literature that this pass could not independently re-confirm in time (verifiers abstained). Used carefully, flagged each time.
- **[craft]** is practitioner writing (Superhuman, Linear, NN/g), not empirical research. Used for mechanics, not for claims about the brain.

The single most important honesty note up front: **the claim that "admitting I-cannot-verify increases credibility" was refuted (0-3).** The evidence does not say refusal builds trust. It says *calibration drives appropriate reliance* and that *miscalibration is the failure mode*. The refusal state is not valuable because confession is endearing. It is valuable because it is the instrument that keeps the user's reliance matched to what was actually checked. That reframing runs through the whole report.

---

## 1. Cachet today (so the recommendations build on it, not over it)

Restated from `DESIGN.md` (2026-05-29, 2026-05-31, 2026-06-02 decision-log entries) and `VerifyView.module.css`.

### Philosophy already in code

The verify surface has already won most of the anti-dark-pattern argument. These are shipped, not aspirational:

- **"A verdict is a finding, not a score."** `VerifyVerdictSummary` shows counts only. No pass-rate, no percentage, no completion bar. (`VerifyView.tsx`, the summary computes `needsReview` and supported counts, never a ratio.)
- **The not-confirmed set is the headline.** `DISPOSITION_ORDER` sorts flags first, the honest refusal next, supported statements last.
- **Absence of a flag is the pass.** There is deliberately no green VERIFIED badge. The CSS says it outright: "No green VERIFIED badge by design." Your own cross-professional discovery (2026-05-29) found the green badge is "the single most dangerous element."
- **"Checking is not a finding."** A streaming claim shows a quiet "Checking..." register and never flashes a premature pass (`badgeChecking`, `verdictCardChecking`).
- **Three registers of finding, already built:**
  - deterministic flag (a fabricated cite, an altered quote) wears the oxblood struck underline `--verify-flag: #7a2230`.
  - an AI judgment (a holding that contradicts) wears the *assistive* register: a dotted pencil query, achromatic, "for your review," never oxblood.
  - the refusal (could-not-check) wears a composed ink bracket, "grave but neutral ink, never an accusation."
- **Honest failure.** A stream that ends without a result sets the error "No verdict was produced; nothing was marked supported," never a partial pass.
- **Scope honesty.** Every result carries: "This confirms grounding, not legal correctness or strategy."

### Design makeup (scoped `/verify` deviation, founder-approved)

- Palette: warm paper `#f6f2ea` (surfaces `#efe7d9` / `#f1ebe0` / `#fcfaf4`), near-black ink `--text-primary: #1c1814`, ink-quiet functional accent `--accent: #23201c`, one grave oxblood `--verify-flag: #7a2230` reserved for flags only. No traffic-light green/amber/red.
- Type: a reading serif for document body (`--font-serif-body: Charter, ...`). Display stays the cold serif. **Open item: the intended cold display face is Libre Caslon Display (per the 2026-06-02 direction and the founder brief), but `DESIGN.md` and the shipped CSS still specify Instrument Serif.** Doc-sync gap, flagged in section 6.
- Motion: near-zero on `/verify`. The one sanctioned exception is the certification seal (PR2, 2026-05-31): a 900ms WAAPI press-and-settle on seal, a 600ms crack with luster-loss when the sealed draft later changes. Ink, never brass (no gold).
- The Shelf (`/shelf`, PR6c, 2026-06-02) is the warm register: Fraunces, warm cream "chambers" ground, an ink seal disc, grouped by the human's act (sealed / unsealed), carrying no oxblood and no verdict count. "Warmth never touches a verdict."
- The logo is the "withheld-strike" mark: a truncated C drawn as an open ring, severed upper-left. Ink/paper, oxblood reserved, no gold/blue/green. **Hold this thought; the brand mark and the core interaction rhyme (section 5).**

This is a product with taste and spine. The job is not to fix it. The job is to make a lawyer reopen it every day without betraying any of the above.

---

## 2. The tension, diagnosed and reconciled

### 2a. Steelman the founder: Cachet *must* be dopaminergic, or it dies a vitamin

The strongest version of "make it addictive" is not frivolous. It is neurologically literate:

- Dopamine is a **reward prediction error** signal. It fires for outcomes *better than expected*, is silent for fully-expected outcomes, and dips when an expected reward is withheld [confirmed 3-0, Hollerman & Schultz, Nature Neuroscience 1998; confirmed 3-0, Frontiers in Human Neuroscience 2017]. Unpredictable reward is genuinely, mechanically potent. The founder's instinct that "dopamine works" is correct science, not hype.
- Professional tools that nobody loves get **opened when forced and abandoned when not.** Legal-tech is a graveyard of accurate, unloved software (Westlaw and Lexis are used because they are mandatory, not because anyone reopens them with anticipation). Accuracy alone does not create a habit. If Cachet is merely austere and correct, it becomes another compliance chore, and "trust" cannot save a tool that is never opened.
- The retrospective memory of an experience is dominated by its **peak and its end**, not its accuracy or its duration [confirmed 3-0, peak-end rule, Psychonomic Bulletin & Review 2008]. A tool that produces no peak produces no memory, and an unremembered tool is an unrenewed subscription.

Conclusion of the steelman: a verification tool that refuses to be felt will be accurate and dead. Emotion is not the enemy of trust; *indifference* is.

### 2b. Steelman the skeptic: the dopamine playbook would destroy the moat

The strongest version of "do not make it addictive":

- The standard engagement playbook manufactures the prediction error *in the interface*: variable rewards, streaks, surprise confetti, points. The dopamine comes from an **unpredictable reward schedule the designer controls** [confirmed 3-0, the prediction-error mechanism is exactly what slot designs exploit]. For a credibility instrument, a designer-controlled surprise is a lie. The moment the user senses the celebration is choreographed, the verdict feels choreographed too.
- The real danger Cachet exists to fight is **overreliance**: people accept an AI suggestion even when it is wrong [confirmed 2-0, Buçinca et al. 2021]. Calibrated trust, not maximal trust, is the goal [confirmed 3-0, Lee & See, Human Factors 2004]. Any mechanic that nudges the user toward "feel good, click accept" pushes them back into the exact failure the product sells protection from.
- Worse, **explicitly communicating confidence can backfire.** When a tool surfaces its calibration level, users get better at detecting miscalibration but trust drops and they *under-rely*, with no net gain in decision quality [confirmed 3-0, arXiv 2402.07632]. So even the "honest" move of slapping a confidence number on a verdict is not free. Uncertainty has to be designed, not dumped.
- Gamification of serious professional work tends to **backfire**: extrinsic motivators crowd out the intrinsic motive and degrade the behavior they were meant to reinforce [unverified but well-supported, Cornell 2025 on goal-app backfire; craft, Rahul Vohra: "gamification does not work, but game design does"]. Regulators now name these patterns: the FTC's 2022 Dark Patterns report catalogs manufactured urgency and obscured choice as enforcement targets [confirmed-class, FTC 2022].

Conclusion of the skeptic: every gram of manufactured dopamine is paid for in credibility, and credibility is the entire product.

### 2c. The reconciliation (the stance to design against)

Both are right, and they resolve into one sharp principle:

> **Honest variable reward. The variability lives in the draft, never in the interface.**

Dopamine is a prediction error [confirmed 3-0]. The founder is right that Cachet needs it. The skeptic is right that the designer must never *manufacture* it. The resolution is that Cachet already sits on top of a genuine, high-stakes, genuinely unpredictable reward: **the finding.** Every verify run has a real and uncertain outcome. Is the brief clean? Did it cite a case that does not exist? Was a quote altered? The user does not know until the tool reads it. That uncertainty is not a UI trick. It is the actual state of an AI-generated draft, and the user desperately needs to know it.

So the slot machine is the draft, not the screen. The pull of the lever is the paste. The variable reward is **the catch**: the relief of finding a fabricated citation before it reaches a judge. That is a true positive prediction error ("I thought my brief was fine; it caught three problems") and it is completely honest, because the surprise was already in the world. The interface's only job is to surface that real surprise with maximum clarity and weight, and then get out of the way.

This gives three design corollaries:

1. **Engineer the gap, not the reward.** The dopamine is in the distance between what the user expected (a clean draft) and what was found. Design the *reveal of the finding* as the peak. Never design a reward that is not a finding.
2. **The act is the second engine.** Intrinsic satisfaction does not require an external payoff; it is "intrinsic to the arousal and maintenance of the activity" [confirmed 3-0, effectance motive, Frontiers 2017]. Make the act of verifying fast, keyboard-first, and masterful, and the work becomes its own reason to return. This is the daily-habit driver. (Note: the claim that mastery is *dopaminergic* was refuted 0-3, so this is an intrinsic-satisfaction argument, not a dopamine argument. It is no weaker for that.)
3. **The refusal is the calibration instrument, not a confession.** Its job is to keep reliance matched to what was checked [confirmed 3-0, Lee & See], and to do so without the backfire of naive confidence-dumping [confirmed 3-0, arXiv 2402.07632]. Designed well, it is the most trustworthy screen in the product precisely because it is the moment the tool would rather be useful-and-honest than impressive-and-wrong.

Everything below serves that stance.

---

## 3. Research landscape, reduced to transferable mechanics

| Finding | Evidence | Transferable mechanic for Cachet |
|---|---|---|
| Dopamine = prediction error; potent for unexpected, silent for expected | confirmed 3-0 (Schultz 1998; Frontiers 2017) | Make the verdict reveal a genuine expectation gap. The "clean" result should feel earned and slightly surprising; the "caught it" result should land as relief. Do not flatten the reveal into a uniform list. |
| Intrinsic satisfaction needs no external reward (effectance) | confirmed 3-0 (Frontiers 2017) | The act of verifying must be its own reward: sub-second feel, keyboard-first, legible labor. No points needed. |
| Mastery is dopaminergic | **refuted 0-3** | Do not promise a dopamine hit from mastery. Sell competence as satisfaction and speed, not as a high. |
| Peak-end rule applies to pleasant experience; duration is neglected | confirmed 3-0 (peak); confirmed 2-1 (duration) | Spend the craft budget on two moments: the peak (the catch) and the end (the seal). Let the middle be quiet and fast. A 14-statement check and a 3-statement check should both end on the same dignified seal. |
| People rely on automation inappropriately; trust governs reliance | confirmed 3-0 (Lee & See 2004) | The design's target is *appropriate* reliance, not acceptance. Friction at the right places is a feature. |
| Trust must be calibrated to real reliability | confirmed 3-0 (Lee & See 2004) | Distinguish a deterministic miss (oxblood, high certainty) from an AI judgment (pencil, lower certainty). You already do this; protect it. |
| LLMs systematically fail to abstain; knowing when not to answer is fundamental | confirmed 3-0 (arXiv 2511.11500) | Refusal must be engineered as first-class. The product's differentiation is that it abstains where models do not. Make abstention visible and dignified. |
| Abstention trainable via ternary reward (+1 / 0 / -lambda) | confirmed 3-0 (arXiv 2511.11500) | Backend/eval framing: an honest "I do not know" is worth strictly more than a confident error. Mirror that hierarchy in the UI: a refusal outranks a false pass. |
| Miscalibrated AI confidence impairs reliance; users cannot self-detect it | confirmed 3-0 (arXiv 2402.07632) | You cannot rely on the user to catch a bad verdict. The verdict's register must carry the calibration *for* them. |
| Communicating calibration level can reduce trust and cause under-reliance | confirmed 3-0 (arXiv 2402.07632) | **Do not add a confidence percentage.** Encode certainty in register (ink weight, mark style), not in a number. This is empirical backing for your existing "no numbers" rule. |
| People overrely on AI even when it is wrong | confirmed 2-0 (Buçinca et al. 2021) | The whole justification for the product. The UI's emotional job is to make "do not just accept this" feel native, not nagging. |
| Refusal/abstention "builds credibility" as a coordination signal | **refuted 0-3** | Do not market the refusal as trust-building. Frame it as reliance-calibrating. Sharper and defensible. |
| Friction (cognitive forcing) reduces overreliance but is liked less | unverified (Buçinca 2021, abstained this pass) | Treat as a hypothesis for the T66 validation test, not a settled law. If true, it predicts the most trustworthy Cachet will not be the most immediately "fun," which is the founder tension stated as data. |
| Speed is the feature; sub-100ms response | craft (Superhuman) | Verify entry and every interaction should feel instant. Latency is the enemy of ritual. |
| Command palette as the power-user spine | craft (Superhuman, Raycast, Linear) | A ⌘K verb surface ("Verify draft", "Open last brief", "Export certification") is the keyboard-first ritual entry. |
| "Game design, not gamification" | craft (Vohra) | Borrow game *feel* (responsiveness, clarity, earned progression through real work) without game *tokens* (points, streaks, badges). |
| Empty/error states as signature moments | craft (NN/g, pencilandpaper) | The blank state and the refusal are not gaps to fill; they are the first and the bravest things the user sees. Design them first. |

---

## 4. The right kind of addictive: five honest loops

Each loop is specified as Trigger / Action / Variable reward / Investment (the Hooked skeleton), but every reward is a *real finding* or a *real artifact*, never a manufactured token.

### Loop 1 — The Catch (the core engine)
- **Trigger** (external, then internal): "I have an AI-drafted brief I am about to file." Over time this becomes the internal reflex: never send AI work unread by Cachet.
- **Action**: paste, one keystroke to verify. Must be sub-second to first sign of life.
- **Variable reward** (honest): the finding. Sometimes clean, sometimes three fabricated cites and an altered quote. The variability is real and consequential. This is the prediction-error peak [confirmed 3-0].
- **Investment**: sealing the result to the Shelf. The user accumulates a body of verified work, which raises the cost of leaving and the value of returning.

### Loop 2 — The Clean Record (earned confidence)
- **Trigger**: the pre-send moment, the same ritual.
- **Action**: verify, read the flags, fix or stand by each, re-verify.
- **Variable reward**: the transition from "3 need your review" to "all supported by the sources you provided." Not a score going up. A document becoming defensible. The reward is the *changed state of the work*, which the user earned by acting.
- **Investment**: the seal converts the clean check into a record with a fingerprint. The crack-on-stale (already built) means the record is a living promise.

### Loop 3 — Effectance / speed (the daily-habit driver)
- **Trigger**: any verify, any day.
- **Action**: keyboard-first flow. ⌘K to verify, ⌘↵ to seal, ⌥click to drill a flag, j/k through findings.
- **Reward** (intrinsic, not dopaminergic): the feeling of a well-tuned instrument answering instantly. Effectance: the act is its own satisfaction [confirmed 3-0]. This is the Superhuman lesson [craft].
- **Investment**: muscle memory. A user who has learned the keys is a user who has paid in skill and will not re-pay it elsewhere.

### Loop 4 — The Drill (competence and understanding)
- **Trigger**: a flag the user does not yet believe ("it says this cite is fabricated, but I am sure it is real").
- **Action**: open the Examination drawer on that flag.
- **Reward**: seeing exactly *why*. The missing case at the reporter. The quoted passage shown against the source with the altered words exposed. Competence: "now I understand." This is the antidote to the calibration-communication backfire [confirmed 3-0]; instead of a number that erodes trust, the user gets evidence that earns it.
- **Investment**: the user learns the failure modes of their own AI tools, which makes Cachet the lens through which they now read all AI output.

### Loop 5 — The Shelf (identity and return)
- **Trigger**: needing to revisit or prove past work.
- **Action**: open the Shelf, find the sealed brief.
- **Reward**: a warm room of one's own verified record. Relatedness and identity: "this is my body of careful work." The warm register (Fraunces, cream) is doing exactly the right job here.
- **Investment**: the corpus. Every sealed brief makes the Shelf more valuable and Cachet more irreplaceable.

What is deliberately absent from all five: streaks, points, badges, levels, confetti, surprise rewards, daily-goal rings. Each was considered and refused (section 7) on the evidence that they backfire for serious tools and that any manufactured variability would corrupt the honest variability that is the product.

---

## 5. Signature moments, re-imagined

Eight concrete designs. Motion is specified against the documented tokens (`--dur-*`, `--ease-*`), honors `prefers-reduced-motion` with a static end-state, and uses only `transform`/`opacity` unless it rides the existing seal WAAPI exception (flagged). Copy follows the verb-led, no-em-dash, lab-notebook voice.

### SM-V1. The Paste (the draft becomes a sheet)
- **Now**: a plain `<textarea>` and a button.
- **Reimagined**: on paste, the textarea *settles* into a sheet of paper. The draft text sets in the reading serif (`--font-serif-body`) on `--surface-2: #fcfaf4`, with a hairline edge. As the engine reads, a quiet lab-notebook line materializes: "Reading the draft. 14 statements." The count is the first honest signal: the tool has understood the shape of the work before it judges it.
- **Motion**: `fadeUp` (Tier 2, 220ms `--ease-out`) on the settle. Statement count counts up once with a 280ms opacity fade, no spring.
- **Why it works**: it builds honest anticipation (the prediction-error setup) without promising an outcome. The user now expects a verdict and does not yet know it. That gap is where the dopamine will land.
- **Copy**: "Reading the draft and extracting claims..." (already shipped; keep).

### SM-V2. The Read (legible labor, not a spinner)
- **Now**: "Checking citations · 3 of 14" with a spinner; per-card "Checking..." (good bones, already shipped).
- **Reimagined**: the streaming list reads like a clerk working down a page. Each statement sits in its "Checking..." ink register; as its check lands, it *settles* into its disposition with a 120ms `--ease-out` opacity/transform, flags rising toward the top as they resolve. The eye watches real work happen in real order. No progress bar (a bar implies a score finish line; this is a reading, not a race).
- **Motion**: Tier 1 settles only, 120ms. The reorder uses FLIP on opacity/transform, never layout properties.
- **Why it works**: effectance made visible [confirmed 3-0]. The user trusts a verdict they watched be assembled (your SM-3 instinct, applied to verify). And the peak is *built*: each landing flag raises the stakes of the final reveal.

### SM-V3. The Catch (the peak; the one motion worth breaking the rule for)
- **The moment**: a fabricated citation is caught. This is the single most valuable thing Cachet does and today it renders as a static oxblood line. That undersells the peak.
- **Reimagined**: the oxblood struck mark *draws* across the dead citation, left to right, like a proofreader's pen striking through it, 360ms. It is the same gesture as the logo (the withheld strike, the severed ring). The brand mark and the core interaction become the same act: **Cachet strikes what it cannot stand behind.** Beneath, in `--text-secondary`, the plain finding: "No case at 576 U.S. 644. Citation not found." A breath of stillness (120ms hold) before the user can act. That stillness is the peak landing.
- **Motion**: a `scaleX(0 -> 1)` of the underline rule, `transform-origin: left`, 360ms `--ease-soft`. **Transform-only, so it satisfies the DESIGN.md "transform/opacity only" rule.** Under `prefers-reduced-motion`, the struck mark is simply present. This is a *new* motion moment on a near-zero-motion surface; it must be approved as a scoped exception, exactly as the seal was (section 6).
- **Why it works**: this is the honest variable reward made physical. The relief of the catch is the dopamine [confirmed 3-0, prediction error], and it is earned by a real event, not a designed one. Peak-end says this is one of the two moments the user will remember [confirmed 3-0]. Spend here.
- **Register discipline**: only the *deterministic* miss (fabricated cite, altered quote) gets the drawn strike. An AI judgment (a holding that may contradict) keeps the quiet dotted pencil query. Never let the softer, less certain finding borrow the strike's confidence.

### SM-V4. The Reckoning (the verdict summary, not a verdict score)
- **Now**: "3 of 14 statements need your review" with counts. Good. Keep the substance.
- **Reimagined**: the headline sentence sets in the cold display serif at h1, the flags' oxblood already drawn above it, the supported statements visually *receding* (`--text-tertiary`, smaller) below. The composition says: here is what needs you; the rest is quietly fine. No percentage, no ratio, no bar.
- **Motion**: the supported set fades to its recessive weight 280ms after the flags settle, so the eye is led to the problems first.
- **Why it works**: this is calibration by composition. The register carries the certainty the user cannot self-assess [confirmed 3-0]. It resists the score the whole category reaches for, which is exactly the discipline that signals credibility to a distrustful professional buyer.

### SM-V5. The Refusal (the emotional core, redesigned to calibrate)
- **The moment**: "Could not verify." The source was not provided, or the engine could not reach it. Today: a composed ink bracket, neutral. Correct register, underbuilt.
- **Reimagined**: the refusal is the most *complete* card in the product, not the emptiest. It states, in order:
  1. what it checked ("Read the draft. Found the citation. Could not retrieve the opinion text.").
  2. what it therefore cannot say ("So I cannot confirm the holding supports your claim.").
  3. the precise next action ("Add the opinion PDF, then verify again," with that action as a button, per the empty-state rule).
- It hands responsibility back with precision. It never shrugs ("could not check") and never accuses. The ink bracket holds it like a held breath.
- **Motion**: none beyond the Tier-1 settle. Stillness is the point. A refusal that animates is a refusal performing; this one simply *is*.
- **Why it works**: this is the calibration instrument doing its job [confirmed 3-0, Lee & See]. Critically, it avoids the confidence-number backfire [confirmed 3-0, arXiv 2402.07632] by replacing "low confidence" with "here is the specific gap and the specific fix." That is the difference between dumping uncertainty (which causes under-reliance) and *resolving* it into an action.
- **Honesty note**: I am not claiming this screen makes users trust Cachet *more* (that claim was refuted 0-3). I am claiming it keeps their reliance correct, which over many uses is what a professional learns to depend on. The love comes later, from being right when it mattered, not from the confession being charming.

### SM-V6. The Seal (the end; the ritual close)
- **Now**: PR2 seal, 900ms press-and-settle, crack-on-stale. Already the right idea, already the sanctioned motion exception.
- **Reimagined (small)**: make the seal the unmistakable *end* of every session, clean or flagged. Peak-end says the last moment is half the memory [confirmed 3-0]. After the user has resolved or accepted every flag, the seal is the one warm, deliberate, two-handed gesture: ⌘↵ to seal. The press-and-settle is the exhale. The fingerprint binds the record to this exact draft.
- **Keep**: the crack. A sealed record whose draft later changed *should* lose its luster. That is the honest-variability principle applied to time.
- **Why it works**: it converts a check into an artifact (the Hooked investment), and it gives every session the same dignified ending regardless of how messy the middle was. Duration neglect [confirmed 2-1] means the messy middle fades; the seal is what remains.

### SM-V7. The Command Spine (ritual entry, earned mastery)
- **New**: a ⌘K palette scoped to verify verbs: "Verify draft", "Open last sealed brief", "Drill flag 2", "Export certification", "Seal and save". Keyboard path for the whole loop: ⌘V paste, ⌘↵ verify, j/k between findings, ⌥↵ drill, ⌘S seal.
- **Why it works**: speed is the feature [craft, Superhuman]; the palette is the power-user spine [craft, Raycast/Linear]. This is Loop 3 made real, and it is the single biggest lever on daily reopening. A lawyer who has the keys will not retype them in a competitor.
- **Note**: the global Carrel app already stubs a ⌘K palette (`features/palette`); the verify scope can reuse it.

### SM-V8. The Shelf as a body of work (return and identity)
- **Now**: `/shelf`, warm, grouped by sealed/unsealed, Fraunces, no oxblood, no counts. Right instincts.
- **Reimagined (light)**: lead with the human's act, not the engine's findings (already the design). Add one quiet, honest signal: a sealed record whose draft has since drifted shows the *cracked* seal here too, so the Shelf is not a museum of past confidence but a live ledger of what still holds. No streak, no "X briefs verified this week," no count. The warmth is the reward; the integrity of each seal is the substance.
- **Why it works**: relatedness and identity, the return trigger of Loop 5. The Shelf is where Cachet stops being a tool and becomes *the user's record*.

---

## 6. Buildable and on-brand: what this respects, what it breaks

### Respects (no approval needed)
- Every color is an existing token. The only chromatic accent used is `--verify-flag` oxblood, on deterministic flags only. No green, no second accent, no numbers.
- "A finding, not a score" is preserved everywhere. No percentage, no ratio, no progress bar. This is now also evidence-backed [confirmed 3-0, calibration-comms backfire].
- The three finding registers (oxblood strike / pencil query / ink bracket) are preserved and their certainty hierarchy is protected.
- `file://` constraints respected: every reveal is click- or keystroke-triggered or part of the existing SSE stream. No render-time Suspense, no route-split lazy boundaries.
- Reduced-motion: every moment has a static end-state.

### Breaks (require founder approval, flagged honestly)
1. **SM-V3 The Catch is a new motion moment on a near-zero-motion surface.** The 2026-05-29 decision mandates near-zero motion on `/verify`; the seal (PR2) is the sole sanctioned exception. The drawn strike is a *second* exception. I argue it earns the same treatment the seal got, for the same reason: it is the peak of the experience and it is WAAPI/transform-only (no CSS keyframe rule added, so the `verifyScope.test.ts` motion guard still holds). **Recommendation: approve it as the second and final motion exception, and write it into the decision log beside the seal. Do not let a third in without retiring one (the SM-cap discipline).**
2. **The cold display face is unresolved.** The brief and the 2026-06-02 direction say Libre Caslon Display; `DESIGN.md` and the shipped CSS still say Instrument Serif (the seal stamp even sets Instrument Serif below its 24px floor). SM-V4's headline sets in "the cold display serif." **Recommendation: resolve this explicitly. If Libre Caslon Display is the decision, update `DESIGN.md`'s Typography section, the `@font-face` in `tokens.css`, and the seal-stamp note in one PR, and self-host the woff2 the same way as Instrument Serif and Fraunces (local-first, OFL/appropriate license, `font-display: swap`).** Until then, every "cold display serif" reference is correct in either face.
3. **⌘K palette on verify (SM-V7)** is additive but touches the global palette stub. Low risk, but it is a new surface; scope it to verify verbs first.

### Explicitly not broken
- No Suspense streaming, no Framer/GSAP/Lottie, no scroll-driven or ambient motion, no third-party font CDN. All within the documented motion constraints.

---

## 7. Roadmap

### The three highest delight-and-trust-per-effort changes (do these first)

1. **SM-V3 The Catch.** The honest peak. A `scaleX` drawn oxblood strike on deterministic flags plus the breath-of-stillness, plus the plain finding line. Highest emotional return in the product; the dopamine is real and earned. Effort: small (one WAAPI/transform animation, copy, the register guard already exists). Gated on the one motion-exception approval.
2. **SM-V5 The Refusal, rebuilt to calibrate.** Turn "could not check" into the three-line check / cannot-say / do-this card with an action button. Highest trust return; it is the gem, and the rebuild is mostly copy and layout over the existing ink-bracket register. Effort: small-to-medium. No approval needed.
3. **SM-V7 The Command Spine.** ⌘K verbs and the full keyboard path. Highest *daily-reopen* return; this is the effectance/speed habit. Effort: medium (reuse the palette stub). No approval needed beyond scope.

### Deeper bets (next)
- **SM-V2 The Read** as legible labor (FLIP reorder of findings as they land). Medium effort; large felt-quality gain.
- **SM-V8 The Shelf** as a live ledger (cracked seals surface in the Shelf). Medium; deepens Loop 5 and identity.
- **SM-V1 The Paste** settle and statement-count. Small-to-medium; sets up the prediction-error gap.
- **SM-V6 The Seal** as the universal session end (⌘↵, clean or flagged). Small; the seal already exists.

### The refuse-list (and why refusing is the brand)

These were each considered against the evidence and declined. The discipline of declining them is itself the credibility signal your distrustful buyers are looking for.

- **No streak counter, no daily-goal ring.** Extrinsic motivators crowd out the intrinsic motive and backfire for serious tools [unverified but well-supported, Cornell 2025; craft, Vohra]. A lawyer who verifies because of a streak is a lawyer who will skip verification the day the streak does not matter.
- **No confidence percentage, no trust score.** Communicating calibration as a number reduces trust and causes under-reliance with no gain in decision quality [confirmed 3-0, arXiv 2402.07632]. Encode certainty in register, never in a number. This is your existing "no numbers" rule, now with a citation.
- **No green VERIFIED badge, ever.** Overreliance is the documented failure mode [confirmed 2-0, Buçinca 2021]; a green badge is an invitation to it, and your own discovery already named it the most dangerous element. Absence of a flag is the pass.
- **No manufactured variable reward.** No surprise confetti, no randomized celebration, no "you caught a big one!" The only variability is the finding. Manufactured surprise on a verdict surface reads as a choreographed verdict, which poisons the real one.
- **No fake urgency, no manufactured scarcity.** FTC-named patterns [confirmed-class, FTC 2022]. A verification tool that invents urgency forfeits the standing to be believed about anything.
- **No gotcha framing of the user.** The tool strikes the citation, never the person. The voice is a clerk's, not a judge's. The user is the client of the verification, not its defendant.

The throughline: **refusing these is the same gesture as the product refusing to verify what it cannot.** Cachet is honest about its own limits and honest about the user's draft, and it declines to manipulate for the same reason it declines to bless an unsupported claim. The refuse-list is not a constraint on the brand. It *is* the brand.

---

## 8. Source ledger

Confirmed (used as load-bearing):
- Hollerman & Schultz, Nature Neuroscience 1998, dopamine as reward prediction error. https://www.hms.harvard.edu/bss/neuro/bornlab/nb204/papers/Hollerman_Schultz_NatNeuro_1998.pdf [3-0]
- Frontiers in Human Neuroscience 2017, value-coding dopamine and the effectance motive. https://www.frontiersin.org/journals/human-neuroscience/articles/10.3389/fnhum.2017.00145/full [3-0]
- Peak-end rule for material/pleasant experience, Psychonomic Bulletin & Review 2008. https://link.springer.com/content/pdf/10.3758/PBR.15.1.96.pdf [peak 3-0; duration 2-1]
- Lee & See, "Trust in Automation: Designing for Appropriate Reliance," Human Factors 2004. https://journals.sagepub.com/doi/10.1518/hfes.46.1.50_30392 [3-0 / 2-1]
- Abstention as first-class via ternary reward, arXiv 2025. https://arxiv.org/abs/2511.11500 [3-0]
- Calibrated-confidence and AI-assisted decisions, arXiv 2024. https://arxiv.org/abs/2402.07632 [3-0]
- Buçinca et al., overreliance and cognitive forcing, 2021. https://arxiv.org/pdf/2102.09692 [overreliance 2-0; forcing/tradeoff abstained]

Refuted (reported for honesty):
- "Mastery/competence loops are dopaminergic" [0-3].
- "Abstention builds credibility as a coordination signal" [0-3].

Unverified this pass (real literature, flagged where used):
- Stanford Prominence-Interpretation Theory, Fogg. https://credibility.stanford.edu/pdf/PITheory.pdf
- Cornell 2025, goal-setting apps motivate or backfire. https://news.cornell.edu/stories/2025/12/what-makes-goal-setting-apps-motivate-or-backfire

Craft / practitioner (mechanics, not empirical claims):
- Superhuman on speed and command palettes. https://blog.superhuman.com/superhuman-is-built-for-speed/ , https://blog.superhuman.com/how-to-build-a-remarkable-command-palette/
- Rahul Vohra, "game design not gamification." (20VC summary) https://www.deciphr.ai/podcast/20vc-superhumans-rahul-vohra-...
- Linear method. https://linear.app/method
- NN/g and pencilandpaper on empty/error states. https://www.nngroup.com/articles/prominence-interpretation-theory/ , https://www.pencilandpaper.io/articles/empty-states
- FTC Dark Patterns report 2022. https://www.ftc.gov/system/files/ftc_gov/pdf/P214800+Dark+Patterns+Report+9.14.2022+-+FINAL.pdf

---

## Appendix: one paragraph for the founder

You asked for addictive. The science says the addictive thing is the prediction error, and you already own a real one: the catch. Build the product so the lever is the paste, the peak is the strike through a fabricated citation, and the end is the seal, and let the only variability be the truth about the draft. Make the act fast enough to be a reflex and the refusal precise enough to be trusted, and a lawyer will reopen Cachet every day, not because you manufactured a craving, but because you removed a fear. That is the only kind of addictive a trust instrument is allowed to be, and it happens to be the durable kind.
