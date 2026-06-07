# ADR-0012 T1 Recall Tier — Sequenced, Test-Gated, Dark PR Plan

> Design artifact (2026-06-06). Produced by a 19-agent design workflow (6 seam-readers
> → 3 design tracks → 9 adversarial ADR-0012 invariant checks → synthesis). Governs the
> build of the T1 local discriminative recall tier from
> [`docs/adr/ADR-0012-two-tier-verification-selection.md`](../adr/ADR-0012-two-tier-verification-selection.md).
> **Not yet approved for implementation.** Phase A is buildable now (dark); Phase B is
> blocked on the labeled corpus. Five operator decisions (D1–D5) gate the start.

## Operator decisions resolved (2026-06-06)

- **D3 — RESOLVED: no confidence number on the card.** The card shows a distinct
  `Assessed (local model)` tier (reusing the shipped `assistive` register) with **no
  percentage rendered**. The numeric confidence stays on the wire (`assessed_confidence`)
  because the calibration gate and the audit record need it, but it is never shown on the
  card face. This keeps DESIGN.md's "No confidence scores anywhere, by design" invariant and
  the no-score trust stance intact; ADR-0012's "(N%)" display line is amended to "tier
  label, no rendered score." PR-3 drops the percentage; PR-2's wire field is unchanged.
- **D1 — RESOLVED (Vulcan): rank-only candidacy + pinned deberta NLI.** Pin
  `cross-encoder/nli-deberta-v3-xsmall` (~70MB) behind `CACHET_NLI_MODEL` (the NLI entailment
  is essential complexity T0 regex cannot reach; published SNLI/MNLI numbers are a starting
  point, never the gate — that is Goodhart). The candidacy floor is **rank-only** (top-K
  retrieval rank position, not the unnormalized RRF score, no second model), behind the
  selector interface so a reranker upgrade is a reversible swap. Rationale: the candidacy
  floor is a pre-filter, not a precision boundary (the FAR calibration gate + NLI threshold
  own precision), so a coarse signal cannot compromise correctness; pulling a ~1GB reranker
  to optimize a pre-filter before measuring (NLI latency is an UNKNOWN) violates
  profile-first and YAGNI. The reranker stays a documented upgrade gated on the D4 latency
  benchmark, which now only needs to measure the ~70MB NLI single-pair, not a second model.

This plan ships the T1 LOCAL discriminative recall tier as a sequence of small,
independently shippable, dark-by-default PRs that hold every ADR-0012 invariant by
construction. The work splits cleanly into two phases: **BUILDABLE-NOW** (PRs 1-7), the
dark scaffold — wire, gate machinery, on-device NLI selector, candidacy filter, and
runtime guard — all of which can land green today with T1 physically inert; and
**BLOCKED-ON-CORPUS** (PRs 8-10), which cannot begin until a labeled held-out legal
corpus exists, because their whole job is to set the two thresholds (`τ_cand`,
`τ_verdict`) and the FAR ceiling that the gate enforces. The single critical-path
dependency is that corpus; every threshold in this system is an *output* of a passing
gate over it, never a hand-typed number. T1 can only ever be enabled when the
calibration gate passes on the held-out split under an operator-protected, sanity-capped
ceiling, and the running model/threshold/feature tuple matches the committed gate-pass
artifact hash.

Three corrections from the adversarial verdicts are folded in throughout and worth
stating up front, because they reshape the design: (1) **no new `assessed` frontend
tier** — the shipped `claimDisposition.ts` already has an `assistive` tier built for
exactly "a model judgment, not a deterministic fact"; T1 reuses it (line 47/74). (2) The
`verdict` Literal is **not** widened; "assessed" rides as additive `assessed_*` fields on
an `unknown`-verdict card, so T0 precedence is structural. (3) The dark flag is
**physically inert, not merely default-false** — `t1_permitted()` requires a hash-matched
passing gate-pass artifact to exist, so there is no flag-flip that can ship a live T1
verdict before the gate passes.

---

## Phase A — BUILDABLE NOW (dark scaffold; lands green today)

### PR 1 — Declared deps + offline model-load harness (no T1 logic)
**Scope.** Promote `torch`, `transformers`, `onnxruntime` from transitive-via-docling to
first-class **pinned** declared dependencies. Add a shared offline-load helper that forces
`local_files_only=True` / `HF_HUB_OFFLINE=1` and fails loud (raises, never silent-fetches)
when weights are absent, reusing the `embeddings.py::_enforce_offline_env` pattern. No
selector, no wiring yet.
**Files.** `requirements.txt`, `pyproject.toml`, new `services/legal/_offline_model.py`.
**Verify.** Full verify chain green. New unittest: offline helper raises a clear error
when a fake model id is uncached and never opens a socket (extend `tests/test_zero_egress.py`).
**Status.** DARK (additive deps). **Operator-gated — D1.**

### PR 2 — `assessed_*` wire fields, end to end, defaulted None
**Scope.** Add `assessed_confidence: float | None`, `assessed_model: str | None`,
`assessed_label: str | None` to `VerifyClaimVerdict`; emit them in the single
serialization boundary `_verdict_card_to_dict`; add matching `Optional` fields (with
`ge=0, le=100` on confidence) to `VerifyClaimVerdictItem`. **Do not widen** `VerifyVerdict`.
Regenerate types. No code sets these yet.
**Files.** `services/verify.py`, `api_models.py`, regenerated `endpoints.ts`.
**Verify.** `generate-api-types.sh` no manual diff; round-trip through
`verify_result_to_payload`, default `None`, stream == non-stream; frontend typecheck.
**Status.** DARK (fields always `None`).

### PR 3 — Reuse the `assistive` tier for the T1 disposition (frontend only)
**Scope.** In `claimDisposition.ts`, inside the existing `card.verdict === "unknown"`
branch (line 185), **before** the `could_not_check` return, promote to the **existing
`assistive` tier** (not a new tier) when `card.assessed_confidence != null`. Label UI-side:
`Assessed (local model)` — **no rendered percentage** (D3 resolved; the numeric confidence
stays on the wire for the gate/audit but is never shown on the card). No
`DispositionKind`/`Tier`/`TIER`/`ORDER` additions.
**Verify.** `claimDisposition.test.ts` (structural, not positional): `unknown` +
`assessed_confidence` → `assistive` with the assistive label and **no digit rendered**;
without → `could_not_check`; a `verified`/`unsupported` card with a stray
`assessed_confidence` → fields ignored, deterministic disposition holds. Badge never
`badgePass`/`badgeFlag`.
**Status.** DARK (no card carries `assessed_confidence` until PR 6). D3 resolved.

### PR 4 — T1 NLI selector (Protocol + lazy offline `_ensure`), unwired
**Scope.** New `services/legal/t1_selector.py`: `EntailmentScorer` Protocol,
`T1Candidate`/`T1Assessment` frozen dataclasses, `TransformersEntailment` mirroring the
`rerank.py` lazy/Protocol/env-flag/module-global-cache shape but loading
`AutoModelForSequenceClassification` via the PR-1 offline helper (fastembed structurally
cannot do 3-way NLI). 3-logit → softmax → `{support, contradict, cannot-determine}`
reading `config.id2label` (never hardcoded order). `assess()` returns `T1Assessment | None`;
`None` is the only below-threshold/no-candidate/failure path. **`rationale` is a fixed
template/extractive string**, never model-authored.
**Verify.** New `tests/test_t1_selector.py` with a tiny cached fixture model: logit→outcome
mapping; `cannot-determine` and below-threshold both → `None`; missing model → fail-closed
`None` under the socket ban; rationale template-only. Never imported by the product path yet.
**Status.** DARK (module exists, nobody calls it).

### PR 5 — Calibration gate harness + corpus schema + lint tooling (no corpus data)
**Scope.** Gate spine on the `benchmarks/phase0.py` pattern: `benchmarks/t1_calibration.py`
with direction-aware rules (`false_affirmative_rate.* → lower`, recall **advisory**),
**dual test** (absolute per-surface ceiling AND zero-tolerance relative regression),
`SystemExit(1)` on `--fail-on-gate`. Define the labeled-example JSONL schema,
`manifest.json`, operator-owned `thresholds.json` (ships with **`null` placeholders that
hard-fail**), and blocking-error set **B1-B8** including **B4 (vacuous-pass:
`predicted_affirmatives < min` is a hard fail; 0/0 is not a pass)** and **B8 (document-level
split leakage)**. Add `t1_seed.py --emit-template` and `t1_corpus_lint.py`. **Hard sanity
cap**: any `far_ceiling.<surface>` above a fixed max (e.g. > 0.05) is itself a blocking error
(operator cannot commit a loose ceiling for demo optics). Gate-pass artifact records
`corpus_sha256`, `thresholds_sha256`, `guideline_version`, **`model_sha256`**, and
**`feature_version`**.
**Files.** `benchmarks/t1_calibration.py`, `benchmarks/t1_seed.py`, `benchmarks/t1_corpus_lint.py`,
`data/calibration/thresholds.json` (null), `data/calibration/GUIDELINE-v1.md`, new blocking CI
job `t1-calibration-gate` (path-filtered), CLAUDE.md verify-chain line.
**Verify.** Gate with no corpus trips B1/B2/B3 and exits 1 (premature flag-flip fails loudly
in CI). Unit tests per blocking error incl. B4 and the ceiling cap.
**Status.** DARK + structurally inert (only reachable state is "blocked on B1/B2/B3").

### PR 6 — Wire the selector into the envelope + verify ladder, behind an inert guard
**Scope.** Two sites. **Site A** (`deterministic_envelope.py` anchor-free `else` block):
after the claim dict is appended, if `t1_permitted()` and a candidate passes the candidacy
floor (`τ_cand`, conservative placeholder default, runs **before any NLI call**), call the
selector and stamp `claim["t1_assessment"]` **only** on an above-threshold result. **Site B**
(`verify.py::_claim_dict_to_verdict`): insert the branch with **precedence pinned** — below
`if citations`, below `quote_could_not_check_reason`, below `could_not_check_reason`'s
sibling refusals — firing **only when no T0 disposition key is present** (`not citations and
not contract_verdict and not case_verdicts and not quote_could_not_check_reason`), so T1 can
never paint over a T0 verdict. Runtime assert + test that `t1_assessment` is only ever
written on an otherwise anchor-free-only dict.
**The guard `t1_permitted()`** returns False unless ALL hold — `CACHET_T1_RECALL` truthy
(OFF-default, read at the envelope layer, **no route-level surface default and no
explicit-arg override**, unlike `CACHET_DETERMINISTIC_VERIFY`); a `data/calibration/gate-pass.json`
exists, parses, `passed: true`; and its `corpus_sha256`/`thresholds_sha256`/`guideline_version`/
`model_sha256`/`feature_version` all match the running system. **Fail-closed**:
missing/corrupt/partial → False → byte-identical to off.
**Verify.** New tests: (a) deterministic verified/unsupported/contract/case card never acquires
`assessed_*`; (b) below-threshold / guard-False → byte-identical to today's `could_not_check`;
(c) contract `not_found` + stray `t1_assessment` → still `unknown`; (d) corrupt `gate-pass.json`
→ dark; (e) `quote_could_not_check_reason` + `t1_assessment` → `assessed_*` None, reads
`could_not_check`. Full chain green with `CACHET_T1_RECALL` unset.
**Status.** DARK + physically inert (no gate-pass artifact exists).

### PR 7 — Extend zero-egress + dark-path integration tests to the flag-ON path
**Scope.** Run `build_deterministic_envelope` with `CACHET_T1_RECALL=true` **and a synthetic
passing gate-pass artifact** under the socket ban, asserting the NLI selector + candidacy
reranker load and assess with zero real sockets opened. Add the gate-existence test: flag ON
but **no valid artifact** → selector never constructed, no `t1_assessment` stamped, every
claim dict byte-identical to flag-off.
**Files.** `tests/test_zero_egress.py`, new `tests/test_t1_dark_path.py`.
**Verify.** Both green; full chain green. Makes "cannot ship live before the gate passes" and
"on-device only" executable invariants, not review-time promises.
**Status.** DARK. End of buildable-now phase.

---

## Phase B — BLOCKED ON CORPUS (cannot start until the held-out corpus exists)

### PR 8 — BLOCKED: Build + lint + promote the labeled corpus
Write `GUIDELINE-v1.md` (3 labels; `cannot_determine`-default-on-ambiguity). Seed from a
hand-labeled CUAD contract subset + a litigator-brief set via `t1_seed.py`. Double-blind label
test/dev, adjudicate, single-label only for train. Promote to `{train,dev,test}.jsonl` with
**document-level disjoint** splits, stratified by `surface` and `gold_label`, test
write-once-then-locked. `t1_corpus_lint.py` clean. **This is the critical path — a data task.**

### PR 9 — BLOCKED: Tune on train, sweep `τ_cand`/`τ_verdict` on dev, calibrate confidence
Tune features on `train` only. Sweep `threshold_epsilon` on `dev`. Add confidence calibration
(temperature-scaling or isotonic on `dev`) so `confidence` is a calibrated probability, plus a
top1-minus-top2 **margin floor** (a high-score-wrong argmax must not reach a lawyer even on a
corpus that passes pooled FAR). Replace the PR-6 `τ_cand` placeholder with the corpus-derived
value. Reproducible dev-sweep report under `evals/reports/`; gate never reads train/dev.

### PR 10 — BLOCKED: Operator commits real thresholds; run the gate; enable
Operator replaces `null` placeholders in `thresholds.json` with real `threshold_epsilon` +
per-surface `far_ceiling` (each under the sanity cap). Run `t1_calibration.py --fail-on-gate`
on the **locked test split**. On pass (B1-B8 clean, FAR ≤ ceiling per surface, no regression),
the harness writes `gate-pass.json` with all five hashes. Only then may `CACHET_T1_RECALL` be
flipped; the runtime guard re-checks the hash on every launch. Default posture once green is an
explicit user-facing assistive/beta toggle, not silent enablement (D5). **The only place T1
ever becomes enable-able.**

---

## Corpus dependency (the real critical path)

A data task, not a code task (ADR-0012 C1-C4). Minimal path:
1. **`GUIDELINE-v1.md`** — three labels with worked examples; ambiguity defaults to
   `cannot_determine` (if two careful readers could disagree on support-vs-contradict → `cannot_determine`).
2. **Seed** both surfaces via `t1_seed.py`: a hand-labeled CUAD subset (clause as premise;
   faithful restatement → `support`, altered parameter → `contradict`, silent-on → `cannot_determine`)
   and a litigator brief set (holding as premise; same three constructions).
3. **Double-blind label** test + dev, adjudicate to a third reader, persistent ambiguity →
   `cannot_determine`. Single-label only for train.
4. **Lint + promote** with `t1_corpus_lint.py`: document-level disjoint splits (split key =
   `source_ref.doc`), stratified by surface and label, affirmative-eligible floor enforced, test
   sealed write-once. Any edit to test bumps the corpus version and invalidates every prior
   gate-pass by hash.

Until this corpus exists and PR 10 passes the gate over its locked test split, `thresholds.json`
carries `null` (B1/B2 trip), `gate-pass.json` is absent, `t1_permitted()` returns False, and T1
stays dark by construction.

---

## Open decisions for the operator

- **D1 — RESOLVED (rank-only candidacy + pinned deberta NLI; see "Operator decisions resolved"
  above).** Implementation notes: promote `torch` + `transformers` + `onnxruntime` to declared,
  pinned deps (PR 1); pin `cross-encoder/nli-deberta-v3-xsmall` (~70 MB) behind `CACHET_NLI_MODEL`
  (PR 4). Candidacy is rank-position top-K (no reranker, no `use_reranker=True`, no ~1 GB
  cross-encoder pull); the reranker-score candidacy is a documented upgrade behind the same
  selector interface, gated on the D4 latency benchmark.
- **D2 — Verify the deps are actually present in the target interpreter.** The worktree had no
  `.venv` and all three deps missing; `requirements.txt` pins `fastembed~=0.4`. PR 1 must verify
  against the real project interpreter and land dep promotion in the same PR as any importing code.
- **D3 — RESOLVED (no rendered score; see "Operator decisions resolved" above).** Outcome: keep
  DESIGN.md's `No confidence scores anywhere` invariant; the card shows the `Assessed (local
  model)` tier with no percentage; the numeric confidence stays on the wire for the gate/audit
  only. ADR-0012's I1/I6 display line is amended from "(N%)" to "tier label, no rendered score"
  (amend the ADR in PR 3's branch). No design-review blocker remains.
- **D4 — Latency is an unmeasured UNKNOWN.** On-device NLI single-pair latency on the target Mac
  has no primary source. Must be benchmarked before PR 10; it is a gate input and decides whether
  the reranker+NLI two-model path is viable or candidacy must fall back to rank-only.
- **D5 — Enablement posture (PR 10).** Confirm: once the gate passes, T1 is an explicit
  user-facing assistive/beta toggle, not silently enabled by flipping the env flag.
