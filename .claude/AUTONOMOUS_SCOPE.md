# Autonomous Routine Scope

> Operator-set constraints on what the `/carrel-build` autonomous routine is allowed to do without human approval. Lift any of these by editing this file (operator audit trail in git history) AND updating the corresponding hook code.

## In scope (build-only)

The routine CAN, without operator approval per task:

- Read any file in the repo.
- Write code, tests, migrations, docs.
- Run the canonical verify chain (`CLAUDE.md` §"Verify chain").
- Open feature branches off `main`.
- Open pull requests against `main` with descriptive bodies.
- Admin-merge its own PRs after rater scores 100 and CI is green.
- Delete the merged branch (`gh pr merge --delete-branch`).
- Pull main locally and stay in sync.
- Run evals (`evals/run_evals.py`) and benchmarks (`benchmarks/phase0.py`).
- Spawn subagents (auditor, quality-rater, debate proponents/adversary/synthesizer) when budget allows.
- Update `AUTONOMOUS_WORK_PLAN.md` task statuses (`pending` → `in_progress` → `done` / `blocked`).
- Write closeout logs to `.claude/logs/closeout-{date}.md`.

## Out of scope (require operator approval)

The routine MUST NOT, without operator lifting the constraint:

- Send any DM, iMessage, Slack message, email, or other outbound communication.
- Post to social media or recruitment platforms (LinkedIn, X, etc.).
- Make external HTTP POST/PUT/DELETE to non-localhost endpoints (except Stripe test mode via the documented webhook + checkout flow once Phase 23 lands).
- Force-push to `main` or any open-PR branch.
- Delete a remote branch that isn't a successfully-merged PR's source.
- Modify `main` directly (always via PR).
- Modify the `.gitignore` to gitignore files that aren't operator-local tooling.
- Modify `.claude/hooks/*.py` (those gates are sacred — operator owns them).
- Modify `.claude/AUTONOMOUS_SCOPE.md` (this file).
- Modify `.claude/RATER_RUBRIC.md`.
- Run any script under `script/` whose name contains `delete`, `purge`, `drop`, or `destroy`.
- Run `rm -rf` against any path outside `.claude/logs/` and `data/benchmarks/latest.json`.
- Execute Stripe production-mode API calls. Test mode only until operator flips an env var documented in a future PR.

## Patterns enforced by hooks

`.claude/hooks/audit-gate.py::OUTREACH_BASH_PATTERNS` denies any Bash command matching:

- `mail|sendmail|mutt|mailx`
- `osascript` referencing Messages / Mail / Slack
- `curl` to slack/telegram/discord/twitter/x/linkedin/mailchimp/sendgrid/postmark/resend/convertkit/mailerlite/twilio webhook hosts
- twitter-cli, `tw post`, `tw tweet`
- generic external POST/PUT/DELETE to non-localhost (the new pattern as of 2026-05-12)

`.claude/hooks/audit-gate.py::DESTRUCTIVE_BASH_PATTERNS` denies (until auditor writes APPROVED with full 5-field rollback-plan etc.):

- `rm -rf` against `/`, `$HOME`, `~`, `/Users`
- `git push --force` (any variant, especially against main/master/production)
- `DROP TABLE`, `DROP DATABASE`, `DROP SCHEMA`
- `TRUNCATE TABLE`
- `gh pr merge` (yes — even merges go through the auditor)
- `npm publish`, `pnpm publish`, `cargo publish`
- `docker push` / `docker tag` to `:latest` or `:prod`

## HALT mechanics

To stop the routine cleanly mid-run:

1. `touch /Users/madu/Desktop/Codex/.claude/HALT`
2. The score-loop hook sees the file on the next Stop event and emits a system message; the routine finishes its current iteration, writes status, and exits.
3. To resume: `rm /Users/madu/Desktop/Codex/.claude/HALT` then re-invoke `/carrel-build`.

To stop instantly (rare):

1. Kill the watchdog: find the PID via `ps aux | grep autonomous-watchdog` and `kill <PID>`.
2. Or close the controlling terminal session.

To pause without losing in-progress task state:

1. `touch /Users/madu/Desktop/Codex/.claude/HALT`
2. The current iteration writes `in_progress` to the work plan with notes.
3. Resume: `rm .claude/HALT && /carrel-build`. The routine picks up the `in_progress` task and continues.

## Per-session controls

Environment variables the routine respects:

- `CARREL_AUTONOMOUS=true` — required to activate any of the hooks; if unset, the routine acts as a normal interactive Claude session with no gates.
- `CARREL_RUN_AFM_INTEGRATION=1` — opts in to the AFM real-bridge integration test (requires macOS 26+ Apple Silicon + en_US locale + built bridge).
- `CARREL_AFM_MAX_CHUNKS=4` — AFM context-window discipline (chunks per prompt cap). Default 4.

## Operator-visible logs

- `.claude/logs/audits/pending/*.json` — actions denied by audit-gate awaiting auditor review.
- `.claude/logs/audits/approved/*.json` — auditor approvals (with the 3-or-5 required fields).
- `.claude/logs/audits/rejected/*.json` — auditor rejections with counter-proposals.
- `.claude/logs/debates/triggers.jsonl` — architectural-debate trigger events.
- `.claude/logs/scores/*.json` — quality-rater scores per task.
- `.claude/logs/operator-followups.jsonl` — surfaced moments that need operator attention (e.g., outreach attempts, blocked tasks).
- `.claude/logs/closeout-{date}.md` — written when queue is empty.

## When to expand scope

Reasonable times to lift constraints (and the corresponding edit):

- "I want the routine to send the recruitment DMs" → restore `docs/outreach/README.md` framing AND edit `OUTREACH_BASH_PATTERNS` to exclude the relevant providers. The operator-followups log will tell you which providers triggered.
- "I want the routine to publish to npm" → remove `npm publish` from `DESTRUCTIVE_BASH_PATTERNS`. Add a per-package version-bump guard before allowing.
- "I want the routine to force-push to a feature branch" → narrow the destructive force-push pattern from "any force-push" to "force-push to main/master/production only". The routine can then force-push to its own feature branches.

Whenever scope shifts, append a row to a new `## History` section at the bottom of this file with date, change, and rationale.

---

## History

| Date | Change | Rationale |
|------|--------|-----------|
| 2026-05-12 | Initial scope (build-only, no outreach) | Operator decision to keep the routine narrowly scoped during first multi-week run |
| 2026-05-17 | OUTREACH_BASH_PATTERNS expanded to include generic external POST/PUT/DELETE | Self-audit found gaps; covers webhook hosts the original pattern missed |
| 2026-05-18 | This file written | Documents the existing constraints + provides operator handle for future changes |
| 2026-05-19 | Max-autonomy directive: no voluntary halts on self-resolvable ambiguity | Operator decision after reviewing T01-T03 loop output. The loop voluntarily halted on T03 over a PR-strategy question and a column-name ambiguity in the acceptance text, both of which were self-resolvable. Strengthened `.claude/commands/carrel-build.md` decide-and-proceed contract with a "Things that are NEVER reasons to voluntarily halt" section. Expanded Bash allowlist in `settings.local.json` so the harness never prompts the operator during loop runs. Encoded the two T03 decisions (branch fresh off main; chunk→node page-level translation is acceptable) in the `Operator decisions` header of `AUTONOMOUS_WORK_PLAN.md`. Outreach + destructive gates unchanged. |
| 2026-05-19 | Skill-orchestration pre-action routine mandatory for non-trivial tasks | Operator directive: before any substantive action the loop must (1) state the desired outcome in one sentence, (2) scan available skills, (3) score skill combinations against the outcome, (4) pick 1-3 skills, (5) log the decision to `.claude/logs/skill-orchestration.jsonl`, (6) run the skills inline as part of the task. Default pattern table added to `.claude/commands/carrel-build.md` step 2. Sub-decision skill check added at step 2.5. Rater rubric criterion D extended with two new -5 violations: skipped orchestration on a non-trivial task, and wrong skill combination for the task type. Trivial tasks (formatting, status flip, doc reconciliation that adds no claims, removing provably-dead code) may set `chosen_skills: []` with a populated `skipped_reason`. |
| 2026-05-19 | audit-gate read-only allowlist + heredoc-strip-before-hash | Operator-owned refinement of `.claude/hooks/audit-gate.py` addressing two auditor follow-ups raised in `.claude/logs/status.md` 2026-05-19. (1) Narrowed `MAJOR_BASH_PATTERNS` so `gh pr list|view|checks|status|diff`, `gh issue list|view|status`, `gh release list|view`, `gh workflow list|view` no longer fire the auditor (they are inherently read-only). Same for `git merge-tree`, `git merge-base`, `git merge-file`, `git rebase-todo` — the `\s+` after `merge`/`rebase` excludes hyphenated variants the prior `\b` accepted. (2) The hashed command now passes through `_strip_heredocs` before hashing, so commit-message bodies with timestamp variance no longer force re-audits of identical outer commands with identical staged diffs. `staged_diff_hash` still disambiguates commits by content. Verified by 21 regex cases + 3 hook tests still green + a heredoc-stable-hash spot check. Destructive + outreach gates unchanged. |

*Last updated 2026-05-19.*
