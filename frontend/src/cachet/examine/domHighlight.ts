/**
 * Anchor a cited passage inside rendered DOM (the docx-preview output, or a
 * plain-text record). Same honesty contract as the PDF anchor engine: an
 * exact normalized match wraps the run in <mark data-cachet-anchor> elements;
 * no match returns null and the caller says so on screen. Never a fabricated
 * highlight.
 *
 * Matching reuses the two-pass normalization from anchor.ts ("spaces", then
 * the length-gated "squash" fallback), walked over the container's text nodes.
 * Unlike PDF text items, DOM text nodes preserve real spacing, so a node
 * boundary is NOT treated as a space: inline formatting regularly splits a
 * word across nodes (<b>Veri</b>fication), and a synthetic space there would
 * break the spaces pass for exactly the runs lawyers bold.
 */

import { normalizeQuote, type MatchMode } from "./anchor";

const ANCHOR_ATTR = "data-cachet-anchor";

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
  " ": " "
};

function foldChar(ch: string): string {
  return CHAR_FOLD[ch] ?? ch;
}

interface NodePosition {
  node: number;
  char: number;
}

interface CombinedDomText {
  text: string;
  pos: NodePosition[];
}

function collectTextNodes(root: HTMLElement): Text[] {
  const walker = root.ownerDocument.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  let current = walker.nextNode();
  while (current) {
    nodes.push(current as Text);
    current = walker.nextNode();
  }
  return nodes;
}

function combineNodes(nodes: Text[], mode: MatchMode): CombinedDomText {
  const text: string[] = [];
  const pos: NodePosition[] = [];
  // The collapsed space anchors to the FIRST real space character of the run,
  // not the character after it, so a matched run's marks include their
  // boundary spaces and the underline stays continuous across node breaks.
  let pendingSpace: NodePosition | null = null;
  nodes.forEach((node, nodeIndex) => {
    const data = node.data;
    for (let c = 0; c < data.length; c += 1) {
      const ch = foldChar(data[c]).toLowerCase();
      if (/\s/.test(ch)) {
        if (text.length > 0 && pendingSpace === null) {
          pendingSpace = { node: nodeIndex, char: c };
        }
        continue;
      }
      if (mode === "squash" && !/[a-z0-9]/.test(ch)) {
        continue;
      }
      if (mode === "spaces" && pendingSpace !== null) {
        text.push(" ");
        pos.push(pendingSpace);
      }
      pendingSpace = null;
      text.push(ch);
      pos.push({ node: nodeIndex, char: c });
    }
  });
  return { text: text.join(""), pos };
}

interface NodeSpan {
  nodeIndex: number;
  startChar: number;
  endChar: number;
}

function spansFromPositions(positions: NodePosition[]): NodeSpan[] {
  const spans: NodeSpan[] = [];
  for (const p of positions) {
    const last = spans[spans.length - 1];
    if (last && last.nodeIndex === p.node) {
      last.startChar = Math.min(last.startChar, p.char);
      last.endChar = Math.max(last.endChar, p.char + 1);
    } else {
      spans.push({ nodeIndex: p.node, startChar: p.char, endChar: p.char + 1 });
    }
  }
  return spans;
}

const SQUASH_MIN_LENGTH = 6;

/** Remove every anchor mark previously laid down in this container, restoring
 *  the original text nodes. Safe to call on a container with none. */
export function clearAnchorMarks(root: HTMLElement): void {
  const marks = Array.from(root.querySelectorAll(`mark[${ANCHOR_ATTR}]`));
  for (const mark of marks) {
    const parent = mark.parentNode;
    if (!parent) {
      continue;
    }
    while (mark.firstChild) {
      parent.insertBefore(mark.firstChild, mark);
    }
    parent.removeChild(mark);
  }
  root.normalize();
}

/**
 * Find the quote in the container's text and wrap the matched run in
 * <mark data-cachet-anchor> elements (one per touched text node). Returns the
 * marks in document order, or null when the passage is honestly not present.
 */
export function markQuoteInDom(root: HTMLElement, quote: string): HTMLElement[] | null {
  clearAnchorMarks(root);
  const nodes = collectTextNodes(root);
  if (nodes.length === 0) {
    return null;
  }
  for (const mode of ["spaces", "squash"] as const) {
    const needle = normalizeQuote(quote, mode);
    if (needle.length === 0 || (mode === "squash" && needle.length < SQUASH_MIN_LENGTH)) {
      continue;
    }
    const hay = combineNodes(nodes, mode);
    const at = hay.text.indexOf(needle);
    if (at < 0) {
      continue;
    }
    const spans = spansFromPositions(hay.pos.slice(at, at + needle.length));
    const marks: HTMLElement[] = [];
    const doc = root.ownerDocument;
    for (const span of spans) {
      const node = nodes[span.nodeIndex];
      const parent = node.parentNode;
      if (!parent) {
        continue;
      }
      const run = node.splitText(span.startChar);
      run.splitText(span.endChar - span.startChar);
      const mark = doc.createElement("mark");
      mark.setAttribute(ANCHOR_ATTR, "true");
      parent.replaceChild(mark, run);
      mark.appendChild(run);
      marks.push(mark);
    }
    if (marks.length > 0) {
      return marks;
    }
  }
  return null;
}
