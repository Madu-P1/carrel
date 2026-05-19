---
description: Boot the full autonomous Carrel build routine for one unattended work session.
allowed-tools: Read, Edit, Write, Bash, Agent, Skill, TodoWrite, Grep, Glob
---

# /carrel-build

Boot the autonomous Carrel build routine. This is the entry point for unattended overnight work on the Carrel macOS study app at `/Users/madu/Desktop/Codex`.

## Preflight: mandatory, before any code

Run these in parallel:

1. `cd /Users/madu/Desktop/Codex && git status --short` to confirm clean working tree
2. `cd /Users/madu/Desktop/Codex && git log --oneline -5` to anchor recent state
3. `cd /Users/madu/Desktop/Codex && git branch --show-current` to confirm not on main
4. Read `/Users/madu/Desktop/Codex/CLAUDE.md`, `/Users/madu/Desktop/Codex/AUTONOMOUS_WORK_PLAN.md` (canonical task queue), `/Users/madu/Desktop/Codex/.claude/RATER_RUBRIC.md` (100-point rubric), `/Users/madu/Desktop/Codex/.claude/AUTONOMOUS_SCOPE.md` (in-scope vs out-of-scope), `/Users/madu/Desktop/Codex/TODOS.md`, the latest plan in `/Users/madu/Desktop/Codex/docs/plans/`
5. `export CARREL_AUTONOMOUS=true` so the hooks activate

Halt and ask the operator if any of:
- current branch is `main` or `master`
- the most recent plan is older than 14 days (stale plan signals stale intent)
- working tree is dirty AND the dirty files do not share a directory or feature with the most recent commit (ambiguous in-flight state)

If the working tree is dirty but the dirty files clearly continue a recent commit's PR theme OR a current plan task's scope, do NOT halt. Instead:

1. Run `git diff --name-only` to list modified paths.
2. Run `git log -3 --format='%h %s'` to read the last three commit subjects, AND read the active plan file (most recent file under `docs/plans/`) to see what the next task is.
3. Match the modified paths against (a) any of the last 3 commits' touched directories, OR (b) the next plan task's named scope (e.g., "PR 6.2 touches StudyView.tsx and usage_events.py"). A match on either is sufficient.
4. If multiple distinct file groups are dirty (e.g., routine improvements under `.claude/` AND PR 6.x under `frontend/`), commit each group as a separate coherent commit before continuing. The audit-gate fires on each; the auditor's checkpoint-commit exception applies if the message uses `wip(routine): checkpoint` prefix.
5. Announce "continuing PR <name> from <hash>" or "committing routine improvements then resuming PR <name>" depending on what was found, and proceed.
6. Run the local test command, run lint, run typecheck. If green, the dirty state is closeable. If not green, finish the missing pieces, then commit.
7. Continue the normal loop from the next plan task.

## Checkpoint commit before any voluntary stop

Before the routine reports "done for now" (plan exhausted, time cap hit, voluntary stop), the implementer MUST commit whatever is on the working tree as a checkpoint commit so a chat-clear or session-end does not strand work:

```
git add -A
git commit -m "wip(routine): checkpoint <plan-section> before stop

<one paragraph: what is in-flight, what state the tests are in,
where the next implementing agent should resume>"
```

The audit-gate fires on this commit. Spawn the independent-auditor with the checkpoint context; the auditor's checkpoint-commit exception applies (abbreviated audit, approves liberally if the diff is coherent and tests are not regressed).

A chat-clear or HALT signal AFTER a checkpoint commit means the next /carrel-build session sees a clean tree at preflight and resumes from the next plan task naturally. A chat-clear BEFORE a checkpoint commit means 7+ in-flight files in the working tree and the dirty-tree continuation rule above kicks in.

## The loop

Repeat until a halt condition fires:

### 1. Pull the next task

**Canonical queue:** `/Users/madu/Desktop/Codex/AUTONOMOUS_WORK_PLAN.md`. Read it top-to-bottom. Pick the lowest-ID `pending` task whose `Deps:` line lists only `done` tasks (or `none`). Mark that task `Status: in_progress` by editing the work plan and committing the status flip on the feature branch before starting the implementation. The work plan's task entry tells you which master-plan section (`docs/plans/everything-to-100-2026-05-17.md`) carries the full implementation contract.

**Fallback:** if every `pending` task is currently `blocked` (e.g., depends on operator action) OR the work plan is exhausted, fall back to `TODOS.md` or the latest plan in `docs/plans/`. Pick the highest-leverage incomplete task. If both are empty, generate a 3-item shortlist from CLAUDE.md and the strategy memo, pick the highest-leverage item, and record the rationale in `.claude/logs/task-selection.jsonl`.

**Task announcement:** announce the chosen task by ID + title (e.g., `T01: Phase 3 slice β.1 — rename Citation chunk_id to node_id`) so the operator-visible log carries the queue reference.

### 2. Classify the task

The UserPromptSubmit routing hook will inject a skill suggestion. Honor it unless you have a documented reason not to. Skill routing table:

| Pattern | Skill |
|---|---|
| bug, broken, investigate, debug, crash | `/investigate` |
| security, vulnerability, auth | `/cso` or `/security-review` |
| ship, deploy, release | `/ship` then `/land-and-deploy` |
| plan, architecture | `/claude-mem:make-plan` then `/claude-mem:do` or `/autoplan` |
| accessibility, a11y, WCAG | `design:accessibility-review` |
| performance, benchmark, slow | `/benchmark` |
| visual polish, design review | `/design-review` |
| refactor, simplify | `/simplify` then `/codex challenge` |
| QA, test the site | `/qa` |
| review my diff, code review | `/review` or `/codex` |
| documentation | `engineering:documentation` |

### 3. For architectural decisions: full adversarial debate

Trigger criteria (any one):
- introduces or removes a top-level module under `services/`, `routes/`, `ai/`, `macos-app/Sources/`, `frontend/src/features/`
- changes the database schema (new migration)
- swaps an LLM provider or API client
- changes a public API contract
- changes the install pipeline, bundle layout, or first-launch UX
- changes the licensing or pricing surface

Steps:
1. Spawn the `proponent` subagent (fresh context) with the proposal, the decision context, and a pointer to the relevant codebase area. Run in parallel with the adversary.
2. Spawn the `adversary` subagent (fresh context) with the same inputs. Do not let it see the proponent's output.
3. After both return, spawn the `synthesizer` subagent (fresh context) with both transcripts. Read the verdict.
4. If verdict is `THIRD_OPTION_REQUIRED`, re-run with the third option as the new proposal. Cap at 3 rounds; if 3 rounds fail, halt for human input.
5. Persist the full debate as an ADR at `docs/decisions/NNNN-<slug>.md` with all transcripts attached. Filename uses next sequential 4-digit number.
6. Only after the ADR is written do you begin coding.

### 4. For trivial decisions: skip the debate

Trivial = formatting, variable naming, obvious bugfix where the right answer is in the codebase's existing patterns, or removing dead code. Synthesizer short-circuit applies. Proceed directly. Do not waste cycles.

### 5. Implement

Edit, write, run tests, run linters, run typechecks. Iterate until green. If tests regress, stop and investigate root cause; do not paper over with skip or xfail.

### 6. For major actions: hit the audit gate

The PreToolUse audit gate hook blocks the tool call. The block reason will name a SHA-256 hash of the action. To clear the block:

1. Spawn the `independent-auditor` subagent (fresh context) with the pending action at `.claude/logs/audits/pending/<hash>.json` plus the goal and success criteria.
2. The auditor writes verdict JSON to `.claude/logs/audits/approved/<hash>.json` (APPROVED) or `.claude/logs/audits/rejected/<hash>.json` (REJECTED).
3. If APPROVED, retry the tool call. The hook sees the approval file and lets it through.
4. If REJECTED, read the counter-proposal, revise, and re-submit a fresh proposal. Do not retry the original.

### 7. Score the work

Spawn the `quality-rater` subagent in a fresh context with the goal, the diff, and test results. The rater writes a JSON score. If `verdict == "SHIP"` (total == 100), proceed. If `verdict == "ITERATE"`, read `gaps_to_close` and address each one, then re-score with a fresh spawn. The loop only exits on a fresh-context 100.

### 8. Commit

Conventional Commits message. Co-authored-by line attributing Claude. The audit gate already approved this hash.

### 9. Mark task complete

Update `AUTONOMOUS_WORK_PLAN.md`: flip the task's `Status:` from `in_progress` to `done — PR #XX, commit abc1234, rated 100/100 on YYYY-MM-DD`. Commit the status flip as part of the same PR that lands the work (preferred) OR as a follow-up commit on `main` immediately after merge. Also update `TODOS.md` if the plan file references it. Append a one-line summary to `.claude/logs/completed.jsonl`.

### 10. Halt check

See halt conditions below. If any fire, stop and write `.claude/logs/status.md` summarizing state.

## Operator-set scope: build-only, no outreach (as of 2026-05-12)

The routine is build-only. It does NOT send DMs, recruitment emails, marketing posts, or any other external communication. If a task pulled from the plan would require outreach, surface it as a follow-up in `.claude/logs/operator-followups.jsonl` and skip to the next task. The auditor hard-rejects any action whose effect is to communicate with people outside the codebase.

What this means concretely:

- Code, tests, refactors, docs, ADRs, README, CHANGELOG, runbooks, TODOS.md: build, proceed.
- Git commits, PR descriptions: build, proceed.
- Customer DMs, study-group recruitment, beta invites, marketing posts, social media, sales outreach, mailing list sends: skip and surface.

The constraint is operator-set and time-bound by the phrase "for now" (2026-05-12). It can be lifted by the operator editing the auditor's role file at `.claude/agents/independent-auditor.md`.

## Halt conditions

Stop and report when any fire:

- Plan or `TODOS.md` exhausted (all tasks complete).
- 5 consecutive iterations failed to reach 100 on the same feature (deeper problem).
- Auditor REJECTED 3 times on the same hash (deeper problem).
- Destructive action requested: always halt for explicit operator authorization beyond what the auditor can give.
- Test count regressed by more than 3 without an explicit deletion rationale logged.
- Working tree drift: files modified outside the planned scope without a justification entry in `.claude/logs/scope-drift.jsonl`.
- Session running more than 8 hours of wall clock time.
- Outreach task surfaced as the only remaining work in the plan: halt and surface for operator (do not silently skip an empty plan).
- `.claude/HALT` file exists.

## Resume after halt

1. Read most recent `.claude/logs/status.md`, `.claude/logs/scores/`, `.claude/logs/audits/`.
2. Read most recent ADR in `docs/decisions/`.
3. `export CARREL_AUTONOMOUS=true` in the new shell.
4. Remove `.claude/HALT` if it exists and the operator authorized resume.
5. Invoke `/carrel-build` again. The loop picks up from the next incomplete task.

## Manual override

Operator stop without waiting:
```
touch /Users/madu/Desktop/Codex/.claude/HALT
```

Next hook firing reads this file and exits the routine.

## Decide-and-proceed contract (read this carefully)

You are running unattended. The operator is not at the keyboard. Do NOT ask the operator for confirmation on in-flight decisions. Specifically:

- Pick the next task yourself from the plan or TODOS.md. Do not enumerate options for the operator.
- Pick commit messages, branch names, file paths, and refactor scopes yourself. Apply Conventional Commits style.
- Resolve ambiguity in plan files by reading the surrounding context (CLAUDE.md, prior ADRs, recent commits, the operator-decisions section at the top of `AUTONOMOUS_WORK_PLAN.md`) and making the call. If the call is genuinely 50/50 on a non-architectural choice, default to the option that ships sooner with smaller diff.
- For architectural decisions (per the trigger criteria above), the proponent + adversary + synthesizer subagents decide, not the operator. You read the synthesizer verdict and act on it.
- For major actions, the independent-auditor decides, not the operator. You spawn the auditor, read its verdict, and proceed or revise.
- For quality scoring, the quality-rater decides, not the operator. You iterate until a fresh-context spawn returns 100.

The ONLY moments you stop and surface to the operator are:

1. The preflight halt conditions (working tree not clean AND the dirty files do not match the dirty-tree continuation rule above, on main branch with a task that needs a feature branch, stale plan > 14 days).
2. The runtime halt conditions (plan exhausted, 5 unsuccessful iterations on the same feature, 3 auditor rejections on same hash, destructive action requested, test regression > 3 without justification, scope drift logged in `.claude/logs/scope-drift.jsonl`, 8-hour wall-clock cap, `.claude/HALT` file).
3. An outreach task surfaced as the only remaining work (operator handles outreach manually).
4. A genuinely novel architectural choice the synthesizer flags THIRD_OPTION_REQUIRED three times in a row.

For everything else: decide and proceed. Do not write "should I X or Y?" Decide. If the decision is wrong, the auditor or rater will catch it and you will iterate.

### Things that are NEVER reasons to voluntarily halt

The 2026-05-19 max-autonomy directive in `AUTONOMOUS_WORK_PLAN.md` makes these non-halt-reasons explicit. If any of the following come up mid-session, decide and continue, do not write status.md and stop:

- **PR scope ambiguity** ("should I bundle these tasks on one PR or split them?"). Default: branch fresh off `main` for every task per the 2026-05-19 directive. One task = one PR unless two tasks are mechanically coupled (e.g., a migration and the code that requires it).
- **Branching strategy questions** ("continue on the same feature branch or branch fresh off main?"). Default: branch fresh off `main`.
- **Context budget anxiety** ("session is getting long, should I checkpoint and stop?"). Answer: no. Run until a real halt condition fires. The 8-hour wall-clock cap is the only time-based halt. Context compaction is the harness's job, not yours.
- **Data-modeling questions inside a task's stated scope** ("the acceptance text assumes a column that doesn't exist, what should I do?"). Read the surrounding code, infer the intended translation key, edit the acceptance text in the work plan to record what you picked, and proceed. Surface as a one-line follow-up in `.claude/logs/operator-followups.jsonl` so the operator sees the change on their next review pass, but do not halt.
- **PR-merge readiness anxiety** ("the PR is green, should I admin-merge it or wait for the operator?"). Auditor decides. If the auditor approves the `gh pr merge`, merge. The operator authorized auto-merge after rater 100 in the build-only scope (see `.claude/AUTONOMOUS_SCOPE.md`).
- **Cross-PR landing questions** ("PR #N's work is on a staging branch but the next task needs it on main, what do I do?"). Open the staging→main PR yourself, run the verify chain on the merged result, auditor-approve, merge, then branch the next task off main. Do not surface this as an operator decision.

If you find yourself drafting a status.md entry that names "operator should decide ..." for anything not in the four ONLY-stop conditions above, stop drafting and apply the decide-and-proceed default instead.

## Begin

After preflight passes, announce in chat ONCE:
- The task you are picking up.
- Why it is the highest-leverage item right now.
- Whether it will trigger a full adversarial debate or short-circuit.

Then start the loop. Subsequent tasks announce themselves in one line each as the loop turns; no further preamble.
