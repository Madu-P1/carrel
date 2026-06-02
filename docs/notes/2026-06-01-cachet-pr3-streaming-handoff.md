# Cachet PR3 (honest streaming verify) — handoff

Date: 2026-06-01
Branch: `cachet/pr3-streaming` (off `main` @ `05884617`, which already has PR1+PR2)
Status: **code complete; backend fully verified green; frontend written + partially verified.
NOT committed, NOT pushed.** Stopped per operator's "full handoff for roomy machine" call
after this box hit its memory wall (~60MB free; vitest/build/Read/Bash started returning empty).

This implements PR3 of the locked plan `docs/plans/cachet-verify-port-2026-05-29.md`:
real per-cite "labor" streaming for the Verify surface via an extract-generator refactor +
SSE, so a litigator watches each citation get checked instead of staring at a spinner.

## Why resume on a roomy machine
This machine (~60MB free RAM) OOM-kills vitest/vite/tsc mid-run and the Bash/Read tools
start returning empty. The remaining work (full verify chain + `evals-full` + a clean
re-run of the frontend suite) needs an env where those actually execute. Also required:
**`ANTHROPIC_API_KEY` is currently absent from `/Users/madu/Desktop/Codex/.env`** (and
`COURTLISTENER_API_TOKEN`), so `evals-full` and any live `/api/verify/stream` call cannot
run until a key is present. Both keys missing was confirmed this session.

## Design (how the real engine differs from the plan's A1 pseudocode)
The plan assumed a per-cite loop in the envelope. Reality: the grounded answer is ONE atomic
LLM call (claims arrive together), and the genuinely slow, sequential work (CourtListener
existence + per-hit holding-match LLM call) lives in `verify_claims_for_cases()` in
`services/legal/case_verification.py` (a `for index, raw_text in enumerate(claim_texts)` loop).
That loop is the streamable unit. So the honest event sequence is:
`progress(extracting)` -> (atomic LLM) -> `claims` (skeleton, NO case verdicts) ->
`cite_verdict` per claim as each resolves -> `result` (canonical envelope).

Every layer is generator + thin drain-wrapper, so the non-stream public contract is
byte-identical (the regression net is the existing test battery + evals-full).

**Decision (not in the plan, recorded here):** case-verdict attachment was MOVED from inside
`grounded_tutor_response` up into the envelope (`grounded_tutor_envelope_steps`). Justified
because `grep` proved nothing reads `case_verdicts` off `grounded_tutor_response` directly —
`evals/run_evals.py:446` only uses `claims[].citations[].node_id` + quote text; the only
`case_verdicts` test reads go through `_attach_case_verdicts` directly (still intact). This
kept the diff small (no 237-line generator-ization of `grounded_tutor_response`). Ask
(`routes/tutor.py::tutor_query`) and Verify both flow through the envelope, so both keep verdicts.

## Files changed (all on `cachet/pr3-streaming`, uncommitted)
Backend:
- `services/legal/case_verification.py` — NEW `verify_claims_for_cases_steps()` generator;
  `verify_claims_for_cases()` is now `list(...)` drain. + `Iterator` import.
- `services/tutor.py` — NEW `_attach_case_verdicts_steps()`, `_unique_cited_ids()`,
  `grounded_tutor_envelope_steps()`; `_attach_case_verdicts()` and `grounded_tutor_envelope()`
  are thin drains; removed the now-unused `verify_claims_for_cases` import; `Iterator` import;
  dropped the `_attach_case_verdicts(answer)` call inside `grounded_tutor_response` (moved up).
- `services/verify.py` — NEW `verify_draft_stream()` generator + shared
  `_verify_result_from_envelope()` + `_verdict_card_to_dict()`; `verify_draft()` reuses the
  shared mapper; `Iterator` import.
- `routes/verify.py` — NEW `POST /api/verify/stream` (FastAPI StreamingResponse, SSE,
  `data: {json}\n\n` + `data: [DONE]`, `Cache-Control: no-cache, no-transform` +
  `X-Accel-Buffering: no`, error event on exception). `POST /api/verify` untouched.
- `tests/test_verify_stream.py` — NEW. Event-sequence, claims-skeleton-has-no-case-verdicts,
  cite_verdict passthrough, final-result-matches-non-stream, empty-draft, **dropped-stream-
  emits-no-result** (the critical invariant #6 test), + SSE route happy + error-no-result.

Frontend:
- `frontend/src/services/api/endpoints.ts` — `import { streamSse }`; NEW `VerifyStreamEvent`
  union; NEW `verify.draftStream()`.
- `frontend/src/features/verify/streamProgress.ts` — NEW pure reducer
  (`initialStreamState`/`reduceStreamEvent`/`isCardChecking`/`checkedProgress`). This is the
  single tested home of the safety rule: a claim with no cite_verdict and no result is
  "checking", never a pass.
- `frontend/src/features/verify/streamProgress.test.ts` — NEW, 10 tests incl. 3 invariant-#6.
- `frontend/src/features/verify/VerifyView.tsx` — `submit` now consumes `draftStream` with an
  AbortController; `response` is set ONLY from the `result` event (settled render byte-identical
  to before); live working-indicator + per-card "Checking…" while streaming; dropped-stream
  (no result) surfaces a "did not finish… nothing marked supported" error.
- `frontend/src/features/verify/VerifyView.module.css` — NEW `.badgeChecking`,
  `.verdictCardChecking`, `.workingIndicator`, `.workingLabel` (using the real verify-scope
  tokens: `--text-*`, `--surface-1`, `--hairline`, `--verify-flag`; NO new oxblood on checking).
- `frontend/tests/support/mockFetch.ts` — NEW `sseResponse()` + `mockSse()` helpers.
- `frontend/tests/features/verify-view.test.tsx` — all 6 existing tests migrated from
  `mockJson("POST","/api/verify",X)` to `mockVerifyStream(X)` (via `streamEventsFor`); + NEW
  7th test for the dropped-stream UI behavior.
- `frontend/src/services/api/types.gen.ts` — regenerated; +62 lines for `/api/verify/stream`
  (expected — FastAPI infers the op from request body + 200 even without response_model).

## Verified GREEN this session (clean tool output observed)
- Python: `py_compile` of all 4 backend files OK.
- Python: `python -m unittest tests.test_verify_stream tests.test_verify tests.test_tutor_grounded
  tests.test_legal_case_verification` = **76 passed** (also earlier full selection). The
  76-pass run IS the identical-output regression guard for the envelope/attach refactor.
- Python: `ruff check` + `ruff format --check` on all changed files = clean.
- Frontend: `streamProgress.test.ts` = **10/10 passed**.
- Frontend: `verify-view.test.tsx` (the 6 migrated tests) = **6/6 passed**; 0 leftover
  `mockJson("POST","/api/verify")`.
- Frontend: `endpoints.ts` + `streamProgress.ts` typecheck was green at an intermediate point.

## ONE KNOWN FAILING TEST (real bug, diagnose first on the roomy machine)
After migrating all 6 verify-view tests to SSE + adding the 7th (dropped-stream), the suite is
**16 passed / 1 failed** (`vitest run tests/features/verify-view.test.tsx
src/features/verify/streamProgress.test.ts`). streamProgress = 10/10. The failure:

  `verify-view.test.tsx > "View source opens the side-by-side inspector with the resolved
   span and shows no score"` — after `submitDraft` + clicking "View source", the resolved
   span `/ATP is produced by the mitochondria/` never appears (it queries `/api/evidence/resolve`).

The settled DOM renders correctly (the "Supported" card + "View source (1)" button are present
in the failure dump), so the regression is in the post-click inspector path under streaming,
NOT in the verdict render. Most likely cause to check FIRST: the `SourceInspector` open path
depends on `selectedItem`, which is derived from `items` (built from `response`). Under the new
flow `response` is set on the `result` event — confirm there isn't an async-timing gap where the
click lands before `response`/`items` settle, OR that the migrated test's single `cite_verdict`
+ `result` sequence actually drives `/api/evidence/resolve` the same way the old atomic path did.
This is the ONE thing to fix before the suite is green; do not push until it is. (I did not
hand-fix it blind under memory pressure — it needs a real look at SourceInspector's open path.)

This failing test is ALSO the proof the other 16 (incl. all 3 invariant-#6 safety tests) genuinely pass.

## NOT yet verified — DO THESE ON THE ROOMY MACHINE (in order)
1. **Frontend typecheck** — was RED on `Spinner size={12|14}` (union is `16|20|24`); FIXED to
   `16` in source but NOT re-run. Run `corepack pnpm --dir frontend typecheck` first.
2. **The 7th verify-view test (dropped-stream)** — written, its run result was unread (box died
   mid-run). Re-run `vitest run tests/features/verify-view.test.tsx` (expect 7 passed).
3. **Frontend lint** — passed earlier but re-run after the final edits.
4. **`build:macos`** — was RED on the same spinner-size error; re-run.
5. **Full Python battery** — only the 4 relevant suites ran; run the full CLAUDE.md list.
6. **`evals-full`** — the heavy gate the operator explicitly required. NEEDS
   `ANTHROPIC_API_KEY` in `.env`. Must hold `groundedness@8 >= 0.7` and `quote_validity >= 0.95`.
   (`python -m evals.run_evals --mode full`.)
7. **Adversarial Workflow review** (the proven PR1/PR2 driver: parallel lenses —
   contract-fidelity / streaming-correctness / dropped-stream-safety / test-adversary /
   a11y-of-progress / security — each finding skeptically verified). Then fix or defer-with-reason.
8. **Commit + push DRAFT PR** base `main` (default draft per CLAUDE.md; do not `gh pr ready`).
   Title: `feat(verify): honest streaming verify (extract-generator + SSE) — Cachet PR3`.
   Commit body must note: no em dashes; no "Generated with Claude" footer (Carrel convention).
9. **Visual check** on the Vite dev server (Claude_Preview MCP worked here last session via a
   throwaway harness): confirm the "Checking…" pills + working indicator look right and the
   verdict stays still (DESIGN.md: motion only on the working indicator, never on a verdict).

## Invariant #6 (the one disqualifying behavior) — how it's enforced
A dropped/truncated stream must NEVER read as a pass. Enforced in BOTH layers:
- Backend: `verify_draft_stream` never pre-emits a resolved verdict; the claims skeleton
  carries empty `case_verdicts`; the result event only fires after the full drain. Test:
  `test_verify_stream.py::test_dropped_stream_emits_no_result`.
- Frontend: `isCardChecking` keeps an un-resolved card in "Checking…" (never "Supported"),
  `response` is set only on `result`, and a stream that ends without `result` shows a finish
  error. Tests: `streamProgress.test.ts` (3 invariant tests) + the 7th verify-view test.

## Tooling note for the next session
RTK's `PreToolUse: Bash` hook was removed from `~/.claude/settings.json` this session (it was
splicing instruction-shaped garbage into Bash output). See memory `rtk-bash-hook-corruption.md`.
The claude-mem `Read`-to-line-1 truncation is still active (harmless; workaround =
`awk`/`cp` to a fresh `/tmp` path and Read that). Neither is a blocker on a roomy box.
