# Forge contract schema (draft for review)

This is the per-project contract Forge reads. The engine is portable and built once; this file is
the fuel each project supplies. It is also your interface as the operator: the few things only a
human can decide live here, and the engine does everything else.

Draft status: proposed. Not yet placed in the skill package. Once approved it becomes
`~/.claude/skills/forge/contract.schema.yaml` (the template) and each project fills in a copy at
`<project>/.claude/forge.contract.yaml`.

## The three fields that decide everything

Get these right and the rest has sane defaults:

1. **`verify.commands`** — how the engine proves its work is correct. These are its eyes.
2. **`invariants`** — the lines it must never cross.
3. **`definition_of_done`** — what "good" means in this project.

If those three are missing, the engine has nothing to check itself against, so it refuses to run
autonomously rather than produce confident garbage. That refusal is the feature.

## What happens if a field is missing (the applicability gate)

| Section | Required? | If missing, the engine... |
|---|---|---|
| `verify.commands` | REQUIRED | refuses to run (it would be flying blind) |
| `invariants.prose` | REQUIRED | refuses (no lines to hold) |
| `definition_of_done` | REQUIRED | refuses (no bar to rate against) |
| `queue` | REQUIRED | refuses (nothing to pick) |
| `signals.golden_references` | recommended | routes ALL visual work to you; it cannot auto-verify look |
| `signals.evals` / `held_out` | recommended | cannot catch behavioral regressions; lowers its confidence and says so |
| `human_gates` | recommended | falls back to safe defaults (UI and secret paths route to you) |
| `invariants.machine_checkable` | recommended | leans on prose + the adversary only, which is weaker |
| `scope` / `rubric` / `adversary` / `runtime` | optional | uses built-in defaults |

## The template (commented YAML)

```yaml
# <project>/.claude/forge.contract.yaml
# The engine is the skill; this file is the fuel. Missing a field => the engine
# tells you and either refuses or works with you directly, never guesses.

project:
  name: "my-app"
  root: "."
  autonomous_env: "FORGE_AUTONOMOUS"   # hooks only fire when this env var is true

# 1. VERIFY  (REQUIRED) — the commands that gate a merge. The engine's eyes.
verify:
  commands:
    - name: "typecheck"
      run: "pnpm -C frontend typecheck"
      pass_when: "exit_zero"          # exit_zero | stdout_contains:<text> | no_output
    - name: "lint"
      run: "pnpm -C frontend lint"
      pass_when: "exit_zero"
    - name: "unit"
      run: "pnpm -C frontend test"
      pass_when: "exit_zero"
    - name: "build"
      run: "pnpm -C frontend build"
      pass_when: "exit_zero"
  heavy:                               # slow gates, run at phase boundaries only
    - name: "evals"
      run: "python -m evals.run --mode full"
      pass_when: "stdout_contains:groundedness@8"

# 2. INVARIANTS  (REQUIRED: at least prose) — lines the engine must never cross.
invariants:
  machine_checkable:                   # a command that MUST pass; fails the build
    - name: "no-secret-in-localstorage"
      run: "! grep -rni 'localStorage' frontend/src | grep -i 'key\\|token\\|secret'"
    - name: "no-key-in-logs"
      run: "! grep -rni 'console.log' frontend/src | grep -i 'apikey\\|token'"
  prose:                               # the adversary actively hunts violations
    - "Verify, never generate: this tool checks work, it does not write or auto-replace it."
    - "No success badge or green check; the absence of a flag is the pass."
    - "An unfinished or errored check is reported as could-not-verify, never as supported."

# 3. DEFINITION OF DONE  (REQUIRED) — what "good" means, in plain words.
definition_of_done: >
  A change is done when every verify command passes, every invariant holds, the task's
  stated acceptance criteria are met, and no existing check regresses.

# SIGNALS  (STRONGLY RECOMMENDED) — ground truth. More signals, higher ceiling.
signals:
  evals:
    - { metric: "groundedness@8", threshold: 0.7, direction: ">=" }
    - { metric: "quote_validity", threshold: 0.95, direction: ">=" }
  held_out:
    path: "evals/held_out/"            # implementing agent must NOT read this; rater runs it
  golden_references:                   # approved look per UI state; visual reviewer diffs vs these
    - { state: "workspace", image: ".claude/forge/golden/workspace.png" }
    - { state: "certification", image: ".claude/forge/golden/cert.png" }
  dev_server:                          # how the visual reviewer brings the UI up headlessly
    start: "python -m http.server 4178 --directory prototypes"
    url: "http://localhost:4178/cachet-shell.html"
  benchmarks:
    - { name: "cold-launch", run: "./script/measure_cold_launch.sh", regress_fails: true }

# HUMAN GATES  (RECOMMENDED) — diff paths that force YOUR review even at a rubric 100.
human_gates:
  craft:
    when_paths: ["**/*.css", "frontend/src/features/**/*.tsx"]
    note: "Visual taste; a rubric pass is necessary, not sufficient."
  security:
    when_paths: ["**/auth/**", "**/*keychain*", "**/secrets/**", "macos-app/**"]
    note: "Unknown-unknown attack surface; needs a human security read."
  followups_log: ".claude/logs/operator-followups.jsonl"

# SCOPE + SAFETY  (defaults provided)
scope:
  mode: "build-only"                   # build-only | build-and-deploy
  drafts_only: true                    # never auto-ready a PR; operator merges
  hard_block_extra: []                 # project-specific forbidden commands (extends built-ins)
  audit_timeout_seconds: 300           # auto-reject a pending action with no auditor verdict

# RUBRIC  (optional; default is the 9-dimension rubric)
rubric:
  use_default: true

# QUEUE  (REQUIRED) — where tasks come from.
queue:
  source: "AUTONOMOUS_WORK_PLAN.md"    # tasks with deps + acceptance
  pick: "lowest-eligible"              # lowest-numbered task whose deps are done
  active_plan_dir: "docs/plans/"       # the per-task contract the loop reads

# CROSS-MODEL ADVERSARY  (recommended)
adversary:
  cross_model_cmd: "codex"             # a genuinely different model that tries to refute the work
  votes: 1

# RUNTIME  (defaults provided)
runtime:
  model: "opus"
  kill_switch: ".claude/HALT"
  watchdog: true
```

## Why this shape

- **YAML, not code.** You edit a config file, not a program. Comments explain every field.
- **Required vs recommended vs default** maps to your five irreplaceable inputs: the definition of
  done, the verify chain, the invariants, the golden references, and the queue. Everything optional
  has a built-in default so a non-expert fills in only what matters.
- **Every field has a consequence**, shown in the table above, so you can see exactly what you buy
  by adding a golden reference or an eval, and what you lose by omitting one.
- **It is the same file Carrel already has, generalized.** Carrel's `AUTONOMOUS_WORK_PLAN.md` +
  `RATER_RUBRIC.md` + the hooks' hardcoded scope are a hand-rolled version of this contract. Forge
  reads it from one declared file instead of hardcoding it.

## Open choices for you

1. **Format:** YAML (shown, human-friendly, needs a tiny parser) vs TOML (zero-dependency in Python
   3.11+, less friendly for the prose invariants). My pick: YAML, for your sake as the operator.
2. **Required set:** I made verify + prose-invariants + definition-of-done + queue the hard
   requirements (no run without them). Add or relax?
3. **Golden references location:** I put them under `.claude/forge/golden/`. Fine, or elsewhere?
