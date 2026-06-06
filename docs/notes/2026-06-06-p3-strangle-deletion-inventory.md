# P3 strangle: deletion-safety inventory for PR #119

Date: 2026-06-06. Scope: the operator-led P3 phase of the Cachet extraction
(ADR-0011, plan `docs/plans/cachet-extraction-2026-06-05.md`, both on branch
`cachet-extraction`). This note is the grep-before-delete safety gate the plan
requires, run against the existing P3 draft so the deletion can be approved (or
re-cut) from facts, not vibes. It does not delete anything; deletion stays the
operator's call (Chesterton's Fence).

## What PR #119 is

[PR #119](https://github.com/Madu-P1/carrel/pull/119) (`cachet-extraction-p3` ->
`cachet-extraction-p2`) is a pure-deletion draft: `+0/-3391` across 21 files. It
strangles the study-app **backend** in one bundle (the plan suggested one
leaf-first slice per PR; #119 batched the backend). It deletes:

- Routes: `ask_cards`, `concepts`, `dashboard`, `events`, `evidence`, `exports`,
  `onboarding`, `reader_nodes`, `studio`, `synthesis`, plus the `routes/__init__.py`
  registrations and a `ci.yml` line.
- Services: `dashboard.py`, `evidence_resolution.py`, `synthesis.py`.
- Tests: `test_ask_cards`, `test_ask_pipeline_stage3`, `test_dashboard_session`,
  `test_einstein_tutor`, `test_reader_nodes`, `test_usage_events`.

## Method

Grep-before-delete, per the plan's operating rule 3 ("remove only when nothing in
the verify path imports it"). For each deleted module, find inbound imports across
the repo and classify the importer as also-deleted (safe), verify-spine (blocker),
or surviving-non-spine (needs handling). Verified against the `cachet-extraction-p3`
branch, not just main.

## Finding 1 (the headline): the verification spine is untouched

The Cachet gem imports **none** of the deleted modules. Grep of
`routes/verify.py`, `services/verify.py`, `services/legal/**`, and
`services/tutor.py` for any deleted route/service module name returns nothing but
SQL table references (`FROM concepts`), which are database tables dropped later in
P4, not Python imports. **The deletion does not touch the product.** This is the
core reassurance: P3 removes baggage, not the engine.

## Finding 2 (blocker): a KEEP-set file imports a deleted service

`routes/workspace.py:163` (on `cachet-extraction-p3`) still does
`from services.dashboard import ACTIVE_SESSION_MAX_AGE_HOURS`, and #119 deletes
`services/dashboard.py`. `routes/workspace.py` is **not** deleted; it is registered
even under `CACHET_ONLY` (it hosts `/api/health` alongside the workspace/srs
routes, per `routes/__init__.py`), so it is effectively KEEP set.

- Severity: the import is function-level (lazy), so the app still **starts**; the
  failure is a runtime `ImportError` -> 500 on the workspace endpoint that reads
  `ACTIVE_SESSION_MAX_AGE_HOURS`. The test that would have caught it
  (`test_dashboard_session.py`) is deleted in the same PR, so CI would not flag it.
- Fix (fold into the slice): inline the constant into `routes/workspace.py` (it is a
  single dormancy-window number), or delete the dependent endpoint if it is itself
  study-app baggage. Either keeps the slice verify-green.

## Finding 3 (orphan): a deleted route leaves its service behind

`services/onboarding.py` survives #119, but its only importer
(`routes/onboarding.py`) is deleted, leaving it dead. Not a break, but the plan is
leaf-first (delete the service after its route); sweep `services/onboarding.py` in
the same slice so the strangle does not leave orphans.

## Finding 4 (blocker): the stack is stale

`cachet-extraction-p3` is **19 commits behind main** (merge-base `328de0aaf`, main
HEAD `2ecff4138`). It predates T0 completion (#125), all of T1 Phase A (#130-#134),
and the two PRs from 2026-06-06 (#135 T1 dark-path, #136 contract multi-value).
Those touched the exact verify path P3 strangles around. The stack cannot land as
is; it must be rebased onto current main or re-cut.

## Recommendation

The deletion is conceptually safe for the spine (Finding 1), so P3 is worth
finishing. But given Findings 2 and 4, do not merge #119 as is. Two options:

1. **Re-cut P3 as fresh leaf-first slices off current main.** Cleaner than
   rebasing 14 commits of pure deletion across a 19-commit drift, and it lets each
   slice run the *current* verify chain (with T0/T1 present). Fold in the Finding 2
   constant inline and the Finding 3 orphan sweep. Recommended.
2. **Rebase the stack** (`cachet-extraction-p2` then `-p3`) onto main, resolve the
   verify-path conflicts, then apply the Finding 2/3 fixes.

Either way the gates stay: characterization net green first, grep-before-delete per
slice (this note is slice 1's grep), verify chain green after each slice, every
slice independently revertable. P4 (schema drop) and P5 (rename) remain the only
one-way doors and stay operator-gated and checkpoint-first.

## What stays KEEP in P3 (never delete)

Per the plan: `routes/verify.py`, the grounding seam, `services/verify.py`,
`services/legal/**` (the deterministic engine, T0 + T1), `services/tutor.py` as the
grounding substrate, and `routes/workspace.py` (it hosts `/api/health`). Finding 2
is precisely a KEEP-set file depending on a delete-set file, which is why it must be
resolved inside the slice rather than deferred.
