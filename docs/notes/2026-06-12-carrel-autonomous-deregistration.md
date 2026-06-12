# Carrel autonomous machinery de-registered (2026-06-12)

Part of the jarvis-upgrade subtraction pass (B2, `~/jarvis-upgrade/03-blueprint.md`).
The Carrel autonomous routine was retired 2026-05-30; Forge
(`~/.claude/skills/forge/`) supersedes the entire design. This commit removes
the dead wiring; everything remains recoverable from git history.

## Removed

- Hook registrations in `.claude/settings.json`: `route-task.py`
  (UserPromptSubmit), `audit-gate.py` + `debate-trigger.py` (PreToolUse
  Bash|Edit|Write), `worktree-isolation.py` (PreToolUse Write|Edit|MultiEdit),
  `score-loop.py` (Stop + SubagentStop). All were env-gated on
  `CARREL_AUTONOMOUS=true` and dormant, but each exec'd a Python process per
  matched tool call in every session, and `audit-gate.py` had one observed
  live-fire collision with Forge tests (memory: forge-test-host-gate-collision).
- `script/start-autonomous.sh`, `script/autonomous-watchdog.sh` (armed and
  supervised the retired `/carrel-build` routine).

## Kept

- `.claude/hooks/obsidian-sync-nudge.py` — live and useful; its Stop
  registration stays. (Being promoted to a user-level hook; the project-level
  registration will be dropped only after the global one is verified.)
- The hook `.py` files themselves stay on disk for reference; only the
  registrations and launcher scripts are gone.

## To re-arm (if ever)

`git log --follow script/start-autonomous.sh` and restore from history —
but use Forge instead; it covers the same ground with stronger isolation
(Seatbelt sandbox, deterministic held-out gate, overnight watchdog).
