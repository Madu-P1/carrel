# Anchors-Era Roadmap

**Thesis:** Einstein's atomic unit of learning is the **Anchor** — a piece of evidence with an optional question, an optional claim, and a lifecycle state that can mature into memory. Every highlight, every AI answer citation, every flashcard is a view over the same `anchors` table. Cards, notes, threads, reviews become filtered lenses on one ledger.

**Shipped this session (commits `f89…` → `a1e…`, branch `main`):**

1. **Anchors primitive** (`migrations/0008_anchors.sql`, `services/anchors.py`). Table, CHECK-enforced enums, one-way state machine (`weak → saved → carded → mastered → archived`), CRUD service, 13 tests. Nothing writes to it yet; shipping the shape first is deliberate.
2. **Scope Pill** (`frontend/src/features/ask/components/ScopePill.tsx`). Persistent pill above the Ask prompt shows the corpus choice. Three v1 scopes: Library, Document (searchable), Subject. Opens a popover; closes on Esc / outside-click. Wired to `TutorQueryRequest.doc_id` / `subject_name` — pure client change.
3. **Grounded-only refusal** (`services/tutor.py`, `FallbackAnswer.tsx`). When retrieval falls back from query-specific hybrid to scope-wide and contexts count is below `_WEAK_COVERAGE_MIN_CONTEXTS` (default 3), the tutor refuses with `error="weak_coverage"` instead of calling the LLM on thin evidence. Frontend renders a refusal card with `Broaden to Library` + `Rephrase question` buttons and the nearest passages we did find. Threshold is env-overridable for classroom tuning.

**Verify chain as of this commit:** ruff clean; 18 anchors + tutor + srs backend tests pass; 220 vitest tests pass; `tsc --noEmit` + eslint clean; `vite build` clean.

---

## What's next, in priority order

The numbering matches the "Ship sequence" in the Anchor-era product brief. Each entry names the files it touches, the acceptance criteria, the rough effort, and the biggest risk to plan around.

### Ship 4 — Jobs Tray + pipeline states

**Why now:** Hidden async destroys trust; visible async builds it. Every other ship on this list writes events the tray consumes. Land it next so the rest of the roadmap has a place to show up.

**Acceptance:**
- Top-bar chip shows count of in-flight jobs.
- Click opens a modal with per-job rows + stage pipeline: `Importing → Extract Text → OCR fallback → Indexing → Ready / Partial / Failed`.
- Failed jobs show specific cause + `Retry / Skip / Delete / Open log` actions.
- Stuck jobs show provider status ("Stuck at OCR — Tesseract queue full").
- No silent failures: every stage transition emits a UI event.
- Failed ingests never create orphan documents.

**Files (est):**
- Backend: new `services/jobs/` package (`models.py`, `events.py`, `store.py`). Event stream replaces polling-based status derivation in the ingestion path.
- Backend: `routes/jobs.py` — `GET /api/jobs`, `GET /api/jobs/stream` (SSE), `POST /api/jobs/{id}/retry`, `DELETE /api/jobs/{id}`.
- Frontend: `features/shell/JobsTray.tsx`, `features/shell/JobsRow.tsx`, `features/shell/jobsStore.ts` (signals-based queue subscribed to SSE).
- Frontend: hook the chip into `AppShell.tsx` next to the Commands button.

**Effort:** medium. The SSE plumbing is the biggest unknown; SQLite's polling-via-`WHERE updated_at > ?` is the fallback if `uvicorn --reload` produces flakey SSE during dev.

**Risks:**
- SSE connection churn during frontend HMR. Keep the stream resumable (event id cursor).
- Job rows accumulating forever. Auto-archive rows `> 7 days old + status in (ready, failed-acked)`.

**Unlocks:** ingest pipeline credibility on scanned / long / ugly PDFs — the exact docs students struggle with most. Scope Pill's `readiness` field (currently hardcoded `"ready"`) gets a real data feed.

---

### Ship 5 — Evidence Inspector with page anchors

**Why now:** The single most consistent trust pattern across competitors, and the Anchor primitive's first real UI surface. Every citation chip from the tutor, every highlight, every Anchor Column row leads here.

**Acceptance:**
- Hover on any citation chip → compact preview card (source + page + 1-3 line quote + confidence). <100ms render.
- Click → narrow right-rail panel; PDF scrolls to anchor and passage flashes briefly.
- Approximate anchors are explicitly marked ("approximate location — open OCR text").
- Actions per anchor: copy quote / open page / **promote to Anchor** (creates a `saved` anchor via `anchors_service.create_anchor`) / restrict scope to this source / show other Anchors on this page.
- ≥95% exact anchor accuracy on clean-text PDFs.
- Every answer paragraph has ≥1 clickable evidence object OR an explicit refusal.

**Files (est):**
- Backend: extend retrieval to return `bbox` and `text_offset_start/end` when the source has them (pdfjs text-layer cache). New resolver `services/anchors/resolver.py` with the fallback hierarchy: `bbox → text-offset → nearest-paragraph → page-level`.
- Frontend: `features/reader/EvidenceInspector.tsx` + `.module.css`. Wire into `useCitationFlight` — the inspector replaces the ghost flight's terminal state.
- Frontend: `features/ask/CitationChip.tsx` — hover-preview upgrade from Tooltip text to a richer preview card.

**Effort:** medium-large. The bbox/text-offset resolver is where most of the risk is.

**Risks:**
- Bad anchors erode trust faster than missing anchors. Ship with confidence labels and explicit approximate-anchor states. Never claim exact when you're guessing.
- Cross-PDF coordinate variance — bbox is in PDF points, some PDFs have weird page transforms. Use pdfjs's `getTextContent()` offsets when bbox drifts.

**Unlocks:** the full Anchor promotion flow (next ship). Trust brand. Citation chip hover previews become honest instead of advisory.

---

### Ship 6 — Anchor Model writers + Card Draft Drawer

**Why now:** The primitive exists (ship 1). Nothing writes to it yet. This ship turns the primitive into the product.

**Acceptance:**
- Highlighting in the Reader auto-creates a `weak` anchor (no modal, no friction). `origin='highlight'`, `bbox` + `text_offset_*` populated.
- Every AI answer citation creates a `weak` anchor on the fly (`origin='ai_answer_citation'`, `thread_id` set).
- Right-click on a highlight or AI claim: `Make card / cloze / 3 cards / Save for later`.
- Card Draft Drawer: batch UI for promoting `weak`/`saved` → `carded`. Each draft shows type (basic/cloze/Q&A), front/back, quote preview, strength flag (`good / too long / duplicate-ish / ambiguous`), source citation.
- One-click save-all or per-draft reject/edit.
- Near-duplicate detection before save (jaccard on normalized quote_text against existing cards with the same document_id).
- Every saved card carries source metadata (doc_id, page, quote, origin). The srs_cards row AND the anchors row are linked atomically via the `transition_state(... 'carded', srs_card_id=...)` helper already shipped.

**Files (est):**
- Backend: `routes/anchors.py` — `POST /api/anchors` (create), `POST /api/anchors/{id}/transition` (state machine), `GET /api/anchors/document/{doc_id}`.
- Backend: `services/anchors/promotion.py` — anchor → card promotion flow. Reuses `study_service.create_card` + `anchors_service.transition_state`.
- Frontend: `features/reader/selection/HighlightCreator.ts` — text-layer selection → anchor create.
- Frontend: `features/anchors/CardDraftDrawer.tsx` — the drawer UI.
- Frontend: `features/anchors/AnchorColumn.tsx` — the rail that shows per-page anchors (scaffold; full UI in a follow-up).

**Effort:** large. This is where the product takes shape. Plan for two focused sessions.

**Risks:**
- Low-quality AI card drafts pollute decks. Flagger heuristics (too-long back, ambiguous front, semantic near-duplicate) ship in the drawer so users triage, not author.
- Preact reconciliation with many live anchors on one page. Memoize per-anchor rows and virtualize past 50 visible.

**Unlocks:** every downstream read-to-retain feature. This is the "the promise made real" release.

---

### Ship 7 — Demo Library + 60-second quickstart

**Why now:** First-session conversion dominates study-app retention. Ship once the core loop (scope → ask → refuse-or-answer → promote) is real enough to demo.

**Acceptance:**
- App opens to a bundled Demo Library with three documents: one clean PDF, one table-heavy PDF, one scanned PDF. The scanned one deliberately shows OCR + the Jobs Tray's `still_indexing` / `needs_ocr` states so the user sees capability boundaries up front.
- Scripted tour (dismissable): highlight → ask → inspect → promote → exit.
- New user sees a cited answer and saves their first Anchor in <60s.
- "Your files live here on disk. Export anytime." reassurance closes the tour.

**Files (est):**
- Ship three PDFs under `macos-app/Resources/demo-library/`.
- Backend: `services/onboarding/seed.py` — idempotent seeder that skips if the user already has documents.
- Frontend: `features/onboarding/QuickstartTour.tsx` — overlay with four steps tied to real DOM targets.
- Frontend: "Load sample library" button wired into `LibraryEmptyState.tsx` (the empty-state UI already has the slot).

**Effort:** small-medium. Most of the work is choosing the right three PDFs and writing the tour copy.

**Risks:**
- Demo PDFs shipping in the bundle bloat `macos-app/Resources`. Budget 3-5 MB total. Scanned demo can be a 2-page excerpt.
- Tour gets stale fast. Version-tag the tour text with the app version; bump it when any of the four steps change DOM.

**Unlocks:** credible onboarding story for every marketing channel. Kills the cliff that plagues Anki, Readwise, Obsidian.

---

### Ship 8 — Backlog Relief Suite

**Why now:** Anki-level punishment is the #1 reason students abandon SRS tools (verified across 9 competitors in the prior review round). Einstein's chance to be *less punishing, still serious*.

**Acceptance:**
- Daily load cap configurable ("80 due, 40 minutes — Einstein suggests Chapter 5 first").
- One-key archive / snooze on any due card.
- "Catch up on overdue only" mode.
- Pressure Dashboard: red/yellow/green per subject on the dashboard.
- Plain-language scheduler explanations on demand ("This is due today because you last saw it 4 days ago and got it wrong twice").
- Streak tracking that rewards consistency but doesn't punish skips — displayed as a streak ribbon but not a guilt ribbon.

**Files (est):**
- Backend: `services/study_schedule.py` — daily-load calculator. Uses existing srs_cards.due_date + lapses.
- Backend: `routes/study.py` — new endpoints: `POST /api/srs/cards/{id}/snooze`, `GET /api/srs/catchup`, `GET /api/srs/pressure`.
- Frontend: `features/study/BacklogPressure.tsx` — dashboard chip + in-session.
- Frontend: extend StudyView intro to offer "Catch up only" mode.

**Effort:** medium.

**Risks:**
- "Pressure without punishment" is a taste line. User testing will decide. Start conservative: explicit green zone at `<15 due`, yellow at `15-60`, red at `>60`.
- Snoozing too many cards tanks learning. Cap snoozes to 3 per card lifetime; after that the card auto-promotes to `archived`.

**Unlocks:** confident adoption by students who bounced off Anki. Opens the path to Exam Mode.

---

### Ship 9 — Smart Collections + saved scope views

**Why now:** Cross-document study is where NotebookLM is weakest. Einstein must win it cleanly without becoming a PKM graph. Builds on Scope Pill: a Collection is just a named scope with a filter spec.

**Acceptance:**
- Saved scopes ("AP Bio — Exam 2", "Scanned chemistry", "Unedited AI drafts").
- Auto-smart collections populated by filters (subject=X AND file_type=pdf AND has_ocr=true).
- Pin a collection as active scope for a session; every question, anchor, review binds to it.
- Smart Collection surfaces in the Scope Pill's "Collection" level (currently disabled in the pill's v1).
- Cross-Anchor search: "show me every Anchor mentioning the Calvin cycle across every doc I've read."

**Files (est):**
- Backend: `migrations/0009_collections.sql` — `collections` + `collection_documents` tables.
- Backend: `services/collections.py` — create/update, smart-query evaluator.
- Backend: `routes/collections.py`.
- Frontend: `features/library/CollectionsPanel.tsx`, `features/ask/ScopePill.tsx` (extend with Collection option).

**Effort:** medium.

**Risks:**
- Smart Collections can turn into a query-builder UI nightmare. Ship with three canned filter templates ("unread in subject X", "recently ingested", "AI-drafted unreviewed") and a raw-filter escape hatch. Full query builder after user signal.

**Unlocks:** Exam Mode, cross-Anchor search, exportable study sets, classroom sharing experiments.

---

### Ship 10 — Export + Import Hub

**Why now:** Portability is both reassurance and migration — both are growth levers. The competitive review showed every mature competitor either has export (Readwise) or suffers for not having it (NotebookLM).

**Acceptance:**
- Export center: Markdown, CSV, Anki `.apkg`, PDF-with-annotations, library ZIP.
- Import wizard: Anki decks, Kindle highlights, Readwise JSON, Markdown.
- Duplicate resolution on import (merge / keep-both / skip per row).
- Every export shows exactly what's included, with preview, before the file hits disk.

**Files (est):**
- Backend: `services/export/` package with a format adapter per target. Anki `.apkg` is the highest-leverage (SQLite-in-zip format is well-documented).
- Backend: `services/import/` similarly.
- Backend: `routes/portability.py` — `POST /api/export`, `POST /api/import`.
- Frontend: `features/settings/PortabilityHub.tsx`.

**Effort:** medium-large. The Anki `.apkg` format is the longest implementation.

**Risks:**
- Round-trip fidelity. Shipping an import that loses data silently is worse than not shipping. For every import path, stream the skipped/lossy rows into a plain-text diff the user must acknowledge before commit.
- Anki media (audio, images) import. Defer to v1.1; v1 imports text-only cards.

**Unlocks:** growth from Anki deck-sharers, Readwise expats, Kindle readers. Migration is a major marketing channel.

---

## Deliberately not on this list

Per the brief's Anti-Goals:

- **Plugin SDK / marketplace.** Integration is the moat. If a feature matters, it's core. Revisit only after the core loop is loved and a clear, bounded extension point emerges.
- **Full PKM graph** (backlinks, graph view, transclusion, daily-notes). RemNote's trap. Structure serves retention, not graph aesthetics. If ever, constrain linkage to the Anchor level ("Anchors cited together in 3+ answers"), never document-level ontology.
- **Mind maps / infographics / slide decks / podcasts.** NotebookLM's Studio features are marketing, not learning. Revisit only after the core evidence → Anchor → review loop ships fully.
- **Multi-user / social / classroom.** Shared Anchors pilot (Section 6 experiment) is a disciplined one-off, not a feature pillar yet.
- **iOS companion.** Audio queue (Section 3) is the natural first mobile surface; push-only review would be the natural second. Full companion app is a v2 commitment, not a v1 distraction.
- **Exam Mode** (Section 6.1), **Ghost Questions** (6.2), **Coverage Heatmap** (6.3), **Anchor Revisit** (6.4), **Shared Anchors** (6.5). All are experiments worth running AFTER the 10-ship sequence lands and we have beta users. Prioritize in that order based on what users ask for unprompted.

---

## Dependency graph (for concurrent work planning)

```
┌─ Ship 1 (Anchors table)  ────────────┐
│                                       │
├─ Ship 2 (Scope Pill)    ──────┐       │
│                                │       ▼
├─ Ship 3 (Refusal UX)    ──────┤    Ship 6 (Anchor writers + Drawer)
│                                │       │
├─ Ship 4 (Jobs Tray)     ──────┤       ├─ Ship 8 (Backlog Relief)
│                                │       │
├─ Ship 5 (Evidence Inspector) ──┘       ├─ Ship 9 (Smart Collections)
│                                        │
├─ Ship 7 (Demo Library) ◄───────────────┘
│
└─ Ship 10 (Export/Import) ◄───────────── Ship 6
```

Ship 1, 2, 3 are done. Ship 4 (Jobs Tray) is the next foundation — it feeds the `readiness` indicator in the Scope Pill (ship 2) and is the place where ingest failures become visible (ship 5, 7). Ship 5 (Evidence Inspector) + Ship 6 (Writers + Drawer) are the "product takes shape" pair. Ship 7 (Demo Library) should land after ship 6 so the tour has a real Anchor to create. Ship 8-10 are parallel-safe after ship 6.

---

## Open questions worth deciding before ship 4

1. **Retention of raw bbox data.** pdfjs text-layer bboxes change per render. Do we store at ingest-time (constant) or at first-anchor-creation-time (lazy but potentially drifty)? Recommendation: ingest-time, with a version stamp in `documents.parser_version` so we can detect + re-anchor if pdfjs upgrades break us.
2. **Thread ID source.** Ship 1's schema has `thread_id` as a free string with no FK. Should Ask-level threads get their own table now? Recommendation: defer until AI-answer Anchors exist (ship 6); in-memory thread id assigned by the tutor service is enough until then.
3. **Anchor archival vs delete.** Schema allows both (`archived` state + hard `delete_anchor`). User-facing delete hits which? Recommendation: archive-by-default, hard-delete only from a Settings → Privacy surface so the user has to opt into irreversible removal.
4. **Orphan anchors (no concept, no card).** We already allow concept_id NULL for orphan srs_cards (the prior fix). Anchors follow: no concept_id column by design. This is correct per the brief's anti-goal on PKM ontology.

Punt all of these to the ship they matter for rather than front-loading now.
