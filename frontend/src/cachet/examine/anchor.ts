/**
 * Pure anchor engine for the Document Examination overlay: locate a cited
 * passage inside a PDF page's text items and project it to on-screen
 * rectangles the overlay can underline.
 *
 * Matching is two-pass and honest:
 *
 *   1. "spaces"  — whitespace-collapsed, case-folded, curly-quote-folded
 *                  matching. Handles ordinary extraction noise (line breaks,
 *                  double spaces, smart quotes).
 *   2. "squash"  — alphanumerics only. Handles hyphenation across line
 *                  breaks ("agree-" / "ment") and words split across text
 *                  items with no space. Gated on a minimum length so a short
 *                  needle cannot false-anchor.
 *
 * If neither pass finds the passage the result is null, and the overlay says
 * so. A fabricated highlight is the one disqualifying behavior; no fuzzy
 * scoring, no nearest-match guessing.
 *
 * Geometry: PDF text items carry a 6-element affine transform whose [4]/[5]
 * are the baseline origin in PDF space (bottom-left origin, ISO 32000).
 * Partial item coverage is approximated by proportional character slicing,
 * the standard approach over per-glyph metrics, which pdf.js does not expose
 * per item. The viewport's convertToViewportRectangle applies the scale and
 * the bottom-left to top-left y-flip.
 */

export interface PdfTextItemLike {
  str: string;
  /** [a, b, c, d, e, f]; e/f = baseline origin in PDF space. */
  transform: number[];
  width: number;
  height: number;
  hasEOL?: boolean;
}

export interface ViewportLike {
  convertToViewportRectangle(rect: number[]): number[];
}

/** A matched run inside one text item. endChar is exclusive. */
export interface ItemSpan {
  itemIndex: number;
  startChar: number;
  endChar: number;
}

export type MatchMode = "spaces" | "squash";

export interface AnchorMatch {
  spans: ItemSpan[];
  mode: MatchMode;
}

/** A screen-space rectangle, top-left origin, CSS pixels at the render scale. */
export interface AnchorRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

/** Squash-mode matches shorter than this many alphanumerics are refused:
 *  a 3-character needle stripped of spacing would anchor almost anywhere. */
const SQUASH_MIN_LENGTH = 6;

const CHAR_FOLD: Record<string, string> = {
  "‘": "'",
  "’": "'",
  "‚": "'",
  "‛": "'",
  "“": '"',
  "”": '"',
  "„": '"',
  "«": '"',
  "»": '"',
  "–": "-",
  "—": "-",
  "−": "-",
  " ": " "
};

function foldChar(ch: string): string {
  return CHAR_FOLD[ch] ?? ch;
}

function isSpaceChar(ch: string): boolean {
  return /\s/.test(ch);
}

function isSquashKept(ch: string): boolean {
  return /[a-z0-9]/.test(ch);
}

/** Normalize a quote into a needle for the given mode. Empty result = nothing
 *  matchable (the caller treats that as no anchor, not as a universal match). */
export function normalizeQuote(quote: string, mode: MatchMode): string {
  if (typeof quote !== "string") {
    return "";
  }
  const out: string[] = [];
  let pendingSpace = false;
  for (const raw of quote) {
    const ch = foldChar(raw).toLowerCase();
    if (isSpaceChar(ch)) {
      pendingSpace = out.length > 0;
      continue;
    }
    if (mode === "squash" && !isSquashKept(ch)) {
      continue;
    }
    if (mode === "spaces" && pendingSpace) {
      out.push(" ");
    }
    pendingSpace = false;
    out.push(ch);
  }
  return out.join("");
}

interface CombinedPosition {
  item: number;
  char: number;
}

interface CombinedText {
  text: string;
  /** pos[i] = source position of normalized char i (spaces anchor to the
   *  character that follows them). */
  pos: CombinedPosition[];
}

/** Concatenate items into one normalized haystack with a position map.
 *  Item boundaries count as potential spaces in "spaces" mode: pdf.js
 *  usually groups a line's words into items without trailing spaces, so a
 *  boundary is far more often a real word gap than a mid-word split. The
 *  mid-word split case falls through to "squash". */
export function combineItems(items: PdfTextItemLike[], mode: MatchMode): CombinedText {
  const text: string[] = [];
  const pos: CombinedPosition[] = [];
  let pendingSpace = false;
  const safeItems = Array.isArray(items) ? items : [];
  safeItems.forEach((item, itemIndex) => {
    const str = typeof item?.str === "string" ? item.str : "";
    for (let c = 0; c < str.length; c += 1) {
      const ch = foldChar(str[c]).toLowerCase();
      if (isSpaceChar(ch)) {
        pendingSpace = text.length > 0;
        continue;
      }
      if (mode === "squash" && !isSquashKept(ch)) {
        continue;
      }
      if (mode === "spaces" && pendingSpace) {
        text.push(" ");
        pos.push({ item: itemIndex, char: c });
      }
      pendingSpace = false;
      text.push(ch);
      pos.push({ item: itemIndex, char: c });
    }
    if (str.length > 0) {
      pendingSpace = text.length > 0;
    }
  });
  return { text: text.join(""), pos };
}

function spansFromPositions(positions: CombinedPosition[]): ItemSpan[] {
  const spans: ItemSpan[] = [];
  for (const p of positions) {
    const last = spans[spans.length - 1];
    if (last && last.itemIndex === p.item) {
      last.startChar = Math.min(last.startChar, p.char);
      last.endChar = Math.max(last.endChar, p.char + 1);
    } else {
      spans.push({ itemIndex: p.item, startChar: p.char, endChar: p.char + 1 });
    }
  }
  return spans;
}

/**
 * Locate the quote in a page's text items. Returns the covered item spans and
 * which pass matched, or null when the passage is honestly not there.
 */
export function matchQuoteInItems(quote: string, items: PdfTextItemLike[]): AnchorMatch | null {
  for (const mode of ["spaces", "squash"] as const) {
    const needle = normalizeQuote(quote, mode);
    if (needle.length === 0) {
      continue;
    }
    if (mode === "squash" && needle.length < SQUASH_MIN_LENGTH) {
      continue;
    }
    const hay = combineItems(items, mode);
    const at = hay.text.indexOf(needle);
    if (at < 0) {
      continue;
    }
    const spans = spansFromPositions(hay.pos.slice(at, at + needle.length));
    if (spans.length > 0) {
      return { mode, spans };
    }
  }
  return null;
}

/** Vertical overlap fraction of two rects relative to the shorter one. */
function verticalOverlap(a: AnchorRect, b: AnchorRect): number {
  const top = Math.max(a.top, b.top);
  const bottom = Math.min(a.top + a.height, b.top + b.height);
  const overlap = bottom - top;
  const shorter = Math.max(1e-6, Math.min(a.height, b.height));
  return overlap / shorter;
}

/** Merge same-line neighbours so a one-line quote draws one clean underline
 *  instead of a dashed run of per-item slivers. */
export function mergeLineRects(rects: AnchorRect[]): AnchorRect[] {
  const merged: AnchorRect[] = [];
  for (const rect of rects) {
    const last = merged[merged.length - 1];
    if (last && verticalOverlap(last, rect) > 0.5) {
      const left = Math.min(last.left, rect.left);
      const right = Math.max(last.left + last.width, rect.left + rect.width);
      const top = Math.min(last.top, rect.top);
      const bottom = Math.max(last.top + last.height, rect.top + rect.height);
      last.left = left;
      last.top = top;
      last.width = right - left;
      last.height = bottom - top;
    } else {
      merged.push({ ...rect });
    }
  }
  return merged;
}

/**
 * Project matched spans to screen-space rectangles via the page viewport.
 * One rect per matched line after merging.
 */
export function spansToViewportRects(
  spans: ItemSpan[],
  items: PdfTextItemLike[],
  viewport: ViewportLike
): AnchorRect[] {
  const rects: AnchorRect[] = [];
  const safeItems = Array.isArray(items) ? items : [];
  const safeSpans = Array.isArray(spans) ? spans : [];
  for (const span of safeSpans) {
    const item = safeItems[span.itemIndex];
    if (
      !item ||
      typeof item.str !== "string" ||
      item.str.length === 0 ||
      !(item.width > 0) ||
      !Number.isFinite(span.startChar) ||
      !Number.isFinite(span.endChar)
    ) {
      continue;
    }
    const x = item.transform?.[4];
    const y = item.transform?.[5];
    if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(item.height)) {
      continue;
    }
    const fraction = (n: number) => Math.max(0, Math.min(1, n / item.str.length));
    const x1 = x + fraction(span.startChar) * item.width;
    const x2 = x + fraction(span.endChar) * item.width;
    const projected = viewport.convertToViewportRectangle([x1, y, x2, y + item.height]);
    if (projected.some((value) => !Number.isFinite(value))) {
      continue;
    }
    const left = Math.min(projected[0], projected[2]);
    const top = Math.min(projected[1], projected[3]);
    rects.push({
      left,
      top,
      width: Math.abs(projected[2] - projected[0]),
      height: Math.abs(projected[3] - projected[1])
    });
  }
  return mergeLineRects(rects);
}

/**
 * Search the document for the quote, preferring the cited page and spiralling
 * outward (cited pages are occasionally off by one after re-pagination).
 * The page fetcher is injected so this stays pure and testable.
 */
export async function findAnchorPage(
  getPageItems: (pageNumber: number) => Promise<PdfTextItemLike[]>,
  pageCount: number,
  quote: string,
  preferredPage?: number | null
): Promise<{ page: number; match: AnchorMatch } | null> {
  if (pageCount <= 0) {
    return null;
  }
  const order: number[] = [];
  const seen = new Set<number>();
  const push = (page: number) => {
    if (page >= 1 && page <= pageCount && !seen.has(page)) {
      seen.add(page);
      order.push(page);
    }
  };
  const start =
    preferredPage && preferredPage >= 1 && preferredPage <= pageCount ? preferredPage : 1;
  push(start);
  for (let step = 1; order.length < pageCount; step += 1) {
    push(start + step);
    push(start - step);
  }
  for (const page of order) {
    let items: PdfTextItemLike[];
    try {
      items = await getPageItems(page);
    } catch {
      // An unreadable page is honestly "no match here," not a reason to
      // abandon the rest of the document — keep spiralling outward.
      continue;
    }
    const match = matchQuoteInItems(quote, items);
    if (match) {
      return { match, page };
    }
  }
  return null;
}
