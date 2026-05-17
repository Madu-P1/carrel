# Carrel Autonomous Build Runbook

This runbook documents the autonomous build routine that lets Claude Code ship Carrel to a 100/100 quality bar with zero human intervention during a work session.

If you are reading this for the first time, the entry point is the `/carrel-build` slash command. Everything else is mechanism.

## Operator-set scope: build-only, no outreach (active 2026-05-12)

The routine is BUILD-ONLY. It does not send DMs, recruitment emails, marketing posts, social media, or any external communication. The auditor hard-rejects any action whose effect is to communicate with people outside the codebase. If a plan task would require outreach, the routine surfaces it to `.claude/logs/operator-followups.jsonl` and skips to the next task.

This constraint is set by the operator and uses the word "for now". To lift it, edit `.claude/agents/independent-auditor.md` and remove the "Operator-set scope: build-only" section. The hook in `.claude/hooks/audit-gate.py` will also need its `OUTREACH_BASH_PATTERNS` rewritten or emptied. Both changes should themselves be audited and recorded as ADRs.

## What the routine is

A loop. For each task in the active plan:

1. Classify the task. Route to the most fitting skill or slash command.
2. If the task is an architectural decision, spawn a fresh proponent and a fresh adversary in parallel, then a synthesizer, then persist the verdict as an ADR before any code is written.
3. If the task is implementation, do the work and run the standard gates (tests, lint, typecheck).
4. Before any major action (commit, migration, dependency change, install-script edit), spawn the independent-auditor in a fresh context. The audit-gate hook blocks the action until the auditor signs off.
5. After the work is done, spawn the quality-rater in a fresh context. The rater scores against a 100-point rubric. If the score is below 100, iterate. The loop only exits on a fresh-context 100.

The fresh context spawns are non-negotiable. The whole point is that each judging agent has no memory of the implementing agent's prior reasoning, so the judgment cannot be biased by sunk cost.

## The five agents

All five live at `.claude/agents/`:

- [proponent.md](.claude/agents/proponent.md): builds the strongest case FOR a proposed approach.
- [adversary.md](.claude/agents/adversary.md): steelmans the case AGAINST.
- [synthesizer.md](.claude/agents/synthesizer.md): reads both cold, picks a winner or demands a third option.
- [independent-auditor.md](.claude/agents/independent-auditor.md): gatekeeper for major actions.
- [quality-rater.md](.claude/agents/quality-rater.md): scores completed work against a 100-point rubric.

Each has frontmatter (name, description, tools, model). Each is callable as a `subagent_type` once a Claude Code session is launched from this repo.

## The four hooks

All four live at `.claude/hooks/`. They are Python 3 scripts with `python3` shebangs and the executable bit set:

- [route-task.py](.claude/hooks/route-task.py) on UserPromptSubmit: pattern-matches the prompt to a skill or slash command, injects an additionalContext suggestion, logs to `.claude/logs/routing.jsonl`.
- [audit-gate.py](.claude/hooks/audit-gate.py) on PreToolUse for Bash, Edit, Write: detects major actions (commits, migrations, dependency changes, install-script edits, top-level module creation, destructive operations), hashes the action, blocks until an approval file exists at `.claude/logs/audits/approved/<hash>.json`.
- [debate-trigger.py](.claude/hooks/debate-trigger.py) on PreToolUse for Bash, Edit, Write: detects architectural keywords, logs to `.claude/logs/debates/triggers.jsonl`, nudges (does not block).
- [score-loop.py](.claude/hooks/score-loop.py) on Stop and SubagentStop: nudges Claude to spawn the quality-rater if no recent 100 score exists, with per-session nudge cap to prevent runaway recursion.

All four are gated on the `CARREL_AUTONOMOUS=true` environment variable. Without it, they exit silently and your normal Claude Code sessions are unaffected. The opt-in is by design: you do not want adversarial debate firing on a five-minute ad-hoc edit.

## How to start a routine

```bash
cd /Users/madu/Desktop/Codex
export CARREL_AUTONOMOUS=true
claude
```

Then in Claude Code, type `/carrel-build`. The routine boots, runs preflight, and starts the loop.

## How to stop it

Hard stop:
```bash
touch /Users/madu/Desktop/Codex/.claude/HALT
```

The next hook firing reads this file, returns a deny decision (PreToolUse) or halt-requested message (UserPromptSubmit, Stop, SubagentStop), and the routine winds down. Remove the file when you want to resume.

Soft stop: in the chat, tell Claude `halt the routine` and it should write `.claude/logs/status.md` and exit the loop.

## Halt conditions baked into the routine

- Plan exhausted: all tasks in `TODOS.md` or the active plan are marked complete.
- Convergence failure: 5 consecutive iterations on the same feature failed to reach 100. The deeper problem needs human review.
- Auditor convergence failure: 3 rejected proposals on the same hash. The implementing agent is going down the wrong path.
- Destructive action requested: halt regardless of auditor verdict, since these are catastrophic if wrong.
- Test regression: count drops by more than 3 without an explicit deletion rationale.
- Scope drift: files modified outside the planned scope without justification.
- Time cap: 8 hours of wall clock.
- HALT file present.

## Where the logs live

```
.claude/logs/
├── routing.jsonl                  # one line per UserPromptSubmit, the skill chosen
├── debates/
│   └── triggers.jsonl             # one line per architectural keyword hit
├── audits/
│   ├── pending/<hash>.json        # the major action awaiting auditor verdict
│   ├── approved/<hash>.json       # auditor signed off; hook lets the action through
│   └── rejected/<hash>.json       # auditor refused; implementing agent reads counter-proposal
├── audit-allowed.jsonl            # one line per audited action that ran
├── scores/
│   ├── <feature-slug>-<ts>.json   # rater output per feature
│   └── nudge-count-<session>.txt  # per-session counter for score-loop hook
├── completed.jsonl                # one line per shipped task
├── scope-drift.jsonl              # files touched outside planned scope
├── task-selection.jsonl           # rationale when picking next task from a generated shortlist
└── status.md                      # written on halt; current state for resume
```

ADRs live separately, under `docs/decisions/NNNN-<slug>.md`, since they outlive any single session.

## How to inspect a debate

```bash
ls -lt /Users/madu/Desktop/Codex/docs/decisions/ | head -10
cat /Users/madu/Desktop/Codex/docs/decisions/0001-*.md
```

Each ADR has the proponent transcript, the adversary transcript, the synthesizer verdict, and the auditor sign-off if a major action was tied to the decision.

## How to inspect a routing decision

```bash
tail -n 20 /Users/madu/Desktop/Codex/.claude/logs/routing.jsonl | jq .
```

Each line has `ts`, `session`, `prompt_snippet`, `suggestion`, and `reason`. If the routing was wrong, override in chat (the suggestion is a nudge, not a command).

## How to inspect a quality score

```bash
ls -lt /Users/madu/Desktop/Codex/.claude/logs/scores/*.json | head -5
cat /Users/madu/Desktop/Codex/.claude/logs/scores/<feature>-<ts>.json | jq .
```

Each score file has nine rubric dimensions, the total, the verdict, and the `gaps_to_close` list.

## How to manually approve a stuck major action

If the auditor is wrong or unavailable and you need to ship:

1. Read the pending action: `cat /Users/madu/Desktop/Codex/.claude/logs/audits/pending/<hash>.json | jq .`
2. Decide whether you actually approve. If yes, write an approval file by hand:
```json
{
  "hash": "<hash>",
  "verdict": "APPROVED",
  "auditor_ts": "<ISO timestamp>",
  "goal_understood": "<one sentence>",
  "diff_summary": "<your summary>",
  "carrel_correctness_bar": "PASS",
  "trust_bar": "PASS",
  "destructive_bar": "N/A",
  "rationale": "Manual operator approval: <why>",
  "follow_ups": []
}
```
3. Save as `.claude/logs/audits/approved/<hash>.json`.
4. Tell Claude to retry the blocked tool call.

## Tradeoffs the routine accepts

- Throughput: a full debate round is slower than a single-agent pass. Acceptable because the routine is designed for unattended overnight operation; wall clock is bounded by sleep cycles, not agent count.
- Token cost: each debate spends three to five fresh-context agent runs. Acceptable because every shipped artifact carries an audit trail that doubles as documentation for future contributors.
- False positives on architectural triggers: the debate-trigger hook will nudge on near-misses. Acceptable because the synthesizer's short-circuit terminates trivial debates fast.
- Hook complexity: four hooks plus five agents is real infrastructure. Acceptable because the routine ships unattended; humans only debug it when something breaks.

## What this routine does NOT do

- It does not write the strategic plan. The plan in `docs/plans/` is human-authored. The routine executes the plan; it does not invent direction.
- It does not push to main. Force pushes are denied at the permission layer. Real production deploys are an operator-only step.
- It does not send external messages (email, Slack, GitHub issues). The hooks block PUT and POST to non-localhost URLs.
- It does not move money. There are no payment integrations in the autonomous path.
- It does not promote itself. If the rater hits a hard wall, it surfaces; it does not paper over.

## Maintenance

The routine is small enough to understand end-to-end. If you change any agent file, hook script, or settings file:

1. Bump the version line in this runbook (top of file).
2. Add an ADR documenting the change at `docs/decisions/`.
3. Update the routing table in `/carrel-build` if you added or removed skills.

## Version

Routine v1: first deployment 2026-05-12. Initial dry-run on the AFM Pass 1 ship-strategy decision. See `docs/decisions/0001-afm-pass1-ship-strategy.md`.
