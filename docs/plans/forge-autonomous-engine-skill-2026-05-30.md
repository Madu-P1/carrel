# Plan: Forge — a portable autonomous build engine, as a skill

A reusable Claude Code skill you point at any project to get an autonomous build loop with
best-in-class verification, adversarial review, safety gates, and the right human checkpoints.
"Forge" is a working name; rename freely.

- Status: APPROVED for build (operator-directed, 2026-05-30)
- Author: `/claude-mem:make-plan`, grounded in a Phase 0 discovery of the live Claude Code docs
  and the existing Carrel autonomous machinery (the reference implementation)
- Executable in phases, each self-contained for a fresh context

## The one honest truth this plan is built around

The loop's output quality equals the quality of the signals it can check its work against. The
engine cannot conjure tests, evals, golden references, or a definition of "done." It can only be
the engine AND a forcing function: it refuses to run autonomously when those signals are missing,
and routes the two things a machine structurally cannot finish (taste and the unknown-unknown
security edge) to you. A fully-autonomous 10/10 on everything is not real. A 10/10 SYSTEM, the
engine doing 95% at a verified 9 and your judgment spent only where it is irreplaceable, is real,
and is what this builds.

---

## Phase 0 — Discovery findings (the Allowed APIs, verified)

### Platform APIs (source: code.claude.com/docs, fetched 2026-05-30)

- **Skills** (`code.claude.com/docs/en/skills.md`): a skill is `SKILL.md` with YAML frontmatter
  (`name`, `description` required; optional `tools`, `model`, `permissionMode`, `context: fork`,
  `hooks`, `skills`, `maxTurns`, `effort`). Project skills live in `.claude/skills/<name>/`; a
  user-level skill in `~/.claude/skills/<name>/` is available in **every** project, which is what
  "point it at anything" requires. Skills ship supporting files in the same dir, referenced as
  `${CLAUDE_PROJECT_DIR}/.claude/skills/<name>/...` and run via the Bash tool. **Anti-pattern:
  skills cannot be invoked from hooks** (hooks are gates, not skill triggers).
- **Hooks** (`hooks.md`): events include `UserPromptSubmit`, `PreToolUse`, `PostToolUse`,
  `Stop`, `SubagentStop`, `SubagentStart`, `SessionStart`. Stdin is JSON
  (`hook_event_name`, `session_id`, `cwd`, `tool_name`, `tool_input`, `prompt`, `agent_type`).
  Exit 0 = allow (stdout JSON parsed); exit 2 = block. JSON output:
  `{"decision":"block","reason":...,"hookSpecificOutput":{"hookEventName":...,"additionalContext":...}}`.
  Registered in `settings.json` under `hooks.<Event>[].matcher` + `command`. Handler types:
  `command`, `http`, `mcp_tool`, `prompt`, `agent`.
- **Sub-agents** (`sub-agents.md`): `.claude/agents/<name>.md` with frontmatter (`name`,
  `description`, `tools`, `model`, `permissionMode`, `maxTurns`, `isolation: worktree`, `memory`,
  `hooks`). **Anti-pattern: subagents do NOT enforce structured output.** They return a text
  summary. The working pattern is the one Carrel already uses: the agent **writes a verdict/score
  JSON file** and the parent (or a hook) reads it. Copy that convention, do not assume a JSON
  return.
- **Cross-model**: `codex` CLI is confirmed on PATH (`/Users/madu/.local/nodejs/current/bin/codex`);
  the gstack `/codex` skill wraps it (review / challenge / consult). Shell out via Bash from an
  agent or hook. This is the verified path to a genuinely different model.
- **Headless visual review**: the `Claude_Preview` MCP (`preview_start`, `preview_screenshot`,
  `preview_eval`, `preview_resize`) is **verified working in this environment** (used 2026-05-29 to
  screenshot the Cachet prototype). Documented alternative: Playwright MCP
  (`npx @playwright/mcp@latest --headless`).
- **State + kill switch**: filesystem state (queue file, plan docs, verdict/score JSON, git) read
  at the top of each iteration; `.claude/HALT` sentinel read by every hook and the watchdog.

### The reference implementation (Carrel, verified by direct read)

`.claude/settings.json` wires: `UserPromptSubmit → route-task.py`; `PreToolUse →
audit-gate.py` + `debate-trigger.py`; `Stop` and `SubagentStop → score-loop.py`.

| Reference file | Role | Copy-ready pattern |
|---|---|---|
| `.claude/hooks/audit-gate.py` | Hard gate before major/irreversible/outward actions | PreToolUse; hashes the staged diff; checks `.claude/logs/audits/approved/<hash>.json`; `OUTREACH_BASH_PATTERNS` + `DESTRUCTIVE_BASH_PATTERNS` hard-block lists (L196, L212); `AUDIT_TIMEOUT_SECONDS=300` auto-REJECT (L39) fixes the silent-auditor wedge; HALT-aware; `CARREL_AUTONOMOUS`-gated |
| `.claude/hooks/score-loop.py` | Quality gate; blocks Stop until the bar | Stop/SubagentStop; releases only on HALT, a recent `total>=100` score JSON, or the 25-nudge cap; `GATE_SUBAGENT_TYPES` skip. **Has a real bug to fix in the generalized version: the "no feature, just stop" escape is unreachable, so it blocks every stop. The port must add a marker the implementing agent writes to release a genuine no-op.** |
| `.claude/hooks/debate-trigger.py` | Nudge to run proponent/adversary/synthesizer on architectural changes | PreToolUse(Bash/Edit/Write); manifest-file + arch-path + dep-verb patterns; strips heredocs to avoid false positives; does NOT block |
| `.claude/hooks/route-task.py` | Suggests the best skill for a task | UserPromptSubmit; regex → `additionalContext`. **Weakness to fix: crude keyword routing false-positived `/investigate` on a design brainstorm this session. The generalized version should classify by task type, not raw keyword, or be advisory-only.** |
| `.claude/agents/independent-auditor.md` | Fresh-context gatekeeper | opus; writes `approved/<hash>.json` or `rejected/<hash>.json`; build-only/no-outreach scope; destructive-action bar; checkpoint exception; MANDATORY-write-output + wedge-postmortem (T68 fixes) |
| `.claude/agents/quality-rater.md` | Fresh-context scorer | opus; 9-dimension 100-pt rubric; SHIP only at exactly 100; writes `scores/<slug>-<ts>.json`; MANDATORY-write-output |
| `.claude/agents/{proponent,adversary,synthesizer}.md` | Adversarial decision round | proponent argues for, adversary against, synthesizer picks |
| `.claude/commands/carrel-build.md` | The loop routine | task pick → skill-orchestrate → implement → audit-gate → rate-to-100 → loop → HALT check |
| `script/start-autonomous.sh`, `autonomous-watchdog.sh`, `tests/test_watchdog_kill.sh` | Launch + supervise + kill | exports the autonomous env flag + `bypassPermissions`; relaunch on rate-limit; idleness + orphan detection; pre-flight smoke; HALT graceful stop |

**The generalization gap:** every reference hook is gated on `CARREL_AUTONOMOUS=true` and hardcodes
Carrel paths, the Carrel rubric, and Carrel scope. Generalizing = read those from a per-project
**contract** instead, and swap the env flag to a generic one.

---

## The anatomy: every component, best approach, and honest ceiling

This is the engine taken apart. "Ceiling" is how close to perfect the component gets on its own.

| # | Component | Best approach available today | Buys you / costs you | Autonomous ceiling | Human gate? |
|---|---|---|---|---|---|
| 1 | Task selection | Queue file with deps + priority, read top-of-loop, lowest-eligible-first (copy the AWP picker) | Deterministic, resumable / you keep the queue | 9 | only for strategy |
| 2 | Planning | Phased plan doc per task, fresh-context-executable (this skill's own format) | Self-contained phases / upfront authoring | 8 | scope calls |
| 3 | Implementation | One capable agent, skill-orchestrated (scan available skills, pick, run) | Reuses curated skill process / can drift | 8 | no |
| 4 | Self-verification | The project's verify chain as a gate (test/lint/build/typecheck), declared in the contract | Objective pass/fail / only as good as the chain | 9 where chain is strong | no |
| 5 | Independent review | Fresh-context auditor gating major actions via verdict JSON (copy `independent-auditor.md` + `audit-gate.py`) | Catches drift + scope creep before irreversible acts / same-model blind spots | 8 | no |
| 6 | Adversarial verification | **Cross-model**: `codex` refutes each acceptance criterion, plus proponent/adversary/synthesizer | Breaks correlated blind spots / cost + latency | 9 (backend) | no |
| 7 | Quality scoring | Fresh-context rater, contract-supplied rubric, exits only at the bar (copy `quality-rater.md` + `score-loop.py`) | Honest gate, no "good enough" / a rubric cannot rate taste | 9 on code, 5 on craft | YES on craft |
| 8 | Visual / craft review | Headless screenshots (Claude_Preview, verified) diffed vs golden references + an anti-slop critique | Catches layout, hierarchy, slop / cannot judge "feels alive" | 8 | YES |
| 9 | Safety / scope gate | Hard-block lists (copy `OUTREACH`/`DESTRUCTIVE` patterns) + auditor + timeout auto-reject | Stops outward/irreversible harm / occasional false positive | 8 | YES on security |
| 10 | State / memory | Filesystem: queue, plan docs, verdict/score JSON, git; resumable each iteration | Survives restarts / light housekeeping | 10 | no |
| 11 | Kill switch | `.claude/HALT` read by every hook + watchdog (copy) | Instant graceful stop / none | 10 | operator owns |
| 12 | Supervisor | Watchdog: relaunch + idleness + orphan-sweep + pre-flight smoke (copy `autonomous-watchdog.sh`) | Survives rate-limits + wedges / complexity | 9 | no |
| 13 | **Applicability gate (NEW)** | Pre-run check: does the contract supply a verify chain, invariants, signals, and a definition of done? If thin, refuse or drop to "work with me directly" mode | Stops confident garbage on non-ready work / sometimes refuses work you wanted | this IS the headline feature | operator can override |
| 14 | **Human-in-the-loop (NEW)** | Diff-path triggers route craft- and security-touching work to `needs_human_review` even at a rater pass | Spends your scarce judgment exactly where machines cannot reach / you must show up | n/a | YES, the point |

**Where it is near-perfect on its own:** task selection, self-verification (with a real chain),
state, kill switch, supervisor, scoring of code-correctness. **Where it structurally cannot finish,
no matter the tuning:** craft (a rubric cannot rate "feels alive"; the loop tops out at "correct
and on-brand"), and the security unknown-unknown (it cannot reason about an attack class nobody put
in the threat model). Those two are the human checkpoints, by design, not by weakness.

---

## Architecture: the portable engine vs the per-project contract

```
~/.claude/skills/forge/            ← PORTABLE. Built once, works in any repo.
  SKILL.md                         the loop routine + the applicability gate (generalize carrel-build.md)
  hooks/{gate,score,debate,route}.py   generalized from Carrel's 4 hooks; read the contract, not hardcoded paths
  agents/{auditor,rater,proponent,adversary,synthesizer,cross-model-adversary,visual-reviewer}.md
  watchdog/                        generalize start-autonomous.sh + autonomous-watchdog.sh
  contract.schema.md               the documented template a project fills in

<any-project>/.claude/forge.contract.md   ← PER-PROJECT. The fuel. The project brings its own.
```

**The contract is everything the engine cannot invent.** A project that wants to be built
autonomously declares:

- **verify**: exact commands that gate a merge (test, lint, typecheck, build, evals) + pass criteria.
- **invariants**: machine-checkable ones (a grep/lint/test that must pass, e.g. "no `localStorage` of
  a secret") AND prose ones for the adversary to attack.
- **scope**: allowed actions; hard-block patterns (extend the OUTREACH/DESTRUCTIVE lists).
- **signals**: where ground truth lives, eval suites + thresholds, a held-out set, golden
  screenshots, benchmarks. This is the single biggest determinant of output quality.
- **human_gates**: path globs that force a human checkpoint (UI paths → craft; auth/secret/crypto
  paths → security).
- **rubric**: the scoring rubric (or use the default 9-dimension one).
- **queue + model + kill**: where tasks live, which model, the HALT path.

**The loop is only as good as the contract.** The applicability gate (component 13) enforces this:
no verify chain → refuse; UI work but no golden reference → downgrade that PR to human-paired; fuzzy
acceptance criteria → refuse and tell the operator exactly what is missing. A tool that knows when
NOT to run is the difference between this being a 10/10 system and a confident-garbage generator.

---

## What you, the operator, must supply (the only inputs that decide gold vs garbage)

You are not a senior dev and you should not have to be. The engine encodes the engineering judgment.
These five are the irreplaceable human inputs; spend your attention only here:

1. **The definition of done** — the contract's verify chain + invariants. What "good" means for this
   project. If you get this right, the engine self-checks against it relentlessly. Get it vague and
   no amount of machinery saves you.
2. **Golden references for anything visual** — an approved screenshot or mockup per key screen. This
   is what turns "rate taste in the abstract" (impossible) into "diff against this" (tractable).
3. **Sign-off at the two human gates** — craft and security. A few minutes of your eye on the PRs the
   engine flags. This is where your taste and your "does this feel trustworthy" judgment enter.
4. **The queue / priority** — what to build and in what order. The engine executes; you point.
5. **HALT discipline** — `touch .claude/HALT` is your brake; pull it to go.

Everything else, the implementing, verifying, adversarial review, scoring, gating, and supervising,
the engine does.

---

## The build, in phases

Each phase is self-contained, frames work as COPY-from-reference (not "transform"), and ends with a
verification checklist and anti-pattern guards.

### Phase 1 — Skill skeleton + contract schema + applicability gate
- **Implement:** create `~/.claude/skills/forge/SKILL.md` (the loop routine, generalize
  `.claude/commands/carrel-build.md`). Author `contract.schema.md` (the template above). Build the
  applicability gate as step 1 of the loop: read the contract, confirm verify + invariants + signals
  + definition-of-done are present; refuse or downgrade with a specific "missing X" message if not.
- **Doc refs:** skill frontmatter from `skills.md`; loop routine from `.claude/commands/carrel-build.md`.
- **Verify:** the skill loads; pointed at a repo with no contract, it refuses with a clear list of
  what is missing; pointed at a contract missing only golden refs, it downgrades UI work to paired.
- **Anti-pattern guards:** do not invent frontmatter fields; do not let the loop start work when the
  applicability gate says "not ready."

### Phase 2 — Generalize the four gate hooks
- **Implement:** copy `audit-gate.py`, `score-loop.py`, `debate-trigger.py`, `route-task.py` into
  `~/.claude/skills/forge/hooks/`. Replace hardcoded Carrel paths/rubric/scope with contract-read
  values; swap `CARREL_AUTONOMOUS` → `FORGE_AUTONOMOUS`; keep HALT-awareness, the staged-diff hashing,
  `AUDIT_TIMEOUT_SECONDS` auto-reject, `GATE_SUBAGENT_TYPES`, and the hard-block lists (now
  contract-extensible).
- **Doc refs:** the four files in the Phase 0 table; settings wiring from `hooks.md`.
- **Verify:** hooks fire only under `FORGE_AUTONOMOUS`; they read the contract; the audit gate blocks
  an un-approved commit and releases on a verdict file.
- **Anti-pattern guards:** **fix the `score-loop.py` unreachable-escape bug** (a genuine no-feature
  turn must be able to release via a marker file the implementing agent writes, not only via HALT /
  100-score / 25-nudge-cap). **Fix `route-task.py`** to be advisory-only or classify by task type, so
  it cannot wedge a session onto the wrong skill (it false-positived `/investigate` on a design
  brainstorm this session).

### Phase 3 — Port and parameterize the gate agents
- **Implement:** copy `independent-auditor.md`, `quality-rater.md`, `proponent/adversary/synthesizer.md`
  to `~/.claude/skills/forge/agents/`. Replace the Carrel rubric + correctness bar + the hardcoded
  `/Users/madu/Desktop/Codex` paths with the contract-supplied rubric and `$CLAUDE_PROJECT_DIR`. Keep
  the MANDATORY-write-output and wedge-postmortem sections verbatim (those are hard-won T68 fixes).
- **Doc refs:** the two agent files (full contracts read in Phase 0).
- **Verify:** the rater reads the contract rubric and writes a score JSON; the auditor reads contract
  scope and writes a verdict JSON; both refuse to skip the mandatory output.
- **Anti-pattern guards:** do not assume agents return JSON; they write the file and the hook reads it.

### Phase 4 — Cross-model adversary
- **Implement:** a `cross-model-adversary` agent (and a debate step) that shells to `codex` to
  independently refute each acceptance criterion, default-to-refuted. Wire it into the debate round
  and as a second, different-model rater.
- **Doc refs:** the gstack `/codex` skill invocation; `codex` at `/Users/madu/.local/nodejs/current/bin/codex`.
- **Verify:** a planted bug the same-model rater passes is caught by the codex refutation (regression
  fixture).
- **Anti-pattern guards:** treat codex output as advisory evidence the synthesizer weighs, not an
  auto-merge or auto-block.

### Phase 5 — Visual / craft review
- **Implement:** a `visual-reviewer` agent that starts the contract's dev-server command, screenshots
  each UI state via `Claude_Preview` (verified) or Playwright MCP, diffs against the contract's golden
  references, runs an anti-slop checklist, and routes findings to `needs_human_review`.
- **Doc refs:** the `Claude_Preview` tools used 2026-05-29; `mcp.md` for Playwright.
- **Verify:** a deliberate visual regression vs the golden reference is flagged; a clean state passes.
- **Anti-pattern guards:** never let a rubric pass substitute for the human craft gate; visual review
  is necessary, not sufficient.

### Phase 6 — Verification-signal gates
- **Implement:** run the contract's property-based + mutation-test commands as gates; enforce
  machine-checkable invariants as grep/lint/test that fail the build; run a held-out eval set at phase
  end.
- **Doc refs:** the contract's `signals` and `invariants` sections.
- **Verify:** a surviving mutation is reported; an invariant violation fails the gate; the held-out
  evals run and compare to thresholds.
- **Anti-pattern guards:** do not let the loop overfit to the evals it can see; the held-out set is
  not readable by the implementing agent.

### Phase 7 — Human-in-the-loop checkpoints
- **Implement:** diff-path triggers (contract globs) that, on a craft- or security-touching change,
  write a `needs_human_review` entry (`kind: craft|security`) to `operator-followups.jsonl`, leave the
  PR draft, and stop the loop from marking that task fully done on a rater pass alone.
- **Doc refs:** the Carrel `operator-followups.jsonl` convention.
- **Verify:** a UI-path or secret-path change routes to the human gate even at a rater 100.
- **Anti-pattern guards:** the gate is automatic from the diff, not the agent's discretion.

### Phase 8 — Supervisor + kill switch
- **Implement:** generalize `start-autonomous.sh` + `autonomous-watchdog.sh` (relaunch, idleness,
  orphan-sweep, pre-flight smoke, HALT) to take the project root + `FORGE_AUTONOMOUS`.
- **Doc refs:** the watchdog scripts + `tests/test_watchdog_kill.sh`.
- **Verify:** HALT stops within seconds (port the kill test); the pre-flight smoke refuses launch if
  the gate machinery is broken.
- **Anti-pattern guards:** never run without the smoke test; never run without a HALT path.

### Final Phase — Verification by dogfood
- **Implement:** run the finished Forge skill on a real, signal-rich task. The **Cachet verify port
  (T69-T75)** is the ideal first target: it already has a contract (verify chain, invariants, golden
  references from the prototype, human gates).
- **Verify:** the engine refused where signals were thin; caught the planted bugs via cross-model
  refutation; routed the craft PRs (cert, Margin) and the security PR (Keychain) to your human gate;
  produced verified, chain-green output on the mechanical PRs.
- **Anti-pattern guards:** if the dogfood run reveals the engine shipped craft or security on a rubric
  pass alone, the human-gate wiring is broken; fix before trusting it on anything else.

---

## Anti-patterns to prevent (global)

- Inventing hook events or skill/agent frontmatter fields not in the Phase 0 Allowed-APIs list.
- Assuming subagents return enforced JSON; they write a verdict/score file and a hook reads it.
- Trying to invoke a skill from a hook; hooks gate, agents verify, the loop is the skill.
- Reintroducing the `score-loop` unreachable-escape bug or the `route-task` keyword false-positive.
- Hardcoding project paths; read `$CLAUDE_PROJECT_DIR` + the contract.
- Letting a rater 100 stand in for the craft or security human gate.
- Running autonomously when the applicability gate says the contract's signals are too thin. The
  refusal is the feature.

## A note on dogfooding, because it matters here

You are building the engine with an AI loop, to build a product whose entire pitch is that you do not
trust unverified AI output on work that matters. Hold the engine to its own standard: independent
(cross-model) verification, machine-checkable invariants, and a human at the two gates a machine
cannot close. The human-in-the-loop is not the engine failing. It is the engine eating its own
dogfood.
