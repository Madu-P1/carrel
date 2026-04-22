/*
 * Icon catalog.
 *
 * All icons share the same contract:
 *   - viewBox "0 0 16 16"
 *   - stroke="currentColor", fill="none", stroke-width 1.5
 *   - round line caps + joins (set on the primitive, not per-icon)
 *   - single `d` string (use `M` subpath commands for multi-stroke glyphs)
 *
 * Visual language: modern outline, matched optical weight, enough negative
 * space that every icon reads at 16×16 in the sidebar and 20–24 in headers.
 * Inspired by Lucide but redrawn on our own grid so the whole set feels
 * authored rather than borrowed.
 *
 * When adding a new icon:
 *   1. Design at 24×24 first, then scale to 16×16 (×0.667). 24 gives more
 *      room to iterate; 16 is what the sidebar ships with.
 *   2. Keep every stroke on a whole-pixel or half-pixel tick so edges don't
 *      blur on standard-density displays.
 *   3. Prefer 3–5 subpaths max. Busier than that and the glyph stops
 *      reading at small sizes.
 */

export const icons = {
  // --- Interface primitives ---
  search: "M11.5 11.5 16 16 M7 12a5 5 0 1 1 0-10 5 5 0 0 1 0 10Z",
  plus: "M8 3v10 M3 8h10",
  x: "M4 4l8 8 M12 4 4 12",
  "chevron-left": "M10.5 3.5 5.5 8l5 4.5",
  "chevron-right": "M5.5 3.5 10.5 8l-5 4.5",
  "chevron-up": "M3.5 10.5 8 5.5l4.5 5",
  "chevron-down": "M3.5 5.5 8 10.5l4.5-5",
  // Arrow-right for inline CTAs ("Start review →"). Swaps in for the
  // literal Unicode arrow character so stroke weight matches siblings.
  "arrow-right": "M3 8h10 M9 4l4 4-4 4",

  settings:
    "M8 2.5 9.2 3l1-.5 1 1-.5 1 1.1 1H13v2h-1.2l-1.1 1 .5 1-1 1-1-.5-1 .5-1-1 .5-1-1.1-1H3v-2h1.2l1.1-1-.5-1 1-1 1 .5L8 2.5Z M8 6a2 2 0 1 1 0 4 2 2 0 0 1 0-4Z",

  // dashboard: 2x2 grid of small rounded squares. Classic "overview"
  // idiom — panels of content arranged on a board. Reads as "home /
  // multi-widget page" at 16×16.
  dashboard: "M2.5 2.5 h4.5 v4.5 h-4.5 z M9 2.5 h4.5 v4.5 h-4.5 z M2.5 9 h4.5 v4.5 h-4.5 z M9 9 h4.5 v4.5 h-4.5 z",

  // --- Sidebar nav (upgraded pass) ---
  // library: four books of varying heights with the rightmost slightly
  // tilted. The leaning book is the signature Lucide "Library" cue —
  // tells you at a glance this is a COLLECTION, not a single book.
  library: "M3 13.5V3 M6 13.5V5.5 M9 13.5V4 M11.4 4.3 L13.6 13.3",

  // doc: rounded-rect document with a dog-eared fold and three content
  // lines. Fold is drawn as its own subpath so the corner reads as a
  // real crease rather than a missing triangle.
  doc: "M4 2 h5 l4 4 v8 a0.5 0.5 0 0 1 -0.5 0.5 H4 a0.5 0.5 0 0 1 -0.5 -0.5 V2.5 a0.5 0.5 0 0 1 0.5 -0.5 z M9 2 v4 h4 M6 9 h4 M6 11.5 h4 M6 6.5 h1.5",

  // ask: chat bubble with a question mark. Tail on the lower-left so it
  // reads as a speech balloon, not a generic circle. Question mark is
  // two strokes — the hook and the dot — so the dot is visible even at
  // small sizes.
  ask: "M8 2 a5.5 5.5 0 0 1 5.5 5.5 a5.5 5.5 0 0 1 -5.5 5.5 h-3 l -2.5 2 v-2.7 a5.5 5.5 0 0 1 -0.5 -4.8 A5.5 5.5 0 0 1 8 2 z M6.5 6.2 a1.5 1.5 0 1 1 2.6 1 c -0.55 0.55 -1.1 0.85 -1.1 1.6 M8 10.8 v 0.05",

  // study: open book. Two mirrored pages meeting at a spine. Beats the
  // old clipboard — a book is the universal symbol for study/reading and
  // matches the "study room at night" thesis better than a to-do list.
  study: "M2 3.5 h4.5 a1.5 1.5 0 0 1 1.5 1.5 v8.5 a1.25 1.25 0 0 0 -1.25 -1.25 H2 z M14 3.5 h-4.5 a1.5 1.5 0 0 0 -1.5 1.5 v8.5 a1.25 1.25 0 0 1 1.25 -1.25 H14 z",

  // --- Accent glyphs ---
  // command: proper ⌘ (four open loops connected by a square). The old
  // path was miswired and rendered as a tangle. This version is a
  // faithful simplified ⌘ — the four 1.5-radius arcs at each corner
  // read correctly at 14–16px.
  command:
    "M5.5 10.5 a1.5 1.5 0 1 0 1.5 -1.5 H10.5 V5.5 a1.5 1.5 0 1 1 1.5 1.5 H5.5 a1.5 1.5 0 1 1 1.5 1.5 V10.5 a1.5 1.5 0 1 0 -1.5 -1.5 H10.5 V10.5 a1.5 1.5 0 1 1 -1.5 1.5 H5.5 z",

  // sparkle: four-point star with a small secondary. Used on the "Ask"
  // submit button and any AI-flavored affordance. Two sparkles signals
  // the ✨ idiom without a unicode fallback.
  sparkle:
    "M8 2 L9.2 6.8 L14 8 L9.2 9.2 L8 14 L6.8 9.2 L2 8 L6.8 6.8 Z M12.5 2 L13 3.5 L14.5 4 L13 4.5 L12.5 6 L12 4.5 L10.5 4 L12 3.5 Z",

  // trash: outline bin for destructive actions (Manage Cards, Library
  // duplicates). Lid overhang + body + two internal ribs. Thin-weight
  // so it sits quietly next to text labels.
  trash:
    "M3 4.5 h10 M6 4.5 V3 a1 1 0 0 1 1 -1 h2 a1 1 0 0 1 1 1 V4.5 M4.5 4.5 l0.8 8.3 a1 1 0 0 0 1 0.9 h3.4 a1 1 0 0 0 1 -0.9 l0.8 -8.3 M6.75 7 v4.5 M9.25 7 v4.5"
} as const;

export type IconName = keyof typeof icons;
