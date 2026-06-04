# How to Become a Claude Code Power User

> Source-cited research report produced 2026-06-04 via the `/deep-research` harness
> (6 search angles, 24 sources, 115 claims extracted, top 25 adversarially verified
> 3-votes-each, all 25 survived 3-0). Findings marked **[VERIFIED]** are cited to
> primary sources. Findings marked **[SYNTHESIS]** are assembled from named-but-unverified
> sources and should be treated as informed practitioner guidance, not fact-checked claims.

## The one-sentence version

Everything reduces to two disciplines: **treat the context window as a finite, degrading
resource you actively curate**, and **give the agent a check it can run so it closes its own
verification loop**. The features are just instruments for those two goals.
[VERIFIED — [best-practices](https://code.claude.com/docs/en/best-practices),
[context-engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)]

---

## Thread 1 — Claude Code Mastery [mostly VERIFIED]

### Context is the master resource
The context window fills fast and model performance degrades as it fills (it "forgets"
earlier instructions and makes more mistakes). Independently corroborated by Chroma's
"Context Rot" study (18 SOTA models incl. Claude 4, GPT-4.1, Gemini 2.5) and Stanford's
"Lost in the Middle." The frontier move is **minimizing context, not maximizing it.**
[VERIFIED 3-0 — [best-practices](https://code.claude.com/docs/en/best-practices),
[Chroma Context Rot](https://trychroma.com/research/context-rot)]

### CLAUDE.md
Loaded at the start of every session. Keep it short: bloated CLAUDE.md files cause Claude
to ignore your actual instructions. Prune test: "would removing this cause Claude to make
mistakes?" If no, cut it. Claude also builds auto-memory (build commands, debugging
insights) across sessions automatically. [VERIFIED 3-0 —
[overview](https://docs.anthropic.com/en/docs/claude-code/overview), best-practices]

### Subagents (parallelism + context isolation)
Each runs in its own context window with a custom system prompt, specific tools, independent
permissions; starts fresh (no main history) and returns only a summary. Defined as Markdown
+ YAML frontmatter (`name` + `description` required; `tools`/`model` optional) in
`.claude/agents/` (project) or `~/.claude/agents/` (user). Delegation is controllable:
auto-delegates on `description`, `"use proactively"` encourages it, @-mention or `--agent`
forces it. Win = parallelism AND context hygiene (dirty exploration in a throwaway window,
only the conclusion returns). [VERIFIED 3-0 —
[sub-agents](https://docs.anthropic.com/en/docs/claude-code/sub-agents),
[autonomy announcement](https://www.anthropic.com/news/enabling-claude-code-to-work-more-autonomously)]

### Hooks (deterministic gates)
Shell commands at lifecycle points (PreToolUse, PostToolUse, Stop, SessionStart, etc.).
Power move: the **Stop hook** blocks turn-end until a check passes. Limit: Claude Code
overrides the Stop hook and ends the turn after **8 consecutive blocks**. [VERIFIED 3-0 —
best-practices, autonomy announcement]

### Checkpointing
Auto-saves code state before each change; rewind with Esc-Esc or `/rewind`. Boundary:
**covers Claude's edits only**, not your manual edits or bash side effects (a `rm` or DB
migration is NOT undone). [VERIFIED 3-0 — [checkpointing](https://code.claude.com/docs/en/checkpointing)]

### Plan mode + core loop
Four-phase **explore → plan → code → commit**. Skip plan mode when you could describe the
diff in one sentence (typo, log line, rename). Use it for multi-file changes, unfamiliar
code, uncertain approach. [VERIFIED 3-0 — best-practices]

### Agent SDK
Claude Code as a library (Python + TS, renamed from "Claude Code SDK"). Ships built-in tools
(Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch, AskUserQuestion) and runs the
agent loop for you (unlike the Client SDK where you write the `while stop_reason == "tool_use"`
loop). Plus lifecycle hooks, subagents via the Agent tool, MCP connections, permissions,
resumable/forkable sessions. [VERIFIED 3-0 —
[Agent SDK overview](https://docs.claude.com/en/api/agent-sdk/overview)]

---

## Thread 2 — Workflows & Methods [VERIFIED core + SYNTHESIS]

**Verified backbone:**
1. Explore-plan-code-commit with plan mode. [VERIFIED]
2. **Close the verification loop.** Give the agent a check it can run (tests, build exit
   code, linter, fixture/output diff, screenshot-vs-design). Without one, "looks done" is
   the only signal and YOU become the verification loop. Single most important habit.
   [VERIFIED 3-0 — best-practices]

**[SYNTHESIS — not independently verified]:**
- **Orchestrator/worker (fan-out/verify):** lead decomposes, spawns N isolated workers,
  collects summaries, runs a separate verification pass. Pipeline default: stream items
  through stages without a barrier unless a stage needs all prior results.
- **Adversarial self-review:** a second, *fresh-context* agent critiques the first. Fresh
  context is the mechanism, not cleverness.
- **Context hygiene:** `/clear` when switching tasks (full reset). `/compact` to continue a
  heavy same-task session (lossy summary). Fresh session for genuinely new work.
- **Git worktrees** for true parallelism: one worktree per parallel agent so edits don't
  collide.

Honest caveat: little *empirical* public evidence that multi-agent orchestration beats a
disciplined single-agent loop for most tasks. More agents = more context = more places to
degrade. Reach for orchestration when work is genuinely parallel or needs an independent critic.

---

## Thread 3 — Agents That Grow and Learn [VERIFIED core + limits + SYNTHESIS]

**Built in [VERIFIED]:** Subagents support a `memory` field (user/project/local scope) =
a directory that persists across conversations. The first **200 lines or 25KB of MEMORY.md**
(whichever first) is injected into the subagent's system prompt, with a curate-on-overflow
instruction. [VERIFIED 3-0 — sub-agents]

**The realistic limit — read twice:** There are **no weight updates.** Every persistent-memory
system (MEMORY.md injection, vector stores, memory MCP servers) is **retrieval + context
injection** — notes the future agent reads, not a changed brain. And it degrades: more
accumulated "learnings" = more tokens = worse recall (context rot). The paradox: remembering
more makes the agent dumber per token. The 200-line cap is the defense, not an arbitrary limit.

**[SYNTHESIS — research scaffolds, efficacy unverified]:**
- **Reflexion** ([arXiv:2303.11366](https://arxiv.org/pdf/2303.11366)): agent reflects on
  failures in natural language, stores reflection as context for the next attempt.
- **Voyager** ([arXiv:2305.16291](https://arxiv.org/abs/2305.16291)): the "agent writes its
  own skills" pattern — a growing skill library of reusable code. The skill library compounds,
  not the model.
- **Episodic vs semantic memory:** episodic = what happened (logs/transcripts); semantic =
  distilled facts/patterns. Production lesson: distill episodic to semantic; don't dump raw.
- **Where it breaks:** unbounded growth, lossy compression dropping the one fact that mattered,
  stale/now-wrong memories surfacing, "memory poisoning" (one bad stored conclusion contaminates
  every future session). Fix: verify a memory still holds before acting; delete wrong ones.

Highest-ROI "learning" = a curated, aggressively-pruned semantic memory file + a retrievable
skill library + a periodic consolidation pass that distills and *deletes*. Memory is a garden
you weed, not an attic you fill.

---

## Thread 4 — Prompting Craft [VERIFIED]

- **Context engineering is the successor skill.** Prompt engineering = instructions for one
  optimal completion. Context engineering = iterative curation of the optimal token set across
  the agent's whole run. [VERIFIED 3-0 — context-engineering]
- **Right altitude.** System prompts sit between brittle hardcoded logic and vague hand-waving:
  specific enough to steer, flexible enough for strong heuristics, organized with XML/Markdown
  headers, aiming for the **minimal set that fully specifies the behavior.** [VERIFIED 3-0]
- **Let the model think.** Prefer general "think thoroughly" over prescriptive step lists —
  Claude's reasoning frequently exceeds what a human would prescribe. Thinking off → manual
  chain-of-thought with `<thinking>`/`<answer>` tags. Caveat: on Opus 4.5+ with thinking off,
  the literal word "think" is sensitive; "consider"/"evaluate" can prompt better. [VERIFIED 3-0 —
  [chain-of-thought](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/chain-of-thought)]
- **Adaptive thinking** (`thinking: {type: "adaptive"}`) on current models: the model decides
  when/how much to reason from an effort parameter. Anthropic's internal evals say it beats the
  old `budget_tokens` approach (deprecated on newer Opus). Flag: vendor self-eval, magnitude
  unproven externally. [VERIFIED 3-0, with caveat — extended-thinking]

---

## Thread 5 — Concrete Week-One Plan [SYNTHESIS, grounded in verified principles]

- **Day 1 — Context foundation.** Audit CLAUDE.md against the prune test. Cut everything that
  fails. A 40-line file that gets followed beats a 300-line one that gets ignored.
- **Day 2 — Close one verification loop.** Pick your most common task; give the agent a command
  that proves success. Wire it as a hook if repeatable. Highest single ROI.
- **Day 3 — One good subagent.** An Explore-style subagent (read-only, returns a conclusion not
  a file dump). Watch the main context stay clean.
- **Day 4 — Context hygiene reflexes.** `/clear` between tasks, `/compact` within a long one,
  until it's muscle memory.
- **Day 5 — One Stop-hook gate.** Block turn-end until tests pass (keep the check fast/real;
  remember the 8-block override).
- **Day 6-7 — Memory discipline.** Curated semantic memory file with curate-on-overflow.
  Distill, don't dump. Delete one stale memory.

**Anti-patterns that bite hardest:**
- Context pollution (#1 silent killer): one long session, everything inline. Fix: subagents + `/clear`.
- Over-automation / runaway loops: autonomous loops without a real check generate confident
  garbage faster. The 8-block Stop override exists because loops wedge.
- Trusting unverified output: "looks done" is not a signal. Build a check or you are the check.
- Memory hoarding: append-only memory rots. Weed it.

**Measure effectiveness:** time-to-first-working-change, diff-acceptance rate (kept vs. redone),
verification-loop closure rate (fraction of tasks the agent self-verifies), context resets per
task (going up is good — clearing instead of accumulating).

---

## Source quality note

All 25 verified claims trace to Anthropic primary docs / engineering blog / announcements, with
two independent corroborations (Chroma, Stanford) on context degradation. Strength for *what the
features are*; weakness for *efficacy* claims (several rest on Anthropic's own evals). High
time-sensitivity: the 200-line/25KB cap, the 8-block Stop override, the built-in tool list, and
thinking syntax are current as of mid-2026 and will drift. Several docs.anthropic.com URLs now
301-redirect to code.claude.com / platform.claude.com.

## Key sources
- https://code.claude.com/docs/en/best-practices
- https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- https://docs.anthropic.com/en/docs/claude-code/sub-agents
- https://docs.claude.com/en/api/agent-sdk/overview
- https://www.anthropic.com/news/enabling-claude-code-to-work-more-autonomously
- https://code.claude.com/docs/en/checkpointing
- https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/chain-of-thought
- https://trychroma.com/research/context-rot
- https://arxiv.org/abs/2305.16291 (Voyager) · https://arxiv.org/pdf/2303.11366 (Reflexion)
