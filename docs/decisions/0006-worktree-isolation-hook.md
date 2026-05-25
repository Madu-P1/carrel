# ADR 0006 — Worktree isolation PreToolUse hook

- **Status:** Accepted
- **Date:** 2026-05-25
- **Owner:** Operator (autonomous routine safety)
- **Scope:** Carrel `/carrel-build` autonomous routine running in fleet
  worktrees under `/Users/madu/Desktop/Codex/.claude/worktrees/`.

## Context

The Carrel autonomous routine runs `/carrel-build` in git worktrees
(`.claude/worktrees/fleet-1/`, `.claude/worktrees/fleet-2/`) so multiple
slots can work in parallel without stepping on each other. Each slot
must keep all of its filesystem writes inside its own worktree.

On 2026-05-25 we observed a leak: slot 1 and slot 2 BOTH used Write/Edit
calls with ABSOLUTE PATHS pointing at the main repo at
`/Users/madu/Desktop/Codex/` instead of their own worktree paths.

- Slot 1 wrote `services/retrieval/quote_heuristics.py`, tests, and an
  eval report into MAIN. Those files showed up STAGED in main's index.
- Slot 2 wrote `docs/decisions/0005-...md` and
  `docs/plans/cross-platform-...md` into MAIN. Those files showed up
  UNTRACKED in main's working tree.

Root cause: the `Write` tool ignores CWD when given an absolute path; it
writes wherever the path points. The existing `audit-gate.py` hook only
fires on `MAJOR_FILE_PATTERNS` (manifests, migrations, CLAUDE.md, etc.)
and on major Bash verbs. Writes under `docs/decisions/`,
`services/retrieval/`, `tests/`, etc. don't match those patterns, so
they leak silently.

## Steelman of the counter-argument

The strongest opposing view: "Don't add another hook. Fix the routine's
prompt to always use relative paths. Hooks add latency on every tool
call, and the audit-gate is already there as a safety net."

It doesn't change my answer. Prompt-only fixes have failed before on
this exact failure mode (the operator has seen it twice in one
evening). The autonomous routine generates absolute paths from
training-data muscle memory; relying on prompts to forbid that is
exactly the kind of soft control we built audit-gate to replace.
Latency of a PreToolUse Python check is microseconds and there is no
network call. The hook is also OPT-IN via `CARREL_AUTONOMOUS=true` so
operator sessions see zero cost. Audit-gate is not a substitute: it
explicitly does not match new files in `docs/decisions/` or
`services/retrieval/`, which is exactly what leaked.

## Decision

Add a new PreToolUse hook at `.claude/hooks/worktree-isolation.py`
matching `Write|Edit|MultiEdit`. The hook:

1. No-ops unless `CARREL_AUTONOMOUS=true` (mirrors audit-gate and
   debate-trigger; ad-hoc operator sessions are not policed).
2. Reads `tool_input.file_path`, expands `~`, resolves against
   `CLAUDE_PROJECT_DIR` if relative, calls `.resolve(strict=False)`.
3. Allows if the resolved path is inside `CLAUDE_PROJECT_DIR` (the
   current worktree root).
4. Otherwise applies the allow-list. If still not allowed, returns a
   `permissionDecision: "deny"` with a reason that names the leak class
   (main-repo, sibling-worktree, or generic out-of-tree) and instructs
   the routine to use a path relative to CWD or prefixed with
   `$CLAUDE_PROJECT_DIR`.
5. Appends every block to
   `.claude/logs/worktree-isolation-blocks.jsonl`.

Settings registration uses a SECOND PreToolUse entry with matcher
`Write|Edit|MultiEdit`. We do not extend the existing
`Bash|Edit|Write` entry, both to keep the hook lifecycle independent
and because the existing entry would not match `MultiEdit`.

## Allow-list rationale

Writes outside the current worktree are sometimes legitimate. The hook
permits exactly these prefixes:

- `~/.agent-cockpit/` — cockpit user config (writes here are state
  shared across all worktrees by design).
- `~/.gstack/` — gstack analytics, project-state index, builder
  profile. Same reasoning: shared user state, not project content.
- `~/.claude/` — Claude Code user config.
- `/tmp/` and `/private/tmp/` — transient. The macOS subprocess layer
  reports `/tmp/foo` as `/private/tmp/foo` after `Path.resolve()`, so
  both prefixes are listed.

Sibling worktrees (`/Users/madu/Desktop/Codex/.claude/worktrees/<other-slot>/`)
are explicitly NOT on the allow-list. A slot writing into another
slot's worktree is the exact failure we are blocking; the hook
classifies that case as `sibling-worktree` for a clearer deny reason.

Deliberately NOT on the allow-list:

- `/var/folders/...` / `/private/var/folders/...` (macOS
  `NSTemporaryDirectory`). The autonomous routine has no business
  writing there. Test fixtures use `tempfile.mkdtemp()` against the
  evaluate function directly, which sidesteps the worktree check by
  using a synthetic worktree root inside the same tmp tree.

## Test strategy

`tests/test_worktree_isolation_hook.py` covers three layers:

1. **Pure function (`evaluate`):** 15 cases on synthetic worktree/sibling
   /main paths in `tempfile.TemporaryDirectory`. Confirms allows,
   blocks, MultiEdit handling, `~` expansion, relative-path resolution,
   relative-traversal blocking, empty `file_path` pass-through.
2. **Carrel layout:** uses the real
   `/Users/madu/Desktop/Codex/.claude/worktrees/fleet-{1,2}` paths
   (string-only; no on-disk dirs needed) to confirm the leak-class
   reason strings (`main-repo leak`, `sibling worktree leak`) match the
   actual deployment.
3. **Subprocess:** drives the hook script over stdin so the env-gate
   and `main()` flow are exercised end-to-end. Includes a no-op test
   when `CARREL_AUTONOMOUS` is unset, a block-and-log test, and a
   pass-through for non-matching tool names.

Run: `./.venv/bin/python -m unittest tests.test_worktree_isolation_hook -v`.
20/20 green at landing time.

## What this does NOT catch

- **Bash commands that move files.** A `cp /path/in/worktree/foo
  /path/in/main/bar` or `mv` evades this hook because it only matches
  `Write|Edit|MultiEdit`. The audit-gate still catches `git commit`,
  `git push`, `gh pr` style escalations on the destination side, but
  the file copy itself is unguarded. Mitigation: if Bash leaks become a
  pattern, extend with a Bash matcher and parse target paths from `cp`,
  `mv`, `rsync`, `install`, and shell redirects.
- **Symlinks.** A symlink inside the worktree pointing at a file in
  main would let an Edit write the main file. `Path.resolve()` follows
  symlinks, so the resolved path would land outside the worktree and
  the hook would block — but a symlink CREATED by Write inside the
  worktree on a non-existent target wouldn't trigger this hook for the
  create itself.
- **Reads.** This is a write isolation hook, not a read isolation hook.
  Cross-worktree reads are intentional (sharing eval reports, ADRs,
  etc.) and are not blocked.
- **Operator sessions.** The hook is gated on `CARREL_AUTONOMOUS=true`.
  An operator with that env unset can write anywhere. This is by
  design: the goal is to police the autonomous routine, not to add
  ergonomic friction.

## Rollout

- Hook ships as a working-tree change in this worktree. Operator
  reviews + commits.
- After commit, `CARREL_AUTONOMOUS=true` sessions (started via
  `script/start-autonomous.sh`) pick up the new hook automatically on
  next launch.
- First-week telemetry lives in
  `.claude/logs/worktree-isolation-blocks.jsonl`; review weekly for
  surprises.
