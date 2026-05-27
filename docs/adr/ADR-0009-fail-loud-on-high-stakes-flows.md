# ADR-0009 — Fail-loud on high-stakes AI flows

**Status:** Accepted
**Date:** 2026-05-27
**Drives:** T64 (answer-quality investigation) Phase 3 policy decision; implemented in T64 Phase 4.
**Supersedes:** none. **Superseded by:** none.

## Context

Carrel V2 is positioned as an independent AI verification layer for high-stakes AI output, with litigation pre-flight as the wedge ([ADR-0008](ADR-0008-v2-pivot-validation-first-sequencing.md)). A 30-day litigator validation test (T65 → T66) is the explicit decision gate for committing to Approach B versus falling back to Approach A or killing the category.

T64 Phase 1 reproduced a hollow-answer bug: the Apple Foundation Models (AFM) provider returned a heading-only response ("MITOSIS") to a substantive grounded-answer question. The pattern surfaced because the Carrel provider-resolution layer silently falls back from Claude → AFM → Ollama → Null when `ANTHROPIC_API_KEY` is missing or unreachable. The user never saw which provider produced the answer; the answer was technically `ok=True` but semantically empty.

This is exactly the demo signal that would kill the validation test: a litigator interacting with a hollow-answer Verify or Ask demo concludes the engine is unreliable and disengages, regardless of whether the underlying CourtListener and holding-match infrastructure works.

## Decision

On **high-stakes** request kinds, the Carrel backend fails loud when the active provider is not Claude. The frontend renders a non-dismissable banner explaining the gate and pointing at the remediation (set `ANTHROPIC_API_KEY`).

### High-stakes request kinds (gated)

- `tutor.grounded_answer` — the Ask flow (`POST /api/tutor/query`, `POST /api/tutor/query/stream`).
- (Verify reuses `tutor.grounded_answer` per `services/verify.py`; when a future PR splits Verify onto its own request_kind, that kind joins `HIGH_STAKES_REQUEST_KINDS` in the same commit.)

### Low-stakes request kinds (graceful degradation preserved)

- `flashcard_generation`
- `dialogue_followup`
- `note_expansion`
- `srs_review`

Low-stakes flows keep the silent-fallback behavior because (1) they are not litigator-facing, and (2) AFM and Ollama can produce useful output for these kinds even with the hollow-answer risk.

### Provider provenance is visible everywhere

Phase 2 added `provider: str` to `ClaudeCallResult`, `GroundedAnswer`, `VerifyResult`, `TutorQueryResponse`, and `VerifyResponse`. Phase 4 surfaces it in the UI via a `ProvenanceBadge` primitive on both high-stakes views.

## Implementation

- `ai/providers.py::ensure_provider_allowed(request_kind, provider)` raises `ProviderUnavailableError` when `request_kind ∈ HIGH_STAKES_REQUEST_KINDS` and `provider != "claude"`.
- `services/tutor.py::grounded_tutor_response` calls the gate at entry. On `ProviderUnavailableError`, it returns a fail-loud `GroundedAnswer(ok=False, error="provider_below_quality_bar", model="", provider=<active>, ...)` and emits a `tutor_provider_below_quality_bar` log event. Retrieval and LLM dispatch are short-circuited.
- `frontend/src/features/shared/ProviderQualityGateBanner.tsx` renders the non-dismissable banner with `role="alert"`. Used by `AskView` and `VerifyView` when `response.error === "provider_below_quality_bar"`.
- `frontend/src/design-system/primitives/ProvenanceBadge/` shows the active provider tag (`Claude` / `Apple Intelligence` / `Ollama` / `Unavailable`) on every response.
- `services/tutor.py::_AFM_GROUNDED_TUTOR_SYSTEM` adds an explicit "do not echo a chunk heading" instruction. `ai/afm_client.py::request_grounded_answer` post-parse adds a `hollow_answer` guard rejecting fragment-shaped output before it reaches the user (belt-and-suspenders for low-stakes paths AFM still serves).

## Alternatives considered

- **(a) Fail-loud only on high-stakes (chosen).** Litigator-facing surfaces refuse to answer rather than risk hollow output; low-stakes paths keep working without a Claude key.
- **(b) Visible provenance badge only, no gate.** Keeps every surface answering, surfaces which provider produced what. Rejected because a litigator watching a demo does not pause to interpret a badge; the hollow answer reaches their eyes before the badge does. Saved for low-stakes surfaces.
- **(c) Full provider-chain quality re-ranking.** Too large for the validation-test window; punts to post-T66.
- **(d) Force Claude API for every flow.** Rejected because Carrel's local-first thesis requires AFM/Ollama-only operation to work. Forcing Claude on flashcard generation would lock out users without an API key from features that AFM serves adequately today.

## Consequences

**Good**
- A litigator watching the demo with no `ANTHROPIC_API_KEY` set sees an explicit "Claude required" banner instead of a hollow answer; the demo signal is clean.
- Provider provenance is visible everywhere; future quality regressions can be tracked per provider via the badge + the `provider` field on every response.
- Low-stakes flows (flashcards, dialogue, notes) continue to work locally without an API key.

**Costs**
- A litigator who wanted to dry-run the Ask/Verify flow without setting a key cannot. Acceptable because (1) the validation test recruits litigators willing to install and configure Carrel, and (2) the alternative (hollow answer) is strictly worse.
- The `ProviderQualityGateBanner` adds one render branch on each high-stakes view and one new design-system primitive (`ProvenanceBadge`). Bundle delta is small.

**Risk**
- A future PR that adds a new high-stakes flow may forget to add its `request_kind` to `HIGH_STAKES_REQUEST_KINDS`. Mitigation: the constant lives in `ai/providers.py` next to `ensure_provider_allowed`; the test `tests/test_tutor_provider_fallback.py::test_phase4_gate_short_circuits_on_high_stakes_with_non_claude_provider` pins the contract for the existing kind, and the routine's auditor verifies new request_kinds against the high-stakes list when reviewing new PRs.
- The hollow-answer guard threshold (40 chars OR terminal punctuation) is heuristic. A genuinely correct one-line answer like "Mitochondria produce ATP." (25 chars) passes only because of the terminal punctuation check. If the heuristic false-rejects in the wild, T64 Phase 6 verification will surface it; the fix is to tune the threshold, not to remove the guard.

## Exit conditions

This decision is reconsidered when:

1. **T66 verdict is `KILL`.** If the validation test concludes the high-stakes verification thesis does not produce a buying signal, the V2 pivot is shelved; the gate may be relaxed to (b) visible badge only on the surviving tutor surface.
2. **T66 verdict is `FALLBACK_A`.** The single-vertical product still benefits from this gate; keep as-is.
3. **Local LLM quality crosses the threshold.** A future AFM/Ollama model that produces substantive grounded answers on the seeded T65 memo would prompt revisiting the high-stakes list. The decision rule: re-run the T64 Phase 1 reproduction test with the new model and the gate disabled; if substantive-answer-rate ≥ 0.95 (Phase 5 metric), the gate can drop AFM/Ollama from its block list.

## References

- T64 plan: [`docs/plans/answer-quality-2026-05-26.md`](../plans/answer-quality-2026-05-26.md) §"Policy decision (operator 2026-05-27 00:30 GMT+2)"
- V2 sequencing: [ADR-0008](ADR-0008-v2-pivot-validation-first-sequencing.md)
- Phase 1 reproduction: `tests/test_tutor_provider_fallback.py::test_afm_path_produces_substantive_answer_or_documents_degradation`
- Phase 4 gate test: `tests/test_tutor_provider_fallback.py::test_phase4_gate_short_circuits_on_high_stakes_with_non_claude_provider`
