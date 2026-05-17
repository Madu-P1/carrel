# ADR-0005: install.sh detects AFM eligibility and defaults to AFM on eligible Macs

**Status:** Accepted (autonomous build, 2026-05-17)
**Branch:** `feat/afm-phase5-bundle-bridges`
**Driver:** AFM strategic bet from `docs/plans/afm-decision-brief-2026-05-11.md`; runbook Phase 6 in `docs/plans/afm-runbook-2026-05-10.md`.

## Context

After Phase 5 (commit `80f14fba`) bundled `EinsteinAFMBridge` into the `.app`, fresh installs that ran `curl | bash` without an `ANTHROPIC_API_KEY` still fell through to an Ollama-warn branch (`install.sh:298-309`) and never mentioned Apple Foundation Models. That is the opposite of the strategic positioning: "we use the LLM Apple ships with your Mac" only converts if eligible installs land on AFM by default at first launch.

Phase 6 of the runbook prescribes (a) detecting AFM eligibility (arm64 + macOS 26+ + en_US locale) before writing `.env`, (b) leaving `EINSTEIN_AI_PROVIDER=auto` on eligible Macs so `select_provider()` resolves to AFM, (c) optionally probing the bundled bridge after `swift build` and surfacing the specific `availability_state` when Apple Intelligence is disabled/downloading/ineligible.

## Adversarial debate

Proponent and adversary subagents ran in parallel with the runbook section 3 as the proposal. Both transcripts and the synthesizer verdict are summarised below; the full transcripts live in this session's chat record.

### Proponent — core case
- Patch surface is one file, ~30 new lines, with insertion points (`install.sh:67-72` macOS check; `:298-309` Ollama-default branches) already structurally aligned with the runbook.
- Sidecar protocol already speaks the runbook's vocabulary (`EinsteinAFMBridge/main.swift:328-358` returns `availability_state` in `{available, apple_intelligence_not_enabled, device_not_eligible, model_not_ready}`).
- Strategic asymmetry: without Phase 6, every eligible fresh install still gets an Ollama "tutor will refuse every question" warning at first run.
- Risk is bounded: non-eligible Macs fall through to today's Ollama branch unchanged.

### Adversary — strongest attacks
1. `EINSTEIN_AI_PROVIDER=auto` allegedly returns `NullProvider` when no Claude key — runbook prescription broken.
2. Phase 4.5 schema work (two-tier tool schema in `tutor.py`) never landed; AFM still emits visually-empty answers — sending fresh installs to AFM means regression.
3. Locale detection `[[ "$mac_locale" != "en_US" ]]` is brittle against `en_US@rg=*` / `en-US` BCP-47 variants.
4. AFM latency 10.1s p50 vs Sonnet 4s p50 means free-tier first-touch is materially worse.
5. Branch hygiene: branch already mixes PR-S/PR-D/PR-P + concurrency + bundles; CLAUDE.md mandates "independently shippable" PRs.
6. Coordination collision: two fresh autonomous-watchdog PIDs + parked Claude PID could race `install.sh`.
7. Premature optimization vs. user-facing open-debts in CLAUDE.md.

### Orchestrator verification (before synthesizer)
- **Claim 1 REFUTED.** `ai/providers.py:304-342` already implements `auto → Claude (with key) → AFM (when _afm_available()) → Ollama → NullProvider`. No `providers.py` patch needed.
- **Claim 2 FUNCTIONALLY REFUTED.** While literal "Phase 4.5" never landed, AFM has its own grounded-answer flow at `ai/afm_client.py:178-220` + `ai/afm_grounded.py` using Apple's `@Generable` constrained decoding. Commits `d867af74` + `9611e2bf` landed it end-to-end and bypass the nested-claims schema the decision brief flagged.
- Claims 3, 4, 5, 6, 7 stand as honest tradeoffs.

### Synthesizer verdict: PROCEED_WITH_AMENDMENTS (HIGH confidence)

The two killer adversary claims collapsed under code verification; remaining objections are amendable rather than blocking.

## Decision

Execute runbook Phase 6 on `feat/afm-phase5-bundle-bridges` with these mandatory amendments:

1. **Tolerant locale match.** Use regex `[[ "$mac_locale" =~ ^en[_-]US ]]`, not exact-string. Accepts `en_US`, `en-US`, `en_US@rg=*`.
2. **Architecture: arm64 only.** Reject `x86_64` even on macOS 26.
3. **Fail-closed probe.** If post-`swift build` availability returns anything other than `available`, fall through to existing Ollama-warn with the specific `availability_state` echoed in `AFM_REASON`. Do not silently force `provider=afm`.
4. **Wrap, don't rewrite.** Existing Ollama-default branches at `install.sh:298-302` and `:307-311` must be byte-identical inside the `else` arms.
5. **Default to `EINSTEIN_AI_PROVIDER=auto`, not `afm`.** The verified `providers.py:304-342` resolves auto → AFM correctly; hardcoding `afm` removes the Claude-key escape hatch for users who later add a key.
6. **Reconcile watchdogs.** Before writing, confirm no parallel session has `install.sh` claimed (verified empty in `.claude/logs/audits/pending/`).
7. **Commit message must cite `providers.py:304-342` + `afm_grounded.py`** so reviewers see why auto-resolution and grounded answers are not regressions.

## Consequences

**Positive:**
- Eligible Macs (arm64 + macOS 26+ + en[-_]US) land on AFM at first launch with zero manual setup; the strategic "LLM Apple ships with your Mac" pitch becomes truth at install time.
- Ineligible Macs continue today's Ollama-warn behavior unchanged.
- `availability_state` probe surfaces Apple-Intelligence-disabled / model-downloading reasons in the install transcript instead of silent fallback.

**Negative / open:**
- Free-tier first-token latency (~10s p50 for grounded answers, per decision brief) is materially worse than paid Claude (~4s p50). Acceptable for free tier; revisit if telemetry shows abandonment.
- `install.sh` accretes more complexity; opportunity for refactor when next person touches it.
- Locale matching covers the common cases but is not BCP-47-complete; a user with a custom `en_GB@rg=uszzzz` would still be classified ineligible. Acceptable for current release.

## References

- `/Users/madu/Desktop/Codex/install.sh` (patch target; lines 67-72, 298-302, 307-311)
- `/Users/madu/Desktop/Codex/ai/providers.py:304-342` (verified auto-resolution)
- `/Users/madu/Desktop/Codex/ai/afm_grounded.py` (verified `@Generable` grounded path)
- `/Users/madu/Desktop/Codex/ai/afm_client.py:178-220` (`request_grounded_answer`)
- `/Users/madu/Desktop/Codex/macos-app/Sources/EinsteinAFMBridge/main.swift:328-358` (availability protocol)
- `/Users/madu/Desktop/Codex/ai/native_bridge_paths.py` (`CARREL_BUNDLE_MACOS` bundle discovery)
- `/Users/madu/Desktop/Codex/docs/plans/afm-runbook-2026-05-10.md` (Phase 6 spec; sections 3.1-3.4)
- `/Users/madu/Desktop/Codex/docs/plans/afm-decision-brief-2026-05-11.md` (strategic AFM bet)
