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
4. Read `/Users/madu/Desktop/Codex/CLAUDE.md`, `/Users/madu/Desktop/Codex/TODOS.md`, the latest plan in `/Users/madu/Desktop/Codex/docs/plans/`
5. `export CARREL_AUTONOMOUS=true` so the hooks activate

Halt and ask the operator if any of:
- working tree is not clean
- current branch is `main` or `master`
- the most recent plan is older than 14 days (stale plan signals stale intent)

## The loop

Repeat until a halt condition fires:

### 1. Pull the next task

Read `TODOS.md` or the active plan. Pick the highest-leverage incomplete task. If both are empty, generate a 3-item shortlist from CLAUDE.md and the strategy memo, pick the highest-leverage item, and record the rationale in `.claude/logs/task-selection.jsonl`.

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

Update `TODOS.md` or the plan file. Append a one-line summary to `.claude/logs/completed.jsonl`.

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
- Resolve ambiguity in plan files by reading the surrounding context (CLAUDE.md, prior ADRs, recent commits) and making the call. If the call is genuinely 50/50 on a non-architectural choice, default to the option that ships sooner with smaller diff.
- For architectural decisions (per the trigger criteria above), the proponent + adversary + synthesizer subagents decide, not the operator. You read the synthesizer verdict and act on it.
- For major actions, the independent-auditor decides, not the operator. You spawn the auditor, read its verdict, and proceed or revise.
- For quality scoring, the quality-rater decides, not the operator. You iterate until a fresh-context spawn returns 100.

The ONLY moments you stop and surface to the operator are:

1. The preflight halt conditions (working tree not clean, on main branch, stale plan).
2. The runtime halt conditions (plan exhausted, 5 unsuccessful iterations, 3 auditor rejections on same hash, destructive action requested, test regression > 3, scope drift, 8-hour cap, .claude/HALT file).
3. An outreach task surfaced as the only remaining work (operator handles outreach manually).
4. A genuinely novel architectural choice the synthesizer flags THIRD_OPTION_REQUIRED three times in a row.

For everything else: decide and proceed. Do not write "should I X or Y?" Decide. If the decision is wrong, the auditor or rater will catch it and you will iterate.

## Begin

After preflight passes, announce in chat ONCE:
- The task you are picking up.
- Why it is the highest-leverage item right now.
- Whether it will trigger a full adversarial debate or short-circuit.

Then start the loop. Subsequent tasks announce themselves in one line each as the loop turns; no further preamble.
