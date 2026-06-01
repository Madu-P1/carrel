/**
 * Cachet PR5b (Direction A) — pure rail-note vertical layout.
 *
 * Each margin note wants to sit at its claim's eye-line (the claim span's
 * offsetTop). When two notes would overlap, they push down in order so they
 * never collide. This is extracted as a PURE function over measured anchors so
 * the collision rule is unit-tested arithmetic rather than a DOM closure (the
 * prototype embedded it in an effect; pulling it out is what buys coverage).
 *
 * The DOM effect measures each claim's offsetTop and each note's height, then
 * calls this; the returned tops are applied as `style.top`. No DOM here.
 */

export interface RailAnchor {
  /** Stable key (claim_index) so the caller maps a result row back to a note. */
  key: number;
  /** Desired top: the claim span's offsetTop within the rail's coordinate space. */
  desiredTop: number;
  /** Measured rendered height of the note. */
  height: number;
}

export interface RailPlacement {
  key: number;
  top: number;
  /** Pixels this note was pushed below its desired eye-line (0 when undisplaced).
   *  The renderer can draw a connector or fade the anchor when this grows large
   *  so the mark-to-note link stays legible under dense collision. */
  displacement: number;
}

/**
 * Lay out notes top-to-bottom with a minimum gap, never overlapping.
 *
 * Notes are placed in ascending desiredTop order (ties broken by key for
 * determinism). Each note sits at max(its desiredTop, previousBottom + gap), so
 * a note can only ever move DOWN from its eye-line, never up, and two notes are
 * always at least `gap` apart. Returns placements keyed back to the input,
 * preserving the input order of the returned array == input order (so the
 * caller can render in claim order while the `top` values reflect the sort).
 */
export function layoutRail(anchors: RailAnchor[], gap = 16): RailPlacement[] {
  if (anchors.length === 0) return [];
  // Sort a COPY by desiredTop, then key, for stable deterministic stacking.
  const ordered = anchors
    .map((a, i) => ({ a, i }))
    .sort((x, y) => x.a.desiredTop - y.a.desiredTop || x.a.key - y.a.key);

  const topByKey = new Map<number, number>();
  let prevBottom = -Infinity;
  for (const { a } of ordered) {
    const top = Math.max(a.desiredTop, prevBottom + gap);
    topByKey.set(a.key, top);
    prevBottom = top + Math.max(a.height, 0);
  }

  // Return in the ORIGINAL input order so the caller's rendering loop is stable.
  return anchors.map((a) => {
    const top = topByKey.get(a.key) ?? a.desiredTop;
    return { key: a.key, top, displacement: Math.max(0, top - a.desiredTop) };
  });
}
