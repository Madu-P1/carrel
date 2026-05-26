# Plan: Carrel Autonomous Routine Hardening — Make the Loop Trustworthy Unattended

- **Status:** drafted 2026-05-27, awaiting operator approval
- **Owner:** operator-led design call on scope cut; autonomous-loop execution on approved items
- **Tracks:** new (proposed T68 in `AUTONOMOUS_WORK_PLAN.md` if approved); blocks "operator can walk away overnight" property
- **Strategic frame:** post-mortem of the 2026-05-26 T64 wedge. The routine delivered (PR #88, 263 tests passing) once two latent bugs were patched, but the bugs were diagnosable in principle and the fix path required ~2 hours of operator-side debugging. This plan converts the markdown-rule invariants the routine depends on into code-enforced invariants, so the next wedge class (whatever it is) surfaces fast and doesn't hang silently.
- **Plan ref for the wedge that motivated this:** [`docs/plans/answer-quality-2026-05-26.md`](answer-quality-2026-05-26.md) and the 2026-05-26 status memo at `.claude/logs/status.md` (now archived as `.claude/logs/archive/status-2026-05-26-t64.md` per Phase 0 task below).

---

## Premise

The autonomous routine has a series of contracts between hooks and agents that are documented in markdown but not enforced in code. When the contract is violated, the routine wedges silently — no exception thrown, no auditor verdict, no halt memo, just an unresolved pending file and a watchdog that keeps a dead session alive past the operator's expected check-in window.

The 2026-05-26 wedge: `.claude/hooks/score-loop.py` fires on `SubagentStop` and nudges the stopping agent to spawn the quality-rater with an escape clause ("if no feature touched, respond with brief status and stop"). The independent-auditor subagent — whose required output is a verdict JSON, not feature work — adopted the escape clause as its own response and exited without writing the verdict. The audit-gate's release condition is the verdict file's existence, so the implementing agent's commit stayed blocked forever. Two hours of debugging, two file patches (`score-loop.py` gate-subagent skip + `independent-auditor.md` MANDATORY-write-verdict section), one successful relaunch.

The patches work. The pattern is unsafe. The same class of bug — a subagent stopping without producing its required artifact — can recur on the rater (no score JSON written), the proponent/adversary (no debate transcript), or the synthesizer (no decision file). Each would manifest as a different silent wedge. The fix is not "patch each role individually." The fix is to make required-artifact-on-stop a code-enforced property of the gate-loop machinery.

### The five contract failures I want to make impossible

1. **Auditor stops without writing verdict.** → Pending file lingers forever. (Hit 2026-05-26.)
2. **Rater stops without writing score JSON.** → Stop hook keeps nudging the implementing agent. Effectively wedges the Stop event.
3. **Implementing agent commits without going through audit-gate hash invalidation.** → Already prevented by `compute_staged_diff_hash`, but the hashing is brittle (heredoc and trailing-redirect handling carry edge cases; future commits with different shapes may slip past).
4. **Watchdog kills a session due to idle threshold but the underlying claude process keeps running.** → Orphan process, screen state captured but no progress (the user's screenshot from 2026-05-26).
5. **Loop claims a task without reading its plan doc.** → Rule-based not code-enforced; loop has historically wandered without plan docs on prior tasks (T13, T58 — see git log of `AUTONOMOUS_WORK_PLAN.md` for status flips with no preceding plan-doc commit).

### What this plan does NOT do

- Does NOT redesign the audit-gate's hashing logic. Out of scope; the existing implementation is sound for the cases it covers.
- Does NOT add new auditor agents or change the existing role contracts. Out of scope; the rubric problem (no carve-out for orchestration) is acknowledged but punted to a separate follow-up.
- Does NOT touch the Carrel product code paths. This plan is entirely about `.claude/hooks/`, `.claude/agents/`, `script/*`, and `tests/test_routine_*.py`.
- Does NOT add monitoring or telemetry beyond what's needed for the wedge-postmortem convention. The operator's eyes on `.claude/logs/status.md` and the watchdog log remain the primary observability surface.

---

## Phase 0: Documentation discovery (DONE 2026-05-27)

### Files already verified

| File | Location | Notes |
|---|---|---|
| `.claude/hooks/score-loop.py` | repo root | `GATE_SUBAGENT_TYPES` constant + subagent-skip block added 2026-05-26. |
| `.claude/hooks/audit-gate.py` | repo root | Hashes tool input + staged_diff for git commit; persists pending JSON at `.claude/logs/audits/pending/<hash>.json`; passes if approved file exists. No timeout currently. |
| `.claude/hooks/route-task.py` | repo root | Pre-tool router that emits skill hints into the user prompt. Not in scope for this plan; works as designed. |
| `.claude/hooks/debate-trigger.py` | repo root | Triggers proponent/adversary debate on AI-touching diffs. Not in scope; was working correctly during the T64 run (one legitimate trigger, one regex false-positive that did not wedge). |
| `.claude/agents/independent-auditor.md` | repo root | Got the MANDATORY-write-verdict section 2026-05-26. Approval/rejection JSON schema documented near the bottom. |
| `.claude/agents/quality-rater.md` | repo root | NOT verified for the same "MUST write score JSON" property — Phase 2 below confirms and patches if needed. |
| `.claude/agents/proponent.md`, `.claude/agents/adversary.md`, `.claude/agents/synthesizer.md` | repo root | NOT verified. Phase 2 audits all gate-role agents for the required-artifact property. |
| `script/autonomous-watchdog.sh` | repo root | Idle-threshold kills work; graceful-halt detection via `status.md` mtime works. Open question: child orphaning on watchdog exit (Phase 5). |
| `script/start-autonomous.sh` | repo root | `CARREL_MODEL` + `CARREL_AUTONOMOUS_DRY_RUN` already added 2026-05-26. |
| `tests/test_routine_hooks.py` | repo root | Created by the autonomous loop during T64 closeout. Covers the gate-subagent skip path. Will be extended in Phase 1. |

### Allowed APIs in scope (verified)

- `json` (stdlib): hooks parse stdin and emit stdout JSON. Already used in every hook.
- `pathlib.Path`: file operations. Already used.
- `time`, `os`: timestamps + env vars. Already used.
- `subprocess`: NOT in current hooks; will be needed in Phase 3 (smoke test invokes the auditor). Allowed per repo conventions.
- `hashlib`: hashing for audit-gate. Already used.

### Reference patterns from the existing routine

- **Hook output shape:** `{"hookSpecificOutput": {"hookEventName": "<event>", "permissionDecision": "allow|deny", "permissionDecisionReason": "..."}}` for PreToolUse; `{"decision": "block", "reason": "..."}` for Stop nudges; `{"systemMessage": "..."}` for advisory output. All three shapes used in current hooks.
- **Agent verdict JSON shape:** documented in `.claude/agents/independent-auditor.md` lines 87-103 (for auditor); rater uses a 100-point rubric JSON at `.claude/logs/scores/<feature>-<ts>.json`. Phase 2 unifies the "required artifact path" convention across all gate roles.

---

## Phase 1: Verdict timeout on audit-gate (~30 min, ship-now)

### Goal

The audit-gate hook must auto-write a REJECTED verdict for any pending action whose pending file is older than 5 minutes with no matching approved/rejected sibling. The gate can never silently hang.

### Premise

Tonight's wedge would have surfaced in <5 min instead of 21+ min if this existed. The 5-min budget is generous (the auditor agent's median runtime in the existing audit log is ~2 min); pending files older than 5 min are almost certainly stuck.

### Implementation

`.claude/hooks/audit-gate.py`:

```python
# New constant near the top of the file:
AUDIT_TIMEOUT_SECONDS = 300  # 5 minutes; pending older than this auto-REJECTs

# In main(), AFTER the "Already audited; allow through" block at line ~334
# and BEFORE the "Persist pending action" block at line ~352:

stale_pending = pending_dir / f"{h}.json"
if stale_pending.exists():
    try:
        age = time.time() - stale_pending.stat().st_mtime
    except Exception:
        age = 0
    if age > AUDIT_TIMEOUT_SECONDS:
        # Auto-REJECT and let the operator see the timeout.
        rejection_file = audit_dir / "rejected" / f"{h}.json"
        try:
            rejection_file.write_text(
                json.dumps(
                    {
                        "hash": h,
                        "verdict": "REJECTED",
                        "auditor_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "auto_timeout": True,
                        "goal_understood": "unknown — auditor did not converge within the timeout",
                        "diff_summary": "see pending file at .claude/logs/audits/pending/" + h + ".json",
                        "rejection_reasons": [
                            f"Audit-gate timeout: pending action older than {AUDIT_TIMEOUT_SECONDS}s with no auditor verdict. "
                            "The auditor subagent failed to write either an APPROVED or REJECTED verdict file. "
                            "Operator review required to determine root cause and unblock."
                        ],
                        "counter_proposal": (
                            "Operator should: (1) check .claude/logs/audits/pending/" + h + ".json for the original action, "
                            "(2) check whether the auditor subagent spawn produced any tool-use trace in the watchdog "
                            "session log, (3) manually approve or reject the action, (4) investigate the auditor "
                            "subagent's failure mode if this becomes a pattern."
                        ),
                        "what_would_change_my_mind": "auditor subagent successfully writes a verdict file on the next spawn",
                    }
                )
            )
        except Exception as e:
            # If we can't even write the timeout rejection, log and fall through.
            try:
                (log_dir / "audit-gate-errors.jsonl").open("a").write(
                    json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "hash": h, "error": str(e)}) + "\n"
                )
            except Exception:
                pass
        # Tell the calling agent the gate auto-rejected with timeout.
        out = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"AUDIT-GATE TIMEOUT (hash {h}): pending action older than {AUDIT_TIMEOUT_SECONDS}s. "
                    f"Auto-REJECTED at .claude/logs/audits/rejected/{h}.json. "
                    "The auditor subagent did not converge. Operator review required."
                ),
            }
        }
        print(json.dumps(out))
        sys.exit(0)
```

### Acceptance

- Touch a stale pending file with `touch -A -0500 .claude/logs/audits/pending/<hash>.json` (mtime 5 min ago), then trigger any git commit that hashes to the same `<hash>` — expect immediate REJECTED file + denial.
- Existing approved/rejected paths still work (regression test).
- No effect on fresh pending files (< 5 min old).

### Test plan

`tests/test_routine_hooks.py::test_audit_gate_timeout_writes_rejected` — fixture that pre-creates a stale pending file, invokes `audit-gate.py main()` with matching tool_input via stdin, asserts the rejected file is written with `auto_timeout: true`.

---

## Phase 2: Required-artifact contract on all gate-role agents (~45 min, ship-now)

### Goal

Every gate-role agent (auditor, rater, proponent, adversary, synthesizer) has a MANDATORY-write-output section identical in shape to the one added to `independent-auditor.md` on 2026-05-26. The independent-auditor section is the template.

### Premise

The 2026-05-26 wedge happened because the auditor was the first gate role to hit the score-loop nudge contamination. The rater, proponent, adversary, and synthesizer have the same structural risk. The fix is to copy the MANDATORY-write-output rule to each role definition, with role-specific output paths.

### Implementation

For each of:
- `.claude/agents/quality-rater.md` → required output: `.claude/logs/scores/<feature>-<ts>.json`
- `.claude/agents/proponent.md` → required output: `.claude/logs/debates/<topic>-pro-<ts>.md`
- `.claude/agents/adversary.md` → required output: `.claude/logs/debates/<topic>-con-<ts>.md`
- `.claude/agents/synthesizer.md` → required output: `.claude/logs/debates/<topic>-decision-<ts>.json`

Append a "MANDATORY: write the <artifact> before you stop" section with the same four rules pattern (artifact non-negotiable / ignore Stop-hook escape clause / write-even-if-declining / confirm-existence-as-last-action).

### Acceptance

- Each gate-role file has the section.
- The output-path naming convention is consistent (`<role>` directory under `.claude/logs/`, `<ts>` in ISO-8601 UTC).
- Existing successful artifact files in those directories match the convention (or the convention adjusts to match existing files — don't break running history).

### Test plan

Pure documentation; no automated test beyond `grep -l "MANDATORY:" .claude/agents/*.md` returning all five files.

---

## Phase 3: Wedge postmortem `.jsonl` convention (~30 min, ship-now)

### Goal

Every routine wedge produces one line in `.claude/logs/wedge-postmortems.jsonl` describing root cause + the file/rule changed to prevent recurrence. Same class of bug never costs two hours twice.

### Premise

Tonight's two-hour debug should have been one-line writeup. The patches were small; the diagnosis was the expensive part. Capturing the diagnosis turns the routine into a system that learns.

### Implementation

`.claude/hooks/score-loop.py` — at the top of the file, add the file path:

```python
WEDGE_POSTMORTEM_PATH = ".claude/logs/wedge-postmortems.jsonl"
```

`.claude/agents/independent-auditor.md` — in the MANDATORY section (Rule 5):

> If your verdict is REJECTED due to a wedge condition (auditor timeout, missing verdict file from a prior spawn, contradiction between gates), also append a one-line entry to `.claude/logs/wedge-postmortems.jsonl` with shape `{"ts": "<iso8601>", "hash": "<hash>", "wedge_class": "<one-of: timeout, missing-artifact, gate-contradiction, audit-pattern-false-positive, test-failure-blocking, other>", "root_cause": "<one sentence>", "fix_applied": "<file:line of the change OR null if not yet fixed>", "fix_owner": "<auditor|operator|unfixed>"}`. The operator reads this file to track recurring failure classes.

`AUTONOMOUS_WORK_PLAN.md` — add to the "How the loop picks tasks" section:

> When the loop encounters a wedge it cannot self-resolve, it MUST write a wedge-postmortem entry per `.claude/logs/wedge-postmortems.jsonl` shape before surfacing to operator. Wedge surfacing without postmortem entry is incomplete handoff.

### Acceptance

- Touch the file with the initial wedge from 2026-05-26 (manually backfilled by Phase 3 implementer):

```json
{"ts": "2026-05-26T22:43:54Z", "hash": "404990ae2fcd183a", "wedge_class": "missing-artifact", "root_cause": "score-loop.py SubagentStop nudge contaminated independent-auditor subagent into adopting 'no feature touched, stop' escape clause instead of writing verdict JSON", "fix_applied": ".claude/hooks/score-loop.py:GATE_SUBAGENT_TYPES + .claude/agents/independent-auditor.md:MANDATORY-write-verdict section", "fix_owner": "operator"}
```

- File is gitignored OR explicitly committed (operator choice; recommend committing so the lesson travels with the repo).

### Test plan

None beyond a schema check: `python -c "import json; [json.loads(l) for l in open('.claude/logs/wedge-postmortems.jsonl')]"` must not raise.

---

## Phase 4: Gate-machinery smoke test (~1 hr, ship-if-time)

### Goal

A pre-flight test that exercises the full gate-loop cycle: spawn the auditor on a synthetic pending action, assert a verdict file appears within 60 seconds. Runs at watchdog startup. If it fails, the watchdog refuses to launch.

### Premise

We would have shipped tonight's fix two weeks ago if this test existed. The cost is one synthetic auditor spawn per watchdog launch (~30s, one-time per session).

### Implementation

New file `tests/test_routine_gate_smoke.py`:

```python
"""Pre-flight gate smoke test. Asserts that spawning the auditor on a
synthetic pending action produces a verdict file within the timeout.
Run at watchdog startup; refuse launch on failure."""

import json
import subprocess
import time
from pathlib import Path

SYNTHETIC_HASH = "smoke-test-synthetic-action"
TIMEOUT_S = 60


def test_auditor_writes_verdict_on_synthetic_action():
    project = Path(".").resolve()
    pending = project / ".claude/logs/audits/pending" / f"{SYNTHETIC_HASH}.json"
    approved = project / ".claude/logs/audits/approved" / f"{SYNTHETIC_HASH}.json"
    rejected = project / ".claude/logs/audits/rejected" / f"{SYNTHETIC_HASH}.json"

    # Clean prior runs.
    for p in (pending, approved, rejected):
        p.unlink(missing_ok=True)

    # Write a benign synthetic pending action that should approve fast.
    pending.write_text(
        json.dumps(
            {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "hash": SYNTHETIC_HASH,
                "kind": "smoke-test",
                "tool_name": "Bash",
                "tool_input": {
                    "command": "echo smoke-test no-op",
                    "description": "synthetic gate-smoke probe",
                },
            }
        )
    )

    # Trigger an auditor spawn via the claude CLI in --print mode.
    # (Equivalent to spawning the auditor subagent; --print mode exits.)
    cmd = [
        "claude",
        "--print",
        "--permission-mode", "default",
        "--model", "haiku",   # cheap; the auditor reads the pending JSON.
        f"Audit pending action {SYNTHETIC_HASH}. Write APPROVED to "
        f".claude/logs/audits/approved/{SYNTHETIC_HASH}.json or REJECTED to "
        f".claude/logs/audits/rejected/{SYNTHETIC_HASH}.json per the auditor agent definition.",
    ]
    try:
        subprocess.run(cmd, timeout=TIMEOUT_S, check=False, capture_output=True)
    except subprocess.TimeoutExpired:
        raise AssertionError(f"auditor spawn exceeded {TIMEOUT_S}s on synthetic action")

    # Poll for verdict file (auditor may write after subprocess returns).
    deadline = time.time() + TIMEOUT_S
    while time.time() < deadline:
        if approved.exists() or rejected.exists():
            break
        time.sleep(1)

    assert approved.exists() or rejected.exists(), (
        f"auditor did not write a verdict file within {TIMEOUT_S}s; "
        "gate machinery is broken — refuse to launch the autonomous loop"
    )
```

`script/autonomous-watchdog.sh` — add at the top, before the main loop:

```bash
# Gate-machinery smoke test. Refuse to launch if the auditor can't
# converge on a synthetic action. Skip with CARREL_SKIP_SMOKE=1.
if [ -z "${CARREL_SKIP_SMOKE:-}" ]; then
  echo "$(date '+%F %T'): running gate-machinery smoke test..."
  if ! "$REPO_ROOT/.venv/bin/python" -m pytest \
       "$REPO_ROOT/tests/test_routine_gate_smoke.py" \
       -x --tb=short --no-header -q; then
    echo "$(date '+%F %T'): gate-machinery smoke test FAILED. Refusing to launch."
    echo "  See .claude/logs/audits/pending/smoke-test-synthetic-action.json"
    echo "  Override with CARREL_SKIP_SMOKE=1 if you know what you're doing."
    exit 1
  fi
  echo "$(date '+%F %T'): gate-machinery smoke test PASSED."
fi
```

### Acceptance

- Smoke test passes when the gate is healthy.
- Smoke test fails (and watchdog refuses to launch) when `.claude/agents/independent-auditor.md` is broken (rename it to simulate a missing file).
- `CARREL_SKIP_SMOKE=1` bypasses the check.

### Test plan

The smoke test itself is the test. Manual verification: rename `independent-auditor.md` to `.broken`, run `./script/autonomous-watchdog.sh`, expect "Refusing to launch."

### Cost

One auditor spawn per watchdog launch. With `--model haiku`, this is cheap and fast (~10-30s).

---

## Phase 5: Watchdog orphan-claude detection (~45 min, ship-if-time)

### Goal

When the watchdog kills a session via the idle threshold, it must also kill the underlying claude process. No more orphaned claude processes that keep running after the watchdog declares the session dead.

### Premise

Tonight, after the loop wedged and the watchdog killed the session, the claude process (PID 20882 in tonight's debugging) kept running. The user's TUI screenshot showed a session that LOOKED alive but was idle. The orphan was harmless this time but creates ambiguity in the diagnostic flow ("is the loop running or wedged?").

### Implementation

`script/autonomous-watchdog.sh` — in the poller's kill block (currently around line 130), after the existing `pkill -TERM -P` and `kill -TERM` calls, add a pgrep-based sweep for any claude process whose CWD is the worktree:

```bash
# After the existing TERM/KILL block:
# Belt-and-suspenders: sweep any claude process whose cwd is this worktree.
# This catches orphans that survived the parent kill (script(1) → start-autonomous.sh → claude
# where claude was exec'd and lost its parent linkage).
for orphan_pid in $(pgrep -f "claude.*--permission-mode bypassPermissions" 2>/dev/null); do
  orphan_cwd=$(/usr/sbin/lsof -p "$orphan_pid" 2>/dev/null | awk '$4 == "cwd" {print $NF}' | head -1)
  if [ "$orphan_cwd" = "$REPO_ROOT" ]; then
    echo ">>> $(date '+%F %T'): killing orphaned claude (PID $orphan_pid, cwd=$orphan_cwd)"
    kill -TERM "$orphan_pid" 2>/dev/null || true
    sleep 2
    kill -KILL "$orphan_pid" 2>/dev/null || true
  fi
done
```

### Acceptance

- After a poller-triggered kill, `ps aux | grep claude | grep -v grep | grep <worktree>` returns empty.
- No false-positive kills of claude processes in OTHER worktrees (the `cwd` check ensures isolation).

### Test plan

Extend `tests/test_watchdog_kill.sh` with a new case that spawns a fake claude process under the worktree, triggers an idle-kill, and asserts the fake claude is also killed.

---

## Phase 6: Programmatic queue index for the work plan (~1 hr, ship-after-validation)

### Goal

A `AUTONOMOUS_WORK_PLAN.json` derived from `AUTONOMOUS_WORK_PLAN.md` that the loop reads first on every iteration. Schema: `{"active_override": "<reference to operator-decision block>", "tasks": [{"id": "T64", "status": "done|in_progress|pending|paused|blocked", "deps": ["T63"], "plan_doc": "docs/plans/...", "is_autonomous": true|false}, ...]}`.

### Premise

The work plan is now ~800 lines of dense markdown with multiple operator-decision override blocks (some superseded, some active). The loop has to re-parse all of this on every iteration, and the parsing is regex-based. A small JSON index lifts the runtime contract out of the prose.

### Implementation deferred

Scope cut: ship Phase 1-3 first, validate the routine survives an unattended overnight run, then consider Phase 6. The benefit is real but speculative — current parsing has not failed in production, just felt brittle. Re-evaluate after the validation test (T66) returns.

### Acceptance

- `script/generate-queue-index.py` generates the JSON from the markdown.
- The loop reads the JSON first (`/carrel-build` skill updated to honor it).
- `AUTONOMOUS_WORK_PLAN.md` remains the authoritative human-readable narrative.

### Test plan

`tests/test_routine_queue_index.py` — parses the markdown, asserts the JSON output matches a known fixture for the current work plan state.

---

## Phase 7 (optional): Operator-set session goal (~30 min, ship-after-validation)

### Goal

Operator can set a session goal at watchdog launch (`CARREL_SESSION_GOAL="ship T64 and surface T65 design questions"`), and the loop's task picker respects it: tasks the goal explicitly names get priority over the next-numbered-pending default.

### Premise

The 2026-05-26 session demonstrated the gap: the operator said "run T64" but the routine had no mechanism to confirm "T64 is the goal." The override block worked but is heavyweight (markdown edit, full justification, supersession of prior blocks). A session goal env var is lightweight.

### Implementation deferred

Scope cut: same as Phase 6. Speculative ROI; re-evaluate after validation test.

---

## Recommended scope cut

**Tier 1 (ship now, ~1.75 hr total):**
- Phase 1: Verdict timeout on audit-gate
- Phase 2: Required-artifact contract on all gate-role agents
- Phase 3: Wedge postmortem `.jsonl` convention

**Tier 2 (ship if time before next validation gate, ~1.75 hr total):**
- Phase 4: Gate-machinery smoke test
- Phase 5: Watchdog orphan-claude detection

**Tier 3 (re-evaluate after T66 validation test, ~1.5 hr total):**
- Phase 6: Programmatic queue index
- Phase 7: Operator-set session goal

### Why this cut

Tier 1 addresses the wedge class we already hit (verdict file missing) plus the prevention pattern (lesson capture). Total cost ~1.75 hr. ROI: every future wedge surfaces in <5 min instead of indefinitely.

Tier 2 closes adjacent gaps without changing the routine's task-picker semantics. Lower priority because they're prevention-only, not correction-only.

Tier 3 changes the loop's behavior (queue index, session goal). Speculative because we don't yet know what the validation test (T66) will surface as bottlenecks. Premature optimization risk.

---

## Verification plan for the whole pass

After Tier 1 ships:

1. `./.venv/bin/python -m unittest tests.test_routine_hooks tests.test_routine_gate_smoke -v` — all pass.
2. Manually backfill the 2026-05-26 wedge into `.claude/logs/wedge-postmortems.jsonl`. File is well-formed JSON-lines.
3. Trigger a synthetic stale-pending by `touch -A -0500 .claude/logs/audits/pending/test-hash.json`, then run any git commit that hashes to `test-hash` — auto-REJECTED file written, gate denies with timeout message.
4. Spot-check each gate-role agent file has the MANDATORY section.
5. Launch the watchdog with `CARREL_MODEL=opus ./script/autonomous-watchdog.sh > /tmp/carrel-watchdog-tier1-test.log 2>&1 &` and let it run on the next pending task (T65 prep or T67 design) for one full iteration cycle. Confirm: no wedge, status memo written on graceful halt, audit verdicts all written.
6. Update `AUTONOMOUS_WORK_PLAN.md` with a new task entry (T68 or rename to fit numbering) marking this work `done`.

After Tier 2 ships:

7. Rename `.claude/agents/independent-auditor.md` to `.broken`, launch watchdog, confirm it refuses to launch via the smoke test failure path.
8. Trigger a poller-kill via the existing `tests/test_watchdog_kill.sh`, plus the extended assertion that any claude process in the worktree is also killed.

After Tier 3 ships (if ever):

9. Generate `AUTONOMOUS_WORK_PLAN.json` from the current markdown. Confirm shape matches the planned schema. Confirm `/carrel-build` skill reads it correctly.
10. Launch the watchdog with `CARREL_SESSION_GOAL="<task>"`. Confirm the task picker honors it.

---

## What "trustworthy hands-off" means after this lands

The operator can:
1. Set a session goal (Tier 3) OR rely on the work plan's natural order (Tier 1).
2. Walk away.
3. Come back to one of three states:
   - **Shipped:** PRs open, status memo summarizes what landed. No surprises.
   - **Operator decision required:** loop halted gracefully with a specific question. No wedge.
   - **Wedge:** loop self-diagnosed, wrote postmortem, auto-REJECTED if applicable, surfaced clearly. Same wedge class never recurs.

Never:
- A silently hung audit-gate.
- An orphaned claude process consuming context.
- A subagent that stopped without producing its required artifact.
- A two-hour debug session for a five-minute fix.

---

## Open questions for operator

1. **Should the wedge-postmortem `.jsonl` be committed to the repo or gitignored?** Recommend commit (lesson travels with code). Mild privacy concern only if the postmortems leak system internals; the wedge class names are generic enough that this is low risk.
2. **For Phase 4 smoke test, is the haiku-tier spawn cost acceptable per watchdog launch?** ~$0.005 per smoke test at current haiku pricing. Run ~30x per day at worst (one per session). ~$0.15/day. Acceptable; document the cost in the watchdog script.
3. **Should Phase 6 (queue index) wait for Phase 7 (session goal), or is each independently shippable?** Independently shippable. Phase 6 unlocks Phase 7 (the session goal references task IDs from the index) but is also useful standalone.

---

## Out-of-scope items captured for follow-up

- **Rubric carve-out for orchestration-only diffs** (the 60/ITERATE result on tonight's diff). Real problem. Separate task; not infrastructure, it's rubric design.
- **Auditor common-pattern memory.** Currently every auditor spawn is fresh-context, which is correct for adversarial independence. A pre-prompt listing "5 most common legitimate non-feature commits" would help but breaks the independence property. Punt.
- **Multi-category rater rubric.** Current rubric assumes feature work. Should support feature / infra / docs / bug-fix categories. Larger scope than this plan.
- **Debate-trigger false-positive review.** One false-positive trigger during the T64 run (regex matched "schema migration" inside an explanatory docstring). Not a wedge, but a noise source. Worth tightening the trigger regex.
