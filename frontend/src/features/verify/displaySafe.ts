/**
 * Cachet: display-safe text for the draft read-back.
 *
 * Pasted legal text (especially copied out of a PDF) often carries non-printable
 * control or format characters: C0/C1 controls, zero-width and bidi marks, the
 * object-replacement character. The body font has no glyph for these, so the
 * browser draws the "missing glyph" box (a black tofu rectangle) mid-sentence,
 * which reads as a rendering bug in the lawyer's own draft.
 *
 * `displaySafe` replaces each such character with U+FFFD (the replacement
 * character), which every fallback font renders, so the anomaly is surfaced
 * honestly instead of tofu-ing. It is DISPLAY-ONLY and 1-to-1 (one code point
 * in, one out), so it never shifts the character offsets that
 * `placement.char_start`/`char_end` index into `draft_text`; claim-span marks
 * stay aligned. Tab (U+0009), newline (U+000A), and carriage return (U+000D)
 * are preserved (layout whitespace, not tofu). No I/O, no DOM; pure string in,
 * string out.
 *
 * The set is expressed as code-point ranges rather than a regex literal so the
 * source stays plain ASCII and never embeds the very characters it strips.
 */
const NON_PRINTABLE_RANGES: ReadonlyArray<readonly [number, number]> = [
  [0x00, 0x08], // C0 controls before TAB
  [0x0b, 0x0c], // VT, FF (TAB/LF excluded)
  [0x0e, 0x1f], // C0 controls after CR
  [0x7f, 0x9f], // DEL + C1 controls
  [0x200b, 0x200f], // zero-width space/joiners + LRM/RLM
  [0x2028, 0x2029], // line/paragraph separators
  [0x202a, 0x202e], // bidi embedding/override
  [0x2060, 0x2060], // word joiner
  [0x2066, 0x2069], // bidi isolates
  [0xfeff, 0xfeff], // BOM / zero-width no-break space
  [0xfff9, 0xfffc] // interlinear annotation + object replacement
];

const REPLACEMENT = String.fromCharCode(0xfffd);

// One character class compiled from the ranges (which stay the single source
// of truth). The render path calls displaySafe over the whole document, so the
// per-character JS loop with a linear range scan was the hot path; a single
// native-regex pass is the same 1-to-1 mapping at a fraction of the cost.
const NON_PRINTABLE_PATTERN = new RegExp(
  `[${NON_PRINTABLE_RANGES.map(([lo, hi]) =>
    lo === hi
      ? `\\u{${lo.toString(16)}}`
      : `\\u{${lo.toString(16)}}-\\u{${hi.toString(16)}}`
  ).join("")}]`,
  "gu"
);

export function displaySafe(text: string): string {
  return text.replace(NON_PRINTABLE_PATTERN, REPLACEMENT);
}
