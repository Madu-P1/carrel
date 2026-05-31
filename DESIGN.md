# Design System — Carrel

Source of truth for all visual and motion decisions. Do not deviate without explicit user approval. Authored via `/design-consultation` on 2026-04-21. Renamed from Einstein on 2026-04-29 (the design language is unchanged; only the brand name changed).

## Product Context

- **What this is:** Carrel is a local-first, source-grounded AI study and research workspace for macOS. Drop in PDFs, notes, slides. Get a concept graph, SRS cards, grounded tutor answers that cite back to page-level spans, and a coach that proposes study blocks against your real calendar.
- **Why "Carrel":** A carrel is a small enclosed study booth in a library. The product is named after the room it tries to feel like.
- **Who it's for:** People who read for a living. Students, researchers, analysts, clinicians, grad students.
- **Space/industry:** Document intelligence, AI tutoring, local-first knowledge tools. Adjacent to NotebookLM, Humata, Readwise Reader, Khanmigo, Obsidian + AI plugins.
- **Project type:** Native macOS desktop app. Swift + SwiftUI shell wraps a WKWebView that loads a bundled Preact + TypeScript + Vite app. SQLite storage. FastAPI backend. Claude API for grounded answers with hybrid FTS5 + sqlite-vec retrieval.

## Aesthetic Direction

**Confident quiet.** A serious tool for serious reading, tuned so precisely it feels alive.

- **Direction:** Minimal-functional, instrumented. Dark default. High signal density on Library and Source Panel. Reading-first in Reader. Clean and airy in Ask.
- **Decoration level:** Minimal. Typography, hierarchy, and motion carry the weight. No patterns, no decorative blobs, no gradient backgrounds.
- **Mood:** Well-tuned instrument responding to input. Premium-native, 60fps, keyboard-first.
- **Reference vocabulary to steal from:**
  - Linear (keyboard snap, optimistic state, opinionated defaults)
  - Raycast (command-palette cadence, staggered reveals)
  - Things 3 (restraint, spatial clarity)
  - Superhuman (invisible speed, done-state)
  - Arc (one-big-gesture moments per page)
  - Granola (post-capture enhancement feel)
- **Explicitly avoid:**
  - Notion-style bounce-everywhere
  - Figma-spring-on-everything
  - AI-wrapper feel (blank canvas + one textbox)
  - Gradient mesh backgrounds
  - Decorative parallax
  - Lottie confetti
  - Decorative ambient motion

## Typography

One distinguishing display face added to an otherwise-native stack. The reading product gets a reading voice.

- **Display / Hero (h1, display):** Instrument Serif. Loaded from Bunny Fonts. Used only for `Text variant="display"`, `Text variant="h1"`, artifact titles, hero moments. Roughly 18 KB woff2.
- **Body / UI:** `-apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", Arial, sans-serif`. System stack, no download.
- **Data / Tables:** Same SF Pro Text with `font-variant-numeric: tabular-nums` applied via the `Text variant="data"` primitive variant.
- **Code / Mono:** `ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace`.
- **Loading strategy:** Self-hosted woff2 files under `frontend/src/assets/fonts/`. Vite bundles them, `build-macos.mjs` copies them into `macos-app/Resources/assets.new/` and rewrites CSS url()s to resolve correctly under `file://`. `@font-face` declaration in `tokens.css` with `font-display: swap` for instant fallback rendering. Zero network at boot; works offline; no third-party CDN dependency. Serif fallback stack: `"Instrument Serif", "Charter", "Iowan Old Style", Georgia, "Times New Roman", serif`.
- **Weights:** SF Pro Text at 400 regular, 500 medium, 600 semibold, 700 bold. Instrument Serif at 400 only (display serif, weight variants hurt it).

### Scale

| Variant | Size / line-height | Font |
|---|---|---|
| caption | 11px / 14px | SF Pro Text |
| body | 13px / 18px | SF Pro Text |
| h3 | 15px / 20px | SF Pro Text |
| h2 | 18px / 24px | SF Pro Text |
| h1 | 24px / 30px | Instrument Serif |
| display | 32px / 38px | Instrument Serif |

## Color

PR-E1 palette retained. Dark default. Light mode optional via `prefers-color-scheme` and manual toggle.

### Dark theme (default)

| Token | Value | Usage |
|---|---|---|
| `--color-bg-base` | `#0e0e10` | Window background |
| `--color-bg-elevated` | `#16161a` | Cards, panes, dialogs |
| `--color-bg-overlay` | `rgba(20, 20, 22, 0.92)` | Modal backdrops |
| `--color-bg-hover` | `rgba(255, 255, 255, 0.06)` | Interactive hover |
| `--color-bg-active` | `rgba(255, 255, 255, 0.10)` | Interactive pressed |
| `--color-border-subtle` | `rgba(255, 255, 255, 0.06)` | Hairline dividers |
| `--color-border-default` | `rgba(255, 255, 255, 0.10)` | Panel edges |
| `--color-border-strong` | `rgba(255, 255, 255, 0.18)` | Focus rings, emphasis |
| `--color-text-primary` | `#f5f5f7` | Body text |
| `--color-text-secondary` | `#b8b8be` | Captions, metadata |
| `--color-text-tertiary` | `#74747a` | Muted hints |
| `--color-text-disabled` | `#4a4a50` | Disabled controls |
| `--color-text-inverse` | `#0e0e10` | On-accent text |
| `--color-accent` | `#4f8cff` | Primary CTA, citation highlight, focused input |
| `--color-accent-hover` | `#6ba0ff` | Accent hover |
| `--color-success` | `#34c759` | Positive state |
| `--color-warning` | `#ff9f0a` | Warning state |
| `--color-danger` | `#ff453a` | Destructive state |
| `--color-info` | `#64d2ff` | Informational state |

### Light theme

Mirrors dark structure with inverted neutrals and system-light accent values. Exact hex in `frontend/src/design-system/themes.css`.

### Accent usage rule

Accent reserved for three uses only:
1. Primary CTAs.
2. Citation highlights (including the SM-2 flight target state).
3. Focused input borders.

No decorative accent. No second accent color. If a UI element needs emphasis and there's already accent on screen, use `--color-border-strong` or a weight/size change instead.

### Dark mode strategy

Saturation reduced roughly 15% vs light. Background hierarchy via elevated surfaces, not shadows. Avoid black on black; `--color-bg-base` is `#0e0e10`, never pure `#000`.

## Spacing

4px base unit.

| Token | Value |
|---|---|
| `--space-0` | 0 |
| `--space-1` | 4px |
| `--space-2` | 8px |
| `--space-3` | 12px |
| `--space-4` | 16px |
| `--space-5` | 20px |
| `--space-6` | 24px |
| `--space-8` | 32px |
| `--space-10` | 40px |
| `--space-12` | 48px |
| `--space-16` | 64px |

Density target: compact-comfortable. Closer to Linear than Notion. Typical card padding `--space-4`, typical pane gutter `--space-6`.

## Layout

- **Shell approach:** Three-pane hybrid. Shell is grid-disciplined. Feature content within each pane follows content type (Reader is reading-first, Library is list-dense, Ask is centered-single-column).
- **Shell grid:** CSS `grid-template-columns: [left-nav] auto [main] 1fr [right-panel] auto`. Collapsible sidebars via width transitions on the first and third tracks.
- **Max content width:**
  - Reader body: 760px (readable measure).
  - Ask answer: 680px.
  - Library: full main pane, no max.
  - Dialogs: 480px default unless task-specific.
- **Border radius scale:** `[0, 4, 6, 8, 12, 16, 9999]`. Cards 8. Buttons 6. Inputs 6. Dialogs 12. Pills (including citation chips) 9999.

## Motion

Three-tier system. Strict boundaries.

### Tier 1: Functional (invisible if done right)

Every hover, focus, press, toggle, pane collapse. CSS transitions only. 60fps mandatory.

**Duration tokens**

| Token | Value | Use |
|---|---|---|
| `--dur-instant` | 60ms | Pointer-down press, caret reveal |
| `--dur-fast` | 120ms | Hover, focus ring, color swap |
| `--dur-base` | 180ms | Pane collapse, tab switch |
| `--dur-medium` | 280ms | Panel reveal, route change |
| `--dur-slow` | 420ms | Narrative moments only |
| `--dur-long` | 640ms | Signature moments only (rare) |

**Easing tokens**

| Token | Curve | Use |
|---|---|---|
| `--ease-out` | `cubic-bezier(0.22, 1, 0.36, 1)` | Default, decelerating |
| `--ease-in` | `cubic-bezier(0.55, 0, 1, 0.45)` | Exits, accelerating |
| `--ease-swift` | `cubic-bezier(0.4, 0, 0.2, 1)` | Material-style, snappy |
| `--ease-soft` | `cubic-bezier(0.65, 0, 0.35, 1)` | Smooth both sides |
| `--ease-spring` | `cubic-bezier(0.34, 1.56, 0.64, 1)` | Single overshoot. Curated use only. |

### Tier 2: Narrative (felt, not noticed)

Route changes, panel reveals, sidebar toggles, empty-to-populated transitions. CSS + occasional WAAPI. 180-280ms.

**Keyframe library** ships as `frontend/src/design-system/animations.css` plus matching helpers in `frontend/src/design-system/motion.ts`.

| Name | Description | Default timing |
|---|---|---|
| `fadeUp` | opacity 0 → 1, translateY(8px → 0) | 220ms ease-out |
| `slideInRight` | translateX(24px → 0) + fade | 240ms ease-out |
| `slideInLeft` | mirror for left nav | 240ms ease-out |
| `scalePress` | scale(1 → 0.97 → 1) on `:active` | 180ms ease-swift |
| `pulseOnce` | scale(1 → 1.04 → 1) + shadow breathe, one cycle | 600ms ease-soft |
| `shimmer` | skeleton loading, CSS-only | 1.4s infinite linear |
| `focusRing` | outline grows 0 → 2px + glow | 120ms ease-out |
| `caretBlink` | steps(2) blink for focused input | 1.0s infinite |

### Tier 3: Signature moments (rare, memorable)

Max five in v1. Hand-coded, hand-tuned. Each earns its code budget.

**SM-1. Document card flight (Library → Reader)**
Click a doc card. Capture the card's bounding rect. Route to `/reader/:id`. Card morphs into the Reader title bar region via FLIP. Page 1 fades up from below. 320ms total.

**SM-2. Citation chip flight (Ask → Reader)**
Click a citation chip. Ghost chip detaches, flies to the target chunk's rect in Reader. Reader scrolls to center the target chunk in the same gesture. Chunk gets `pulseOnce` on landing. 420ms total. Invest heavily here. This is the center of the product story.

**SM-3. Grounded answer reveal**
When `GroundedAnswer` arrives: summary fades up first (220ms). Claims cascade with 60ms stagger. Citation chips fade in 120ms after their claim text. `unsupported_spans` slides up after claims finish. Total 600-900ms depending on claim count. Looks like the answer is being assembled, not appearing.

**SM-4. Ingest complete**
Progress ring finishes with ease-soft, brief hold, 600ms radial pulse dissolves outward. Doc card in library gets `pulseOnce`. No confetti. No sound.

**SM-5. First paint / cold boot**
Window opens. Left nav slides in from `-16px` with 40ms delay. Main content fades up. Right panel slides from `+24px` right. Titlebar text fades in last. Total 240ms. Starts after first paint, never blocks it.

### Motion constraints

- Zero runtime animation libraries. CSS transitions + Web Animations API only. No Framer Motion, no GSAP, no Motion One, no Lottie.
- All animated properties must be `transform` or `opacity`. Never layout-triggering (`width`, `height`, `top`, `left`, `margin`).
- All Tier 2 and Tier 3 motion respects `prefers-reduced-motion: reduce` (disabled entirely). Tier 1 stays at 60ms when reduced.
- No scroll-driven animations.
- No ambient background motion.
- Signature moments capped at five in v1. If a sixth is proposed, something in the existing five must retire.

### Performance budget

Cold launch budget 800ms p50. Measured baselines (5-run, not post-purge):

| milestone | p50 | p95 | mean |
|---|---:|---:|---:|
| Pre-E8 (no motion upgrades) | 244 ms | 351 ms | ~280 ms |
| E8a (bunny.net CDN font, 3 runs) | 335 ms | 1014 ms | — |
| E8a-followup (self-hosted font) | 498 ms | 648 ms | 531 ms |
| E8b (self-hosted + SM-1/2/4) | **299 ms** | **481 ms** | **332 ms** |

- Self-hosted `Instrument Serif` is the reason for the p95 collapse from 1014 ms to 481 ms. Never depend on a third-party CDN for core typography.
- SM-5 cold-boot orchestration starts *after* first paint. Not on critical path.
- All other motion is user-triggered. Zero on boot path.
- Current headroom to 800 ms budget: ~319 ms at p95.

## Voice

The product talks like a serious study platform, not an AI demo. Codified in Ship 7 (premium UI pass) after a sweep that replaced "Ask Einstein," "AI assistant," and generic "Try again" strings across the app. (After the 2026-04-29 rename to Carrel, "Ask Einstein" no longer appears anywhere — the rule generalizes: never invoke the product by name in a button label; describe the action.)

### Rules

1. **Buttons start with a verb.** "Reload the queue", "Reveal the source-grounded answer", "Draft from a topic", "Resume" — not "Try again", "Show answer", "Generate with AI". The verb tells the user what will happen on click.
2. **Helper text is one sentence, max.** No paragraphs under inputs. Period.
3. **No "AI assistant" phrasing.** Say what the system does ("the model drafts cards", "answers cite the chunks the retriever found"), not what category it belongs to. The user already knows it's an AI app — leading with the disclaimer is throat-clearing.
4. **Errors name a concrete recovery action.** Not "Try again" — say which action ("Reload the dashboard", "Retry end session", "Re-rate this card", "Wait a few seconds, then ask again"). The user shouldn't have to guess what re-trying means in this surface.
5. **Empty states ship a Button CTA.** Not just text. If the surface is empty, the next step belongs as a primary or secondary action that takes the user there.
6. **Loading states are skeletons over the real layout.** Never a centered spinner on an empty page; the layout should hold while the data arrives.
7. **Lab-notebook tone in section labels.** Mono uppercase, terse: "Pick the depth", "Set the corpus", "Set the timer", "What would you like to learn?" Reads as instruments on a cockpit, not labels on a form.
8. **No em dashes in product copy.** Use commas, periods, or "..." (per the broader voice guide; the dash is reserved for editorial copy).

### Examples (the critique called these out by name)

| Before | After |
|---|---|
| "Ask something you're unsure about" | "Ask from your sources" |
| "Enter deep work" | "Set the focus" / "Start focused study session" |
| "Show answer" | "Reveal the source-grounded answer" |
| "Try again" (refetch) | "Reload the queue" / "Reload the dashboard" / "Retry end session" |
| "Try again" (rate failure) | "Re-rate this card" |
| "Generate with AI" | "Draft from a topic" |
| "Expand with AI" | "Expand the draft" |
| "AI synthesis unavailable" | "Couldn't synthesize an answer." |
| "The AI service is rate-limited" | "The model is rate-limited" |
| "Wait a few seconds and try again" | "Wait a few seconds, then ask again" |

### Where the rules live in code

- Empty states must include a `Button` per the existing primitives. See `LibraryEmptyState.tsx` for the canonical shape: badge + headline + helper + Button CTA.
- Error copy in `frontend/src/features/ask/errorMessages.ts` is the model for the error pattern: each entry is `{ title, action }` where `title` says what happened and `action` says what to do — not "try again."
- Section labels for cockpit surfaces use `--text-label-md` mono uppercase. See `SessionView.module.css` `.sectionLabel` / `.fieldLabel`.

## File map

| Role | Path |
|---|---|
| Color + spacing + radius + type tokens | `frontend/src/design-system/tokens.css` |
| Dark/light theme values | `frontend/src/design-system/themes.css` |
| Motion tokens + keyframe library | `frontend/src/design-system/motion.ts`, `frontend/src/design-system/animations.css` |
| FLIP utility for SM-1 / SM-2 | `frontend/src/lib/flip.ts` (new, in PR-E8) |
| WAAPI declarative hook | `frontend/src/design-system/hooks/useAnimation.ts` (new, in PR-E8) |
| Design system primitives | `frontend/src/design-system/primitives/*` |

## Decisions Log

| Date | Decision | Rationale |
|---|---|---|
| 2026-04-21 | Initial design system codified via `/design-consultation` | Captures the PR-E1 visual system, adds motion tiers, adds one typographic voice. Source of truth before PR-E8 motion work lands. |
| 2026-04-21 | Added Instrument Serif for display only, kept SF Pro for body | Distinguishes from generic SF-Pro-everywhere macOS productivity apps. One font, one role, reversible. |
| 2026-04-21 | Zero runtime motion library | Bundle discipline. CSS + WAAPI handle all needed motion. Framer Motion rejected as overkill (~50 KB gzip). |
| 2026-04-21 | Defined 5 signature moments (SM-1 through SM-5), capped at 5 | Limit protects against motion feature-soup. Each moment earns its code budget. |
| 2026-04-21 | Kept PR-E1 color palette unchanged | No brand-signal strength earned yet for a custom accent. System blue reads correctly on macOS. Revisit post-launch. |
| 2026-04-26 | Codified product voice (Ship 7) | After the surface redesigns, swept user-facing strings across the app: verb-led button labels, concrete error recoveries (no generic "Try again"), no "AI assistant" phrasing, empty states ship a Button CTA. Rules + before/after table now live in the Voice section above so future copy decisions snap to one source of truth. |
| 2026-04-21 | Bunny Fonts over Google Fonts for Instrument Serif | GDPR-clean, no tracking, same CDN latency. |
| 2026-04-21 | Self-hosted Instrument Serif (PR-E8a-followup) | Bunny CDN stylesheet pushed cold-launch p95 from 351 ms to 1014 ms due to render-blocking external fetch. Self-hosting the woff2 restored p95 to 481 ms and removes the third-party dependency from a local-first product. |
| 2026-04-21 | PR-E8b signature moments (SM-1, SM-2, SM-4) landed with zero runtime motion library | FLIP utility (`lib/flip.ts`) + flight registry (`features/shared/flightRegistry.ts`) handle cross-feature rect handoff. Ghost chip flight uses cloned DOM appended to body, never touches Preact tree. Full motion system weighs < 250 LOC of new JS + 250 LOC of CSS. |
| 2026-05-29 | Scoped lawyer-grade "verify" visual mode (Cachet), founder-approved deviation | The verification surface (litigation pre-flight, the V2/Cachet wedge) adopts a warm-paper / near-black-ink palette with a single proofreader-oxblood accent reserved for flags, a reading serif (Charter/Georgia; Instrument Serif stays display-only) for document body, near-zero motion, and no traffic-light green/amber/red. Scoped to the `/verify` route via a `.verifyScope` token layer in `VerifyView.module.css`; global dark study tokens unchanged so the rest of the app and the verify chain are untouched. Rationale: the cross-professional discovery (`docs/notes/2026-05-29-cachet-cross-professional-discovery.md`) found credentialed buyers distrust a consumer/AI-styled verdict surface, and that a green VERIFIED badge is the single most dangerous element (invites over-trust and overclaims grounding as truth). Founder approved the deviation 2026-05-29 ("handle all the PRs"). Whole-app rebrand deferred until after the T66 validation verdict. |
| 2026-05-31 | Certification seal is the one permitted motion moment on the verify surface (Cachet PR2), founder-approved | The 2026-05-29 deviation mandated near-zero motion on `/verify`. PR2 makes the human seal real: setting it runs a restrained 900ms press-and-settle, and a seal gone stale (the draft changed after sealing) draws a 600ms crack with a loss of luster. Approved as a single scoped exception rather than a sixth signature moment, so the SM-1..SM-5 cap is untouched. Motion is WAAPI-only (no CSS keyframe rule is added, so the `verifyScope.test.ts` motion guard still holds) and fully disabled under `prefers-reduced-motion`, which falls back to the static set/cracked end-states. The seal renders in ink, not the prototype's brass: brass is gold-family and the 2026-05-31 logo palette reserves oxblood and admits no gold. The seal stamp ("CACHET VERIFIED RECORD") sets Instrument Serif below its documented 24px display floor as an intentional engraved-glyph treatment of the signature artifact, not body type; it reads as stamp texture on the 96px disc. |
