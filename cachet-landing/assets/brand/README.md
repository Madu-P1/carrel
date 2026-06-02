# Cachet brand assets

The Cachet logo is the **withheld-strike** mark: the truncated C drawn as an open ring (a signet seal), cleanly severed in the upper-left. The unfinished impression is the refusal, which is the product's
core. Chosen 2026-05-31.

## Files

| File | What it is | Use |
|---|---|---|
| `cachet-mark.svg` | Primary mark: open ring (severed C), `currentColor` | All general use |
| `cachet-icon.svg` | Same mark, heavier stroke, `currentColor` | Very small sizes (favicon scale) |
| `cachet-lockup.svg` | Mark + `Cachet` wordmark in a reading serif, `currentColor` | Headers, docs, marketing lockups |
| `web/favicon.svg` | Adaptive favicon (paper in light, dark surface in dark) | Primary favicon |
| `web/favicon.ico` | 32px PNG-embedded ICO | Legacy fallback |
| `web/favicon-16.png`, `web/favicon-32.png` | Raster favicons | Legacy fallback |
| `web/apple-touch-icon-180.png` | Ink-ground app tile | iOS / Safari pinned |
| `web/icon-192.png`, `web/icon-512.png` | PWA / manifest icons | `manifest.webmanifest` |
| `macos/AppIcon.icns` | macOS app icon, ink ground + paper mark | `macos-app` (not yet wired) |
| `macos/cachet-appicon-1024.png` | 1024 master for the icon | Source for re-export |

## Color (locked)

| Token | Value | Role |
|---|---|---|
| ink | `#1c1814` | Mark on light |
| paper | `#f6f2ea` | Light ground |
| paper-reverse | `#f8f5ee` | Mark on dark |
| desk | `#0e0e10` | Dark ground |
| oxblood | `#7a2230` | Reserved accent, flags/corrections only |

The three source SVGs draw all ink with `currentColor`, so they reverse with one line:

```html
<span style="color:#1c1814">…on paper…</span>
<span style="color:#f8f5ee">…on the dark desk…</span>
```

Hard rules: no gold, no blue, no green. A green "verified" feel is the single most
dangerous signal on a verification surface. The withheld-strike mark itself uses no
oxblood; the cut carries the gravity. Oxblood is reserved for flag/correction states
(see the sibling `proofreaders-mark` direction if a single-accent mark is ever needed).

## Web wiring (not applied yet)

```html
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon-180.png">
```

## macOS app icon (not applied yet)

The legacy app ships as `EinsteinDesktop`. To adopt this icon, drop `AppIcon.icns`
into the app bundle's resources (or the asset catalog) and point the bundle at it.
Hold this until the Einstein to Cachet rename lands so the icon and identity flip
together.

## Geometry

All marks are built on a 240-unit grid. The mark is a single open ring: the truncated C scaled up to radius 64 about center (120,120), drawn as two arcs and severed by a gap in the upper-left (the withheld strike). There is no separate frame, so it never reads as a C inside a circle (a copyright mark). The app-icon master places the ring on an 824-unit rounded square (corner radius 185, about 22.4 percent) with ink ground and paper mark.

## Motion

The mark animates with four states: idle breath, wriggle (a small tilt), and reveal (the ring draws itself on). The ring moves with transforms or a path-draw so the shape is never altered, and it never resolves into a verdict or a color. Spec in
`MOTION.md`; production component at
`frontend/src/design-system/primitives/CachetMark` (CSS + WAAPI, `currentColor`,
reduced-motion aware, typecheck-clean).

## Clearance

A C with a circle can read as a copyright mark, and "Cachet" is a laudatory word, so this mark and
name need a real clearance pass before any USPTO filing. See `CLEARANCE.md` for the
worksheet: USPTO design-code search (Classes 9 + 42), reverse-image search, the
CACHET word knockout, and the common-law sweep, with a decision gate. Do not file
until that gate is clean.
