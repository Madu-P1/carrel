<!-- /autoplan restore point: ~/.gstack/projects/Codex/feat-companion-on-main-autoplan-restore-20260509-210617.md -->
# Carrel Flashcards — Focus Mode + Real-Value Upgrade

**Date:** 2026-05-09
**Surface:** `frontend/src/features/study/`
**Trigger:** User reported (1) cannot flip a card back to re-read the question once revealed, (2) typography on the cards is "very displeasing," and (3) the broader sense that the flashcard feature does not yet feel like something a user would *value*, not just tolerate.

## Current state — what actually exists

- **`FlipCard.tsx`** — well-built parent-driven component. `flipped: boolean` + `onFlip?: () => void`. Both faces rendered always; CSS `transform: rotateY(180deg)` flips the inner. Click + Space + Enter all wired. `aria-pressed` + `aria-label` reflect state. **This component is not the bug.**
- **`StudyView.tsx`** wires it (lines 399-428):
    ```tsx
    flipped={phase === "back"}
    onFlip={phase === "front" ? revealAnswer : undefined}
    ```
  After reveal, `phase = "back"` and `onFlip` becomes `undefined`. The click handler is *deliberately* nulled. The card's accessibility label still claims "Activate to hide" — **the UI promises a thing the code refuses to deliver**.
- **`revealAnswer()`** is one-way: `front → back`. There is no `hideAnswer()` or `toggleFlip()`.
- **`StudyFocusOverlay.tsx`** — full-viewport liquid-glass overlay. Esc closes. Looks reasonable; the user did not complain about the overlay frame, only about the card inside it.
- **Card faces** in `StudyView.tsx`:
    - Eyebrow: `{concept} · {document_name}` in `--font-mono` style (per `.cardEyebrow`).
    - Question: `<Text variant="h1" weight="semibold">` — heavy and large.
    - Hint: "Press space or click to reveal" inline below question.
    - Answer face: plain `<Text>` — *much smaller and lighter than the question*. Asymmetric typography. The visual weight inverts when you flip, which feels jarring.
- **`RatingRow.tsx`** — colour-graded buttons (red Again → amber Hard → green Good → teal Easy). Numeric shortcut badge. Clean.
- **Keyboard:** Space/Enter reveals when on front. Numbers 1-4 rate when on back. **No keystroke flips back.**

## Diagnosis — the actual gap

Carrel's flashcard surface today behaves like *Anki without the polish*. It enforces Anki's "no take-backs" semantics (once you flip, you must rate) but presents none of Anki's compensating affordances (no peek mode, no quick edit, no hint progression, no source-grounding view, no time-to-completion estimate, no rich card types). The design takes the constraint without the value.

Worse, the visual treatment of question vs answer is unbalanced: question dominates with H1-semibold typography while answer renders as body text. This makes the answer feel like a footnote to the question rather than the *thing being learned*.

The user's complaint is correct on both fronts. The fix is not just a bug patch.

---

## The plan — six PRs, each independently shippable

Order is: bug-first (PR 1), visual-truth (PR 2-3), Carrel's wedge made real (PR 4), feature breadth (PR 5-6).

### PR 1 — Restore bidirectional flip (~1 hour)

**Files:** `frontend/src/features/study/StudyView.tsx`, `frontend/src/features/study/components/FlipCard.tsx` (no change), `frontend/tests/study/flip-card.test.tsx` (regression test).

**Changes:**
1. Add `toggleFlip()` that swaps `phase` between `"front"` and `"back"` both directions.
2. Wire `onFlip={toggleFlip}` unconditionally regardless of phase.
3. Extend keyboard handler: Space/Enter toggle in either direction (currently only reveals).
4. Keep `RatingRow` rendering tied to `phase === "back"` so rating only appears when answer is visible — that semantic is correct and doesn't conflict.
5. `aria-label` on FlipCard already handles both directions correctly; no change needed.

**Test:** add `tests/study/flip-card.test.tsx` case: render in `phase="back"`, click the card, assert `phase === "front"`. Currently 0 such test exists; if I introduce regression later it'll be caught.

**Why first:** smallest change, biggest UX win, unblocks the tester complaint immediately.

### PR 2 — Card typographic redesign (~1 day)

**Files:** `frontend/src/features/study/StudyView.module.css`, new `frontend/src/features/study/components/FlashcardFace.tsx` extracted from inline JSX in StudyView.

**The problem:** front uses H1-semibold; back uses plain body. Asymmetric weight makes the *question* feel like the protagonist and the *answer* feel like a footnote — the inverse of how learning actually works.

**Changes:**
1. Extract front + back rendering into a `FlashcardFace` component with `kind: "question" | "answer"`.
2. Define a flashcard-specific type scale that's separate from the generic design-system text:
    - `--flashcard-question`: 28px / 1.3 / weight 500 (medium, not semibold) — readable but doesn't dominate
    - `--flashcard-answer`: 32px / 1.35 / weight 500 — *slightly larger than the question*, putting visual weight on what's being learned
    - `--flashcard-eyebrow`: 11px mono uppercase tracking-wide — for concept · document
    - `--flashcard-hint`: 12px tertiary — keyboard cue, corner-pinned (see PR 3)
3. Both faces use the same wrapper layout (eyebrow top-left, body centered, hint corner-pinned). Visual rhythm is identical between flips, only the content swaps.
4. Better long-content behaviour: `max-height: 60vh` with `overflow-y: auto` and scroll fade. A 500-word answer should not break the card.
5. Vertical rhythm: more breathing room around the body text, less around the eyebrow.

**Out of scope for PR 2:** images, math rendering, code blocks. Plain text only. Those are PR 5.

### PR 3 — Hint + keyboard affordance polish (~30 min)

**Files:** `frontend/src/features/study/components/FlashcardFace.tsx` (from PR 2), CSS module.

**Problem:** "Press space or click to reveal" is functional but reads as instructions. Visual noise.

**Changes:**
1. Replace the inline text hint with a subtle keyboard-glyph chip pinned bottom-right of the card: `[ Space ]` in mono, low-contrast, fades in slowly on first card, then fades to even lower opacity after 1 review (the user has learned).
2. Same chip changes label across phases: `[ Space ]` to reveal → `[ 1 2 3 4 ]` to rate.
3. Add a tiny "Show question" link in the bottom-left of the back-face card *if* PR 1 didn't make this discoverable enough (test with the user before adding — might be redundant).

### PR 4 — Citation reveal on the back face (~half day) — **SHIPPED 2026-05-12**

Shipped as: backend `services/study.py::fetch_due_cards` LEFT JOINs `anchors` keyed on `srs_card_id`, surfacing `document_id`, `chunk_id`, `page_num`, `quote_text` (most-recent anchor wins). New `SourceCitation` component renders on the answer face when both `document_id` and `chunk_id` are present; whole row is a single button deep-linking to `/reader/{document_id}?chunk={chunk_id}` via the existing `buildReaderChunkPath` helper. Tests: 4 backend + 6 component + 2 view-integration. Header reads "From {doc}, page N" (page hidden when null); excerpt italic, truncated to ~40 words; existing anchor index (`idx_anchors_srs_card`) keeps the per-card subquery O(1).

**Why this is the real value moment.** Carrel's wedge is "verbatim source-grounding, never fabricates." But the SRS loop today exposes none of that. The user reviews a card and never sees the underlying chunk, the page, or the source — they just see Q + A. That's the same product as Anki + ChatGPT.

**Changes:**
1. Read `currentCard.chunk_id` (already returned by `study.due()` per the `SrsDueCard` type — verify in `endpoints.ts`; if missing, add it backend-side).
2. Below the answer body on the back face, render a `SourceCitation` component:
    - "From {document_name}, page N, chunk #C"
    - Excerpt of the chunk text in italic, truncated to ~40 words
    - Click → navigate to `/reader/{document_id}?chunk={chunk_id}` (the existing reader-deep-link path)
3. Cards that have no source chunk (manual cards) hide the citation; everything else surfaces it.

**Why this matters strategically:** every review session becomes a reminder that *Carrel knows where the answer came from*. That's the brand promise rendered into the loop most students do daily. NotebookLM and Anki cannot do this without rebuilding their data model. This is the moat made visible.

### PR 5 — Cloze + reverse cards (~1 day)

**Currently:** every card is a Q-front, A-back pair.

**Add:**
1. **Cloze deletion** (Anki-style) — **PR 5.1 SHIPPED 2026-05-13.** Sentence with one term blanked out via the Anki `{{cN::term}}` marker. Schema: `srs_cards.kind ∈ {"qa", "cloze"}` (default 'qa' so legacy rows back-compat). Both faces store the same source; front face renders the term as a placeholder, back face reveals it in accent color. Architecture documented in [ADR 0002](../decisions/0002-pr-5-1-cloze-cards-schema.md). Mandatory scope additions folded in from the adversary leg: (a) `list_cards` search projection strips cloze markers (SQLite UDF), (b) `_normalize_card_text` skips cloze marker spans so a concept named `"c1"` doesn't corrupt markers. Tests: 15 backend + 9 frontend rendering.
2. **Reverse cards**: for any AI-drafted Q/A card with a single-term answer, auto-generate the reverse direction (term → definition).
    - Toggle in card creation: "Also create a reverse card."
    - Stored as a separate `srs_cards` row linked via `paired_card_id`.

**Out of scope for PR 5:** image cards, audio cards, multi-cloze.

### PR 6 — Session-level pacing + signal (~half day)

**Add to the session experience:**
1. **Estimated time remaining** — **SHIPPED 2026-05-13.** Running median of this session's (reveal + rate) per-card seconds × cards remaining, rendered in the focus-mode header as "~Nm left" (or "~Ns left" under 60s, with a 5s floor). Hidden until 3 samples land so an outlier first card doesn't anchor a misleading estimate. Pure client-side; reuses PR 7's per-card timing refs. Tests: 6 unit cases on `formatEta` + 2 overlay-render cases.
2. **Per-card timing telemetry** — **SHIPPED 2026-05-11** (commit `2f9e248d`; author date 2026-05-10, committer date 2026-05-11 — SHIPPED tracks the landed (committer) date; commit subject reads "PR 7" — historical renumbering before this item moved to PR 6 item 2). Records `seconds_to_first_reveal` and `seconds_to_rate` on every review event. Don't display yet; this is data for future tuning of FSRS parameters.
3. **"Defer this card" affordance** — **SHIPPED 2026-05-13.** Small ghost button next to the rating row that splice-out-and-appends the current card to the end of the session queue without calling `study.review`. Visible only in `phase === "back"` (after reveal) and only when there's at least one card to defer past. Emits `srs.card_deferred` with `{card_id, remaining}` so the dashboard can measure usage. Session-local reorder only — the card still sits on whatever SRS schedule the backend would otherwise give it. Tests: 2 view-integration cases (defer pushes A behind B; defer hidden on last card) + 1 backend-allowlist case.
4. **Streak indicator** — **SHIPPED 2026-05-13.** Small chip in the focus-mode header showing consecutive Good+Easy ratings within the current session. Resets to 0 on Again or Hard. Hidden until the streak reaches 2 (a "1 in a row" chip is noise). Format: "N in a row" — no flame emoji, no leaderboard, no color shift, just a subdued tertiary-text chip matching the ETA's quiet treatment. Reuses the overlay's 200ms fade-in animation (throttled by `prefers-reduced-motion`). Tests: 3 `formatStreak` unit cases + 2 overlay-render cases + 1 view-integration case driving the chip end-to-end through rateCard.

---

## Out of scope (deliberately)

- **Audio (TTS) on cards.** Adds Anthropic API cost; better as a Phase 4+ addition.
- **Image cards from PDF figures.** Requires PDF region-extraction work in the ingestion pipeline; bigger surface.
- **Multi-cloze.** Cognitive load mismatch with the simple-review use case.
- **Card editing in the review flow.** Already exists in `ManageCardsView`; deep-link from a "Edit this card" button on the back face is an obvious future, not now.
- **FSRS parameter tuning.** Use the data PR 6 collects for ~2 months before touching the algorithm.

---

## Success criteria

| Metric | Target | How measured |
|---|---|---:|
| Flip-back works | Regression test green | `tests/study/flip-card.test.tsx` |
| Card typography rated "balanced" or better | by ≥4 of 5 testers | Verbal feedback in first session |
| Citation on back is clicked | by ≥30% of testers | telemetry event `srs.citation_opened` |
| Session retention | ≥60% complete sessions started | `srs.review_started` vs `srs.review_completed` |

If after 2 weeks of real usage post-PR-4 the citation-click rate is below 10%, the citation surface is wrong (probably needs to be more prominent) and PR 4 gets a follow-up. Pre-commit kill condition: if PRs 5-6 ship and engagement metrics don't move, sunset PR 6's complexity (defer + streak) and keep only the typography work.

---

## Risk + things to watch

1. **PR 1 may surface a deeper UX question:** if users routinely flip back-and-forth before committing, are they self-grading harder than the FSRS algorithm assumes? The rating they give may be inflated. Watch the `seconds_to_reveal` telemetry from PR 6 for evidence.
2. **PR 4 (citation) needs the chunk_id field.** Verify it's already on `SrsDueCard`; if not, backend change is a prerequisite.
3. **PR 5's schema migration** must preserve existing `qa` cards. Default value, no backfill needed. Single migration.
4. **PR 2's typographic scale** could clash with the design system if other features adopt it. Keep it scoped to the flashcard surface — don't promote to design tokens until at least one other view needs it.

---

## What I am NOT doing in this plan

- A full rebuild of the SRS algorithm.
- Replacing FSRS with anything else.
- Touching `ManageCardsView` or card-creation flows except where PR 5 requires.
- Cross-platform (iOS / Android) considerations — Carrel is macOS-only.
- Pricing, gating, or paywall around the feature.

The flashcards feature isn't broken at the data-layer or scheduler level. The FSRS pipeline works. The cards persist correctly. What's missing is the *experience around the card during a review* — and that's the entire scope of this plan.

---

# AUTOPLAN PHASE 1 — CEO REVIEW

**Mode:** SELECTIVE EXPANSION (auto-selected per autoplan principles).
**Voices:** Claude subagent ✅ · Codex ❌ (rate-limited until 2026-05-11). Status: `[subagent-only]`.

## 0A. Premise Challenge

The plan rests on **four load-bearing premises**, none of which are explicitly stated or argued in the document. Each is challenged below:

| # | Premise | Stated? | Challenge |
|---|---|---|---|
| **P1** | Flashcards are core to Carrel's value | Implicit | If users have <20 cards each, no review polish saves engagement. The complaint "doesn't feel valuable" may be a quantity problem, not a quality problem. |
| **P2** | Users want bidirectional flip | Implicit | Anki famously enforces one-way commit-then-rate to prevent self-grading inflation. The user is overriding this convention. Is the override evidence-based or stylistic? |
| **P3** | Typography is the visual problem | Implicit | "Displeasing" could mean layout/density/animation/color — not type scale. Plan picks typography without diagnostic. |
| **P4** | Citation-on-back drives engagement | Implicit | Citation at *generation* time (every AI-generated card stores chunk_id, source-locked) is plausibly 10x bigger than citation at *review* time. The plan picks the smaller move. |

**Subagent verdict on premises:** "The user said 'doesn't feel valuable.' That sentence has at least three readings: (i) the cards I'm reviewing aren't useful, (ii) I don't have enough cards to bother, (iii) I don't trust the cards are right. The plan picks reading (i) without checking."

## 0B. Existing Code Leverage Map

| Sub-problem | Existing code that already does most of this | What's actually new |
|---|---|---|
| Bidirectional flip | `FlipCard.tsx` (parent-driven, fully wired). Bug is in `StudyView.tsx:402-403` only. | One conditional swap. ~5 LOC. |
| Card typography | `Text` design-system primitive, `--text-*` tokens, `cardEyebrow`/`cardQuestion`/`cardAnswer` classes in `StudyView.module.css` | New flashcard-scoped scale (vs. existing tokens) |
| Citation on back | `SrsDueCard` type, reader deep-link route at `/reader/{document_id}?chunk={chunk_id}` (already supported per the codebase audit) | Read & render. Verify chunk_id is already returned. |
| Cloze cards | Nothing — schema is qa-only | Migration + UI + AI prompt template |
| Reverse cards | `paired_card_id` does not exist | Migration + creation flow |
| Session telemetry | `events.track()` infra exists, `srs.review_started` / `srs.review_completed` already fire | Add `seconds_to_reveal`/`seconds_to_rate` properties |

**The 90% of value sits in PRs 1-3** (flip-back, typography, hint affordance) — pure frontend, no schema, no LLM, ~1.5 days realistic. PRs 4-6 layer on real database/ingestion work.

## 0C. Dream State Diagram

```
CURRENT (today)
  ├─ FlipCard works mechanically
  ├─ Review surface looks "displeasing" (user's word)
  ├─ One-way reveal (cannot flip back) — feels broken
  └─ Cards exist in isolation from the source corpus they came from

THIS PLAN (after PRs 1-6)
  ├─ Flip-back works
  ├─ Typography balanced, Q + A weighted symmetrically
  ├─ Citation chip on back face links to source
  ├─ Cloze + reverse cards available
  └─ Per-card timing telemetry quietly captured

12-MONTH IDEAL (the dream the plan should be aiming at)
  ├─ User drops a textbook chapter → 50 cards proposed in 30s, all source-linked → accept-all in one click
  ├─ Review surface is polish, not the wedge
  ├─ Cards regenerated when source updates (drift-aware)
  ├─ Subject-aware FSRS tuning (math vs. literature recall curves differ)
  └─ Group-decks (share a source-linked deck with a study group)

DELTA: this plan covers ~30% of the trajectory to the dream state.
The other 70% is in card *generation*, not card *review*.
```

## 0C-bis. Implementation Alternatives

| # | Approach | Effort (CC) | Risk | Net change in user value |
|---|---|---:|---|---|
| **Plan-as-written** (PRs 1-6 sequential) | ~10 days CC | Medium | Polish + 2 new card types + telemetry. Review surface feels modern. |
| **Trim to PRs 1-4 + telemetry only** | ~3-4 days CC | Low | Bug fix, redesign, citation. Defer cloze/reverse/streak until usage data justifies. |
| **Pivot: generation-first** | ~5 days CC | High | Replace PRs 4-6 with: bulk-card-generation flow ("turn this PDF chapter into a deck of 30"). Citation becomes a generation byproduct. |
| **Stop and instrument first** | ~0.5 days CC | None | Ship PR 1 only, instrument cards-per-user + 7-day return rate, decide the bigger plan after 2 weeks of data. |

**Recommended path (auto-decided):** combination of "Trim" + "Stop and instrument." Ship PR 1 today (1 hour), ship PRs 2-3 in the next 2 days (typography + hint), then **stop** and instrument. PRs 4-6 wait for usage data.

This is `SELECTIVE EXPANSION` mode applied honestly: hold scope, expand only the bug-fix moment, surface PR 4-6 decisions to the gate.

## 0D. Mode-Specific Analysis (SELECTIVE EXPANSION)

| Question | Answer |
|---|---|
| What's the smallest shippable thing that addresses the user's complaint? | PR 1 (flip-back fix). 1 hour. Fixes the actual reported bug. |
| What's the highest-leverage expansion that fits inside the same week? | PRs 2-3 (typography + hint). ~2 days. Addresses the visual complaint. |
| What expansions look like scope creep? | PRs 4 (citation) — useful but speculative; PR 5 (cloze + reverse) — schema work; PR 6 (telemetry+streak+defer+ETA) — grab bag. |
| What's the kill switch? | Pre-commit metric: 30% of users with the new surface reach `srs.review_completed` for ≥5 sessions over 4 weeks. If not, PR 4 was wrong direction; revisit. |

## 0E. Temporal Interrogation

```
HOUR 1 (PR 1 ships)         → flip-back works, user's bug closed.
DAY 2 (PRs 2-3 ship)         → typography balanced, hint chip cleaner.
WEEK 2 (gate decision)       → instrument data tells us if to ship PR 4-6 OR pivot to generation-first.
MONTH 1 (post-gate work)     → either citation+cloze+reverse OR bulk-card-generation flow.
MONTH 6 (regret check)       → did engagement metrics actually move? If review surface improvements moved them <10%, pivot was correct.
```

## 0F. Mode Selection — Confirmed

`SELECTIVE EXPANSION` is the right mode because (a) the plan's first 3 PRs are clearly load-bearing (the bug + the user's reported visual complaint), (b) PRs 4-6 are speculative bets that the data should drive, and (c) the alternative (full SCOPE EXPANSION to "rebuild card generation") deserves its own dedicated plan, not an appendix to this one.

## CEO DUAL VOICES — CONSENSUS TABLE

```
═══════════════════════════════════════════════════════════════
  Dimension                            Subagent  Codex  Consensus
  ──────────────────────────────────── ────────── ────── ─────────
  1. Premises valid?                   ❌ stated  N/A    DISAGREE [subagent-only]
                                       implicitly
  2. Right problem to solve?           ❌ wrong   N/A    DISAGREE [subagent-only]
                                       funnel
                                       stage
  3. Scope calibration correct?        ❌ "1 wk"  N/A    DISAGREE [subagent-only]
                                       is 2.5wk
  4. Alternatives sufficiently         ❌ skipped N/A    DISAGREE [subagent-only]
     explored?                         generation
                                       reframing
  5. Competitive/market risks covered? ❌ no moat N/A    DISAGREE [subagent-only]
                                       statement
  6. 6-month trajectory sound?         ❌ regret  N/A    DISAGREE [subagent-only]
                                       scenario
                                       compelling
═══════════════════════════════════════════════════════════════
```

**Subagent's killer question:** *"How many flashcards does the median active Carrel user have, and what's the 7-day return rate after first review session?"* If the answer is "we don't track that" or "fewer than 20 / under 30%," the entire plan is wrong-funnel-stage and should be replaced by a generation-first plan.

## Phase 1 — NOT IN SCOPE (deferred to TODOS.md)

- **Bulk-card generation from a document section** (the generation-first reframe). Deferred because it's a separate plan, not an appendix.
- **Drift-aware card regeneration** (cards re-suggest when source updates). 12-month dream-state work.
- **Group/shared decks.** Out of scope; contradicts local-first product values.
- **FSRS subject-aware tuning.** Needs 2 months of data first.

## Phase 1 — Failure Modes Registry

| Failure mode | Likelihood | Severity | Plan response |
|---|---|---|---|
| User has <20 cards; review polish doesn't move retention | High | Critical | Ship PR 1, instrument, decide PRs 4-6 against data |
| Bidirectional flip causes rating inflation (users "peek-back" then over-rate) | Medium | Medium | Capture `seconds_to_rate` telemetry to detect drift |
| Typography rebuild fights the design system | Medium | Low | Scope new tokens to flashcard surface; don't promote globally until ≥1 other view needs them |
| Cloze migration corrupts existing decks | Low | Critical | Default value preserves `qa`, no backfill, single migration with rollback |

## Phase 1 — Completion Summary

| Section | Status | Output |
|---|---|---|
| 0A Premise challenge | ✅ | 4 load-bearing premises identified, all implicit, P1 + P4 high-risk |
| 0B Existing code leverage | ✅ | 90% of value in PRs 1-3; PRs 4-6 add real schema/ingest work |
| 0C Dream state diagram | ✅ | Plan covers ~30% of 12-month trajectory; rest is generation-side |
| 0C-bis Alternatives | ✅ | 4 approaches; recommended hybrid trim + instrument |
| 0D-0F Mode | ✅ | SELECTIVE EXPANSION confirmed |
| Dual voices | ⚠️ | `[subagent-only]` — Codex rate-limited |
| Consensus | ⚠️ | 6/6 subagent challenges, no Codex confirmation; conservative read = treat all as disagreements |
| NOT in scope | ✅ | Generation-first reframe deferred to its own plan |
| Failure modes | ✅ | 4 modes registered with mitigation |

---

# 🚦 PREMISE GATE — your call

This is the **one** decision in autoplan that's never auto-decided. The premises below are load-bearing for the plan but not stated in it. Confirm or override each before Phase 2 (Design) begins.

**The 4 premises:**

1. **P1 — Flashcards are core to Carrel's value (today, not aspirationally).** ⚠️ HIGH-RISK
2. **P2 — Users want to flip back to re-read the question after revealing the answer.** ⚠️ MEDIUM-RISK (overrides Anki convention)
3. **P3 — Typography is *the* visual problem (not layout, density, animation, color).** ⚠️ MEDIUM-RISK
4. **P4 — Citation-on-back at review time is the right way to surface Carrel's source-grounding moat (not citation-at-generation time).** ⚠️ HIGH-RISK

**Subagent's killer question** (worth answering before confirming):
> *How many flashcards does the median active Carrel user have, and what's the 7-day return rate after first review session?*

If you don't know, the highest-leverage move is to ship PR 1 today, instrument those two metrics, then revisit the rest of the plan in 2 weeks with data.

**Options:**
- **A) Confirm all 4 premises as-stated** → proceed to Phase 2 (Design Review) with the plan unchanged.
- **B) Override one or more premises** → tell me which and how; I'll rewrite the affected sections of the plan, then continue.
- **C) Reframe to generation-first** (subagent's recommendation) → I draft a new plan focused on bulk-card-generation; this plan goes to TODOS.md as "review-surface-polish, deferred."
- **D) Stop and instrument first** → ship PR 1 only as a hotfix this week, defer the rest of the plan until usage data is in.

---

## PREMISE GATE — RESOLVED 2026-05-09

**User decision:** Option A — all 4 premises confirmed as-stated.

**User added three new directives that materially expand scope:**

1. **Card extraction quality is bad.** The AI-generated cards aren't trustworthy enough.
2. **Remove automated card-generation on document upload.** Cards become user-triggered. Generation gated to paying users with their own Anthropic API key.
3. **Voice/copy across the app should be more welcoming.** Less clipped/technical, more appealing.

**Plan revision baked in below.**

---

## REVISED PLAN — six PRs, reordered + two new

### PR 0 (NEW) — Remove auto card-generation on upload (~1 day)

**Files:** `services/ingestion/orchestrator.py`, `routes/documents.py`, `frontend/src/features/library/`, possibly `services/cards/draft.py`.

**Changes:**
1. Disable the auto-card-generation path that fires after a successful upload. Keep the function; gate it behind a feature flag `EINSTEIN_AUTO_DRAFT_CARDS=false` (default false post-this-PR).
2. Replace the silent generation with an explicit user action: an "AI-draft cards from this document" button on the library detail view, **disabled with a "Pro" tooltip** for free users.
3. Free users still get manual card creation (existing `CardCreateDialog`) and a "Use my own Anthropic key" option that, when enabled, unlocks the AI-draft button.
4. Cards previously auto-generated stay in the database — no migration. Mark them with `source: "auto_legacy"` in the events log so we can find them if we ever want to bulk-prune.
5. Telemetry: log `cards.auto_generation_disabled` once on first run after upgrade. Log `cards.draft_request` per user-triggered draft, broken down by tier.

**Why first (before PR 1):** the user's complaint about quality is upstream of the review surface. Stop the bleeding before polishing the bandage.

**Out of scope:** improving the prompt/extraction quality. That's a separate plan in TODOS.md (`flashcard-quality-investigation.md`).

### PR 1 — Restore bidirectional flip (~1 hour) [unchanged from original]

[original PR 1 content stays]

### PR 2 — Card typographic redesign (~1 day) [unchanged from original]

[original PR 2 content stays]

### PR 3 — Hint + keyboard affordance polish (~30 min) [unchanged from original]

[original PR 3 content stays]

### PR 4 (NEW) — Voice/copy refresh on the flashcard surface (~half day)

**Files:** `frontend/src/features/study/StudyView.tsx`, `frontend/src/features/study/components/*.tsx`, `frontend/src/features/study/CardCreateDialog.tsx`, `frontend/src/features/study/ManageCardsView.tsx`.

**Why:** user reports voice across the app reads as "clipped/technical" not "welcoming." The flashcard surface is where the user is right now, so it's where the fix bites hardest. Broader app-wide voice work is in TODOS.md.

**Changes:**
1. Audit every user-visible string in the flashcard surface (~50 strings estimated). For each, check against `DESIGN.md`'s voice rules AND the new "more welcoming" criterion.
2. Specific patterns to fix:
    - "No flashcards are due right now." → "Nothing to review today — come back when there's more material to work through."
    - "Reviewed N cards." → "Nice work. {N} card{s} done."
    - "The rating didn't reach the scheduler." → "Couldn't save that rating. {recovery action}."
    - "Press space or click to reveal" → "Tap to flip" (chip from PR 3 covers this)
    - Eyebrow concept · document_name → consider warmer phrasing, maybe just the document title with the concept as a softer secondary line
3. Keep verb-led button copy from existing rules. Don't deviate without explicit reason.
4. NO em dashes added (existing rule).

**Out of scope:** app-wide voice refresh (Library, Reader, Ask, Plan, Dashboard, Session). Goes to TODOS.md as `voice-refresh-app-wide.md`.

### PR 5 (formerly PR 4) — Citation reveal on the back face (~half day) [DEFERRED — see gate decision]

**Status:** deferred to Phase B (after data) per the user's instinct that quality > polish. Citation on back is review-surface garnish; the real moat moves with PR 0 (gating quality behind paid tier) + future generation-quality investigation.

If the post-PR-3 telemetry (cards-per-user, 7-day return rate) shows engagement holds, ship this; if not, this PR's value premise was wrong and we revisit.

### PR 6 (formerly PR 5) — Cloze + reverse cards (~1 day) [DEFERRED]

**Status:** deferred to Phase B. New card types only matter if existing card types are valuable; user has signaled current cards aren't trustworthy. PR 0 + future quality investigation must precede.

### PR 7 (formerly PR 6) — Session telemetry capture (~30 min) [moved up from PR 6 grab-bag]

**Slimmed:** drop streak/defer/ETA. Capture only `seconds_to_reveal` and `seconds_to_rate` on every review event. This is the data we need to decide PR 5/6 in 2 weeks. No UI surface; pure instrumentation.

---

## REVISED EXECUTION ORDER

**Ship this week (~3 days CC):**
- PR 0: Disable auto card-gen, add user-triggered AI-draft button (paid-gated)
- PR 1: Bidirectional flip
- PR 2: Typography redesign
- PR 3: Hint chip
- PR 4: Voice/copy on flashcard surface
- PR 7: Telemetry capture (~30 min addendum)

**Defer to Phase B (week 3+, gated on usage data):**
- PR 5: Citation on back
- PR 6: Cloze + reverse cards

**Defer to separate plans (TODOS.md):**
- `flashcard-quality-investigation.md` — improve generation prompt + evals
- `voice-refresh-app-wide.md` — Library, Reader, Ask, Plan, Dashboard, Session
- `paid-tier-infrastructure.md` — Stripe + license keys (Phase 4 work)

---

## DECISION AUDIT TRAIL — additions

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|---|---|---|---|---|---|
| 6 | 1-gate | Premises P1-P4 confirmed | User decision | gate-rule | User explicitly chose option A | Reframing |
| 7 | 1-gate | Add PR 0 (disable auto-gen) | User Challenge → accepted | P3 (pragmatic) | User has direct quality evidence; bad cards damage trust more than missing magic-moment | Keeping auto-gen on, fixing prompt instead |
| 8 | 1-gate | Add PR 4 (voice on flashcards) | User decision | P3, P5 | Welcoming voice is the user's directive; scope to flashcard surface only to keep PR small | App-wide voice refresh in this plan |
| 9 | 1-gate | Defer PRs 5-6 to Phase B | Mechanical (followed from PR 0) | P2 (boil lakes appropriately) | Quality issues upstream make review-side polish premature | Shipping all 7 PRs in one milestone |
| 10 | 1-gate | Move telemetry up (was PR 6 grab-bag, now PR 7 slim) | Mechanical | P5 (explicit > clever) | Telemetry is the load-bearing piece; streak/defer/ETA were speculation grab-bag | Keeping the bundle |

---

<!-- AUTONOMOUS DECISION LOG -->
## Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|---|---|---|---|---|---|
| 1 | 0 | Mode = SELECTIVE EXPANSION | Mechanical | P1, P3 | Bug + visual gripe are real, but PRs 4-6 are speculative — hold scope on confirmed asks, flag rest | SCOPE EXPANSION (full generation-first reframe), HOLD SCOPE (no expansion at all) |
| 2 | 0 | Skip Phase 3.5 (DX review) | Mechanical | P3 | DX-keyword grep returned 12 hits but all false-positive (Library feature, API mentions, "command" as keyboard) — flashcards are end-user UX | running DX review on a non-DX plan |
| 3 | 1 | Codex unavailable → continue subagent-only | Mechanical | P6 (bias to action) | Skill's documented degradation matrix — `[subagent-only]` mode with conservative consensus reads | aborting Phase 1 |
| 4 | 1 | Treat all 6 dual-voice dimensions as DISAGREE | Mechanical | conservative read | Codex absent → cannot confirm subagent's challenges → mark all as needing user judgment | marking as CONFIRMED with single-voice corroboration |
| 5 | 1 | Surface 4 premises at gate (not auto-confirm) | **Skill rule** | premise gate is non-auto-decidable | Premises are the one AskUserQuestion the skill preserves for human judgment | auto-confirming premises and continuing |


---

# AUTOPLAN PHASE 2 — DESIGN REVIEW

**Voices:** Claude design subagent ✅ · Codex ❌ (rate-limited until 2026-05-11). Status: `[subagent-only]`.

## Design Litmus Scorecard

| # | Dimension | Score | Highest-impact gap |
|---|---|---:|---|
| 1 | Information hierarchy | 6/10 | Eyebrow `{concept} · {document_name}` is mono-uppercase noise competing with the question on every card |
| 2 | Missing states | 4/10 | No mid-session resume — quitting at card 5/12 silently loses position |
| 3 | Emotional arc | 5/10 | Done screen at `StudyView.tsx:338-359` reads as ledger entry, not celebration |
| 4 | Specificity vs. generic | 6/10 | PR 4 voice work names 5 example strings out of ~50; needs full inventory |
| 5 | Voice/copy under "welcoming" | **3/10** | Worst offender: error heading "The rating didn't reach the scheduler." (`StudyView.tsx:370`) |
| 6 | Layout density | **5/10** | PR 2's `max-height:60vh + overflow-y:auto` does NOT work as written — architectural sizing problem |
| 7 | Accessibility | 7/10 | Stale `aria-label` on FlipCard ("Activate to hide" while flip-back disabled), missing SR confirmation on rate, rating buttons may be sub-44px |

**Single highest-impact gap:** PR 2's overflow strategy is structurally broken before it ships. Faces are `position: absolute` inside `min-height: 360px` parent with `overflow: hidden`. **A 400-word answer silently truncates ~75% of its text with no scrollbar.** PR 2 must redesign the FlipCard sizing model, not add `overflow-y` to `.cardFace` — the latter scrolls within 360px (effectively 280px after padding) and fights perspective.

## Worst-5 Strings That Defeat "Welcoming"

| File:line | Current | Proposed | Severity |
|---|---|---|---:|
| `StudyView.tsx:370` | "The rating didn't reach the scheduler." | "That rating didn't save. Give it another go and we'll try again." | **critical** |
| `StudyView.tsx:344-348` | "Reviewed N cards." / "The scheduler has updated each card's next review date based on your ratings." | **"Nice work."** + "You moved through {N} card{s}. We've spaced the next review for each one based on how it felt." | **critical** |
| `CardAiDraftDialog.tsx:83` | "The model is turned off. Set CARREL_AI_PROVIDER to claude or ollama in .env and restart the backend to use this." | "AI drafting is off in this build. Add an Anthropic key in Settings to turn it on." | **critical** (also contradicts PR 0's paid-gating) |
| `StudyView.tsx:295` | "No flashcards are due right now. Come back later or ingest more material in Library." | "You're all caught up. Add more to your library when you're ready for the next round." | high |
| `StudyView.tsx:413` | "Press space or click to reveal" | "Tap to flip" (card 1) → chip glyph (card 2+) | medium |

## Long-Content Stress Test — what really happens with a 400-word answer

1. `.cardFace` has no `overflow` rule and no `max-height` (`StudyView.module.css:48-57`).
2. `.face` parent (`FlipCard.module.css:41-52`) is `position:absolute; inset:0; overflow:hidden`.
3. `.scene` and `.inner` have `min-height: 360px` and no `height`.
4. **Result:** a 400-word answer (~1200-1400px tall) renders inside a ~360px-tall absolutely-positioned face with `overflow: hidden` → **75% of the answer is silently clipped. No scrollbar.** User cannot read what they're rating.
5. **Focus-mode does not save it** — `.glassFrame` has no `max-height`, but the `FlipCard` inside is the same broken sizing. Same clip.

PR 2 needs an architectural FlipCard rework: drop `min-height` from `.scene`/`.inner`, replace with `height: clamp(360px, 60vh, 70vh)`, OR redesign so faces flex inside a parent that grows. Either fights the 3D-flip illusion if not done carefully. **This is half a day of CSS spelunking, not the paragraph PR 2 currently allocates.**

## Missing States — Beyond the Plan

- **Mid-session resume** (`StudyView.tsx:130-140`): closing focus at card 5/12 silently resets to card 0 on next "Start a session." Fix: detect `completedCount > 0 && phase !== "done"` on intro, offer "Resume where you left off (5 of 12)."
- **Submit in-flight**: `submitting` disables buttons via opacity 0.55 (`RatingRow.module.css:42-45`) but no visible "which rating is processing." Add spinner ring around active button.
- **No SR confirmation on rate**: visual transition is the only signal. Add `aria-live` polite region: "Rating saved. Card {N+1} of {total}."

## DESIGN DUAL VOICES — CONSENSUS TABLE

```
═══════════════════════════════════════════════════════════════
  Dimension                            Subagent    Codex   Consensus
  ──────────────────────────────────── ─────────── ─────── ─────────
  1. Hierarchy serves the user?         ⚠ partial   N/A     [subagent-only]
  2. States specified or hand-waved?    ❌ thin     N/A     [subagent-only]
  3. Specificity > generic patterns?    ⚠ partial   N/A     [subagent-only]
  4. Voice meets "welcoming" goal?      ❌ critical N/A     [subagent-only]
  5. Layout robust to long content?     ❌ broken   N/A     [subagent-only]
  6. A11y specified or aspirational?    ⚠ partial   N/A     [subagent-only]
  7. PR 4 sequenced correctly?          ❌ too soon N/A     [subagent-only]
═══════════════════════════════════════════════════════════════
```

## Phase 2 — Single Biggest Design Risk

Subagent's call: **"PR 4 (voice) ships before the substance work has been validated. It paints over a flavor problem with a frosting problem."** The user said *"doesn't feel valuable"* — that's a substance complaint, not a tone complaint. Polishing words on cards that came from the same low-trust auto-gen pipeline that PR 0 just turned off risks confirming the user's suspicion in the most visible way.

Subagent's mitigation: **defer PR 4 by one cycle.** Ship PRs 0-3 + 7 this week, use telemetry from PR 7 to pick the 5-8 strings that actually matter, then voice-refresh only those.

## Decision Audit Trail — additions

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|---|---|---|---|---|---|
| 11 | 2 | PR 2 sizing model rework added to scope | Auto-decide | P1 (completeness) | Long-content silently truncating is a critical failure that PR 2 as written does not address | Shipping PR 2 with the original CSS fix only |
| 12 | 2 | Add resume-mid-session affordance | Auto-decide | P1 | Free-tier users will quit mid-session; silent reset destroys retention | Leaving as-is |
| 13 | 2 | Add SR live region on rating | Auto-decide | P1 | Accessibility completeness; cheap | Leaving as-is |
| 14 | 2 | PR 4 (voice) sequencing — TASTE DECISION | Surfaced to gate | none | Subagent recommends defer; user explicitly listed voice as a directive | (user decides) |
| 15 | 2 | Done screen celebration rewrite added to PR 2 (or split as PR 4.5) | Auto-decide | P1 | "Nice work" + structured confirmation is the celebration moment the plan currently lacks | Leaving as ledger entry |

**Phase 2 complete.** Subagent: 7 dimensions reviewed, 4 critical findings, 1 sequencing recommendation surfaced as TASTE DECISION.

---

# AUTOPLAN PHASE 3 — ENG REVIEW

**Voices:** Claude eng subagent ✅ · Codex ❌ (rate-limited until 2026-05-11). Status: `[subagent-only]`.
**Test plan artifact:** `~/.gstack/projects/Codex/main-test-plan-20260510-014535.md`

## 🚨 The Single Highest-Cost Finding

**PR 0 cannot deliver "AI drafting gated to paying users with their own Anthropic key" because Carrel has no concept of a user, account, tier, license, or auth.**

Eng subagent verified by reading the codebase:
- No `users` / `accounts` / `licenses` table in any of the 16 migrations
- No auth middleware on the API routes
- No license-key validator or Stripe integration
- No Settings panel for storing a per-user API key
- The "Free-tier / Pro-tier" labels in `routes/ask_cards.py:1-10` and `services/retrieval/typed_hybrid.py:61` are **decorative routing labels**, not enforcement

The plan's PR 0 silently presupposes tier infrastructure that does not exist. Without that infrastructure the only ways to ship "PR 0" as scoped are:
- (a) `localStorage.user_tier === "pro"` — one-line bypass via DevTools, not a real gate
- (b) "user has set `ANTHROPIC_API_KEY` in `.env`" — every dev running locally is "Pro," gate is meaningless

**Required action:** split PR 0 into two pieces:
- **PR 0a** (this milestone): kill auto-gen on upload, wire the existing `CardAiDraftDialog` as the user-triggered post-upload entry point, **available to everyone**. ~1 day. Real, defensible, ships value immediately.
- **paid-tier-infrastructure.md** (deferred plan): user accounts / license keys / Settings panel for BYOK Anthropic key / macOS Keychain integration. Multi-week work. Its own milestone.

The plan as currently written conflates these. PR 0a alone delivers the user's stated quality goal ("don't auto-generate bad cards") without inventing a gate that can't be enforced.

## Section 0 — Scope Honesty Verdict

| PR | Verdict | Real cost |
|---|---|---|
| PR 0 (paid-gate) | **DISHONEST** | ~3 days realistic; not 1 day. Splits per above. |
| PR 1 (flip-back) | HONEST (slight understatement) | ~1.5 hours with regression test |
| PR 2 (typography) | **UNDERSTATED** | ~1.5 days; PR 2 absorbs the design-review's FlipCard sizing-rework |
| PR 3 (hint chip) | HONEST | 30 min |
| PR 4 (voice) | UNDERSTATED + ORDER-DEPENDENT | Half day for sweep; depends on PR 0 Settings panel that won't exist after split |
| PR 5/6 (cloze, citation) | DEFERRED — **but PR 5 cost was wrong**: `SrsDueCard` does NOT include `chunk_id` (verified `endpoints.ts:770-784`). Backend change required. |
| PR 7 (telemetry) | HONEST | 30 min |

**Net plan-level scope correction:** ~8 working days, not the original "~3 days." The split-out of PR 0a alone saves ~2 days on this milestone.

## Section 1 — Architecture (current + proposed touchpoints)

```
CURRENT SRS REVIEW DATA FLOW
────────────────────────────
Library Upload                                     Review Surface
    │                                                  │
    ▼                                                  ▼
routes/documents.py                              StudyView.tsx (phase fsm)
    │   POST /api/documents                           │
    ▼                                                  │
services/ingestion/orchestrator.py                    │ GET /api/srs/due
   ingest_document_record()                           ▼
    │  for concept in concepts:                  services/study.py
    │    INSERT srs_cards (concept_id…)          fetch_due_cards()
    │    link_evidence_to_card()                  │ SELECT srs_cards JOIN concepts JOIN documents
    │  [orchestrator.py:356-374]                  │ ⚠ does NOT join card_evidence (PR 5 gap)
    ▼                                              ▼
SQLite                                          rateCard() → POST /api/srs/{id}/review
                                                FSRS scheduler updates due_date

PR 0a INTERCEPT: extract _draft_cards_for_concept() from orchestrator.py:356-374,
                 gate behind CARREL_AUTO_CARD_DRAFT env flag (default false).
                 NO tier check — wire CardAiDraftDialog.tsx as post-upload entry.

PR 7 TELEMETRY: in-component refs at StudyView.tsx:142 (revealAnswer entry)
                and :151 (rateCard entry). usage_events table already exists
                (migration 0011). No schema change.
```

**Coupling concerns:**
- PR 0 (full version) leaks user-tier knowledge into the ingestion pipeline → reason it must split.
- PR 0a (split) does NOT leak tier info; flag-only gating is clean.

## Section 2 — Code Quality

- **DRY win** (PR 2): `FlashcardFace.tsx` extraction is real — both faces share eyebrow + body structure today.
- **Naming issue**: `EINSTEIN_AUTO_DRAFT_CARDS` is wrong — "Einstein" appears nowhere else in the codebase post-rename. Use `CARREL_AUTO_CARD_DRAFT` for consistency with `INGEST_USE_DOCLING`.
- **Reuse missed**: `CardAiDraftDialog.tsx` already exists and already calls `routes/study.py:323::ai_draft_cards`. PR 0a should explicitly say "wire existing CardAiDraftDialog as the post-upload entry point," not "build a new user-triggered button."
- **Complexity**: `ingest_document_record` (`services/ingestion/orchestrator.py`) is already long. Extract `_draft_cards_for_concept()` first as a refactor, *then* gate it. Two small commits, not one big one.

## Section 3 — Test Diagram

Full test matrix written to `~/.gstack/projects/Codex/main-test-plan-20260510-014535.md`. Highlights:

- **Required and currently missing:** `frontend/tests/study/flip-card.test.tsx` flip-back regression (PR 1), long-content layout assertion (PR 2 — the architectural fix), `tests/test_einstein_tutor.py` post-upload-no-cards integration (PR 0a).
- **The single most important test:** PR 2's long-content assertion. Without it, the "fix" ships the same silent-clip bug behind new typography.

## Section 4 — Performance

- `clamp(360px, 60vh, 70vh)` is one CSS calc, no reflow concern.
- PR 0a's gating: zero ingestion latency (branch before the per-concept loop). Free uploads actually become *faster* by skipping card creation.
- Bundle size: `FlashcardFace` extraction is bytes-neutral. Voice copy doesn't move bytes. Comfortably under the 96.5KB JS gz budget.

## Section 5 — Security / Privacy

- **Without PR 0a/paid split:** any "Pro gate" Carrel ships today is honor-system, bypassable in DevTools. Acceptable for a local-first single-user app; **must be documented as honor-system, not enforced**.
- **BYOK Anthropic key storage:** if/when paid-tier-infrastructure.md ships, the right answer is **macOS Keychain via Swift IPC** (Carrel is a WKWebView shell). Plan doesn't mention this; defer to that separate plan.

## Failure Modes Registry

| # | Mode | Severity | Mitigation |
|---|---|---|---|
| 1 | PR 0 ships env-flag-only "Pro gate" — gates everyone, not "paying users" | **HIGH** | **Split per recommendation: PR 0a flag-only; tier infra deferred** |
| 2 | PR 2 ships new typography but `min-height` parent doesn't grow; long answers still clip | **HIGH** | `clamp(360px, 60vh, 70vh)` rework + 1500-char assertion test |
| 3 | PR 1 + PR 7 telemetry produce noisy `seconds_to_reveal` because users now flip back/forth | Medium | Track `first_reveal_ms` separately from `total_reveal_ms` |
| 4 | PR 4 voice copy references Settings panel that PR 0 split-out doesn't build | Medium | Pin CardAiDraftDialog string change to AFTER tier infra ships; leave original error string alone in this milestone |
| 5 | Card-creation refactor breaks existing tests in `tests/test_einstein_tutor.py` | Medium | Search and update tests in same PR |

## ENG DUAL VOICES — CONSENSUS TABLE

```
═══════════════════════════════════════════════════════════════
  Dimension                            Subagent     Codex  Consensus
  ──────────────────────────────────── ──────────── ────── ─────────
  1. Architecture sound?               ❌ PR 0 leak  N/A    [subagent-only]
                                       tier knowledge
  2. Test coverage sufficient?         ❌ critical   N/A    [subagent-only]
                                       gaps
  3. Performance risks addressed?      ✅ none new   N/A    [subagent-only]
  4. Security threats covered?         ❌ honor-     N/A    [subagent-only]
                                       system gate
                                       not flagged
  5. Error paths handled?              ⚠ partial    N/A    [subagent-only]
  6. Deployment risk manageable?       ❌ scope is   N/A    [subagent-only]
                                       2-3x stated
═══════════════════════════════════════════════════════════════
```

## Decision Audit Trail — additions

| # | Phase | Decision | Classification | Principle | Rationale |
|---|---|---|---|---|---|
| 16 | 3 | Split PR 0 → PR 0a (kill auto-gen) + paid-tier-infrastructure.md | Auto-decide | P5 (explicit > clever) | Tier infra invented from nothing isn't a one-PR job; split honesty |
| 17 | 3 | Wire existing CardAiDraftDialog as post-upload entry | Auto-decide | P4 (DRY) | Plan was inventing UI that already exists |
| 18 | 3 | Rename env flag CARREL_AUTO_CARD_DRAFT (was EINSTEIN_*) | Auto-decide | P5 | Naming consistency with INGEST_USE_DOCLING |
| 19 | 3 | PR 2 long-content assertion test required | Auto-decide | P1 (completeness) | Without it PR 2 ships same bug behind new typography |
| 20 | 3 | Document honor-system gating explicitly | Auto-decide | P5 | Hidden assumption is worse than stated limitation |
| 21 | 3 | macOS Keychain for BYOK key (deferred to paid-tier plan) | Auto-decide | P1 | Right answer documented even if implementation deferred |

**Phase 3 complete.** Subagent: 6/6 dimensions raised concerns, 5 failure modes registered, 1 critical scope-honesty finding (PR 0 split). No Codex confirmation; conservative read = treat findings as needing user judgment.


---

# AUTOPLAN PHASE 4 — FINAL APPROVAL GATE

## Plan Summary
Originally 6 PRs scoped at "~1 week" to fix flashcard flip-back, redesign typography, and add citations. After three review phases, the plan is now: **PR 0a (kill auto-card-gen, wire existing dialog), PR 1 (flip-back), PR 2 (typography + sizing-model rework), PR 3 (hint chip), PR 4 (voice — sequencing decision pending), PR 7 (telemetry)**. PRs 5/6 deferred. Real cost: ~8 working days, not 1 week. PR 0's "paying users" semantic is split into a separate `paid-tier-infrastructure.md` plan because Carrel has no user/tier/license infrastructure today.

## Decisions Made: 21 total (16 auto-decided · 1 user challenge · 1 taste decision · 3 user-resolved)

### User Challenge (one model agrees with user direction; second model rate-limited)

**Challenge 1: PR 0 paid-gating presupposes infrastructure that doesn't exist** (from Phase 3 eng review)
- **You said:** "Eliminate automated card-generation on upload; gate to paying users with their own API key."
- **Eng subagent recommends:** Split into PR 0a (kill auto-gen, ship for everyone) + separate `paid-tier-infrastructure.md` plan.
- **Why:** No `users` table, no auth middleware, no license-key validator, no Stripe, no Settings panel. The "Pro" labels in Ask routes are decorative. Any gate today is honor-system + bypassable in DevTools.
- **What we might be missing:** Maybe you have a near-term plan to ship Stripe + accounts that I don't know about. If true, PR 0 stays as one piece.
- **If we're wrong, the cost is:** PR 0 ships as one piece and stalls for 2+ weeks while inventing tier infrastructure mid-milestone. The user-quality goal ("don't auto-generate bad cards") gets blocked behind "build the entire monetization layer first."

⚠️ **Codex was rate-limited; this finding is single-voice. Flagged regardless because severity is critical and the codebase-grounding evidence is concrete.**

**Your call — your original direction stands unless you explicitly change it.**

### Taste Decision (auto-recommend, user can override)

**Choice 1: PR 4 (voice/copy refresh) sequencing** (from Phase 2 design review)
- **Recommend: defer one cycle.** Ship PRs 0a, 1, 2, 3, 7 this week. Use PR 7 telemetry to pick the 5-8 highest-traffic strings, then refresh voice in week 3 with data.
- **Alternative: keep PR 4 in this cycle but slim** to only the worst-5 strings audit (1 hour, not half-day). Gets the worst offenders without 50-string sweep.
- **Alternative: full PR 4 as-scoped** — 50-string sweep this week. Your original directive stands.
- **Downstream impact if you keep full PR 4:** voice work ships referencing UI patterns (Settings panel for BYOK key) that the split-out PR 0a won't build. CardAiDraftDialog.tsx:83's "Set CARREL_AI_PROVIDER..." copy can't be replaced with "Add an Anthropic key in Settings" if no Settings panel exists. **You either rewrite that copy to something neutral, or skip that string.**

### Auto-Decided: 16 decisions (full audit trail in plan file under Decision Audit Trail)
Notable picks:
- Mode = SELECTIVE EXPANSION
- Skip Phase 3.5 (DX) — false-positive grep
- Codex unavailable → continue subagent-only with conservative consensus reads
- Add PR 0 split (PR 0a + deferred plan)
- Wire existing CardAiDraftDialog (don't invent new UI)
- Rename `EINSTEIN_AUTO_DRAFT_CARDS` → `CARREL_AUTO_CARD_DRAFT`
- PR 2 long-content layout assertion test = required, not optional
- Document honor-system gating explicitly
- Defer macOS Keychain BYOK to paid-tier-infrastructure.md

## Review Scores

- **CEO:** `[subagent-only]`. 6/6 dimensions raised concerns. Killer question: *how many cards per user, what's 7-day return rate?*
- **Design:** `[subagent-only]`. 7 dimensions, scores 3-7/10. Worst dimension: voice (3/10). Critical structural finding: PR 2 sizing model broken.
- **Eng:** `[subagent-only]`. 6/6 dimensions raised concerns. **Critical scope finding: PR 0 paid-gating presupposes nonexistent infrastructure.** 5 failure modes registered.
- **DX:** Skipped (no developer-facing scope).

## Cross-Phase Themes (concerns flagged in 2+ phases independently)

**Theme 1: "Substance > tone."** Appeared in CEO (subagent: "user said 'doesn't feel valuable' is a substance complaint, not tone"), Design (subagent: "voice work ships before substance work has been validated → reads as performative"), Eng (subagent: "PR 4 references UI that PR 0 split-out won't build"). **Three phases, independently, all said: don't polish words on cards that came from the same low-trust generation pipeline.** High-confidence signal.

**Theme 2: "Plan understates real cost."** CEO (1 week is actually 2.5 weeks), Design (PR 2 is 1.5 days not 1 day), Eng (real cost ~8 days, PR 0 split saves 2 of them). Cost honesty is consistently weak.

## Deferred to TODOS.md

- `paid-tier-infrastructure.md` — accounts / license keys / Settings panel / macOS Keychain BYOK
- `flashcard-quality-investigation.md` — improve generation prompt + evals before re-enabling auto-gen
- `voice-refresh-app-wide.md` — Library, Reader, Ask, Plan, Dashboard, Session
- `bulk-card-generation-flow.md` — the "generation-first" reframe surfaced in CEO review (subagent's recommendation if telemetry shows quantity-of-cards is the real funnel issue)


---

# 🟢 PLAN APPROVED — 2026-05-10

**User decision:** Option A — approve as-is. Recommendations locked in:
- PR 0 split into PR 0a (this milestone) + paid-tier-infrastructure.md (deferred)
- PR 4 deferred one cycle (waits for PR 7 telemetry)
- PRs 5/6 deferred to Phase B
- All auto-decided items confirmed
- The PR 0 user-challenge: subagent's split recommendation accepted

## Final shipping order (~3.5 days CC)

1. **PR 0a** — kill auto-gen + wire CardAiDraftDialog as user-triggered post-upload (~1 day)
2. **PR 1** — bidirectional flip + regression test (~1.5 hours)
3. **PR 2** — typography + FlipCard sizing-model rework + long-content assertion test (~1.5 days)
4. **PR 3** — keyboard hint chip (~30 min)
5. **PR 7** — `seconds_to_reveal` + `seconds_to_rate` telemetry (~30 min)

PR 4 (voice) re-evaluates in week 3 with PR 7 data. PRs 5/6 re-evaluate against engagement metrics.

## Pre-commit kill conditions (locked in)

- If `srs.review_completed / srs.review_started` < 60% over 2 weeks → PR 1 didn't move retention; revisit
- If 1500-char-answer test ever regresses → PR 2 sizing model broken again; do not merge
- If `cards_per_user_p50` < 20 over 4 weeks → quantity-of-cards is the real issue; pivot to `bulk-card-generation-flow.md`

Restore point preserved at top of file. `/ship` is the next step when work is ready.
