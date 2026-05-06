# Carrel — Autonomous Overnight Work Plan

> Single source of truth for the autonomous work loop. Each wake-up: read this file, do the next task in the queue, update progress + queue, schedule next wake-up. Do not skip the update step — if the loop drops, the next session needs to pick up from here.

## Standing context (do not re-derive)

- **Repo:** `/Users/madu/Desktop/Codex` (Carrel — NOT the IAF worktree).
- **Branch policy:** work on `main` directly. Commit every meaningful chunk. Never force-push.
- **Reframed positioning (per founder, 2026-05-07):** Carrel is a *universal-ingest study workspace for students* with deadline-driven planning as the wedge. NOT a PDF research tool. The Reader is one mode; the Plan + SRS + Calendar coach loop is the heart. Files = anything (PDF, slides, EPUB, docx, audio, video transcripts, OCR, web, code, screenshots).
- **Build constraints:** macOS app today, Android next. No breaking changes. Tests must stay green. Each commit must build.
- **Founder is asleep.** Do not ask questions; make decisions, document them, and move on. Bias toward additive changes over rewrites. If genuinely blocked, write the question into `BLOCKERS.md` and skip to next task.

## Heartbeat protocol

Every wake-up:
1. `cd /Users/madu/Desktop/Codex && git status` — confirm clean tree.
2. Read this file. Pick the top-of-queue task.
3. Execute it. Run the relevant gate (tsc, vitest, pytest, swift build) for what you touched.
4. Commit with a descriptive message. Format: `[autonomous] <area>: <change>`
5. Update this file: move task to "Done", add anything new to "Queue" or "Discovered".
6. Schedule the next wake-up via ScheduleWakeup (45 min default). Use the `<<autonomous-loop-dynamic>>` sentinel.
7. End the turn.

If a task fails irrecoverably: write to `BLOCKERS.md` with file + line + the exact error + a suggested fix. Skip and continue.

## Scope (what is in / out)

**IN:**
- Reframe pitch artifacts (deck.html, onepager.html, FAQ.md, PITCH_PLAN.md) for student / time-mgmt / universal-file thesis.
- Audit and shore up universal file ingestion (extend beyond PDF).
- Strengthen Plan/Deadlines/SRS UX in the existing app.
- Begin Android readiness — research, write a `docs/android-strategy.md`, identify the cleanest path (Capacitor wrap of existing web bundle vs Tauri vs separate React Native app).
- Add tests as you go. Never reduce coverage.
- Polish: design system gaps, accessibility passes, copy.

**OUT:**
- Touching IAF (`/Users/madu/Downloads/Claude Code/`).
- Major architectural rewrites without leaving a written rationale.
- Anything that requires a paid API key the founder hasn't already configured.
- New external dependencies without a written justification in commit message.

## Queue (top → bottom = priority)

### Phase 1 — reframe the pitch (DONE 2026-05-07 ~01:18)

- [x] Q1.1 Audited ingestion: 10 file types live (csv, docx, md, markdown, pdf, pptx, tsv, txt, xls, xlsx). Universal-ingest claim is honest today. Source: `services/uploads.py:10-21`.
- [x] Q1.2 Deck slides 1, 2, 3, 4, 7, 8, 10, 12 rewritten for student/deadline thesis. Competition table headers now: Deadline planning / Universal ingest / Spaced review / Cited answers. New competitor set: Notion AI / Quizlet / NotebookLM / ChatGPT Study Mode.
- [x] Q1.3 Onepager fully rewritten with same reframe.
- [x] Q1.4 PITCH_PLAN/FAQ updates queued for Phase 1.5 — done in same commit.
- [x] Q1.5 Both PDFs re-exported (deck 478KB, onepager 224KB).
- [x] Q1.6 About to commit.

### Phase 2 — universal file ingestion (the table-stakes gap) — MOSTLY DONE

- [x] Q2.1 Audit complete. **Massive find:** 15 parsers exist (PDF, DOCX, EPUB, HTML, image, audio, video, RTF, JSON, etc.) but upload allowlist gated to 10. Source-of-truth fix: `services/uploads.py:ALLOWED_SUFFIXES = SUPPORTED_SUFFIXES - {".zip"}`. Now 65 extensions reachable from upload. Tests pass (7 upload-security + 29 dedupe).
- [x] Q2.2-Q2.5 Reframed: zero new parser code needed. The table-stakes were already coded; only the gate was wrong.
- [ ] Q2.6 Frontend ImportDropzone copy update: list new categories ("PDFs, slides, docs, EPUB textbooks, audio lectures, photos of notes, web articles"). Defer to next loop iteration.
- [ ] Q2.7 NEW: manually test EPUB + audio + image upload end-to-end on the running app. Defer to next iteration.
- [ ] Q2.8 NEW: zip-extraction safety pass so `.zip` can be allowed too (per-entry size cap, format-validation per extracted file). Lower priority.

### Phase 3 — Plan / Deadlines / SRS heart-of-product polish

- [ ] Q3.1 Audit PlanView.tsx + Sessions + Review Queue. List every TODO, every gap, every coarse edge.
- [ ] Q3.2 Implement the top 3 polish items.
- [ ] Q3.3 Add a "Deadlines" first-class concept if it doesn't exist (calendar event linked to a source/concept with target mastery date).

### Phase 4 — Android readiness

- [ ] Q4.1 Read DESIGN.md, CLAUDE.md, frontend architecture. Identify what's macOS/file://-coupled and what's portable.
- [ ] Q4.2 Investigate the three viable paths: (a) Capacitor wrap of existing Vite bundle into Android Studio project, (b) Tauri Mobile (alpha), (c) separate React Native app talking to the same FastAPI backend.
- [x] Q4.3 `docs/android-strategy.md` written. Decision: Capacitor wrap. Trade-off matrix vs Tauri Mobile and React Native included. 6-week implementation plan documented. Backend hosting decision recorded.
- [ ] Q4.4 If Capacitor is the call: prototype the wrap. Just see if it boots.

### Phase 5 — Quality gates push (toward 95)

- [ ] Q5.1 Run the full verify chain. Document every failure.
- [ ] Q5.2 Fix the top 5 type/lint/test failures discovered.
- [ ] Q5.3 Audit accessibility on Library + Plan + Reader. Add aria/keyboard fixes as needed.
- [ ] Q5.4 Check stylelint design-token violations. Reduce them.

### Phase 6 — Founder morning brief

- [ ] Q6.1 Once Phase 1+2 are done at minimum, write `MORNING_BRIEF.md` summarizing: what shipped, what's queued, any blockers, recommended next action for the founder.

## Done

(none yet — populate as you go)

## Discovered (out-of-scope but worth flagging)

(use mcp__ccd_session__spawn_task for these if appropriate, or list here)

## Blockers

(see BLOCKERS.md if any)

## Decisions made autonomously (justify each)

(format: `YYYY-MM-DD HH:MM | decision | rationale`)
