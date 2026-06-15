/**
 * Cachet PR5b (Direction A, document-primary) — pure draft segmentation.
 *
 * Turns the lawyer's `draft_text` plus the per-claim `placement` ranges (from
 * PR5a, server-computed, never mis-pinned) into an ordered list of segments the
 * Workspace renderer maps to VNodes: plain-text runs interleaved with claim
 * spans. This is the pure, unit-tested core so the safety-critical rules live in
 * tested logic, not JSX (the same discipline as streamProgress.ts).
 *
 * Rules (each gated by documentSegments.test.ts):
 *  - Only a claim whose placement.placed === true and has a valid char range
 *    contributes a span. Unplaced claims contribute NOTHING here (they live in
 *    the tray); a span is never invented.
 *  - Spans never overlap. If two placed ranges overlap, the earlier-starting
 *    (then longer) one wins and the other is dropped from the document (it stays
 *    in the verdict list / tray); we never double-mark a character.
 *  - Text outside every span is preserved verbatim, in order, with no loss.
 *  - Each span carries its claim_index, disposition tier, and placement method
 *    so the renderer can mark flag/assistive/refusal/pass distinctly and render
 *    a `fuzzy` (approximate) placement differently from an `exact` one.
 *
 * No I/O, no rendering, no DOM. Returns data; the component renders it.
 */
import type { VerifyClaimVerdict } from "@/services/api/endpoints";

import { dispositionForClaim, type DispositionTier } from "./claimDisposition";

export type PlacementMethod = "exact" | "fuzzy" | "unplaced";

export interface TextSegment {
  kind: "text";
  text: string;
}

export interface ClaimSegment {
  kind: "claim";
  text: string;
  claimIndex: number;
  tier: DispositionTier;
  method: PlacementMethod;
}

export type DocumentSegment = TextSegment | ClaimSegment;

interface PlacedSpan {
  start: number;
  end: number;
  claimIndex: number;
  tier: DispositionTier;
  method: PlacementMethod;
}

/** Extract the valid, placed spans from the claim verdicts, resolving overlaps
 *  deterministically. Exported for direct unit testing of the overlap rule. */
export function placedSpans(draftLength: number, cards: VerifyClaimVerdict[]): PlacedSpan[] {
  const candidates: PlacedSpan[] = [];
  cards.forEach((card, i) => {
    const placement = card.placement;
    if (!placement || !placement.placed) return;
    const start = placement.char_start;
    const end = placement.char_end;
    if (typeof start !== "number" || typeof end !== "number") return;
    // Guard against malformed ranges: must be in-bounds and non-empty.
    if (start < 0 || end > draftLength || start >= end) return;
    const method: PlacementMethod = placement.method === "fuzzy" ? "fuzzy" : "exact";
    const claimIndex = typeof card.claim_index === "number" ? card.claim_index : i;
    candidates.push({ start, end, claimIndex, tier: dispositionForClaim(card).tier, method });
  });

  // Deterministic order: by start, then longer span first, then claim_index.
  candidates.sort((a, b) => a.start - b.start || b.end - a.end || a.claimIndex - b.claimIndex);

  // Greedily keep non-overlapping spans; drop any that overlaps a kept one.
  const kept: PlacedSpan[] = [];
  let lastEnd = 0;
  for (const span of candidates) {
    if (span.start >= lastEnd) {
      kept.push(span);
      lastEnd = span.end;
    }
  }
  return kept;
}

/**
 * Segment `draftText` into ordered text + claim runs using the placed spans.
 * The concatenation of all segment `text` equals `draftText` exactly (no loss).
 */
export function segmentDraft(
  draftText: string,
  cards: VerifyClaimVerdict[]
): DocumentSegment[] {
  const draft = draftText ?? "";
  if (!draft) return [];
  const spans = placedSpans(draft.length, cards);
  if (spans.length === 0) {
    return [{ kind: "text", text: draft }];
  }

  const segments: DocumentSegment[] = [];
  let cursor = 0;
  for (const span of spans) {
    if (span.start > cursor) {
      segments.push({ kind: "text", text: draft.slice(cursor, span.start) });
    }
    segments.push({
      kind: "claim",
      text: draft.slice(span.start, span.end),
      claimIndex: span.claimIndex,
      tier: span.tier,
      method: span.method
    });
    cursor = span.end;
  }
  if (cursor < draft.length) {
    segments.push({ kind: "text", text: draft.slice(cursor) });
  }
  return segments;
}

export interface HighlightRun {
  text: string;
  /** True for a run that is one of the flagged (contradicted) draft spans. */
  flagged: boolean;
}

/**
 * Split a claim span's text into runs, marking the verbatim ``spans`` the engine
 * flagged as contradictions (e.g. the altered figure "60 billion") so the
 * renderer can underline the precise changed token inside the statement.
 *
 * Safety rules (gated by documentSegments.test.ts):
 *  - Only literal substrings are marked; a span not present in ``text`` is
 *    ignored, so a canonical-but-not-verbatim value never mis-highlights.
 *  - Longest match wins at each position and runs never overlap, so two spans
 *    that share a prefix cannot double-mark a character.
 *  - The concatenation of all run ``text`` equals the input exactly (no loss).
 *  - No spans (or none found) returns a single unflagged run, so a caller can
 *    always render the result the same way.
 */
export function highlightRuns(text: string, spans: readonly string[]): HighlightRun[] {
  const needles = Array.from(
    new Set((spans ?? []).map((s) => s.trim()).filter((s) => s.length > 0 && text.includes(s)))
  ).sort((a, b) => b.length - a.length); // longest first: prefer the maximal match
  if (needles.length === 0) return [{ text, flagged: false }];

  const runs: HighlightRun[] = [];
  let buffer = "";
  let i = 0;
  const flush = () => {
    if (buffer) runs.push({ text: buffer, flagged: false });
    buffer = "";
  };
  while (i < text.length) {
    const hit = needles.find((n) => text.startsWith(n, i));
    if (hit) {
      flush();
      runs.push({ text: hit, flagged: true });
      i += hit.length;
    } else {
      buffer += text[i];
      i += 1;
    }
  }
  flush();
  return runs;
}

/**
 * Split a segment list into paragraphs on blank lines (\n\n+), preserving the
 * claim segments. A claim span never crosses a paragraph boundary in practice
 * (placements come from contiguous draft ranges), but if a text segment spans a
 * blank line it is split so each paragraph renders independently.
 */
export function paragraphsFromSegments(segments: DocumentSegment[]): DocumentSegment[][] {
  const paragraphs: DocumentSegment[][] = [];
  let current: DocumentSegment[] = [];
  const pushCurrent = () => {
    if (current.length > 0) paragraphs.push(current);
    current = [];
  };
  for (const seg of segments) {
    if (seg.kind === "text" && /\n\s*\n/.test(seg.text)) {
      const parts = seg.text.split(/\n\s*\n/);
      parts.forEach((part, idx) => {
        if (part) current.push({ kind: "text", text: part });
        if (idx < parts.length - 1) pushCurrent();
      });
    } else {
      current.push(seg);
    }
  }
  pushCurrent();
  return paragraphs;
}
