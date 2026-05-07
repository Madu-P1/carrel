# Morning brief — 2026-05-07 autonomous run

## Addendum (after the 16:00 push)

Six more commits landed in a single autonomous block continuing from the original brief:

| Commit | What |
|---|---|
| `3376282b` | DeadlineRail a11y (severity announced via aria-label) + shadow design tokens |
| `53b562e1` | **Stylelint 169 → 0** across all component CSS. Added `--shadow-card`/`--shadow-overlay` and `--color-tour-accent` tokens; rewrote 5 files to use canonical tokens + color-mix |
| `9ec8ac38` | Q3.5 polish: hover-revealed × on manually-added deadline cards (only `feed_kind: "manual"`); display-prefix strip on the rail |
| `ae28e74d` | Fix: deadline ↔ suggestion feedback loop. Coach-spawned "Study — Deadline:" events no longer surface as their own deadlines (STUDY_ALLOCATION_KEYWORDS exclusion + regression test) |
| `_(unhashed)_` | Smart-prefix: only prepend "Deadline:" when the user's wording lacks a keyword. EventBlock strips the prefix for grid display so labels are clean everywhere |

Final gate state: **372 backend tests** + 18 subtests + 1 skipped; **346 frontend tests** across 72 files; **stylelint zero**; **tsc clean**; Swift build clean.

The deadline thesis is now polished end-to-end: add → see in rail → severity in label and color → marker on the day → coach generates study time → accept → deadline doesn't double-count → remove with hover X. Demoable as a coherent product feature, not a stack of disconnected parts.

---



> Single-page summary of what shipped overnight, what's queued, and what to do first when you wake up.

## TL;DR

Carrel's deadline thesis is now fully implemented end-to-end. Students can add a deadline directly in the app (no calendar required), see it on the WORKING TOWARD rail with severity color, see a marker on the corresponding day in the WeekTimeGrid, and the coach automatically schedules study time before it. All gates green: 371 backend tests, 346 frontend tests, tsc clean, Swift build clean.

## What shipped (commits, oldest → newest)

| Commit | Phase | Summary |
|---|---|---|
| `f793fecd` | Pitch | Reframed deck for student/deadline thesis (deck.html + onepager.html + plan + FAQ) |
| `6af8a54f` | Wave 3-5 | Hooks split, lazy routes, dual-Preact fix, prompt-injection suite (~140-file backlog) |
| `e5c22441` | Phase 2 | Upload allowlist 10 → 65 suffixes (single source of truth: SUPPORTED_SUFFIXES) |
| `4d808a0e` | Phase 2 | Word + Excel readers (mammoth + SheetJS, lazy-loaded) |
| `78d87e08` | Phase 2 | DocxReader/ExcelReader file fetches use withLocalApiToken |
| `b2fa9753` | Phase 2 | Token-cache invalidates on 403 + retries; ImportDropzone copy + accept= updated |
| `1c6a9370` | Phase 3 | EPUB + HTML + image OCR verified; audio + video pulled from allowlist (CLI bridge can't host SFSpeechRecognizer) |
| `5d482cc0` | Phase 4 | DeadlineRail + GET /api/plan/deadlines + window.confirm → Dialog |
| `804bea27` | Phase 4 | _rule_deadline_imminent activated in the coach pipeline; score normalization at API boundary |
| `e2df6fad` | Phase 4 | Manual deadline entry — POST /api/plan/deadlines/manual + AddDeadlineDialog + + Add button in the rail |
| `(this run)` | Phase 4+5 | Deadline markers on WeekTimeGrid day headers + coach dedup widened to include source_event_id + test-fixture drift fixed |

12 commits, all atomic, all green at landing.

## Current state of the deadline loop (the wedge)

End-to-end demoable today on a laptop with no calendar setup:

1. Open Carrel → Plan view.
2. Click "+ Add" in the WORKING TOWARD rail.
3. Type "Bio midterm" + pick a date 2 days out.
4. The card appears in the rail (high-severity accent border).
5. The day header on the WeekTimeGrid shows an accent dot.
6. The coach surfaces a 60-min study block at the next free slot, ranked above any SRS-overdue suggestion.

This is the demo a YC partner will respect.

## Repo state

- Branch: `main` (the autonomous loop's policy).
- Tree: clean.
- 371 backend pytest + 1 skipped + 18 subtests passing.
- 346 frontend Vitest passing.
- TypeScript noUncheckedIndexedAccess: true; clean.
- Swift macOS shell builds.

## Known follow-ups (in priority order)

| # | Item | Why it matters | Effort |
|---|---|---|---|
| Q2.9 | Audio transcription via the main app bundle (Info.plist + SFSpeech) instead of the CLI bridge | Lectures are the highest-value student input we don't yet support | 1–2 days |
| Q5.3 | Accessibility audit on Library + Plan + Reader | A11y was deferred during the build push; one pass clears the basics | 2–3 hours |
| Q5.4 | Stylelint design-token violations (~163 remaining) | Reduce drift; design system enforcement | 4–6 hours |
| Q3.5 polish | Manual deadline UI: list + delete affordances on existing manual deadlines, edit-in-place, recurring support | Currently you can add but not see the manual list separately | half a day |
| Phase 4 | Capacitor scaffold for Android (docs/android-strategy.md is the recipe) | Round-funded next step; 6-week implementation plan documented | 6 weeks of focused build |

## First-run hardening (this run)

A stranger opening Carrel for the first time now has a clean path:

- **Dashboard Hero Ask** detects an empty library, swaps suggestion chips for "Import a source" and "Browse the library." Typed questions still work; broken suggestions don't appear.
- **Plan view** always renders the WORKING TOWARD rail with the "+ Add" button, even with zero calendar feeds. The deadline thesis is reachable on cold-start without iCal setup.
- **EmptyPlanState** rewritten to lead with "Start with what's due on Friday" + primary "Add a deadline" CTA; "Connect a calendar" is now the secondary path.
- **EmptyLibrary** already had "Load sample library" backed by `/api/onboarding/demo-library` (3 demo PDFs in `assets/demo-library/`). Verified.
- **ReaderPlaceholder** already had clear copy + "Open Library" CTA. Verified.
- **FirstRunTour** bumped 5 → 6 with a new closing PLAN step. Teaches the deadline thesis (the actual product wedge): "Friday is the unit of work. Add the Deadline that is stressing you out. Carrel surfaces it on the Working Toward rail, marks the day in the week grid, and schedules study blocks backward from it. Imports, citations, and cards above all funnel into it. This is the loop." Progress bar regression fixed (CSS grid was hardcoded to 4 columns). Existing users who completed v5 are auto-prompted on next launch.

## Demo-readiness check (run before any meeting)

```bash
bash script/demo-readiness.sh
```

Eight endpoint checks. Exits 0 → demo confidently. Exits 1 → fix the
red gate before going live. Catches every failure mode the overnight
runs hit at least once: stale token, dead /api/documents, empty plan,
missing deadline rail, broken document detail. Non-destructive
read-only checks; safe to run mid-demo in a side terminal.

## What I would do first this morning

1. **Demo the deadline loop to one human** (anyone — partner, friend, a student you know). Watch them try to add a deadline. Note the first thing they ask. That's the next product cycle.
2. **Send the updated deck.** docs/pitch/Carrel-Investor-Deck.pdf and docs/pitch/Carrel-OnePager.pdf reflect the student/deadline thesis end-to-end. They are ready to send.
3. **Decide on the audio path.** The CLI-bridge approach is documented as wrong (docs/audio-transcription-plan.md). The right path is real but takes 1–2 days of focused Swift work — best done before fundraising conversations get serious because lecture-recording transcription is the most-requested feature once students see the universal-ingest framing.

## Memories saved this run

- `~/.claude/projects/.../memory/carrel_overview.md` — what Carrel is, paths, build commands
- `carrel_architecture_gotchas.md` — token cache, dual-Preact crash, ingestion drift, audio CLI-bridge gotcha, NativeBridge dual-mode, EventKit-wipe pattern, score normalization at boundary
- `carrel_autonomous_loop.md` — heartbeat protocol, scope, what NOT to touch
- `founder_collaboration_style.md` — your standing instructions (no em dashes, "next best recommended action" every turn, parallel execution preferred)

Future sessions read these on boot. Carrel context is now persistent.

## Cron status

- Job `33e52a82` armed: every 30 min at :13 and :43, session-only, expires after 7 days.
- Sentinel `<<autonomous-loop>>` — runtime resolution unverified; if a wakeup fires and the agent stares at the literal string, it will defensively read `AUTONOMOUS_WORK_PLAN.md` and continue.

## Next best recommended action (per your standing instruction)

Open the running app, click + Add in the WORKING TOWARD rail, add a real deadline you actually have this week, and use the resulting study suggestion. Prove the loop on yourself before showing it to anyone else. If anything in that 90-second flow makes you wince, that's the next ticket — and it's a better signal than any sub-task in the queue.
