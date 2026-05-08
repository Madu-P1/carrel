import { useEffect } from "preact/hooks";

import { reader } from "@/services/api/endpoints";

import { requestReaderPage } from "../state";

/**
 * PR 4.2: typed-node deep link.
 *
 * The Ask cards UI (PR 4.1) navigates to `/reader/{doc_id}?node={node_id}`.
 * This hook:
 *   1. Fetches the node by id from `/api/reader/node/{id}`.
 *   2. Verifies the node belongs to the reader's current doc.
 *   3. Requests the node's page via the existing reader state (the
 *      PdfViewer already knows how to scroll to a requested page).
 *   4. After the page render settles, walks the rendered text in the
 *      DOM and wraps the first occurrence of the node's verbatim_text
 *      in a `<mark>` element. The mark gets scrolled into view and
 *      pulses for one beat, then unwraps.
 *
 * Char-offset alignment with the pypdf-rendered reader text is the
 * Risk #4 the parent algorithm spec flagged in PR 1. Until that's
 * resolved (canonical-text reader pane, PR 4.3+), the safest path is
 * a verbatim-text search: if Docling extracted "Photosystem II splits
 * water molecules…" the same string will exist in the rendered chunk
 * — text-search is robust to char-offset drift even when the offsets
 * themselves are wrong.
 *
 * If the verbatim text is NOT found in the rendered DOM (rare —
 * happens when Docling's extraction differs from the chunks renderer
 * on whitespace or hyphenation), the reader still navigates to the
 * page; only the highlight is silently skipped. Page-level navigation
 * is the worst-case UX, never an error.
 */

const HIGHLIGHT_CLASS = "carrel-node-highlight";
const HIGHLIGHT_DURATION_MS = 4000;
const PAINT_RETRY_BUDGET_MS = 1500;
const SEARCH_PREFIX_CHARS = 60;

function _normaliseWhitespace(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function _findRangeForText(root: HTMLElement, needle: string): Range | null {
  if (!needle) return null;
  const target = _normaliseWhitespace(needle).slice(0, SEARCH_PREFIX_CHARS);
  if (!target) return null;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  // Capture text nodes + a normalised text view so cross-node matches
  // can be located via index arithmetic.
  const segments: { node: Text; normalised: string }[] = [];
  for (
    let current = walker.nextNode() as Text | null;
    current !== null;
    current = walker.nextNode() as Text | null
  ) {
    const text = (current.nodeValue ?? "").trim();
    if (!text) continue;
    segments.push({ node: current, normalised: _normaliseWhitespace(text) });
  }
  if (segments.length === 0) return null;

  // Try single-node match first — it's the common case for body
  // paragraphs rendered as one span.
  for (const seg of segments) {
    const idx = seg.normalised.indexOf(target);
    if (idx >= 0) {
      const range = document.createRange();
      // Map normalised index back to the original-text index. We
      // approximate by walking the original text and counting non-
      // whitespace runs — exact for most cases since whitespace
      // collapse is the only normalisation we apply.
      const originalStart = _mapNormalisedIndex(seg.node.nodeValue ?? "", idx);
      const length = Math.min(
        target.length,
        (seg.node.nodeValue ?? "").length - originalStart,
      );
      try {
        range.setStart(seg.node, originalStart);
        range.setEnd(seg.node, originalStart + length);
        return range;
      } catch {
        return null;
      }
    }
  }

  // Cross-node fallback: concatenate normalised segments and search
  // the joined string. If found, walk the segments back to locate the
  // start node + offset.
  const joined = segments.map((s) => s.normalised).join(" ");
  const offsetInJoined = joined.indexOf(target);
  if (offsetInJoined < 0) return null;
  let cursor = 0;
  for (const seg of segments) {
    const segLen = seg.normalised.length;
    if (cursor + segLen >= offsetInJoined) {
      const indexInSegment = offsetInJoined - cursor;
      const originalStart = _mapNormalisedIndex(
        seg.node.nodeValue ?? "",
        indexInSegment,
      );
      const range = document.createRange();
      try {
        // We don't try to span across nodes — wrapping a multi-node
        // range in a single `<mark>` requires extractContents which
        // can disrupt event handlers on the chunk DOM. Highlight the
        // start segment's tail; that's still anchored to the right
        // passage.
        range.setStart(seg.node, originalStart);
        range.setEnd(
          seg.node,
          Math.min(
            (seg.node.nodeValue ?? "").length,
            originalStart + Math.max(8, segLen - indexInSegment),
          ),
        );
        return range;
      } catch {
        return null;
      }
    }
    cursor += segLen + 1; // +1 for the join space
  }
  return null;
}

function _mapNormalisedIndex(original: string, normalisedIndex: number): number {
  let n = 0;
  let prevWasSpace = false;
  for (let i = 0; i < original.length; i += 1) {
    const ch = original[i];
    const isSpace = /\s/.test(ch);
    if (isSpace) {
      if (prevWasSpace) {
        // collapsed in normalised text — don't advance n
        continue;
      }
      prevWasSpace = true;
    } else {
      prevWasSpace = false;
    }
    if (n === normalisedIndex) return i;
    n += 1;
  }
  return Math.max(0, original.length - 1);
}

function _wrapRangeWithMark(range: Range): HTMLElement | null {
  const mark = document.createElement("mark");
  mark.className = HIGHLIGHT_CLASS;
  try {
    range.surroundContents(mark);
    return mark;
  } catch {
    // Range crossed an element boundary. Fall back to extract+insert
    // which always succeeds.
    try {
      const fragment = range.extractContents();
      mark.appendChild(fragment);
      range.insertNode(mark);
      return mark;
    } catch {
      return null;
    }
  }
}

function _scheduleHighlight(verbatimText: string): () => void {
  let cancelled = false;
  let mark: HTMLElement | null = null;
  let unwrapTimer: number | null = null;
  const start = performance.now();

  const tryHighlight = () => {
    if (cancelled || mark) return;
    const root = document.body;
    if (!root) return;
    const range = _findRangeForText(root, verbatimText);
    if (!range) {
      if (performance.now() - start < PAINT_RETRY_BUDGET_MS) {
        requestAnimationFrame(tryHighlight);
      }
      return;
    }
    mark = _wrapRangeWithMark(range);
    if (!mark) return;
    // scrollIntoView is best-effort. JSDOM's no-op throws a TypeError
    // ("not a function") and pre-Chromium versions reject the options
    // bag. Either way, falling back to a static highlight is fine.
    try {
      if (typeof mark.scrollIntoView === "function") {
        mark.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    } catch {
      /* no-op */
    }
    unwrapTimer = window.setTimeout(() => {
      if (!mark) return;
      mark.classList.add(`${HIGHLIGHT_CLASS}--fade`);
      window.setTimeout(() => {
        if (!mark) return;
        // Replace the mark with its children so the DOM returns to
        // its pre-highlight shape — keeps the chunk renderer's event
        // bindings untouched.
        const parent = mark.parentNode;
        while (parent && mark.firstChild) {
          parent.insertBefore(mark.firstChild, mark);
        }
        if (parent) parent.removeChild(mark);
        mark = null;
      }, 600);
    }, HIGHLIGHT_DURATION_MS);
  };

  requestAnimationFrame(tryHighlight);

  return () => {
    cancelled = true;
    if (unwrapTimer !== null) window.clearTimeout(unwrapTimer);
    if (mark && mark.parentNode) {
      const parent = mark.parentNode;
      while (mark.firstChild) parent.insertBefore(mark.firstChild, mark);
      parent.removeChild(mark);
    }
  };
}

export function useNodeDeepLink(docId: string | null, nodeId: number | null) {
  useEffect(() => {
    if (!docId || !nodeId) return;
    let cancelled = false;
    let cleanupHighlight: (() => void) | null = null;

    void (async () => {
      try {
        const node = await reader.fetchNode(nodeId);
        if (cancelled) return;
        if (node.doc_id !== docId) return;
        if (node.page !== null && node.page !== undefined) {
          requestReaderPage(node.page);
        }
        // Wait one frame for the page-render to start, then begin the
        // verbatim-text search. The search itself polls for up to
        // PAINT_RETRY_BUDGET_MS so it tolerates the page taking a
        // moment to render.
        requestAnimationFrame(() => {
          if (cancelled) return;
          cleanupHighlight = _scheduleHighlight(node.verbatim_text);
        });
      } catch {
        // Reader silently degrades to whatever the URL got it to —
        // typically the doc opened on page 1. A failed fetch should
        // never throw to the user.
      }
    })();

    return () => {
      cancelled = true;
      if (cleanupHighlight) cleanupHighlight();
    };
  }, [docId, nodeId]);
}
