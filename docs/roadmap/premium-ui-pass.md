# Premium UI Pass — Handoff Plan

**Source:** product-designer review of the app recording. Critique boiled down: not taste, **resolution**. The structure's right; the precision and hierarchy that make it feel premium aren't there yet. Target feel: *Linear × Notion × Arc × high-end reading tool for serious students* — calm, exact, scholarly, premium, fast.

**Status as of this handoff:**

- ✅ **Token foundation refresh** landed (commit `<sha>`). Deeper dark surfaces, 14/22 body, semantic radius aliases, explicit interaction state ladder, brighter teal accent. Zero test regressions.
- ✅ **Primitive audit** landed (commit `<sha>`). Button/Input/Card snap to `--control-height-*` + `--radius-*` + state tokens. Selection vocabulary now exists.
- ⏳ **Surface redesigns** — this file. Six surfaces queued in priority order.

Every surface below assumes the new tokens and primitives are in play. The rule for each: *don't paint over; rebuild the layout against the new contract.*

---

## Ship 3 — Reader (highest ROI per the critique)

### Why first

Three-column research workstation is the single most visible product surface for a "serious reading" pitch. The critique flagged it as the weakest premium surface: outline too compressed, PDF toolbar under-refined, right rail overloaded, top-right meta card awkward, loading state is a "blank void."

### Acceptance criteria

**Left outline rail**
- Width: `280px` (was cramped). Collapses to `48px` for icon-only via a collapse toggle in the rail's footer.
- Active section gets a left-edge accent rail (2px, `--color-accent`) + `--state-bg-selected` row tint.
- Hover on non-active rows uses `--state-bg-hover`. Matches the WorkspaceSidebar nav treatment.
- Indentation rhythm: 16px per level. Second-level indent = `--space-4`; third-level = `--space-6`.
- Only ≤ 3 levels rendered by default; deeper tree behind a "Show full outline" footer toggle.
- Row height: `32px` (compact), label is `--text-body-sm` (13/20) so rows read dense without being tiny.

**Center document plane**
- Toolbar height: `44px`, fixed. Pulls from `--color-bg-elevated` with a 1px bottom hairline (`--border-subtle`).
- Toolbar groups (left / center / right) separated by `--space-6` gaps. Within a group: `--space-2` gaps. This is the "three zones" pattern that Linear uses and the critique explicitly praised.
- Left group: document title + file-type chip (mono label).
- Center group: prev / page-input / next / zoom-out / fit-mode / zoom-in. Page input uses the new Input primitive at size-sm (28px).
- Right group: `Search (⌘/)`, `Open source panel`, overflow menu.
- PDF canvas gets a `--reader-page-bg` surface with `--shadow-card` lift and `--radius-card` edges. Pages feel like paper on a dark room desk.
- Breathing room: `--space-6` min horizontal padding around the canvas at >1400px viewports; clamps to `--space-4` on narrow screens.

**Right insights rail**
- Width: `340px`.
- Structured into tabs (not a flat list): **Chunks · Notes · Related · Ask**. Tab bar uses the Button primitive at size-sm, variant-ghost, with a `--state-bg-selected` treatment on the active tab.
- Each list row: title (14px, `--weight-semibold`), one-line summary (13px, `--text-secondary`), source location (`--text-label-md` mono), subtle hover + click affordance (full-row target).
- Row padding: `--space-3` vertical, `--space-4` horizontal. Row-to-row gap: 2px (hairline separator, no border).
- Empty states per tab: short scripted copy + one primary action. **No blank voids allowed.**

**Document meta card (top-right)**
- Becomes a compact summary stripe at the top of the right rail:
  - File-type chip (mono, `--radius-full`)
  - Course / subject chip
  - Page count · added date · status (all `--text-label-md`, `--text-tertiary`)
  - Primary action: "Make an Anchor from selection" (becomes live once Anchor writers ship).
- Total height: ~72px. No card wrapper — it's a header strip.

**Loading / empty states**
- Persistent layout. Rails stay present during async; document area renders `3-5` skeleton rows tinted at `--surface-3`.
- Copy: `"Loading insights from {filename}…"` (real filename, not a placeholder).
- Skeleton rows animate with the existing `shimmer` keyframe (already in `animations.css`).
- Jobs Tray (ship 4 of the Anchors roadmap) feeds the "indexing / OCR / ready" states; reader surfaces a scoped banner if the current doc isn't fully indexed yet.

### Files touched

- `frontend/src/features/reader/ReaderView.tsx` — shell restructure (toolbar groups, right-rail tab bar, skeleton states).
- `frontend/src/features/reader/ReaderView.module.css` — full rewrite against new tokens.
- `frontend/src/features/reader/components/OutlineRail.tsx` + CSS — collapse toggle, active rail, indentation.
- `frontend/src/features/reader/components/PdfToolbar.tsx` + CSS — three-zone layout, size-sm page input.
- `frontend/src/features/reader/components/PdfSearchBar.tsx` — unchanged behavior, tighten to new tokens.
- `frontend/src/features/reader/components/source-panel/*` — tab bar, per-tab empty states, row compaction.
- `frontend/src/features/reader/components/ReaderLoadingState.tsx` — kill the blank void; render persistent layout + skeletons.

### Effort

Large. Two focused sessions. Split as: (a) shell + toolbar + outline, (b) right rail tabs + empty states + loading.

### Risks

- The OutlineRail's existing tree model may not carry enough levels data — if the backend's outline is already flat, the indentation UX is cosmetic only until richer outline extraction lands.
- pdfjs zoom controls fight the toolbar's fixed height on narrow windows. Plan for a `≤900px` width breakpoint that collapses the toolbar to two rows.

### Unlocks

Every downstream Anchor-era feature (Evidence Inspector, Anchor Column) slots into the right rail's tab bar without more rework.

---

## Ship 4 — Session Setup

### Why second

The critique explicitly compared it to "filling a form" and flagged weak CTA presence + competing content modules. The page's job is to feel like setting up a cockpit; right now it feels like a settings dialog.

### Acceptance criteria

**Mode cards**
- Layout: 2-column grid on ≥900px, stack on narrow. Card padding `--space-5`, gap `--space-4`.
- Each mode card:
  - Icon (24px) + title (`--text-h3`, semibold)
  - One-line purpose (`--text-body`, `--text-secondary`)
  - Optional metric footer (`--text-label-md`, `--text-tertiary`)
- Selected state:
  - Background = `--state-bg-selected`
  - Border = `1px solid var(--state-border-selected)`
  - Title color bumps from `--text-primary` to the accent (`--color-accent`)
  - Subtle `--shadow-card` elevation
  - Transform `translateY(-1px)` on hover (kept on selected)
- Default state: `--color-bg-elevated` + `--border-subtle`. Hover adds `--state-bg-hover` over the base fill and `--border-default` border.

**Session controls**
- Every control row at `var(--control-height-md)` (36) or `var(--control-height-input)` (40 for inputs). Mixed heights are a visual bug; standardize.
- Labels use `--text-label-md` + uppercase (matching Input primitive's label).
- Duration chips: use the new segmented-control pattern (a row of ghost buttons with one carrying `--state-bg-selected` + `--state-border-selected`). Minimum 28px tall (control-height-sm) + 40×40 hit target on touch surfaces.
- Alignment: every control row snaps to a 12-column grid. No floating labels or orphan controls.

**Primary CTA**
- "Start focused study session" (or similar — see copy below) at size-lg (44px), variant-primary, full width on narrow, auto on wide. Single most visible action on the page.
- Dismissible recommendation banner sits above the CTA, not next to it, so the two never compete.

**Recommendation banner**
- Narrow (max 720px), one-line eyebrow + one-line title + one-line reason + two actions: primary accept, secondary dismiss.
- Uses `--state-bg-selected` wash, not a full accent fill — it's supportive, not the hero.
- No long academic text. Punchy.

### Files touched

- `frontend/src/features/session/SessionView.tsx` + CSS — layout rewrite.
- `frontend/src/features/session/components/ModeCard.tsx` (create or refactor) — the premium mode card pattern.
- `frontend/src/features/session/components/SessionRecommendation.tsx` — trim banner per above spec.
- `frontend/src/features/session/components/DurationChips.tsx` (likely extract) — segmented control pattern.

### Effort

Medium. One focused session.

### Risks

- ModeCard may already be used elsewhere. Check for shared uses before refactoring; if shared, build the new premium variant as an explicit `size="page-hero"` prop.

### Unlocks

The mode-card pattern becomes reusable for any "pick a mode" surface (Study intro, Library subject picker v2).

---

## Ship 5 — Answer Card Feed

### Why third

High-density list surface where the critique flagged dense + repetitive + weak scanability. Most-read surface after the Reader.

### Acceptance criteria

**Tier hierarchy per card**
- **Tier 1** — the prompt or key claim. `--text-h3` (18/24), `--weight-semibold`, `--text-primary`.
- **Tier 2** — the answer summary. `--text-body` (14/22), `--text-secondary`.
- **Tier 3** — evidence / source / metadata. `--text-label-md`, `--text-tertiary`. Use the mono font for source locations (page, chunk id).
- **Tier 4** — utility actions (copy, retry, save-as-anchor). Ghost-variant Button size-sm, grouped at trailing edge of the meta row.

**Layout**
- Card background `--color-bg-elevated`, border `--border-subtle`, radius `--radius-card`.
- Padding `--space-5` all around (20px matches the Card primitive's new md).
- Gap between cards: `--space-3` (12).
- Max content width inside a card: 68ch. Wider than the previous unconstrained wrap; keeps body text in a readable measure.
- Checkbox / select affordance (if list has bulk ops): 20×20 sits at top-left with `--space-4` gap to content column.

**Selected state (bulk ops)**
- Row: `--state-bg-selected`, 1px `--state-border-selected` inset.

**Loading / empty**
- Skeleton cards during fetch (same shimmer as Library).
- Empty state has the three-tier hierarchy pattern: eyebrow chip + serif-voice headline + one-sentence helper + primary action.

### Files touched

- `frontend/src/features/ask/components/ClaimList.tsx` + AskView module CSS — the primary answer feed.
- `frontend/src/features/ask/components/FallbackAnswer.tsx` — already refused-state-aware, tighten to the new tiers.
- Any other card-feed pattern (Library subject rows? Study manage cards?) gets the same tier model on their own ship.

### Effort

Small-medium. One focused session.

### Risks

- `--text-h3` jump from 15/20 → 18/24 changes card height. Screenshot test selectors that measure card-level heights will shift — rerun the visual baseline.

### Unlocks

The tier-hierarchy pattern becomes the default for any "list of atomic content" surface in the app (future Anchor Column, Evidence Inspector list).

---

## Ship 6 — Dashboard / Home

### Why fourth

Landing surface. Gets a lot of eyeballs; was critiqued as "stack of cards" with weak orchestration. Token refresh already lifts visual quality here — this ship is about composition, not paint.

### Acceptance criteria

**Hero section**
- Greeting (eyebrow + serif display headline + short subhead) — retain current structure.
- Add a **subject chip + active-session chip row** directly below the subhead (already partially landed; verify it's using the new `--state-bg-selected` treatment).

**Primary composer**
- A single dominant input: "What do you want to understand right now?" wired to `/ask` as a prefill. Size-lg Input (40px ok), with trailing `→` icon (ghost size-sm button).
- This is the strongest object on the page. Card padding `--space-6`, width-clamp to `min(760px, 100%)`.

**Single contextual recommendation**
- One card. Eyebrow: "Recommended next" (mono label-md).
- Title: decisive, ≤ 8 words.
- Reason: one sentence.
- Two actions: primary accept, secondary dismiss.
- **Kill the yellow callout.** The critique flagged it as semantically accidental; the new token system has no "default warning tint." Accent-tint (`--state-bg-selected`) if you want visual emphasis.

**Quick actions row**
- 4 compact tiles (not cards). Each: icon (18px) + title (14px semibold) + meta (`--text-label-md` tertiary). Height 80px, padding `--space-4`.
- Hover: `--state-bg-hover` + `translateY(-1px)` (same pattern as the rest of the app).

**Continue-where-you-left-off module**
- Renders only if there's a recent session or doc.
- Compact horizontal card: last-session summary + one-click resume button.

**Today's progress / stats**
- Keep the current StatStrip, but apply the new tokens (the accent is brighter; stat values should re-check contrast).
- Subject chips row + active-session chip sit above the hero, not below (per critique: urgent info at eye level).

### Files touched

- `frontend/src/features/dashboard/DashboardView.tsx` + CSS — layout shuffle per above.
- `frontend/src/features/dashboard/components/HeroAskPrompt.tsx` — promote to the page's dominant composer.
- `frontend/src/features/dashboard/components/NextBestAction.tsx` — tighten to the one-card recommendation shape; remove the yellow wash.
- `frontend/src/features/dashboard/components/QuickActionGrid.tsx` — tile (not card) treatment.

### Effort

Small-medium. One focused session.

### Risks

- If the hero composer shipping to `/ask` skips the Scope Pill, users lose their scope choice between dashboard and Ask. Pass scope as a query param and hydrate on Ask mount.

### Unlocks

The "command center" feeling the critique called for. Dashboard becomes the decisive landing, not a widget pile.

---

## Ship 7 — Copy + State polish

### Why fifth (cheap, broad ripple)

Before the a11y pass, sweep the copy once: every AI-sounding phrase, every generic "Ask something you're unsure about" — replace with decisive product copy. The critique gave specific examples; apply the pattern everywhere.

### Acceptance criteria

**Copy rules (add to DESIGN.md's voice section)**
- Button labels start with verbs.
- Helper text is one sentence max.
- No "AI assistant" phrasing.
- Sound like a serious study platform.

**Examples the critique called out**
- "Ask something you're unsure about" → "Ask from your sources"
- "Enter deep work" → "Start a focused study session"
- "Show answer" → "Reveal the source-grounded answer"

Sweep every Button label, every empty-state title, every helper in the app. Use the search `grep -rn "Ask something\|Enter deep\|Show answer"` pattern as a starting seed.

**State polish**
- Every empty state renders a `Button` CTA. None are copy-only per the critique.
- Every loading state is a skeleton over the real layout, never a full-page spinner.
- Every error state names a concrete recovery action (not generic "Try again" — "Retry with broader scope", "Check your API key", etc.).

### Files touched

- Most feature CSS modules touched during surface redesigns already handle this. Ship 7 is the sweep to catch stragglers.
- `DESIGN.md` voice section gets the codified copy rules.

### Effort

Small. Half a session.

### Risks

- Copy changes can break e2e selectors that match by visible text. Prefer role-based queries in tests; check each change.

---

## Ship 8 — Accessibility + QA pass

### Why last (but before ship)

Do the fixes after the redesign so the audit reflects the final state, not the in-progress one.

### Acceptance criteria

- WCAG 2.2 AA contrast on all text tiers against their surfaces. Run a script + spot-check key screens.
- Every interactive element has a visible `:focus-visible` state via `--shadow-focus` (the new ring is two-stop, already anchored to `--surface-0`).
- Every icon-only button has an `aria-label`.
- Keyboard nav: Tab order matches visual order. No tabbing into the right rail before completing the primary content flow on a page.
- Every form field has an associated `<label>` (the Input primitive already handles this; verify compliance on custom fields).
- Pointer targets: comfortable buttons `≥ 36px` (control-height-md); minor chips `≥ 28px` with 44×44 hit-area expansion via padding.
- `prefers-reduced-motion` honored by every animation (spot-check; token layer already does the duration collapse).

### Files touched

Most likely feature-level fixes scattered across the app. Run the a11y audit tools once the surfaces are redesigned and file a ship-closing PR per surface if anything surfaces.

### Effort

Medium. One session with an automated audit tool (`axe`, `lighthouse`) + spot-check.

---

## Decision points to revisit before ship 3

Before starting the Reader redesign, decide:

1. **Tab bar component.** Does the app have a Tabs primitive today? If not, Reader's right rail needs one. Option A: build a small generic `<Tabs>` in the design system (worth doing; Dashboard and Study will want it). Option B: inline it in the right rail as a Button row. Recommendation: build the primitive; the Tabs API is not novel and will pay back within two ships.
2. **Outline data richness.** If the backend's outline doesn't include heading levels, the indentation UX is decorative. Check `services/extraction/` for outline fidelity before committing to the 3-level indent plan.
3. **Skeleton component.** Two skeleton patterns already exist inline (Library, Ask). Extract a `<Skeleton>` primitive before ship 3 so Reader loading doesn't invent a third.

---

## Ship order summary

1. ✅ Token refresh (landed)
2. ✅ Primitive audit (landed)
3. **Reader** — biggest visible premium lift. Takes two sessions.
4. **Session setup** — cockpit feel, mode-card pattern.
5. **Answer feed** — tier hierarchy pattern.
6. **Dashboard** — command-center feel, kill decorative yellow.
7. **Copy + state polish** — quick sweep before a11y.
8. **A11y + QA pass** — audit over final state.

At the end of ship 8, the app reads premium end-to-end. Every token decision is intentional, every primitive exercises the state ladder, every surface follows the tier hierarchy. Nothing left to paint over.

---

## What this plan deliberately doesn't include

- **Plugin SDK.** Per the Anchor-era Anti-Goals: integration is the moat.
- **Full PKM graph.** Same reason.
- **Mind maps / podcasts / infographics.** Post-loop experimentation only.
- **Radical re-architecture of AppShell.** The three-zone chrome is right; redesigns above are inside-the-shell.

Stick to the ladder. Ship each surface to a visible premium bar before moving on.
