import { h, type ComponentChildren } from "preact";

import styles from "./cloze.module.css";

/**
 * PR 5.1 of flashcards-focus (ADR 0002) — cloze marker `{{cN::term}}`.
 *
 * The MVP supports the single-occlusion Anki form (one or more
 * markers in the same source). Three-segment markers
 * (`{{cN::term::hint}}`) are out of scope; the regex's `[^}]+` group
 * accepts them but the render treats the entire inner text as the
 * term and would render the wrong thing — explicit reject at the
 * route layer (services/study.py validates the same regex shape).
 */
const CLOZE_MARKER_RE = /\{\{c\d+::([^}]+)\}\}/g;

export function isClozeText(text: string | null | undefined): boolean {
  if (!text) return false;
  CLOZE_MARKER_RE.lastIndex = 0;
  return CLOZE_MARKER_RE.test(text);
}

/**
 * Render cloze source text for the front or back face.
 *
 * front: each marker is replaced with a visual placeholder, e.g.
 *   "The mitochondrion is the {{c1::powerhouse}} of the cell"
 *   →
 *   "The mitochondrion is the [.....] of the cell"
 *
 * back: each marker is replaced with the term itself, wrapped in a
 * span carrying the `.term` style hook (accent color via the design
 * system tokens) so the user can see what filled the blank.
 *
 * Returns Preact children compatible with FlashcardFace's `body` prop.
 */
export function renderClozeBody(
  source: string,
  face: "front" | "back",
): ComponentChildren {
  if (!source) return null;
  const nodes: ComponentChildren[] = [];
  let lastEnd = 0;
  let keyCounter = 0;
  CLOZE_MARKER_RE.lastIndex = 0;
  let match: RegExpExecArray | null = CLOZE_MARKER_RE.exec(source);
  while (match !== null) {
    if (match.index > lastEnd) {
      nodes.push(source.slice(lastEnd, match.index));
    }
    const term = match[1];
    if (face === "front") {
      nodes.push(
        h(
          "span",
          { className: styles.blank, "aria-label": "blanked term", key: `b${keyCounter}` },
          "[…]",
        ),
      );
    } else {
      nodes.push(
        h("span", { className: styles.term, key: `t${keyCounter}` }, term),
      );
    }
    lastEnd = match.index + match[0].length;
    keyCounter += 1;
    match = CLOZE_MARKER_RE.exec(source);
  }
  if (lastEnd < source.length) {
    nodes.push(source.slice(lastEnd));
  }
  return nodes;
}
