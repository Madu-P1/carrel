# Cachet landing page

Standalone, hand-built, zero-framework. Dark-first. Static HTML/CSS with a touch
of CSS-only signature motion. No build step, no runtime JS dependencies.

## Files

| File | Role |
|---|---|
| `index.html` | The live landing page. Hero (the refusal) + ledger proof + stakes + how-it-works + trust + CTA. |
| `tokens.css` | Design tokens. Single source of truth for color, type, space, motion. |
| `base.css` | Reset, base type, shared primitives (sticky header, buttons, focus rings, scroll-reveal base, reduced-motion guard). |
| `site.css` | Page-specific section styles + per-section motion. |
| `motion.js` | Vanilla, zero-dependency motion: IntersectionObserver scroll-reveal, count-up tally, sticky-header scroll state. |
| `hero-a.html`, `hero-b.html`, `hero-c.html` | Archived hero explorations. Not linked from the live site. |
| `concepts.html` | Archive index for the three explorations. |

## Run locally

```bash
python3 -m http.server 4317 --directory cachet-landing
# open http://localhost:4317
```

## Design decisions (the why)

- **Color only ever carries a verdict.** Surfaces are a warm-tinted monochrome
  ramp (never pure #000/#fff). The only saturated colors are `--verified`
  (green), `--unverified` (amber, the gem), and `--refused` (red, reserved for
  "fabricated / does not exist"). Nothing decorative is colored.
- **Three typefaces, three jobs.** Newsreader (serif) for display headlines only,
  Inter (sans) for all UI and body, IBM Plex Mono for citations, verdicts, and
  labels. The legal-document register comes from the serif + mono pairing.
- **The refusal is the hero.** The page opens with Cachet catching a fabricated
  citation and saying "could not verify," then proves it is systematic with the
  line-by-line ledger. The demonstrated refusal is the differentiator no template
  can fake.
- **Motion clarifies, never decorates.** Three tiers: functional micro-feedback
  (hover/focus/press, 120-200ms), narrative reveals (scroll-in, 320-560ms eased),
  and signature beats (the hero scan + dot resolve + verdict rise on load; the
  ledger refusal landing last on its own beat with the tally counting up in view).
  `transform`/`opacity` only, so everything composits at 60fps. Zero runtime
  libraries: scroll-reveal is one IntersectionObserver in `motion.js`.
- **Every motion has a reduced-motion path.** `prefers-reduced-motion` is
  double-guarded: CSS forces all `[data-reveal]` and animated-in elements to their
  final visible state, and `motion.js` reveals everything immediately and sets the
  count-up to its final value. No content is ever gated behind an animation.
- **Degrades without JS.** Reveal elements only start hidden under the `.js` class
  (set by a one-line inline script), so a no-JS or failed-script load shows the
  full page.
- **Contrast is AA-verified.** All text pairs meet WCAG AA for their size
  (text-muted/bg 4.73, refused/refused-dim 6.16, body and primary well above).

## Deploy

Any static host. Drop the `cachet-landing/` contents at the web root. Self-host
the three fonts (currently loaded from Google Fonts) before launch to remove the
third-party request and tighten LCP.

## Copy

No em dashes, no slop vocabulary. The `mailto:` and "sample report" links are
placeholders pending the real access flow and a real sample report.
