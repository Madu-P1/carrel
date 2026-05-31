# Cachet Landing Page — Build Specification

**Audience:** an AI coding agent building the production landing page.
**Source of truth:** the reference prototype in this directory (`cachet-landing/`). It has been design-reviewed and passes. Reproduce it faithfully, finalize it for production (self-hosted fonts), and verify against the acceptance criteria in §13. Do not redesign.
**Status:** the prototype already meets every requirement below. Your job is to productionize and verify, not to reinvent. If you find yourself rewriting large sections, stop — you have drifted from the source of truth.

---

## 0. Hard rules (read first, violate none)

1. **Standalone static site.** Plain HTML + CSS + one vanilla JS file. Zero frameworks, zero runtime dependencies, no build step required to run. It must open from a static file server.
2. **Color only ever carries a verdict.** Surfaces are monochrome. The only saturated colors in the entire page are the three verdict states (verified / unverified / refused). Nothing decorative is ever colored. If you are about to color something that is not a verdict, don't.
3. **Animate `transform` and `opacity` only.** Never animate layout properties (width, height, top, left, margin, padding). Everything composites at 60fps.
4. **Every motion has a reduced-motion path and a no-JS path.** Content is never gated behind an animation or behind JavaScript.
5. **No em dashes anywhere.** Use commas, periods, or "...". No AI-slop vocabulary (elevate, unleash, seamless, supercharge, robust, leverage, unlock, cutting-edge, etc.).
6. **Copy is locked.** Use the copy deck in §9 verbatim, including curly apostrophes (’ not '). Do not paraphrase, expand, or "improve" it.
7. **Do not change the deliberate decisions in §12.** They were reviewed and chosen on purpose. A reviewer will try to "fix" them; don't.

---

## 1. What this is

A landing page for **Cachet**, an independent verification layer for high-stakes AI output. The initial wedge is litigation pre-flight: catching fabricated citations, misquoted holdings, and unsupported claims in AI-drafted legal work before it reaches a court.

Positioning: precise, restrained, trust-first. It sells the credibility of a refusal ("we could not verify this"), not hype. Visual register: Linear / Vercel / Stripe-docs level restraint, dark-first, document-grade. The page must itself embody the product claim by being disciplined and never overselling.

**The signature idea:** the hero shows Cachet *refusing* (catching a fabricated citation), and the next section proves it is systematic (a line-by-line ledger). That demonstrated refusal is the differentiator. Protect it.

---

## 2. Tech constraints

- **Output:** `index.html` + `tokens.css` + `base.css` + `site.css` + `motion.js` + self-hosted `/fonts/*.woff2`.
- **No framework, no bundler required.** If a bundler is used for minification, the un-bundled source must still run directly.
- **JS budget:** one file, `motion.js`, < 2 KB. IntersectionObserver + a count-up + a scroll listener. Nothing else.
- **Browser support:** evergreen (Chrome, Safari, Firefox, Edge). `text-wrap: balance`, `backdrop-filter`, IntersectionObserver are all assumed available; all degrade gracefully where not.
- **Deploy target:** any static host (Vercel, Netlify, Cloudflare Pages, S3). No server.

---

## 3. File manifest

| File | Role | Action |
|---|---|---|
| `index.html` | The page. Semantic markup + reveal hooks + inline `.js` class script + `<script defer src="motion.js">`. | Reproduce from reference. |
| `tokens.css` | Design tokens. Single source of truth for color, type, space, radius, shadow, motion. | Reproduce verbatim. Canonical. |
| `base.css` | Reset, base type, sticky header, buttons, focus rings, scroll-reveal base, micro-interactions, reduced-motion guard, ambient drift. | Reproduce verbatim. |
| `site.css` | Per-section layout + section-specific motion + reduced-motion resolves. | Reproduce verbatim. |
| `motion.js` | IntersectionObserver reveal, count-up tally, sticky-header scroll state. | Reproduce verbatim. |
| `/fonts/*.woff2` | Self-hosted Newsreader, Inter, IBM Plex Mono. | **New for production** (see §6). |
| `README.md` | Already written. | Keep. |
| `concepts.html`, `hero-a/b/c.html` | Archived hero explorations, not linked from the live page. | Keep or drop; not part of the live site. |

The four CSS/JS files and `index.html` in this directory are the canonical baseline. Treat them as already-correct. The only net-new production work is §6 (self-host fonts) and §13 (verify).

---

## 4. Design tokens (canonical: `tokens.css`)

Reproduce `tokens.css` exactly. The values below are the ones a reviewer most often gets wrong; they are load-bearing and were tuned for WCAG AA. Do not "round" them.

**Neutral ramp** (warm-tinted, hue ~36, low saturation; never pure black/white):
- `--n-0: hsl(36 9% 7%)` page base ... `--n-10: hsl(44 20% 97%)` highest.
- `--n-6: hsl(36 7% 49%)` muted text. **This was raised from 40% to 49% to pass AA for small text. Keep it at 49%.**

**Verdict family** (the only colors allowed to mean something):
- `--verified: hsl(152 42% 55%)`, `--verified-dim: hsl(152 30% 22%)`, `--verified-glow: hsl(152 50% 55% / 0.16)`
- `--unverified: hsl(41 72% 60%)` (the gem: authoritative caution, not alarm), `--unverified-dim: hsl(41 45% 20%)`, `--unverified-glow: hsl(41 75% 58% / 0.18)`
- `--refused: hsl(8 66% 68%)`, `--refused-dim: hsl(8 42% 14%)`. **These were tuned so refused-on-refused-dim hits 6.16:1. Keep them.**

**Motion tokens:**
- `--ease-out: cubic-bezier(0.16, 1, 0.3, 1)`, `--ease-in-out: cubic-bezier(0.65, 0, 0.35, 1)`
- `--dur-1: 120ms`, `--dur-2: 200ms`, `--dur-3: 320ms`, `--dur-4: 560ms`

**Type scale** (1.25, 16px base): `--t--1: 0.8rem` ... `--t-5: 3.052rem`, `--t-display: clamp(2.6rem, 1.4rem + 4.6vw, 4.6rem)`.
**Spacing** (8px base): `--s-1: 0.25rem` ... `--s-10: 8rem`.
**Radius:** `--r-1: 6px`, `--r-2: 10px`, `--r-3: 14px`, `--r-full: 999px`.
**Layout:** `--measure: 62ch`, `--container: 1120px`.

---

## 5. Typography — three families, three jobs

| Family | Job | Where | Weights |
|---|---|---|---|
| **Newsreader** (serif, optical sizing) | Display only | H1, section H2s, the stakes pull-quote, CTA H2, brand wordmark, card H3 in "checks" | 400, 500, 400 italic |
| **Inter** (sans) | All UI + body | lede, paragraphs, buttons, nav, trust H3 | 400, 500, 600 |
| **IBM Plex Mono** (mono) | Citations, verdicts, labels, eyebrows, file names | eyebrows, ledger cells, verdict text, doc filename, footer meta | 400, 500 |

Rules: serif is for large display text ONLY. Mono is for anything that reads as machine/legal record. Inter is everything else. Headings use `text-wrap: balance`; body paragraphs use `text-wrap: pretty`. Slight negative tracking on display (handled in CSS); do not crank tracking.

---

## 6. Fonts — self-host for production (the one net-new task)

The reference loads fonts from Google Fonts via `<link>`. For production, **remove the third-party request and self-host:**

1. Obtain `woff2` files for: Newsreader (400, 500, 400 italic; variable `opsz` if available), Inter (400, 500, 600), IBM Plex Mono (400, 500). All three are open-licensed (OFL).
2. Place under `cachet-landing/fonts/`.
3. Replace the Google Fonts `<link>` in `index.html` `<head>` with `@font-face` rules (in `tokens.css` or a new `fonts.css`), `font-display: swap`.
4. **Preload only the hero-critical weights** to avoid FOUT on LCP: Newsreader 400 (the H1) and Inter 400/500. Example:
   ```html
   <link rel="preload" href="fonts/newsreader-400.woff2" as="font" type="font/woff2" crossorigin>
   <link rel="preload" href="fonts/inter-400.woff2" as="font" type="font/woff2" crossorigin>
   ```
5. Keep the exact `font-family` stacks and fallbacks already in `tokens.css` (`Newsreader, Georgia, ...`; `Inter, -apple-system, ...`; `"IBM Plex Mono", ui-monospace, ...`).

Acceptance: production page makes zero requests to `fonts.googleapis.com` / `fonts.gstatic.com`.

---

## 7. Color & verdict semantics (the discipline)

- Page is monochrome warm-neutral. ~60/30/10 split: neutral surface / neutral content / verdict accent.
- The verdict family appears ONLY on: the hero flagged citation + verdict card, the ledger summary counts + row states, the stakes pull-quote accent phrase, the refusal-note left border + tint, the status dot. Nowhere else.
- `--verified` green = confirmed. `--unverified` amber = caution / could-not-verify. `--refused` red = fabricated / does not exist (used most sparingly, only the ledger "NO RECORD" row).
- Dark mode is the only mode for now. It is a real design, not an inversion. Do not add a light theme unless asked.

---

## 8. Layout & spacing

- 8px base grid. Every margin/padding/gap is a token from the spacing scale. No arbitrary values.
- Container max-width 1120px, centered, `padding-inline: var(--s-6)`.
- Body measure held to ~46–62ch on long-form text (lede 46ch, section paragraphs 54ch). Never full-bleed body text.
- Section rhythm is deliberately uneven (varied vertical padding). The page must NOT read as a stack of equal-height bands.
- Sticky header is full-width; its inner content sits in the container.
- Responsive: single breakpoint family. Hero + checks + trust collapse to one column at ≤940px / ≤820px (see the media queries in `site.css`). The hero verdict card becomes static (in-flow) below 940px; the hero scan line is hidden below 940px.

---

## 9. Copy deck (verbatim — curly apostrophes required)

### Nav
- Brand: `Cachet`
- Links: `How it works` (→ `#how`), `Why independent` (→ `#trust`), `Request access` (→ `#access`, ghost button)

### Hero
- Eyebrow: `Independent verification layer`
- H1: `A fabricated citation has ended cases.` then italic serif: `Cachet finds it first.`
- Lede: `Cachet checks every citation, quote, and holding in AI-drafted legal work against the actual record, then tells you, plainly, what it cannot stand behind.`
- Primary button: `Request access` (→ `#access`). Ghost button: `See how it works` (→ `#how`).
- Reassurance: `Runs locally. Your documents never leave your machine.`

### Hero document (the demo)
- Filename: `motion_to_dismiss_draft.docx`. Status: `Checking 14 authorities` (with status dot).
- Paragraph 1: `Plaintiff’s reliance on the discovery rule is misplaced. Courts have consistently held that the limitations period begins at the time of injury, not discovery. See ` + cited: `Whitfield v. Cranston, 412 U.S. 88 (1973)` + `.`
- Paragraph 2: `Even assuming the doctrine applied, equitable tolling is unavailable absent a showing of diligence, as the court reasoned in ` + **flagged**: `Marlow v. Eastbrook Holdings, 559 F.3d 204 (9th Cir. 2009)` + `.`
- Paragraph 3: `The claim is therefore time-barred and should be dismissed with prejudice.`
- Verdict label: `Could not verify` (preceded by the SVG warning triangle, see §11).
- Verdict headline: `No such case exists in any reporter.`
- Verdict detail: `No ` + mono `559 F.3d 204` + ` matches a 9th Circuit decision by this name. The citation appears fabricated.`
- Verdict source: `checked against · Reporter index, CourtListener`

### Ledger section (id `proof`)
- Eyebrow: `The report`
- H2: `Not one lucky catch. Every authority, accounted for.`
- Lede: `Cachet audits a document line by line and shows its work. What it confirms, it marks. What it cannot confirm, it holds back with a reason you can check yourself.`
- Ledger head: `motion_to_dismiss_draft.docx · 14 authorities` | summary: `13 verified` (the `13` is the count-up target) + `1 could not verify`
- Rows (verdict | citation | note):
  1. `Verified` | `Whitfield v. Cranston, 412 U.S. 88 (1973)` | `Quote matches at p. 94.`
  2. `Verified` | `Aldridge v. Penn Mut., 88 F.3d 12 (3d Cir. 1996)` | `Holding supports the cited proposition.`
  3. `Verified` | `In re Saxon, 201 B.R. 510 (Bankr. 1996)` | `Pin cite confirmed.`
  4. `No record` | `Marlow v. Eastbrook Holdings, 559 F.3d 204 (9th Cir. 2009)` | `No case by this name at this citation. Appears fabricated.`

### Stakes section
- Pull-quote: `When the citation is wrong, the brief is wrong, and the ` + accent italic: `court remembers who filed it.`
- Attribution: mono `2023 · S.D.N.Y.` + `A federal court sanctioned two attorneys after they filed a brief citing six cases that did not exist. The cases had been generated by an AI tool and never checked against the record.`

### How section (id `how`)
- Eyebrow: `What Cachet checks`
- H2: `Three questions, asked of every authority.`
- Card 01 `Does the case exist?` — `Every citation is resolved against reporter indexes and the public record. A case that cannot be found is flagged, not assumed.`
- Card 02 `Is the quote verbatim?` — `Each quoted passage is matched against the source text. Paraphrase dressed as a direct quote does not pass.`
- Card 03 `Does the holding match?` — `Cachet compares the proposition you cite a case for against what the court actually held. A real case cited for a holding it never reached is still wrong.`
- Refusal note (amber left border + tint): `And when Cachet cannot confirm something, it says so. The refusal is the feature.`

### Trust section (id `trust`)
- Eyebrow: `Why independent`
- H2: `A checker that did not write the work.`
- Lede: `The model that drafts a brief is the wrong one to grade it. Cachet is a separate layer with one job: confirm, or refuse.`
- Item `Separate` — `It does not write your brief` — `Cachet never generates legal argument. It only verifies what already exists, so its judgment is not defending its own draft.`
- Item `Local` — `Nothing is uploaded` — `Verification runs on your machine. Privileged documents stay on your machine, full stop.`
- Item `Auditable` — `Every verdict shows its source` — `Each result points back to the record it was checked against, so you can confirm the confirmation.`

### CTA section (id `access`)
- H2: `Verify before you file.`
- Paragraph: `Cachet is opening to a small group of litigators. Request access and run your next draft through it.`
- Primary button: `Request access` (placeholder `mailto:` — see §14). Ghost: `See a sample report` (placeholder — see §14).

### Footer
- Brand: `Cachet`. Links: `How it works`, `Why independent`, `Request access`. Tagline: `Independent verification for high-stakes AI work.`

---

## 10. Motion specification

Three tiers (per the design system). All `transform`/`opacity`, all token easings/durations.

**Tier 1 — functional (120–200ms):** button hover lift (`translateY(-1px)` + soft shadow on primary), button active reset, nav link underline grow (`::after` width via `right` transition), card hover lift (`translateY(-3px)` + border brighten + shadow on `.check`; surface fill on `.trust .item`), nav link/footer link color transitions.

**Tier 2 — narrative (320–560ms):** scroll-reveal. Every `[data-reveal]` element starts `opacity:0; translateY(18px)` and transitions to visible when it enters the viewport. Stagger via `--reveal-i` (× 70ms `transition-delay`).

**Tier 3 — signature (hand-tuned):**
1. **Hero load sequence** (timeline from page load):
   - Text + doc reveal: staggered, 0–~330ms (eyebrow `--reveal-i:0`, H1 `:1`, lede/doc `:2`, actions `:3`, reassure `:4`), 560ms ease-out each.
   - Scan line sweep: `@keyframes sweep`, 1.5s ease-in-out, delay 0.9s, runs once (top→bottom of the doc, fades in/out).
   - Status dot resolve: `@keyframes dot-resolve`, 2.6s ease-in-out, delay 0.9s, muted → amber → settles green with glow.
   - Verdict card rise: `@keyframes rise`, 0.62s ease-out, delay 2.2s (opacity + translateY + slight scale). Below 940px: delay 1.6s, card is in-flow.
2. **Ledger reveal in view:** rows are `[data-reveal]` with stagger `--reveal-i` 0,1,2 for the verified rows and **5 for the "No record" row** so the refusal lands last, on its own beat. The `13 verified` count animates 0→13 when the ledger is fully in view.
3. **Ambient drift:** `body::before` (the vignette) drifts via `@keyframes drift`, 24s ease-in-out infinite alternate, `translateY(-1.6%) scale(1.05)`. Barely perceptible. Composited transform only.

**Sticky header:** gains `background` (translucent) + `backdrop-filter: blur(14px)` + bottom hairline when `scrollY > 8` (class `.scrolled` toggled by `motion.js`).

---

## 11. JavaScript behavior (`motion.js`) and degradation

`motion.js` does exactly three things, vanilla, IIFE, `"use strict"`:

1. **Scroll-reveal.** `IntersectionObserver` (threshold `0.18`, `rootMargin "0px 0px -8% 0px"`) adds `.is-visible` to each `[data-reveal]` once, then unobserves. If `prefers-reduced-motion` or no IO support: add `.is-visible` to all immediately.
2. **Count-up.** For `[data-countup]` elements: a separate observer (threshold `1`) runs a `requestAnimationFrame` count from 0 to the target over 950ms (cubic ease-out). On init, set each counter's text to `"0"` so there is no reset flash. If reduced-motion or no IO: set final value immediately.
3. **Sticky-header state.** Toggle `.scrolled` on `.site-header` when `window.scrollY > 8` (passive scroll listener, called once on init).

**Degradation rules (both mandatory):**
- **No-JS:** the hidden initial state for `[data-reveal]` is scoped to `.js [data-reveal]` (the `.js` class is set by a one-line inline script in `<head>`: `document.documentElement.classList.add('js')`). Without JS, nothing is hidden, the full page renders.
- **Reduced-motion:** a `@media (prefers-reduced-motion: reduce)` block forces `scroll-behavior:auto`, disables all animations, makes transitions instant, forces `[data-reveal]`, `.verdict`, and `.row` visible, hides `.scan`, and pins the status dot green. JS independently reveals everything and jumps the count-up to final.

**Status glyphs:** the warning mark on the verdict is an **inline SVG triangle** (stroke `currentColor`), NOT the `⚠` character (which renders as a color emoji on macOS/WebKit and is a slop tell). The ledger ticks `✓` / `✕` are fine as text characters (they default to text presentation). All decorative glyphs carry `aria-hidden="true"`.

---

## 12. Deliberate decisions — do NOT change

These were chosen on purpose and survived an adversarial design review. A reviewer (human or AI) will be tempted to "fix" them. Don't, unless the operator explicitly asks.

- **Contained hero, not full-bleed.** Document-grade restraint is the brand. A poster-style full-bleed hero would read as marketing and undercut trust.
- **Color only ever = verdict.** No decorative accents, gradients-as-decoration, or colored sections.
- **The verdict / refusal-note colored left border is semantic** (it marks a verdict callout), not the generic "colored-left-border card" slop pattern. Keep it; it is used sparingly.
- **Inter for body is intentional.** The brand voice comes from Newsreader (display) + IBM Plex Mono (record), so Inter as the neutral body face is correct, not generic.
- **Two 3-column grids (checks + trust) are intentionally differentiated** (boxed cards vs borderless items). They do not read as a repeated band.
- **No testimonials/logos/pricing section.** Pre-launch and trust-first; the honest credibility anchor is the 2023 sanctions reference, not fake social proof.

---

## 13. Acceptance criteria (verify before calling it done)

Serve the site (`python3 -m http.server 4317 --directory cachet-landing`) and verify each. The first four are the design-review fixes that must not regress; check them by evaluating JS in the page.

1. **Touch targets ≥ 44px.** No interactive element below 44px in either dimension:
   ```js
   [...document.querySelectorAll('a,button,[role=button]')]
     .filter(e => {const r=e.getBoundingClientRect(); return r.width>0 && (r.width<44||r.height<43.6);})
   // expected: []
   ```
2. **No color emoji.** The verdict label contains an `<svg>` and no `⚠` character:
   ```js
   const l=document.querySelector('.verdict .label');
   ({svg:!!l.querySelector('svg'), emoji:/⚠/.test(l.textContent)}) // expected {svg:true, emoji:false}
   ```
3. **Curly apostrophes only.** `(document.body.innerText.match(/[A-Za-z]'[A-Za-z]/g)||[]).length` === `0`.
4. **`text-wrap: balance`** on h1/h2 and the stakes pull-quote.
5. **Contrast (WCAG AA).** Verify these rendered pairs meet target (compute luminance ratio): text-primary/bg ≈ 15.8, text-secondary/bg ≈ 6.0, **text-muted/bg ≥ 4.5** (≈4.73), unverified/bg ≈ 9.7, verified/surface ≈ 7.7, **refused/refused-dim ≥ 4.5** (≈6.16). All body text ≥ 4.5:1.
6. **Reveal works in view.** Scroll the ledger into view: all `.row` gain `.is-visible`, and `[data-countup]` reaches `13`.
7. **Sticky header.** `.site-header` gains `.scrolled` once `scrollY > 8` (hairline + blur appear).
8. **Reduced-motion.** With `prefers-reduced-motion: reduce` emulated: all `[data-reveal]` visible, `.scan` hidden, status dot green, no movement, content fully present.
9. **No-JS.** With JavaScript disabled: the full page renders, nothing stuck at `opacity:0`.
10. **Heading order.** h1 → h2 → h3, no skipped levels.
11. **Fonts self-hosted.** No network requests to Google Fonts; `@font-face` present; `font-display: swap`; hero weights preloaded; no visible FOUT flash on load.
12. **Performance.** LCP < 1.5s, CLS < 0.1 on a cold load (informational-site budget). No layout-triggering animations.
13. **Slop scan.** None of: purple/indigo gradient, icon-in-colored-circle feature grid, centered-everything, decorative blobs, emoji as UI, generic hero copy. (The reference passes; keep it that way.)

A verification harness equivalent to the snippets above lived in the review session; reuse them.

---

## 14. Placeholders to resolve (flag, do not invent)

- **CTA "Request access"** currently points at `mailto:access@cachet.example`. Replace with the real access flow (form / waitlist / real address) when the operator provides it. Do not invent a real email.
- **"See a sample report"** currently points at `concepts.html` (an archive). It needs a real sample-report page. That is a separate build, out of scope here. Leave the link, note it.
- **Fonts** must be self-hosted before launch (§6).
- **Favicon / OG image / metadata** beyond the existing `<title>` + description are not yet built. Add when brand assets exist.

---

## 15. Build order (for the agent)

1. Confirm the five canonical files (`index.html`, `tokens.css`, `base.css`, `site.css`, `motion.js`) are present and unmodified from this directory. They are the baseline. If building in a fresh location, copy them over verbatim.
2. Self-host the three fonts and rewire `<head>` (§6).
3. Confirm the copy deck (§9) matches exactly, curly apostrophes intact.
4. Run the full acceptance checklist (§13). Fix any deviation by returning to the source of truth, not by rewriting.
5. Report: which acceptance items passed, any that need operator input (the §14 placeholders), and the measured LCP/CLS.

Do not add features, sections, analytics, or dependencies not specified here. If something seems missing, it is probably a deliberate omission in §12 or a placeholder in §14. Ask the operator before adding.
