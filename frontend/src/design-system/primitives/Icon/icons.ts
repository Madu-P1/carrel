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
  focus: "M5.5 2.5 H2.5 v3 M10.5 2.5 h3 v3 M13.5 10.5 v3 h-3 M5.5 13.5 h-3 v-3",

  settings:
    "M8 2.5 9.2 3l1-.5 1 1-.5 1 1.1 1H13v2h-1.2l-1.1 1 .5 1-1 1-1-.5-1 .5-1-1 .5-1-1.1-1H3v-2h1.2l1.1-1-.5-1 1-1 1 .5L8 2.5Z M8 6a2 2 0 1 1 0 4 2 2 0 0 1 0-4Z",

  // dashboard: 2x2 grid of rounded squares. Refreshed from the
  // straight-corner original to match the softer aesthetic the rest
  // of the nav set is moving toward. Reads as "home / multi-widget
  // overview" at 16x16.
  dashboard:
    "M3.5 2.5 h2.5 a1 1 0 0 1 1 1 v2.5 a1 1 0 0 1 -1 1 h-2.5 a1 1 0 0 1 -1 -1 v-2.5 a1 1 0 0 1 1 -1 z M10 2.5 h2.5 a1 1 0 0 1 1 1 v2.5 a1 1 0 0 1 -1 1 h-2.5 a1 1 0 0 1 -1 -1 v-2.5 a1 1 0 0 1 1 -1 z M3.5 9 h2.5 a1 1 0 0 1 1 1 v2.5 a1 1 0 0 1 -1 1 h-2.5 a1 1 0 0 1 -1 -1 v-2.5 a1 1 0 0 1 1 -1 z M10 9 h2.5 a1 1 0 0 1 1 1 v2.5 a1 1 0 0 1 -1 1 h-2.5 a1 1 0 0 1 -1 -1 v-2.5 a1 1 0 0 1 1 -1 z",

  // graph: three small nodes connected by lines — concept-graph cue.
  // Top node centered, two on the lower row. Lines connect top-down to
  // each lower node and across between the lower pair. Reads as
  // "network" / "atlas" at 16×16 without overlapping any lines.
  graph:
    "M8 2.5a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3z M3.5 10.5a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3z M12.5 10.5a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3z M7.2 5.4 4.3 9.6 M8.8 5.4 11.7 9.6 M5 12 11 12",

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

  // reader: open book with text-line marks on each page. Distinct
  // from `study` (the generic open-book primitive, no text) by the
  // page-content strokes. Signals "this is what you're currently
  // reading" vs. "study session" semantics.
  reader:
    "M2 3.5 h4.5 a1.5 1.5 0 0 1 1.5 1.5 v8.5 a1.25 1.25 0 0 0 -1.25 -1.25 H2 z M14 3.5 h-4.5 a1.5 1.5 0 0 0 -1.5 1.5 v8.5 a1.25 1.25 0 0 1 1.25 -1.25 H14 z M3 6.5 h3 M3 8.5 h3 M3 10.5 h2 M10 6.5 h3 M10 8.5 h3 M10 10.5 h2",

  // notes: rounded document with three content lines and a small
  // pencil emerging from the lower-right corner. Differentiated from
  // the generic `doc` icon (dog-eared, no pencil) by the pencil
  // mark; reads as "writing notes on a page".
  notes:
    "M3.5 2 h5.5 a0.5 0.5 0 0 1 0.5 0.5 v10 a0.5 0.5 0 0 1 -0.5 0.5 H3.5 a0.5 0.5 0 0 1 -0.5 -0.5 V2.5 a0.5 0.5 0 0 1 0.5 -0.5 z M5 5.5 h3 M5 7.5 h3 M5 9.5 h2 M10.5 14 l3 -3 a0.4 0.4 0 0 0 0 -0.6 l-0.4 -0.4 a0.4 0.4 0 0 0 -0.6 0 l-3 3 z",

  // flashcards: SRS card / credit-card shape. Rounded outer rect, a
  // top stripe band reading as the card's color strip, and two short
  // interior lines hinting at the front-face content. Replaces the
  // open-book on /study, which is the spaced-repetition queue.
  flashcards:
    "M2 4.5 a1 1 0 0 1 1 -1 h10 a1 1 0 0 1 1 1 v7 a1 1 0 0 1 -1 1 H3 a1 1 0 0 1 -1 -1 z M2 6.5 h12 M4.5 10 h3 M4.5 11.5 h1.5",

  // session: hourglass. A single zig-zag traces top bar, right
  // diagonal, waist, bottom-right diagonal, bottom bar, left bottom
  // diagonal, waist, left top diagonal. Two short interior bars read
  // as sand grains. Signals timed focus / study session without the
  // clock-rainbow connotation of a generic timer.
  session: "M5 3 L11 3 L8 8 L11 13 L5 13 L8 8 L5 3 M7 11 L9 11 M7.5 5 L8.5 5",

  // plan: clipboard with a check on the first line and two pending
  // task lines below. Replaces the misplaced `command` (⌘) icon
  // that was acting as a placeholder on /plan.
  plan:
    "M3 4.5 a1 1 0 0 1 1 -1 h8 a1 1 0 0 1 1 1 v9 a1 1 0 0 1 -1 1 H4 a1 1 0 0 1 -1 -1 z M6 2.5 h4 v2 H6 z M5 8 l1 1 l2 -2 M5.5 11 h5 M5.5 13 h3",

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
    "M3 4.5 h10 M6 4.5 V3 a1 1 0 0 1 1 -1 h2 a1 1 0 0 1 1 1 V4.5 M4.5 4.5 l0.8 8.3 a1 1 0 0 0 1 0.9 h3.4 a1 1 0 0 0 1 -0.9 l0.8 -8.3 M6.75 7 v4.5 M9.25 7 v4.5",

  // edit: pencil tilted into the lower-left corner of an editable
  // surface. Tip points down-left so it reads as "writing on this
  // row." Used by the global Notes page for folder rename affordance;
  // any future inline-edit cue can reuse it.
  edit:
    "M11.5 2.5 l2 2 -8 8 H3.5 v-2 z M10 4 l2 2"
} as const;

export type IconName = keyof typeof icons;
