# ADR-0012: Two-Tier Verification Selection (T0 Precision, T1 Recall, Calibration-Gated)

- Status: Proposed (draft for operator decision)
- Date: 2026-06-06
- References: [`docs/notes/2026-06-05-cachet-deterministic-extraction.md`](../notes/2026-06-05-cachet-deterministic-extraction.md) (the T0/T1/T2 honesty tiers and the "extract by anchor" decision), [`docs/notes/2026-06-05-cachet-local-architecture.md`](../notes/2026-06-05-cachet-local-architecture.md), [ADR-0008](ADR-0008-v2-pivot-validation-first-sequencing.md), [ADR-0009](ADR-0009-fail-loud-on-high-stakes-flows.md), PRs #122 + #123 (the party/defined-term/section detectors, merged/open), the open "never build generation" line (P6).

## Context

The Cachet product the operator is building is: upload any document, verify a draft (or AI summary) against your own sources, on-device, no cloud. For that to feel intelligent across arbitrary documents, the engine has to be good at the **selection** problem, deciding which spans need verification, not just the matching problem.

Two facts are in tension.

1. **Today selection is deterministic by anchor (T0).** A sentence is checked only if it carries a surface-detectable artifact: a citation, a quoted run, a money amount, a date/duration, a section reference, a party name, a defined term. Per the deterministic-extraction note, anchor coverage on real contracts is **~25-35%** (CUAD-grounded; the rosier 46-54% figure was refuted). The no-anchor majority, liability caps, anti-assignment, IP ownership, "best efforts," and omission-class discrepancies, is exactly the high-value material a lawyer most wants caught.

2. **LLM-style selection is natural-language understanding.** It is essential complexity (Brooks, No Silver Bullet), not something regex reaches. ~25-35% is a ceiling set by language, not by code. Tuning T0 regex toward LLM recall produces brittle special cases that still miss the semantic claims **and** quietly erode the one guarantee that defines the product: grounding attested, never a false claim. The product's moat is honesty under uncertainty (the loud 3-state tray). An LLM "seems smart" partly by guessing confidently and sometimes hallucinating; optimizing Cachet to *seem* like an LLM by guessing to fill coverage builds a worse LLM and discards the differentiation (Goodhart's Law).

The operator's stated goal ("smart enough to seem like an LLM in how it selects what to verify") cannot be met by tuning T0, and should not be met by guessing. It can be met by adding a **local, discriminative recall tier** under a hard calibration gate, while keeping T0 as the precision spine and the cloud LLM off. This ADR commits to that split and defines the gate.

## Decision

Verification selection is **two explicit, separately-labeled tiers**, never one engine pretending to be smarter than it is.

- **T0 (deterministic, no AI):** anchor detection is the precision spine. Verdicts produced here are labeled *verified (deterministic)*. This is the existing engine (`services/legal/anchors.py` + `deterministic_envelope.py`), plus wiring the already-merged `party` / `defined_term` / `section` detectors into the envelope (coverage already paid for, not yet collected).

- **T1 (local discriminative model, no cloud, no generation):** a recall tier for the anchor-free majority. Two signals, both on-device:
  - **Retrieval-score candidacy:** a draft sentence that strongly retrieves a source clause (`search_typed_hybrid`, already built) is a verification candidate even with no hard anchor. The retrieval signal is selection.
  - **Local NLI entailment:** a small cross-encoder (the `deberta-v3-xsmall`-class model the local-architecture note specs; torch/onnx already installed), premise = source clause, hypothesis = draft sentence, producing support / contradict / cannot-determine with a confidence score.
  T1 verdicts are labeled *assessed (local model, N% confidence)*, **never** *deterministic* and **never** *verified*.

- **The cloud LLM stays off for selection.** Holding-match remains the single optional T2 call, off by default, exactly as today. A cloud or on-device LLM is an explicitly-labeled assistive tier a user opts into; it is never the path by which a "no-cloud" or "deterministic" claim is made.

- **The 3-state tray stays the terminal honesty surface.** T1 raises recall by moving claims out of *could-not-check* into *assessed (with confidence)*. It never upgrades a claim to *verified*, and it never collapses the tray.

## The calibration gate (the discipline that makes T1 safe)

T1 is the dangerous tier: a model that selects and assesses meaning can be confidently wrong, which is the one failure mode this product cannot survive. The gate is what keeps it honest.

1. **Precision-first, gated metric.** The gate measures the **false-affirmative rate** on T1's non-refusal verdicts: a T1 *support* or *contradict* that is actually wrong, on a held-out, hand-labeled legal corpus. This rate must sit under a hard ceiling (ε). Recall is measured and reported but does **not** gate; precision does. One confident wrong verdict in front of a lawyer is product-ending, so ε is near-zero by intent (single-digit basis points on affirmative verdicts; the exact value set when the corpus exists).

2. **Below-threshold is silence, not a guess.** The confidence threshold is set so everything under it routes to *could-not-check* (the tray), never to a verdict. This is the structural enforcement of "right or silent": T1 can only ever move a claim from the tray into an assessed verdict, and only above the threshold the gate proved.

3. **Off until it passes; re-gated on every change.** T1 ships **dark** (off by default, like `CACHET_DETERMINISTIC_VERIFY` today) until the gate passes on the corpus. Any change to the model, threshold, or features re-runs the gate; a regression in the false-affirmative rate blocks the change, the same way the `evals-full` quality bar gates retrieval today. The threshold is operator-protected, not tunable for demo optics.

## Invariants (non-negotiable)

1. **T1 is never presented as deterministic.** Every verdict carries its tier and (for T1) its confidence on the wire (extend the existing provider-provenance convention). The UI distinguishes *verified (deterministic)* from *assessed (local model, N%)* end to end.
2. **No coverage-by-guessing.** Below the calibrated threshold, the answer is *could-not-check*, never a verdict.
3. **The 3-state model stays.** T1 adds a labeled confidence dimension; it does not remove or collapse the refusal tray.
4. **No generation.** T1 is discriminative only (entailment, classification, retrieval scoring). This keeps the locked "never build generation" line (P6) intact; this ADR does not reopen it.
5. **No cloud on the default path.** T1 runs on-device. The cloud LLM is an opt-in, explicitly-labeled tier and is never how a no-cloud claim is satisfied.
6. **T0 and T1 verdicts are distinct, semantically and visually.** A reader can always tell which tier produced a result and how confident it is.

## Why this is defensible, and where the risk remains

- **It raises coverage toward the "upload anything" UX without becoming or needing a cloud LLM,** and without crossing the no-cloud or no-generation lines. The intelligent *feel* comes from real recall on the high-value no-anchor claims plus the calibrated tray, not from guessing.
- **The moat is preserved by construction.** The gate makes "never a false claim" a measured, enforced property rather than an aspiration. A lawyer can trust the tier labels because the affirmative-verdict precision is gated.
- **Residual risk is real and named.** (a) The gate cannot be set without a labeled held-out legal corpus, which does not exist yet; building it is the true dependency, not the code. (b) On-device NLI single-pair latency on the target Mac is unmeasured (carried as an UNKNOWN from the architecture note). (c) The standing temptation is to drop the threshold to "feel smarter" for a demo; the gate must be operator-protected against exactly that. (d) T1 weights add roughly 70MB to the bundle plus cache management, and the contract path already depends on the local embedder being pre-cached (fail-loud, not silent).

## Alternatives considered (rejected)

- **A. Pure T0 (status quo).** Rejected: ~25-35% coverage is too thin for "upload any document"; the experience reads as blind on the high-value no-anchor claims.
- **B. Cloud LLM for selection.** Rejected: violates the no-cloud moat and reintroduces hallucination into the one product whose promise is no false claims.
- **C. Tune T0 regex toward LLM recall.** Rejected: fights essential complexity (the ceiling is set by language), produces brittle per-case regex, and erodes the honest-coverage guarantee by claiming to check what it is guessing at. The autonomous build loop already recorded this lesson (pin and document the irreducible T0/NER limits, do not chase fractal regex edges).

## Open questions for the operator

1. **The calibration corpus is the gating dependency.** Where does the labeled, held-out legal set come from, a hand-labeled subset of CUAD-style contracts plus a litigator-brief set? The gate, and therefore T1, cannot exist without it. This is a data task, not a code task, and it is on the critical path.
2. **The false-affirmative ceiling (ε).** My recommendation: near-zero on affirmative verdicts, because one confident wrong verdict in front of a lawyer ends the product. The operator sets the exact bar.
3. **Default posture once the gate passes:** ship T1 still dark and operator-enabled, or expose it as an explicit "assistive / beta" toggle the user turns on knowingly? (Recommendation: explicit user-facing toggle, labeled, so the tier distinction is in the user's hands, never silent.)

## Non-goals

- Building any generative model. The "never build generation" line stands; this ADR is discriminative-only and does not reopen P6.
- Making the cloud LLM the default, or the path by which a no-cloud claim is met.
- Replacing or weakening the 3-state refusal tray. T1 enriches it; it does not remove it.
- Wiring or shipping T1 before the calibration gate exists and passes. Until then, T0 plus the tray carry the product.

## Implementation notes (PR-6, dark wiring)

PR-6 wires the selector into the verify path, dark behind `services.legal.t1_gate.t1_permitted()` (False on main: opt-in env `CACHET_T1_RECALL` plus a still-valid `gate-pass.json` are both required, and no artifact exists). Three decisions are pinned here so the later corpus/enable PRs honor them:

1. **Candidacy is best-of-K, and the gate must certify the same K.** Site A (the anchor-free contract branch in `deterministic_envelope`) retrieves the top `rank_cutoff` clauses and returns the best above-threshold assessment over them. Best-of-K is a max over K probabilistic NLI calls, so its false-affirmative rate is strictly higher than a single pair's. Therefore `rank_cutoff` lives in `thresholds.json` (it rides `thresholds_sha256`, so `t1_permitted` invalidates on any change) and the corpus/predictions the gate scores **must be generated under the same best-of-K strategy**. A gate that measured top-1 while the runtime runs best-of-3 would certify a FAR the runtime exceeds; that is the one hole this wiring exists to avoid. Requiring `rank_cutoff` to be set (`thresholds_complete`) is **necessary but not sufficient**: it pins the K the runtime *reads*, not that the gate's predictions were *generated* at that K. In PR-6 that equivalence is enforced ONLY by the corpus-generation step (operator discipline) and is not mechanically checked; the runtime gate still measures a per-pair FAR. The enable PR closes this (checklist below). Until it does, no code claims the equivalence is guaranteed.
2. **`model_sha256` is bound at model-load, not in `t1_permitted()`.** The guard re-checks the four cheap bindings (corpus, thresholds, guideline, feature_version) on every call; re-hashing the weights would tax the hot path and, while dark, the model never loads. The load-time weight-hash check lands with the enable PR (the weights are not cache-present in CI to exercise it until then). `t1_gate.FEATURE_VERSION` is the runtime's view of the candidacy/scoring code identity; the enable run must mint the artifact with that value.
3. **Assessed-tier provenance is strictly subordinate to an unknown could-not-check verdict.** Site B (`verify._claim_dict_to_verdict`) maps `t1_assessment` onto the `assessed_*` card fields only when the verdict is `unknown` via could-not-check, never over a T0 verdict, so a local-model assessment can never paint over a deterministic fact (invariant 1). The verdict itself never changes; the assessment only enriches the tray.

### Before T1 goes live (enable-PR checklist, blocking)

T1 must not be enabled until each of these lands, because PR-6 ships the best-of-K runtime and the gate-binding fields but enforces the gate↔runtime FAR equivalence only by operator discipline:

- **Mechanical best-of-K equivalence.** Either (a) the gate performs the best-of-K reduction itself over per-sentence candidate lists under `threshold_epsilon` (corpus schema becomes per-sentence with a clause list, predictions carry per-candidate scores), so the gate and runtime share one reduction; or (b) the predictions file carries a `{strategy, k}` provenance header and a B-check fails the gate unless `k == thresholds.rank_cutoff` and `strategy == "best_of_k"`. Option (a) is stronger and preferred.
- **A regression test that a top-1 / wrong-K / wrong-ε predictions file FAILS the gate.** Today no test asserts this; add one with the mechanical check.
- **`predictions_sha256` recorded in `gate-pass.json`** (`write_gate_pass`), so the exact predictions file that produced the certified FAR is pinned and auditable. The runtime need not re-check it; it anchors the strategy check above.
- **Model-weights hash verified at model load.** `model_sha256` is recorded in the artifact in PR-6 but not yet checked; the enable PR hashes the loaded weights in `TransformersEntailment._ensure` (the offline loader must expose the resolved weights path) and refuses to score on a mismatch.
- **On-device single-pair NLI latency measured** on the target Mac (carried UNKNOWN), with `t1_permitted()` caching added if hashing the enabled-path inputs proves measurable on the hot path.
