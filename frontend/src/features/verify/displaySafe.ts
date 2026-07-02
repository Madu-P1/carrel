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

// Claim/source text reaches this module from parsed API responses and pasted
// documents, so it cannot be trusted to already be a well-formed string: a
// malformed verdict payload can hand this null, a number, an object, or an
// unbounded blob. None of that may throw or fall through to the DOM untouched.
const MAX_DISPLAY_LENGTH = 50_000;

// Matches a whole HTML/XML-like tag (<script>, </script>, <img onerror=...>)
// so it can be neutralized without touching a lone "<"/">" used as a
// less-than/greater-than sign in ordinary legal or financial prose — the
// render path puts this text in a JSX text child (never innerHTML), so
// entity-escaping every "<"/">"/"&" would corrupt that prose on screen
// instead of making it safer.
const HTML_TAG_PATTERN = /<\/?[a-zA-Z!][^>]*>/g;

// The explicit "there is genuinely no value here" token for this module. A
// type-degenerate input (a malformed payload handing this null, undefined, or
// a non-finite number) must never collapse to the empty string: a blank cell
// in the lectern UI reads as a clean, affirmative result to a lawyer, when in
// truth nothing was there to check. Exported so callers/tests can compare
// against it instead of the literal glyph.
export const NEUTRAL_PLACEHOLDER = "—"; // em dash — unambiguous "no value", not a word

function toDisplayString(value: unknown): string {
  // Real string content — including an empty or whitespace-only string — is
  // returned verbatim, never substituted. WorkspaceMargin.tsx applies
  // displaySafe() per-character to slices of the lawyer's own draft_text
  // (e.g. the single space between two adjacent claim spans is a genuine,
  // common text segment); swapping that for NEUTRAL_PLACEHOLDER would inject
  // a visible artifact into the rendered draft and break the 1-to-1,
  // length-preserving contract documented above that keeps claim-span
  // offsets aligned. Only non-string, type-degenerate input gets the
  // placeholder treatment below.
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return NEUTRAL_PLACEHOLDER;
  if (typeof value === "number") {
    return Number.isFinite(value) ? String(value) : NEUTRAL_PLACEHOLDER;
  }
  if (typeof value === "boolean") return String(value);
  // BigInt and Symbol both support the global String() coercion path without
  // throwing (String(symbol) is spec-cased to allow what template-literal/`+`
  // coercion of a symbol would otherwise throw on). Anything else reaching
  // here (object, array, function, ...) skips string coercion entirely rather
  // than risking a hostile toString()/valueOf() — the empty string is the
  // deliberate safe fallback for that whole non-primitive bucket.
  if (typeof value === "bigint" || typeof value === "symbol") return String(value);
  return "";
}

export function displaySafe(text: unknown): string {
  const bounded = toDisplayString(text).slice(0, MAX_DISPLAY_LENGTH);
  return bounded.replace(NON_PRINTABLE_PATTERN, REPLACEMENT).replace(HTML_TAG_PATTERN, REPLACEMENT);
}
