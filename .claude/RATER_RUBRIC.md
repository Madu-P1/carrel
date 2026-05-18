# Quality-Rater Rubric (100 points)

> Used by the `quality-rater` subagent spawned by `.claude/hooks/score-loop.py` after each autonomous-loop task completes. The rater writes JSON to `.claude/logs/scores/{task}-{ts}.json` with `total: <int>` and per-criterion breakdown. The loop iterates until `total == 100` or the session nudge cap (25) is hit.

## 100-point breakdown

### Criterion A — Acceptance criteria met (25 points)

Read the task's `**Acceptance:**` line in `AUTONOMOUS_WORK_PLAN.md`. For each clause:
- All clauses verified true via inspection of the diff + verify-chain output: **25**.
- All structural clauses true, one or more empirical clauses unverified (e.g., eval bar not actually run): **18**.
- Partial coverage of acceptance (e.g., backend done, frontend skipped): **12**.
- Substantive miss (acceptance criterion materially unmet): **0**.

### Criterion B — Canonical verify chain green (25 points)

From `CLAUDE.md` §"Verify chain" lines 39-49. Each step gates a fraction:
- `./script/generate-api-types.sh`: 1 pt
- `pnpm typecheck`: 3 pts
- `pnpm lint`: 2 pts
- `pnpm test` (vitest): 4 pts
- `pnpm build:macos`: 2 pts
- `ruff check ...`: 3 pts
- `ruff format --check ...` (added 2026-05-18): 3 pts
- canonical `python -m unittest ...` suite: 4 pts
- `./script/build_and_run.sh --verify`: 2 pts
- `python -m benchmarks.phase0 --fail-on-regression`: 1 pt

Sum = 25. Any step red drops its full points to zero.

### Criterion C — PR opened with task-aligned description (20 points)

- PR exists, title matches task title format `<type>(<scope>): <short>` per Carrel commit convention: **5**
- PR body cites the task ID (e.g., "Closes T07 of AUTONOMOUS_WORK_PLAN.md"): **5**
- PR body has a verifiable test-plan or verify-chain summary: **5**
- PR target branch is `main` (not a stacked branch — we learned that stacked PRs auto-close on parent squash): **5**

### Criterion D — No anti-pattern violations (15 points)

From `CLAUDE.md` "Conventions" + `docs/plans/everything-to-100-2026-05-17.md` Phase 0 §0.2 + task `**Guards:**`. Each violation drops 5 points:
- Em dashes in PR / commit / product copy.
- Silent AI fallback (provider returns ok=False but tutor proceeds with empty/heuristic).
- `dangerouslySetInnerHTML` introduced.
- New `services/jobs/` or `services/anchors/` package (flat module convention).
- `ALTER TABLE` at startup (migrations are source of truth).
- New write to chunks table after Phase 5 (`T15`) lands.
- New runtime motion library (CSS + WAAPI only).
- New `ENTRY_JS_GZIP_BUDGET` exceeded without bump + justification.
- Schema change without a corresponding migration file in `migrations/`.

### Criterion E — Tests added (10 points)

- Task introduces a functional change AND adds at least one matching unit test: **10**
- Task is a refactor without functional change: **10** (no new test required if existing tests cover the surface).
- Task adds functional change but no new test: **0**.
- Task changes API shape but doesn't update at least one integration / type test: **0**.

### Criterion F — Documentation kept in sync (5 points)

- Master plan / AUTONOMOUS_WORK_PLAN status block updated to `done`: **3**.
- CLAUDE.md / DESIGN.md / HANDOFF.md updated when the task changes a project-wide convention: **2** (skip if no convention shift).

## Total

Sum A+B+C+D+E+F. Maximum 100.

## Iterative scoring

When the rater scores below 100, it MUST write the per-criterion breakdown and one concrete fix-up suggestion per missed criterion. The loop then iterates: Claude reads the rater output, applies the fixes, re-spawns rater. Cap at 25 iterations per task (the score-loop hook's `MAX_NUDGES_PER_SESSION`).

## Audit checklist (separate from the rubric)

`.claude/hooks/audit-gate.py` denies major actions (commit / push / migration / dependency change) until an auditor subagent writes an approval file. The auditor's approval JSON must include:

```json
{
  "goal": "task short description",
  "diff_summary": "files changed + key behavior delta",
  "success_criteria": "the acceptance line from the WORK PLAN, verbatim",
  "rollback_plan": "one-sentence revert path (for destructive actions)",
  "what_would_make_this_not_necessary": "honest answer (for destructive only)"
}
```

For non-destructive `major` actions: only `goal`, `diff_summary`, `success_criteria` are required.
For `destructive` actions: all five fields. Missing fields = the gate stays denied.

## Special cases

- **A task that lands no code** (e.g., T56 final verification): Criteria A + B + C + F. Skip D + E. Max 75 (scale to 100 by ×4/3 or accept 75 as the cap).
- **A task that fails the canonical verify chain but otherwise meets acceptance**: Criterion B drops to zero on the failing step; cap at the resulting total. Do NOT lower B's gate.
- **Rater disagreement with task author**: rater's score wins. If author thinks rubric is wrong, author updates this file in a follow-up PR.

---

*Last updated 2026-05-18. Used by score-loop hook + auditor subagent.*
