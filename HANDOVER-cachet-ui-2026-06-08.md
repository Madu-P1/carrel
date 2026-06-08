# Cachet UI session handover — 2026-06-08

Worktree: `/Users/madu/Desktop/Codex/.claude/worktrees/zealous-taussig-60b96a`
Branch: `claude/zealous-taussig-60b96a` (off main `36bcbf650`)
Main checkout: `/Users/madu/Desktop/Codex` (serves the demo; see "Two-checkout gotcha")

## Commits landed this session (on the branch, in order)
- `b2e5a0897` feat: port full standalone Cachet UI from `origin/claude/nostalgic-mclaren-93d91a` onto main (CachetRail, LecternView, SourcesView, SettingsView, CommandPalette, source/liveDraft/pendingDraft/commands; dropped `__demo__/`; extended `VerifyView` with additive `docIds`/`autoRun`/`onResolve`).
- `e65cdd11c` fix: never treat a law/regulation citation (C.F.R./U.S.C./EU Directive) as a missing case (was a false "cited case not found"). Routing gate in `deterministic_envelope.py` now runs case-existence only for `kind=="case"`; `local_caselaw._lookup_response` skips non-case cites. Regression test added.
- `ec5670171` fix: rail "Verify" returns to the Lectern (`/`, image-1 landing) instead of `/verify` (VerifyStation, image-2 form); ProvenanceBadge `deterministic` tone green→neutral (brand: no green).

## Current live state
- Demo server running: `http://127.0.0.1:8000` via `./.venv/bin/python script/serve-cachet.py` (nohup; log `/tmp/cachet-serve.log`). Real backend + token `cachet-demo-token` + deterministic + offline.
- The served `frontend/dist` is the worktree's `--mode cachet` build, rsync'd into the main checkout's `frontend/dist`.
- Engine verified unchanged by the UI port (120 engine tests green; the UI port touched zero backend files).

## OPEN ITEMS (priority order)

1. **REPORTED, UNINVESTIGATED — engine "doesn't mark a correct phrase as correct."** Likely BY DESIGN: Cachet certifies traceability to a loaded source, not truth of free prose; no source / no anchor → could-not-check. REAL bug ONLY if: a source was loaded AND the phrase was a verbatim quote from it AND it still didn't verify. NEED FROM OPERATOR: the exact phrase + whether a source was loaded + whether it was a verbatim quote. Then trace the verify-stream verdict for that sentence (quote path: `verbatim_run_present`/`validated_citation_quote`; contract clause retrieval `search_typed_hybrid`; note `EMBED_ON_INGEST=false` leaves no vectors so semantic clause-find is off, but the deterministic quote check reads full doc text and should still match via FTS/substring). Do NOT assume bug until confirmed.

2. **Verify-surface unification (the operator's repeated "false page" complaint, partially addressed).** Two compose surfaces exist: `LecternView` (image 1, bespoke landing, the one the operator wants) and `VerifyStation`/`VerifyView` (image 2, "Check the AI's read of your contract" + CHECKING-AGAINST dropdown). This session pointed the rail "Verify" at `/` so you no longer LAND on image 2 — but after you paste in the Lectern and hit Verify, results still render in VerifyView's surface (image 2 look). The real fix the operator wants: verdicts render inside the Lectern aesthetic and VerifyView's compose form is retired. `LecternView` does NOT use `VerifyView` today; it hands off via `stashPendingDraft` + `navigateTo("/verify")`. This is a genuine multi-file unification, NOT a quick patch — budget it.

3. **Document-upload-to-verify (operator wants it).** The Lectern ALREADY lets you upload the SOURCE/record ("Add the record to check against", `LecternView.tsx` lines ~113-124 via `uploadSource`). What's MISSING: upload the DRAFT ITSELF as a document (vs pasting). Wire `useUploadDocument`/`withProgress` → extract uploaded doc text → set as the draft → verify against the selected record's `doc_id`. Scoped feature.

## REMAINING before this branch can land
- Run the 4 ported `frontend/src/cachet/*.test.*` (vitest) — they typecheck but were never executed; may assert branch-era behavior.
- Full CLAUDE.md verify chain (typecheck/lint/test/build:macos + python ruff/unittest + swift test + benchmarks).
- `onResolve` follow-up: accepted as a reserved prop on `VerifyView` but not wired (the resolve-to-Sources refusal CTA / WorkspaceMargin was intentionally not ported to avoid regressing main's newer VerifyView).
- Reconcile the MAIN-CHECKOUT uncommitted edits (see gotcha) on merge.

## GOTCHAS (cost real rework this session)
- **Two-checkout split.** `serve-cachet.py` serves the MAIN checkout's `frontend/dist` and imports the MAIN checkout backend. The branch lives in the WORKTREE. Workflow used: edit + build in the worktree → `rsync -a --delete <worktree>/frontend/dist/ <main>/frontend/dist/` → relaunch. Engine fixes were applied in BOTH the main checkout (for the live demo) AND mirrored to the worktree (for the commit); the main checkout therefore carries the same uncommitted `services/legal/*.py` + `tests/` edits — reconcile on merge. `script/serve-cachet.py` itself is UNTRACKED repo-wide; it also carries an uncommitted `EMBED_ON_INGEST=false` line (commit `ce74049d0` parity) — commit serve-cachet.py to the repo at some point so `git clean` can't lose it.
- **node_modules:** worktree has a symlink `frontend/node_modules -> <main>/frontend/node_modules` (same commit, identical deps; instant, gitignored — do not commit).
- **Port :8000 churn:** `serve-cachet.py`'s own `_port_is_free` guard false-positives on a TIME_WAIT socket right after a kill. After `pkill -f serve-cachet.py` wait ~8s before relaunch. The Claude_Preview MCP refuses to start if :8000 is already bound and will NOT reuse a non-preview server — to use preview tools, free :8000 first.
- **Read-tool truncation:** a memory hook truncates `Read` to line 1 for some files (but registers them so Edit works). Use `cat`/`sed` via Bash to read those reliably.

## How to run the demo
```
cd /Users/madu/Desktop/Codex/.claude/worktrees/zealous-taussig-60b96a/frontend && corepack pnpm vite build --mode cachet
cd /Users/madu/Desktop/Codex && rsync -a --delete .claude/worktrees/zealous-taussig-60b96a/frontend/dist/ frontend/dist/
lsof -ti tcp:8000 | xargs kill -9; sleep 8
./.venv/bin/python script/serve-cachet.py    # http://127.0.0.1:8000
```

## Memory
Full running state in `~/.claude/projects/-Users-madu-Desktop-Codex/memory/cachet-demo-flow.md` (indexed in MEMORY.md).
