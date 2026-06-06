# Cachet engine build — session handoff (2026-06-06)

Read this first, then start. It is self-contained: you do not need the prior chat.

## First move (TL;DR)

Build the **T0 completion**: wire the anchor detectors that are merged but unconsumed, and make the deterministic engine actually run on the Cachet surface. The **T1 recall tier (ADR-0012) is deferred** because it is blocked on a labeled corpus that does not exist yet. Start with PR-1 below.

```
git worktree add -b feat/anchors-consume-defined-term \
  /Users/madu/Desktop/Codex/.claude/worktrees/consume-defined-term origin/main
```

## Current state (ground truth, verified 2026-06-06)

- `main` at `7cacdba64`, synced. **117 engine tests green** on main.
- Deterministic engine on main: `#115` (envelope), `#122` merged (party / defined-term / overlap-guard detectors), `#123` open draft (section-sign `§`).
- **Open PRs:** `#123` (section-sign → `main`, additive, ready once CI greens — **merge it first**, it is part of the detector set you are about to consume); `#121` (animated CachetMark → `cachet-extraction-p3`, stacked, independent of engine work).
- `dreamy-pascal` retired; its value is on main + a bundle at `~/Desktop/Cachet-archives/`.
- **Uncommitted in this checkout (the next session inherits these):** `docs/adr/ADR-0012-two-tier-verification-selection.md` (the decision driving this build — read it), this handoff, plus local scratch (`.claude/launch.json`, `CACHET-SHELL-HANDOFF.md`, `cachet-landing/.gitignore`). If the build session is a fresh clone, commit ADR-0012 + this file first.

## The decision driving the build: ADR-0012

Full text: [`docs/adr/ADR-0012-two-tier-verification-selection.md`](docs/adr/ADR-0012-two-tier-verification-selection.md). Essentials:

- Selection is **two tiers**: **T0** deterministic anchors (precision spine, *verified*) + **T1** local discriminative model (recall, *assessed N%*, corpus-gated) + cloud LLM off.
- **T1 is corpus-blocked** (needs a labeled legal held-out set that does not exist) → **not this session**. This session builds T0 completion + engagement.
- **Invariants (hold these even in T0 work):** never label a non-deterministic result deterministic; no coverage-by-guessing (below-confidence → the tray, never a verdict); the 3-state tray (`verified` / `contradicted-or-not-found` / `could-not-check`) stays; no generation (the P6 "never build generation" line stands — discriminative only); no cloud on the default path.

## What to build this session (prioritized, sliced, test-gated, additive)

Each is its own small PR off current `main`, keeps the verify chain green, independently shippable.

**PR-1 — Consume `defined_term` (kill the dead code).** `build_alias_table` ([anchors.py:165](services/legal/anchors.py)) exists and is tested but is **never called in production**: `build_deterministic_envelope` calls bare `extract_anchors(sentence)` and never passes `alias_table=`. Build the alias table from the source document at the contract path, pass it through, and emit/consume `defined_term` anchors (a draft sentence using a defined term is checked against the contract's own definition). Clear-cut; no product decision needed.

**PR-2 — Consume `party` and `section` (needs one product decision each).** Both are detected ([anchors.py:157, _SECTION](services/legal/anchors.py)) but reach no verdict. Decide what "verify a party" means (party named in the draft is one of the executed parties in the source?) and whether a `§ N` ref should be independently verified (does that section exist in the source?). Wire to a verdict once scoped. **Operator decision needed before coding** (see "What I need from you").

**PR-3 — Make the engine engage by default on the Cachet surface.** This is the single biggest gap (from the Vulcan read): `CACHET_DETERMINISTIC_VERIFY` is read in 3 places and **set by nothing in production**, so a clean `main` runs the LLM path. The `serve-cachet.py` that was meant to set it is not on main. Reconcile with the localhost-delivery work and make the deterministic path the default for the `CACHET_ONLY` / Cachet delivery surface. After this, the product actually does what the engine can do.

**PR-4 — Refactor: promote `_serialize_case_verdict` out of `services.tutor`.** The deterministic core imports a private symbol from the LLM module ([deterministic_envelope.py:41](services/legal/deterministic_envelope.py)). Move the shared serializer to a neutral module both paths import. Low-risk, decouples the clean core from the LLM stack, aids the ADR-0011 extraction.

Deferred (not this session): the `_values_match` multi-value masking ([contract_verify.py:48](services/legal/contract_verify.py)) — put on the contract-wedge risk register; it silently under-reports on real multi-value clauses but the fix needs role-alignment. The double `extract_anchors` on the claim sentence — minor, ignore.

## The engine as it stands (the Vulcan read)

**Strong (do not "improve"):** deep modules (`build_deterministic_envelope` is the orchestrator); why-comments that carry the real reasoning; offline-by-construction case existence (the local caselaw client is the injected floor, not an env toggle); the honest 3-state model encoded structurally; one shared wire contract for both paths. Resist splitting the per-sentence dual-path loop — it is cohesive, not a smell.

**Debts (this session closes 1-3):** (1) flag dormant by default [PR-3]; (2) party/defined_term/section detected-but-unconsumed, `build_alias_table` dead [PR-1/2]; (3) clean core imports a tutor private [PR-4]; (4) `_values_match` multi-value masking [risk register]; (5) double anchor extraction [ignore].

## Where the code lives

| File | Role |
|---|---|
| [services/legal/deterministic_envelope.py](services/legal/deterministic_envelope.py) | `build_deterministic_envelope` — the orchestrator (litigator + contract paths) |
| [services/legal/anchors.py](services/legal/anchors.py) | `extract_anchors` (9 types), `build_alias_table` |
| [services/legal/contract_verify.py](services/legal/contract_verify.py) | `verify_claim_against_clause` (parametric contradiction) |
| [services/verify.py](services/verify.py) | the `CACHET_DETERMINISTIC_VERIFY` swap (non-stream + stream) + verdict mapping |
| [docs/notes/2026-06-05-cachet-deterministic-extraction.md](docs/notes/2026-06-05-cachet-deterministic-extraction.md) | the "extract by anchor" design + the ~25-35% coverage reality + the anchor taxonomy |
| [docs/adr/ADR-0012-two-tier-verification-selection.md](docs/adr/ADR-0012-two-tier-verification-selection.md) | this build's governing decision |

## How to work (gotchas — read before touching anything)

- **Branch off current `origin/main` (`7cacdba64`).** It has the calendar date-bomb fix, so CI is clean. CI runs `on: push:` **unfiltered**, so it fires on every branch push — only push **active** feature branches, never archive branches (they trigger failing CI on the old date-bomb + a `cachet-landing` Vercel build).
- **Worktrees have no `.venv`.** Run Python tests with the main checkout's interpreter: `/Users/madu/Desktop/Codex/.venv/bin/python -m unittest tests.test_anchors ...`. For frontend, `corepack pnpm install` per worktree is ~2s.
- **Relevant test suites for engine work:** `tests.test_anchors tests.test_deterministic_envelope tests.test_contract_verify tests.test_contract_verify_integration tests.test_citations_eyecite tests.test_zero_egress tests.test_local_caselaw tests.test_legal_sentences`. Plus `ruff check` + `ruff format --check`. The full verify chain is in `CLAUDE.md`; run it before merge.
- **Keep the T0 path offline by construction.** No new network on the deterministic path. `tests.test_zero_egress` bans `socket.socket` and must stay green.
- **Use worktree-relative paths** when working in a worktree; `CLAUDE.md`'s absolute `/Users/.../Codex/...` paths are the MAIN checkout, and the worktree-isolation hook does not block out-of-tree edits.
- **No co-author footers, no em dashes, draft PRs by default** (project convention).

## What I need from you (operator) at session start

1. **PR-2 product decisions:** what does "verify a party anchor" mean, and should a bare `§ N` be independently verified against the source? (Needed before wiring party/section.)
2. **Whether to commit ADR-0012 + this handoff** so a fresh-clone build session sees them (recommend yes).
3. **Not yet, but on deck:** ADR-0012's open Q1 — the labeled calibration corpus — is the real gate for the T1 recall tier. It is a data task on the critical path, needed only when T1 starts, not this session.
