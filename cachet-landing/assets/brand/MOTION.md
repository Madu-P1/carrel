# Cachet mark, motion spec

The mark animates the **exact logo**: the truncated C drawn as an open ring. One rule governs everything: only the ring moves, with transforms (or a path-draw), so the mark's shape is never altered. The
mark never turns a color and never becomes a checkmark; on the verify surface the
verdict is reported by the surface, not the logo.

Implementation: `frontend/src/design-system/primitives/CachetMark`. CSS + WAAPI
only, no motion libraries. Ink is `currentColor`. Honors `prefers-reduced-motion`.

## States

| State | What it does | Token |
|---|---|---|
| `idle` | A near-imperceptible breath (scale to 1.015). The resting state. | `--cachet-dur-breath: 3600ms` |
| `wriggle` | A small organic tilt, +7 to -7 degrees and back. | `--cachet-dur-wriggle: 1700ms` |
| `reveal` | The C draws itself along its own path, slow at the start then accelerating to complete. One-shot, for a logo reveal. | `--cachet-dur-reveal: 1100ms` |

All three animate the genuine C via transforms or a `pathLength`-normalized draw, so
the severance and arc shapes are exactly the static logo at every frame.

## Easing

| Token | Value | Use |
|---|---|---|
| `--cachet-ease-io` | `cubic-bezier(0.4, 0, 0.2, 1)` | Breath, wriggle. |
| `--cachet-ease-in` | `cubic-bezier(0.55, 0.055, 0.675, 0.19)` | The reveal draw (slow start, accelerates). |

All motion is eased, never linear. `idle`/`wriggle` loop on the standard
in-out curve; `reveal` is a one-shot ease-in draw (slow at the start, accelerating to complete).

## Reduced motion

`@media (prefers-reduced-motion: reduce)` disables all animations and forces the
draw to its finished state; the mark holds its canonical truncated C. `aria-busy`
and the surrounding surface still convey state, so no feedback is lost.

## Usage

```tsx
import { CachetMark } from "@/design-system/primitives/CachetMark";

<CachetMark state="idle" size={40} />
<CachetMark state="wriggle" />
<CachetMark state="reveal" onRevealEnd={() => setState("idle")} />
```
