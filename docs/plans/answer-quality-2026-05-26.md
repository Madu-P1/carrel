# Plan: T64 Answer-Quality Investigation — Eliminate the Header-Only Response

- **Status:** drafted 2026-05-26, awaiting operator approval
- **Owner:** operator-led with autonomous loop assist on instrumented phases
- **Tracks:** AUTONOMOUS_WORK_PLAN.md T64 (blocker for T65/T66 validation test)
- **Strategic frame:** [ADR-0008](../adr/ADR-0008-v2-pivot-validation-first-sequencing.md) — V2 validation-first reset
- **Memory:** [answer-quality-root-cause](../../../../../.claude/projects/-Users-madu-Desktop-Codex/memory/answer-quality-root-cause.md)

---

## Premise

The header-only / title-only Ask response pattern is NOT a prompt-engineering problem on the Claude path. It is the silent provider fallback in `ai/providers.py` when `ANTHROPIC_API_KEY` is missing. Auto-mode falls back per:

1. Claude (if API key set)
2. AFM (if Apple Silicon + macOS 26+ + bridge present) — **too weak for the grounded-answer task; returns headings as answers**
3. Ollama (only if `OLLAMA_BASE_URL` explicitly set per `_ollama_has_endpoint()` at [ai/providers.py:68](../../ai/providers.py)) — too much RAM strain to be a viable default
4. NullProvider (returns `ok=False` with `error_code="ai_disabled"`)

The "no silent AI fallbacks" rule in CLAUDE.md is satisfied technically (each `ClaudeCallResult` carries `ok=True` and real latency/tokens from AFM, see [ai/router.py:35-53](../../ai/router.py)) but fails practically — the user sees hollow output without knowing the provider was degraded. The plan reconciles this.

Trade-off the plan must hold open: Carrel's local-first thesis cares about the offline / no-API-key user experience. The fix cannot be "always require Claude" — that breaks local-first. The likely shape is: fail-loud on high-stakes flows (Ask, Verify), allow on low-stakes flows (flashcard generation, dialogue follow-ups).

---

## Phase 0 — Documentation discovery (DONE 2026-05-26)

### Allowed APIs (verified by direct read)

| Symbol | Location | Notes |
|---|---|---|
| `ClaudeCallResult` dataclass | [ai/router.py:35-53](../../ai/router.py) | Frozen. Fields: `ok`, `task`, `model`, `request_kind`, `text`, `json_payload`, `error_code`, `error_message`, `latency_ms`, `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, `cache_hit`, `service_tier`, `stop_reason`, `request_id`. **No `provider` / `provider_name` field today.** |
| `AIProvider` Protocol | [ai/providers.py:55-153](../../ai/providers.py) | `ai_enabled`, `model_for_task`, `request_text`, `request_json`, `request_tool_call`, `supports_grounded_answer`, `request_grounded_answer`. Every concrete provider also exposes a `kind: ProviderKind` literal attribute. |
| `ProviderKind` literal | [ai/providers.py:52](../../ai/providers.py) | `Literal["claude", "ollama", "afm", "null"]`. The plan reuses this; do NOT introduce a parallel string. |
| `select_provider(kind)` | [ai/providers.py:112-150](../../ai/providers.py) | Bypasses singleton; tests use this with explicit kind. |
| `get_default_provider()` | [ai/providers.py:189-208](../../ai/providers.py) | Singleton with env-signature cache. Settings UI invalidation lives in `_provider_selection_signature`. |
| `reset_default_provider()` | [ai/providers.py:211-218](../../ai/providers.py) | **Tests must call this in setUp and tearDown when mutating provider env vars.** Pattern: see [tests/test_tutor_grounded.py:541-587](../../tests/test_tutor_grounded.py) `test_pro_tutor_fails_closed_on_null_provider`. |
| `Citation` / `Claim` / `GroundedAnswer` dataclasses | [services/tutor.py:137-194](../../services/tutor.py) | Frozen. `GroundedAnswer` has `model`, `latency_ms`, `ok`, `error`, `cache_hit`, `input_tokens`, `output_tokens`, `scope_fallback_used`, `citation_attempt_count`, `citation_drop_count`, `citation_repair_count`, `citation_structural_drop_count` (default 0), `citation_non_prose_drop_count` (default 0). **No `provider` field today.** |
| `_resolve_grounded_answer` | [services/tutor.py:1264](../../services/tutor.py) | Central citation-validation function. |
| AFM provider call site | [services/tutor.py:1631](../../services/tutor.py) | `afm_router.request_grounded_answer(...)` — different code path from Claude. |
| Claude provider call site | [services/tutor.py:1644](../../services/tutor.py) | `router.request_tool_call(...)` — uses `SUBMIT_GROUNDED_ANSWER_TOOL`. |
| `grounded_tutor_response` | invoked at [routes/tutor.py:39-46](../../routes/tutor.py) via `tutor_service.grounded_tutor_envelope` | The Ask endpoint. |
| Verify endpoint | [routes/verify.py:22-33](../../routes/verify.py) | Calls `services.verify.verify_draft`. Per [services/verify.py:11](../../services/verify.py), the engine reuses `services.tutor.grounded_tutor_response`. **One fix to tutor serves both Ask and Verify.** |
| `TutorQueryResponse` Pydantic model | [api_models.py:237-258](../../api_models.py) | Has `model: str = ""` but no `provider` field. |
| `VerifyResponse` Pydantic model | [api_models.py:299-306](../../api_models.py) | Has `model: str = ""` but no `provider` field. |
| `groundedness_at_k` metric | [evals/run_evals.py:435](../../evals/run_evals.py) (compute), [evals/run_evals.py:549](../../evals/run_evals.py) (summary), [evals/run_evals.py:622-623](../../evals/run_evals.py) (threshold guard `< 0.70`) | Smoke + full mode both compute. |
| `quote_validity` metric | [evals/run_evals.py:503](../../evals/run_evals.py) (compute), [evals/run_evals.py:587](../../evals/run_evals.py) (summary), [evals/run_evals.py:624-625](../../evals/run_evals.py) (threshold guard `< 0.90`). | Full mode only — smoke skips (see harness `if mode == "smoke": return metrics` at [evals/run_evals.py:443-444](../../evals/run_evals.py)). |
| Summary report table | [evals/run_evals.py:656-663](../../evals/run_evals.py) | Markdown table f-strings. New metric rows append here. |

### Anti-patterns to avoid (read from prior memory, not invented)

- **Do not prompt-engineer the Claude `_GROUNDED_TUTOR_SYSTEM` as the first move.** The founder's diagnosis says Claude is not the failure mode. Touching the Claude system prompt is wasted iteration if the failure is on the AFM path.
- **Do not assume AFM and Claude take identical chunk inputs.** AFM uses `GroundedChunk` wire-shape with `chunk_id` field per [services/tutor.py:1621-1630](../../services/tutor.py); Claude takes a synthesized prompt via `_build_user_prompt`. They are structurally different code paths.
- **Do not "fix" AFM by adding a tighter Swift `@Guide` annotation.** Memory 4094 documents that the Swift @Guide already says "do not invent names"; the failure mode is the model returning the document heading verbatim, which the @Guide does not forbid. A new @Guide would be additive, not corrective.
- **Do not add a new `EnvironmentVariables` constant.** The plan reuses `CARREL_AI_PROVIDER` and adds at most one new env var, gated for the policy split (Phase 3).
- **Do not introduce `mock.patch` of `get_default_provider` without `reset_default_provider()` in setUp + tearDown.** Pattern at [tests/test_tutor_grounded.py:574, 587](../../tests/test_tutor_grounded.py).

### Open questions (resolve before Phase 4 code starts)

1. **Definition of "Claude unreachable."** Three sub-cases: (a) `ANTHROPIC_API_KEY` missing entirely, (b) key set but 401/403 from API, (c) key set but 429/5xx. Do all three trigger the same fail-loud behavior, or only (a)? Plan default: (a) and (b) fail-loud immediately; (c) retries once via the existing router retry budget, then fails-loud.
2. **Split definition: high-stakes vs low-stakes flows.** Plan default high-stakes: `tutor.grounded_answer`, `verify.verify_draft`. Plan default low-stakes: `notes.expand_note_content`, `dialogue.start_dialogue`, `dialogue.post_message`, anything that emits `request_kind` not in the high-stakes list. Operator confirms or adjusts in Phase 3.
3. **Surface for the fail-loud signal.** Plan default: existing `ok=False` + `error_code` propagates through `GroundedAnswer.error` → `TutorQueryResponse.error` → frontend renders a banner. Alternative: introduce a dedicated `degraded_provider` error_code for clarity. Operator confirms in Phase 3.
4. **Should the `provider` field be on the public `TutorQueryResponse` / `VerifyResponse`?** Privacy-side this is fine (it is the user's own client's provider). UX side this enables a provenance badge. Plan default: yes, public.

---

## Phase 1 — Reproduction

Goal: a failing test in `tests/` that demonstrates the header-only response pattern. Confirms the founder's diagnosis before any fix touches code.

### What to implement

1. New test file `tests/test_tutor_provider_fallback.py`. Mirror the structure of [tests/test_tutor_grounded.py:534-587](../../tests/test_tutor_grounded.py) (`test_pro_tutor_fails_closed_on_null_provider`).
2. Test class `TutorAFMHollowAnswerTests`. One method `test_afm_path_produces_substantive_answer_or_documents_degradation`:
   - Seeds a doc with a strong heading ("MITOSIS") and a substantive body paragraph ("During prophase, chromosomes condense and become visible under the microscope...").
   - Pins `CARREL_AI_PROVIDER=afm` via `mock.patch.dict` with `reset_default_provider()` bracketing.
   - Stubs `ai.afm_client.AFMClient.request_grounded_answer` to return a `ClaudeCallResult` whose `json_payload` is the documented AFM hollow-output shape: a `summary` and `claims` where every claim text equals a chunk's heading line.
   - Calls `tutor_service.grounded_tutor_response(conn, "Explain mitosis.")`.
   - Asserts: this test SHOULD FAIL on the current main commit. Either the response surfaces `ok=True` with a hollow summary (current buggy behavior — the test asserts the failing state and is marked `@unittest.expectedFailure` for the diagnostic phase), or it surfaces a fail-loud signal (post-fix behavior — remove the expectedFailure decorator).
3. Second test method `test_claude_path_produces_substantive_answer` as a control. Uses `StubRouter` (existing pattern, see [tests/test_tutor_grounded.py:201](../../tests/test_tutor_grounded.py) `test_happy_path_resolves_claims_and_citations`) wired to return a substantive `claims` payload. Asserts substantive output. Should PASS on current main.

### Documentation references

- Test pattern to copy: [tests/test_tutor_grounded.py:534-587](../../tests/test_tutor_grounded.py).
- AFM `request_grounded_answer` JSON shape: memory observation 4094 plus direct read of [ai/afm_client.py](../../ai/afm_client.py) around `request_grounded_answer` (read in this phase before writing the stub — do not assume).
- `reset_default_provider` usage: [ai/providers.py:211](../../ai/providers.py).

### Verification checklist

- [ ] `./.venv/bin/python -m unittest tests.test_tutor_provider_fallback -v` runs both methods.
- [ ] `test_afm_path_produces_substantive_answer_or_documents_degradation` runs and currently surfaces the buggy state (expectedFailure or documented mismatch).
- [ ] `test_claude_path_produces_substantive_answer` passes.
- [ ] No real Claude or AFM calls — stubs only.

### Anti-pattern guards

- Do NOT call real Claude or real AFM. Pure stub.
- Do NOT skip the `reset_default_provider()` in setUp / tearDown — without it, singleton state leaks across tests and the AFM pin silently reverts to whatever was selected at process start.
- Do NOT write the test against `grounded_tutor_envelope` (the Pydantic-serializing wrapper). Test against `grounded_tutor_response` to keep the assertion surface on the dataclass.

### Phase exit

Test file lands on a branch (`fix/t64-reproduce-afm-hollow`). PR review confirms the diagnostic test reproduces the bug deterministically.

---

## Phase 2 — Provider provenance instrumentation

Goal: every `ClaudeCallResult`, `GroundedAnswer`, and public API response carries a `provider: str` field so the eval harness and the UI can stratify behavior by provider.

### What to implement

1. **`ClaudeCallResult` field addition.** Add `provider: str = "unknown"` to the dataclass at [ai/router.py:35-53](../../ai/router.py). Default `"unknown"` so adding the field is backward-compatible with any test that constructs a `ClaudeCallResult` without naming every field. Each provider's call paths set the real value:
   - `ClaudeRouter.request_text` / `request_json` / `request_tool_call`: `provider="claude"`.
   - `AFMClient.request_text` / `request_json` / `request_tool_call` / `request_grounded_answer`: `provider="afm"`.
   - `OllamaClient.*`: `provider="ollama"`.
   - `NullProvider.*` (in `_null_result` at [ai/providers.py:42-61](../../ai/providers.py)): `provider="null"`.
2. **`GroundedAnswer` field addition.** Add `provider: str = ""` to the dataclass at [services/tutor.py:168-194](../../services/tutor.py). Populated from `result.provider` at the provider call sites ([services/tutor.py:1631, 1644](../../services/tutor.py)) and propagated through `_passages_only_fallback` and `_resolve_grounded_answer`.
3. **Pydantic response model additions.**
   - `TutorQueryResponse.provider: str = ""` at [api_models.py:237-258](../../api_models.py).
   - `VerifyResponse.provider: str = ""` at [api_models.py:299-306](../../api_models.py).
4. **TypeScript regeneration.** Run `./script/generate-api-types.sh` so `frontend/src/services/api/types.gen.ts` carries the new fields.
5. **Frontend wiring (read-only this phase).** Touch only the type imports in [VerifyView.tsx](../../frontend/src/features/verify/VerifyView.tsx) and the Ask view so they accept the new field. UX rendering of the badge waits for Phase 4.

### Documentation references

- Existing additive field pattern on `ClaudeCallResult`: `cache_hit: bool` at [ai/router.py:50](../../ai/router.py) — added similarly without breaking older constructors.
- Existing additive field pattern on `GroundedAnswer`: `citation_non_prose_drop_count: int = 0` at [services/tutor.py:194](../../services/tutor.py) — landed in PR #82, copy the shape.
- API type regen: per CLAUDE.md verify-chain line `./script/generate-api-types.sh`.

### Verification checklist

- [ ] `./.venv/bin/python -m unittest tests.test_ai_router tests.test_tutor_grounded -v` passes (no test should break — additive default-valued field).
- [ ] `corepack pnpm --dir frontend typecheck` passes after the regen.
- [ ] Existing eval harness output unchanged (the new field exists but no metric reads it yet — that is Phase 5).
- [ ] `grep -rn "provider:" services/tutor.py routes/ api_models.py | wc -l` confirms the field is plumbed in all four locations.

### Anti-pattern guards

- Do NOT make `provider` `str | None`. Default to `""` on Pydantic models (matches existing `model: str = ""` convention) and to `"unknown"` on the internal dataclass (so any leftover constructor without an explicit value is visibly distinguishable from a real provider name).
- Do NOT introduce a new enum or a `ProviderKind` import in the Pydantic models. Free string keeps the frontend permissive and lets the field carry future provider names without a schema migration.
- Do NOT alter the `ProviderKind` Literal at [ai/providers.py:52](../../ai/providers.py).

### Phase exit

PR lands on `fix/t64-provider-provenance`. Field plumbing visible in API responses (manual `curl` to `/api/tutor/query` shows the new `provider` key).

---

## Phase 3 — Policy decision (operator-led, no code)

Goal: operator picks the fix policy. Plan default ranking baked in, but operator owns the call.

### Three candidate policies

| Policy | Definition | Aligns with | Breaks |
|---|---|---|---|
| **(a) Fail-loud** | When `provider != "claude"` AND `request_kind` is in the high-stakes list, `_resolve_grounded_answer` returns `ok=False` with `error_code="provider_below_quality_bar"`. Frontend renders "AI verification requires a Claude API key. Open Settings to add yours." | CLAUDE.md "no silent fallbacks" most strictly. V2 thesis (verification layer cannot ship degraded). | The offline / no-API-key litigator's first-launch experience. Local-first thesis takes a partial hit: AFM still available for non-verification flows, but the headline feature requires the key. |
| **(b) Visible provenance badge** | All providers ship answers, but fallback-provider answers carry a UI badge: "Answered by on-device AFM. May be limited; add a Claude API key in Settings for full-quality verification." | Local-first thesis fully. User informed consent. | "No silent fallbacks" — technically the fallback is visible, but the user can ignore the badge and still surface a hollow answer to a third party. False-positive verifications still possible during the validation test. |
| **(c) Fix the provider chain** | Improve AFM grounded-answer prompt + post-processing until substantive_answer_rate >= 0.95 on AFM. Improve Ollama, or remove it from auto-mode entirely. Add a new provider tier between AFM and Claude (e.g., Selene Mini per memory 8670) if the gap is unbridgeable. | Local-first thesis fully. Long-run product. | Unknown effort. AFM model is fixed by Apple; we can only iterate the prompt + post-processing. Memory 4094 already documents the Swift @Guide annotation pattern; there may be limited headroom. |

### Recommended sequencing

The plan recommends **(a) + partial (c)**: fail-loud on Ask + Verify (high-stakes), keep AFM in non-verification flows (flashcards, dialogue) so local-first stays alive where degradation is tolerable. Pursue (c) as a parallel longer-arc investigation but do not gate T64 on it.

Counter-argument considered: (b) is gentler and might preserve the local-first user. Rejected because the validation test (T66) is the one event where a false-positive verification poisons the entire test premise. The cost of (a) is a worse first-launch experience for users without an API key; the cost of (b) is a worse 30-day test result. ADR-0008 already paid the cost of pausing polish for the test — paying it again here in product policy is consistent.

### What to implement (this phase)

ONE file: append the operator's decision to this plan doc as a `## Policy decision` section. Cite the chosen letter + rationale + (for (a)) the high-stakes request_kind list. No code touches.

### Verification

- [ ] Operator picks one of (a), (b), (c), or hybrid. Decision written to this file. Phase 4 reads it.

### Phase exit

Decision committed on the same branch as Phase 2 or a new branch — operator choice.

---

## Phase 4 — Implement chosen policy

Goal: ship the policy decision from Phase 3 with regression tests.

### What to implement (worked example: policy (a) + partial (c))

1. **Define the high-stakes request_kind set.** New module constant in `services/tutor.py` (top-level):
   ```python
   _HIGH_STAKES_REQUEST_KINDS: frozenset[str] = frozenset({
       "tutor.grounded_answer",
       # verify reuses tutor.grounded_answer per services/verify.py
   })
   ```
   Co-locate with `SUBMIT_GROUNDED_ANSWER_TOOL` so future readers see them together.
2. **Add a quality gate at `_resolve_grounded_answer` entry.** New helper `_provider_meets_quality_bar(provider: str, request_kind: str) -> bool`:
   - Return `True` when `provider == "claude"`.
   - Return `True` when `request_kind not in _HIGH_STAKES_REQUEST_KINDS` (low-stakes flows allow any provider).
   - Otherwise return `False`.
3. **Wire the gate.** Before the provider call at [services/tutor.py:1631, 1644](../../services/tutor.py), check `_provider_meets_quality_bar(provider.kind, "tutor.grounded_answer")`. When False, short-circuit with a `GroundedAnswer(ok=False, error="provider_below_quality_bar", model="", provider=provider.kind, ...)` and skip the provider call entirely. The `_passages_only_fallback` path then runs with the new error_code so the frontend can surface a specific "add API key" message.
4. **Frontend banner (minimal).** [VerifyView.tsx](../../frontend/src/features/verify/VerifyView.tsx) and the Ask result view check `response.error === "provider_below_quality_bar"` and render: "Verification requires a Claude API key. Open Settings to add yours." with a button that opens Settings. No model picker UI change in this PR.
5. **Regression test.** New test in `tests/test_tutor_provider_fallback.py`: `test_high_stakes_path_fails_loud_under_afm` asserts `ok=False`, `error="provider_below_quality_bar"`, no AFM call made (verify by `mock.patch` counter on `AFMClient.request_grounded_answer`).
6. **Sibling test for low-stakes pass-through.** `test_low_stakes_path_allows_afm` — pin `CARREL_AI_PROVIDER=afm`, exercise `notes_expand_service.expand_note_content` (or another non-tutor request_kind), assert the AFM call goes through.
7. **Update the Phase 1 reproduction test.** Remove `@unittest.expectedFailure` from `test_afm_path_produces_substantive_answer_or_documents_degradation`; the test now passes because the behavior is fail-loud rather than hollow-substantive.

### Documentation references

- Existing module-constant pattern: `NON_CITABLE_NODE_TYPES` at [services/retrieval/node_type_router.py](../../services/retrieval/node_type_router.py).
- Existing fail-closed pattern in tutor: `test_pro_tutor_fails_closed_on_null_provider` at [tests/test_tutor_grounded.py:534-587](../../tests/test_tutor_grounded.py).
- Frontend error-state pattern: existing empty-state rendering in [AskView.tsx](../../frontend/src/features/ask/AskView.tsx) (find by grep `response.error`).

### Verification checklist

- [ ] Full canonical verify chain per CLAUDE.md.
- [ ] New regression tests pass: `test_high_stakes_path_fails_loud_under_afm`, `test_low_stakes_path_allows_afm`.
- [ ] Phase 1 reproduction test now passes without `@unittest.expectedFailure`.
- [ ] Manual `curl -X POST http://localhost:8000/api/tutor/query -H 'Content-Type: application/json' -d '{"question":"x"}'` with `CARREL_AI_PROVIDER=afm` returns `{"ok": false, "error": "provider_below_quality_bar", ...}`.
- [ ] `corepack pnpm --dir frontend test` covers the new banner state in `AskView.test.tsx` and `VerifyView.test.tsx` (T59 was previously gated on this work; once T64 lands, T59 unpauses with a richer test scope).

### Anti-pattern guards

- Do NOT make the gate a runtime env var that can be turned off. The whole point is to enforce in the production binary. (Test override via `select_provider(kind="claude")` bypasses the gate naturally because `provider == "claude"`.)
- Do NOT use `getattr(provider, "kind", "unknown")` in the gate — every provider is required to expose `kind` per the Protocol; if a custom provider in a test omits it, fix the test, not the gate.
- Do NOT touch the `_GROUNDED_TUTOR_SYSTEM` prompt or `SUBMIT_GROUNDED_ANSWER_TOOL` definition. Out of scope.
- Do NOT add a "force allow" admin flag. The validation test demands consistency; an admin override would invite "let me just enable it for this demo" footgun.

### Phase exit

PR lands on `fix/t64-provider-quality-gate`. Manual smoke confirms fail-loud rendering. Original founder-diagnosed bug no longer reproduces.

---

## Phase 5 — Substantive-answer-rate metric in evals

Goal: a CI-grade metric that catches a future regression of the same family (hollow generator output).

### What to implement

1. **Metric definition.** A response is "substantive" when `len(answer.summary.strip())` exceeds `2 * max(len(citation.quote) for citation in all_citations)` AND the summary is not a verbatim prefix of any cited quote. Edge case: zero citations → metric defined as `1.0` (vacuously substantive — the failure mode being targeted is "non-empty answer that copies the heading," not "no answer at all," which is covered by the existing `ok=False` machinery).
2. **Compute it.** New function `_compute_substantive_answer_rate(answer: GroundedAnswer) -> float` in `evals/run_evals.py`, alongside `quote_validity` compute at [evals/run_evals.py:503](../../evals/run_evals.py). Return `1.0` or `0.0` per case; aggregate to a rate at the suite level (copy the `quote_valid_count / quote_total` pattern at [evals/run_evals.py:587](../../evals/run_evals.py)).
3. **Stratify by provider.** Bucket cases by `answer.provider`. Report per-provider rates: `substantive_answer_rate.claude`, `substantive_answer_rate.afm`, `substantive_answer_rate.ollama`. Overall rate is the aggregate across all buckets. Use the new `provider` field shipped in Phase 2.
4. **Threshold guard.** New check at [evals/run_evals.py:622+](../../evals/run_evals.py): if `substantive_answer_rate.claude < 0.95`, warn. AFM and Ollama do not have a threshold guard (they are now expected to short-circuit on high-stakes paths per Phase 4, so their substantive_answer_rate on those cases will be the vacuous-zero case; they may still surface in low-stakes evals).
5. **Summary table row.** New row in the markdown table at [evals/run_evals.py:656-663](../../evals/run_evals.py): `| substantive_answer_rate (claude) | {value} | {threshold note} |`.
6. **Mode availability.** Substantive-answer-rate is computed in **full mode only** (smoke is retrieval-only per CLAUDE.md and skips the answer generation). Mirror the `if mode == "smoke": return metrics` early-return pattern at [evals/run_evals.py:443-444](../../evals/run_evals.py).
7. **Eval cases.** No new eval fixtures needed; the existing `evals/cases/smoke.jsonl` + full set already exercise the answer surface. If full-mode case count is too low to give a meaningful rate (<10 cases on the Claude provider), add 3-5 new cases that specifically test for the hollow-answer failure mode (cases where the cited chunk has a strong heading that could be regurgitated).
8. **Regression test for the metric itself.** New test in `tests/test_evals_runner.py` mirroring an existing metric test (find by `grep "def test_.*metric\|def test_.*quote_validity" tests/test_evals_runner.py`). Stub a `GroundedAnswer` with a hollow summary and assert the metric returns 0.0; stub a substantive one and assert 1.0.

### Documentation references

- Metric compute pattern: `quote_validity` at [evals/run_evals.py:503](../../evals/run_evals.py).
- Threshold guard pattern: [evals/run_evals.py:622-625](../../evals/run_evals.py).
- Summary table format: [evals/run_evals.py:656-663](../../evals/run_evals.py).
- Test pattern: search `tests/test_evals_runner.py` for an existing `test_*` covering a single metric's compute, copy that shape.

### Verification checklist

- [ ] `./.venv/bin/python -m unittest tests.test_evals_runner -v` includes the new metric test.
- [ ] `./.venv/bin/python -m evals.run_evals --mode full` (with `ANTHROPIC_API_KEY` set) reports `substantive_answer_rate.claude` in the summary; value is `>= 0.95`.
- [ ] `./.venv/bin/python -m evals.run_evals --mode smoke` runs without computing the new metric (smoke stays retrieval-only).
- [ ] Comparison report under `evals/reports/compare-t64-*.md` shows the metric pre/post Phase 4 fix (pre: AFM rows have low substantive rate; post: AFM rows do not appear because the gate short-circuits before the AFM call).

### Anti-pattern guards

- Do NOT compute the metric in smoke mode. Smoke is retrieval-only per CLAUDE.md and the metric needs an `answer` object.
- Do NOT couple the metric definition to a specific provider's output shape. The metric reads `answer.summary` (a string), which every provider populates via the unified `GroundedAnswer` dataclass.
- Do NOT raise the existing `groundedness@8` / `quote_validity` thresholds in this PR. Out of scope; if the new metric exposes that those should change, surface as a follow-up task.

### Phase exit

PR lands on `feat/t64-substantive-answer-rate`. Comparison report committed.

---

## Phase 6 — Final verification

Goal: prove the bug is fixed and protected against recurrence.

### What to verify

1. Full canonical verify chain per CLAUDE.md:39-49 (all 12 lines, including the `swift test` line and the watchdog kill test).
2. New tests: `tests/test_tutor_provider_fallback.py` all green.
3. Full-mode evals report `substantive_answer_rate.claude >= 0.95` and no regression on `groundedness@8` (>= 0.70) or `quote_validity` (>= 0.95).
4. Manual smoke (operator-driven):
   - With `ANTHROPIC_API_KEY` set: open Ask, ask a question that requires synthesis ("Explain mitosis in your own words, citing the body text"), confirm the answer is substantive (more than 2x the cited heading length).
   - With `ANTHROPIC_API_KEY` unset and `CARREL_AI_PROVIDER=auto`: open Ask, ask the same question, confirm the banner appears: "Verification requires a Claude API key..." and no hollow answer is surfaced.
   - With `ANTHROPIC_API_KEY` unset and `CARREL_AI_PROVIDER=afm`: open Verify, paste a memo, confirm the same banner.
   - With `ANTHROPIC_API_KEY` unset and `CARREL_AI_PROVIDER=afm`: trigger a low-stakes flow (notes expand or flashcard generation), confirm it still works through AFM.
5. Anti-regression grep: `grep -rn "fallback.*provider\|silent.*fallback" services/tutor.py services/verify.py` returns no new instances introduced by this work.
6. Update `AUTONOMOUS_WORK_PLAN.md` T64 status to `done` with PR numbers + commit hashes.
7. Update T65 (validation test prep) dependency note to remove the T64 block.

### Phase exit

T64 is `done`. T59-T63 V2 polish queue can resume per ADR-0008 exit condition (1) or (2) once the validation test (T66) returns its verdict. T65 prep can start.

---

## Risks and counter-arguments held open

1. **What if the AFM diagnosis is wrong and there is ALSO a Claude prompt issue?** The Phase 1 reproduction test against Claude (via StubRouter with a real-shape payload) would surface that. If `test_claude_path_produces_substantive_answer` fails, Phase 4 expands to include a prompt-engineering sub-phase.
2. **What if the validation test reveals that litigators don't want fail-loud either, they want a fallback they understand?** Then Phase 3's policy decision is wrong and we revisit. The plan does not commit irreversible code paths; the gate is one helper function and can be inverted in a small follow-up PR.
3. **What if the new substantive_answer_rate metric is itself wrong (false positives on legitimately-short answers, false negatives on padded-but-hollow answers)?** The metric definition is deliberately conservative (length-based heuristic). If the V2 test surfaces metric drift, follow-up plan would replace the heuristic with a Selene-Mini judge per memory 8670 (Gate 2 backlog item).
4. **Cost of fail-loud for the operator's own dev workflow.** Operator likely keeps `ANTHROPIC_API_KEY` set in their environment, so day-to-day dev is unchanged. CI runs already pin the key. Test suites that exercise the AFM path explicitly pin `CARREL_AI_PROVIDER=afm` and now also pin a low-stakes `request_kind`, which is consistent with the new gate.

---

## Out of scope (do not let scope creep)

- Prompt engineering on the Claude `_GROUNDED_TUTOR_SYSTEM`. (Founder diagnosis rules this out.)
- New provider integration (Selene Mini, etc.). Tracked in TODOS.md Gate 2 backlog.
- UX redesign of the Settings page (where the user pastes their Claude API key). The new banner deep-links to whatever Settings is today.
- macOS Keychain for the API key. Tracked separately in CLAUDE.md "Open debts" and the paid-tier-infrastructure backlog plan.
- Changes to the AFM Swift sidecar. Out of scope; the policy is "do not call AFM for high-stakes" which side-steps any sidecar work.
