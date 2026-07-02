import { describe, expect, it } from "vitest";

import type { VerifyClaimVerdict } from "@/services/api/endpoints";

import {
  highlightRuns,
  paragraphsFromSegments,
  placedSpans,
  segmentDraft,
  type ClaimSegment,
  type DocumentSegment
} from "./documentSegments";

describe("highlightRuns — exact-token highlight inside a flagged statement", () => {
  it("marks a verbatim flagged span and leaves the rest plain", () => {
    const runs = highlightRuns("60 billion for 6%", ["60 billion"]);
    expect(runs).toEqual([
      { text: "60 billion", flagged: true },
      { text: " for 6%", flagged: false }
    ]);
  });

  it("never marks a span that is not literally present (canonical-value safety)", () => {
    // The per-type parametric path carries canonical values; a span absent from
    // the text must NOT highlight anything (no mis-highlight on a near miss).
    const safe = highlightRuns("turnover 20% France", ["0.2"]);
    expect(safe).toEqual([{ text: "turnover 20% France", flagged: false }]);
  });

  it("longest match wins and runs never overlap or lose text", () => {
    const text = "the cap is 20% not 20% per year";
    const runs = highlightRuns(text, ["20%", "20% per year"]);
    expect(runs.map((r) => r.text).join("")).toBe(text);
    expect(runs.find((r) => r.text === "20% per year")?.flagged).toBe(true);
  });

  it("returns a single unflagged run when there are no spans", () => {
    expect(highlightRuns("plain text", [])).toEqual([{ text: "plain text", flagged: false }]);
  });
});

// Build a claim verdict with a placement. verdict drives the disposition tier:
// "verified" + no case flags -> pass (unmarked); "unsupported" -> flag; etc.
function card(
  claim_index: number,
  opts: {
    placed?: boolean;
    start?: number | null;
    end?: number | null;
    method?: "exact" | "fuzzy" | "unplaced";
    verdict?: "verified" | "unsupported" | "unknown";
    case_verdicts?: unknown[];
  } = {}
): VerifyClaimVerdict {
  const placed = opts.placed ?? true;
  return {
    claim_index,
    claim_text: `claim ${claim_index}`,
    verdict: opts.verdict ?? "unsupported", // default flag tier so spans are visible
    citations: [],
    case_verdicts: (opts.case_verdicts ?? []) as VerifyClaimVerdict["case_verdicts"],
    unsupported_reason: null,
    placement: placed
      ? {
          placed: true,
          method: opts.method ?? "exact",
          char_start: opts.start ?? 0,
          char_end: opts.end ?? 0
        }
      : { placed: false, method: "unplaced", char_start: null, char_end: null }
  } as VerifyClaimVerdict;
}

function claimSegs(segs: DocumentSegment[]): ClaimSegment[] {
  return segs.filter((s): s is ClaimSegment => s.kind === "claim");
}

const DRAFT = "Alpha holds firmly. Beta dissents loudly. Gamma concurs fully.";
//             0123456789...           ^Beta at 20            ^Gamma at 41

describe("segmentDraft — verbatim preservation", () => {
  it("concatenation of all segments equals the draft exactly (no loss)", () => {
    const cards = [card(0, { start: 0, end: 18 }), card(1, { start: 41, end: 60 })];
    const segs = segmentDraft(DRAFT, cards);
    expect(segs.map((s) => s.text).join("")).toBe(DRAFT);
  });

  it("text outside any span is preserved as plain text runs", () => {
    const segs = segmentDraft(DRAFT, [card(0, { start: 0, end: 18 })]);
    // first segment is the claim, then the remaining prose is a text run.
    expect(segs[0].kind).toBe("claim");
    expect(segs[segs.length - 1].kind).toBe("text");
    expect(segs.map((s) => s.text).join("")).toBe(DRAFT);
  });

  it("no claims -> a single text segment of the whole draft", () => {
    expect(segmentDraft(DRAFT, [])).toEqual([{ kind: "text", text: DRAFT }]);
  });

  it("empty draft -> no segments", () => {
    expect(segmentDraft("", [card(0, { start: 0, end: 5 })])).toEqual([]);
  });
});

describe("untreated prose contributes no card", () => {
  // The untreated / could-not-check split (engine side: services/legal/
  // deterministic_envelope.py + services/verify.py). The backend emits NO card for
  // an anchor-free sentence, so the only cards reaching the frontend are the treated
  // ones. The renderer must show every cardless sentence as plain draft text and
  // never synthesize a claim span for it.
  it("a draft with a card for only one sentence leaves the rest as plain text", () => {
    // Only the middle sentence has a card; the two anchor-free sentences around it
    // are untreated (no card emitted by the backend).
    const segs = segmentDraft(DRAFT, [card(1, { start: 20, end: 40 })]);
    expect(claimSegs(segs)).toHaveLength(1);
    expect(claimSegs(segs)[0].text).toContain("Beta");
    const textRuns = segs
      .filter((s) => s.kind === "text")
      .map((s) => s.text)
      .join("");
    expect(textRuns).toContain("Alpha holds firmly.");
    expect(textRuns).toContain("Gamma concurs fully.");
    expect(segs.map((s) => s.text).join("")).toBe(DRAFT); // no loss
  });

  it("a pure-prose draft (no cards at all) is a single plain-text document", () => {
    expect(segmentDraft(DRAFT, [])).toEqual([{ kind: "text", text: DRAFT }]);
  });
});

describe("placedSpans — only placed, valid ranges become spans", () => {
  it("unplaced claims contribute no span", () => {
    const segs = segmentDraft(DRAFT, [card(0, { placed: false })]);
    expect(claimSegs(segs)).toHaveLength(0);
  });

  it("malformed ranges are dropped (out of bounds, empty, inverted)", () => {
    const cards = [
      card(0, { start: -1, end: 5 }), // negative
      card(1, { start: 5, end: 5 }), // empty
      card(2, { start: 10, end: 8 }), // inverted
      card(3, { start: 0, end: 9999 }) // past end
    ];
    expect(claimSegs(segmentDraft(DRAFT, cards))).toHaveLength(0);
  });

  it("carries the placement method (exact vs fuzzy) onto the span", () => {
    const cards = [
      card(0, { start: 0, end: 18, method: "exact" }),
      card(1, { start: 41, end: 60, method: "fuzzy" })
    ];
    const cs = claimSegs(segmentDraft(DRAFT, cards));
    expect(cs[0].method).toBe("exact");
    expect(cs[1].method).toBe("fuzzy");
  });
});

describe("placedSpans — overlap is resolved deterministically, never double-marked", () => {
  it("an overlapping span is dropped; the earlier/longer one is kept", () => {
    const cards = [
      card(0, { start: 0, end: 18 }), // "Alpha holds firmly"
      card(1, { start: 6, end: 18 }) // overlaps inside claim 0
    ];
    const cs = claimSegs(segmentDraft(DRAFT, cards));
    expect(cs).toHaveLength(1);
    expect(cs[0].claimIndex).toBe(0);
  });

  it("is order-independent: same result when cards arrive reversed", () => {
    const a = claimSegs(
      segmentDraft(DRAFT, [card(0, { start: 0, end: 18 }), card(1, { start: 41, end: 60 })])
    );
    const b = claimSegs(
      segmentDraft(DRAFT, [card(1, { start: 41, end: 60 }), card(0, { start: 0, end: 18 })])
    );
    expect(a.map((s) => s.claimIndex)).toEqual(b.map((s) => s.claimIndex));
  });

  it("adjacent (touching) ranges both survive without overlap", () => {
    // "Alpha holds firmly." = [0,19); next starts exactly at 19.
    const cards = [card(0, { start: 0, end: 19 }), card(1, { start: 19, end: 40 })];
    const cs = claimSegs(segmentDraft(DRAFT, cards));
    expect(cs).toHaveLength(2);
    expect(cs.map((s) => s.claimIndex)).toEqual([0, 1]);
  });

  it("spans come out in draft order regardless of input order", () => {
    const segs = segmentDraft(DRAFT, [card(1, { start: 41, end: 60 }), card(0, { start: 0, end: 18 })]);
    const cs = claimSegs(segs);
    expect(cs[0].claimIndex).toBe(0);
    expect(cs[1].claimIndex).toBe(1);
    expect(cs[0].text).toBe("Alpha holds firmly");
  });
});

describe("tier mapping", () => {
  it("a supported (verified, no flags) claim still produces a span, tier pass", () => {
    const cs = claimSegs(segmentDraft(DRAFT, [card(0, { start: 0, end: 18, verdict: "verified" })]));
    expect(cs[0].tier).toBe("pass");
  });

  it("an unsupported claim produces a flag-tier span", () => {
    const cs = claimSegs(segmentDraft(DRAFT, [card(0, { start: 0, end: 18, verdict: "unsupported" })]));
    expect(cs[0].tier).toBe("flag");
  });
});

describe("paragraphsFromSegments", () => {
  it("splits text segments on blank lines into separate paragraphs", () => {
    const draft = "First para sentence.\n\nSecond para sentence.";
    const segs = segmentDraft(draft, []);
    const paras = paragraphsFromSegments(segs);
    expect(paras).toHaveLength(2);
    expect(paras[0].map((s) => s.text).join("")).toContain("First para");
    expect(paras[1].map((s) => s.text).join("")).toContain("Second para");
  });

  it("keeps a claim span intact within its paragraph", () => {
    const draft = "Intro.\n\nAlpha holds firmly here.";
    const start = draft.indexOf("Alpha holds firmly");
    const segs = segmentDraft(draft, [card(0, { start, end: start + 18 })]);
    const paras = paragraphsFromSegments(segs);
    expect(paras).toHaveLength(2);
    expect(paras[1].some((s) => s.kind === "claim")).toBe(true);
  });
});

// Robustness invariant (T-lectern-segments): no malformed, empty, or null
// document/segment input may make this module throw, emit overlapping
// segments, emit out-of-order segments, or emit a segment whose offsets fall
// outside the source text. An empty list is always a valid result. Every test
// below is named for the input category it locks.
describe("robustness invariant — malformed/empty/null input never throws, overlaps, reorders, or goes out of bounds", () => {
  function assertWellFormed(spans: Array<{ start: number; end: number }>, textLength: number) {
    let lastEnd = 0;
    for (const span of spans) {
      expect(span.start).toBeGreaterThanOrEqual(0);
      expect(span.end).toBeLessThanOrEqual(textLength);
      expect(span.start).toBeLessThan(span.end);
      expect(span.start).toBeGreaterThanOrEqual(lastEnd); // ascending, non-overlapping
      lastEnd = span.end;
    }
  }

  it("(a) empty document text yields no segments, no throw", () => {
    expect(() => segmentDraft("", [card(0, { start: 0, end: 5 })])).not.toThrow();
    expect(segmentDraft("", [card(0, { start: 0, end: 5 })])).toEqual([]);
  });

  it("(a) zero draftLength in placedSpans yields no spans, no throw", () => {
    expect(() => placedSpans(0, [card(0, { start: 0, end: 5 })])).not.toThrow();
    expect(placedSpans(0, [card(0, { start: 0, end: 5 })])).toEqual([]);
  });

  it("(b) zero-length text body with a non-empty claims array yields no segments", () => {
    const segs = segmentDraft("", [card(0, { start: 0, end: 1 }), card(1, { start: 2, end: 3 })]);
    expect(segs).toEqual([]);
  });

  it("(c) null cards passed to segmentDraft does not throw and falls back to plain text", () => {
    expect(() => segmentDraft(DRAFT, null as unknown as VerifyClaimVerdict[])).not.toThrow();
    expect(segmentDraft(DRAFT, null as unknown as VerifyClaimVerdict[])).toEqual([
      { kind: "text", text: DRAFT }
    ]);
  });

  it("(c) undefined cards passed to segmentDraft does not throw and falls back to plain text", () => {
    expect(() => segmentDraft(DRAFT, undefined as unknown as VerifyClaimVerdict[])).not.toThrow();
    expect(segmentDraft(DRAFT, undefined as unknown as VerifyClaimVerdict[])).toEqual([
      { kind: "text", text: DRAFT }
    ]);
  });

  it("(c) null cards passed directly to placedSpans does not throw and yields no spans", () => {
    expect(() => placedSpans(DRAFT.length, null as unknown as VerifyClaimVerdict[])).not.toThrow();
    expect(placedSpans(DRAFT.length, null as unknown as VerifyClaimVerdict[])).toEqual([]);
  });

  it("(c) undefined cards passed directly to placedSpans does not throw and yields no spans", () => {
    expect(() => placedSpans(DRAFT.length, undefined as unknown as VerifyClaimVerdict[])).not.toThrow();
    expect(placedSpans(DRAFT.length, undefined as unknown as VerifyClaimVerdict[])).toEqual([]);
  });

  it("(c) null segments passed to paragraphsFromSegments does not throw and yields no paragraphs", () => {
    expect(() => paragraphsFromSegments(null as unknown as DocumentSegment[])).not.toThrow();
    expect(paragraphsFromSegments(null as unknown as DocumentSegment[])).toEqual([]);
  });

  it("(c) undefined segments passed to paragraphsFromSegments does not throw and yields no paragraphs", () => {
    expect(() => paragraphsFromSegments(undefined as unknown as DocumentSegment[])).not.toThrow();
    expect(paragraphsFromSegments(undefined as unknown as DocumentSegment[])).toEqual([]);
  });

  it("(d) empty claims array is a valid passthrough (single text segment, no throw)", () => {
    expect(() => segmentDraft(DRAFT, [])).not.toThrow();
    expect(segmentDraft(DRAFT, [])).toEqual([{ kind: "text", text: DRAFT }]);
  });

  it("(d) empty segments array passed to paragraphsFromSegments yields no paragraphs", () => {
    expect(paragraphsFromSegments([])).toEqual([]);
  });

  it("(e) NaN char_end does not throw and does not silently drop the remainder of the draft", () => {
    // Regression for a real defect: NaN end bypassed the relational bounds
    // guard (all comparisons against NaN are false), got kept as a span, and
    // corrupted the cursor so every char after it vanished from the output.
    const cards = [card(0, { start: 0, end: NaN })];
    expect(() => segmentDraft(DRAFT, cards)).not.toThrow();
    const segs = segmentDraft(DRAFT, cards);
    expect(segs.map((s) => s.text).join("")).toBe(DRAFT);
    expect(claimSegs(segs)).toHaveLength(0);
  });

  it("(e) NaN char_start does not throw and does not corrupt the span list", () => {
    const cards = [card(0, { start: NaN, end: 18 })];
    expect(() => segmentDraft(DRAFT, cards)).not.toThrow();
    const segs = segmentDraft(DRAFT, cards);
    expect(segs.map((s) => s.text).join("")).toBe(DRAFT);
    expect(claimSegs(segs)).toHaveLength(0);
  });

  it("(e) Infinity offsets are treated as out-of-bounds and dropped, never throw", () => {
    const cards = [card(0, { start: 0, end: Infinity }), card(1, { start: -Infinity, end: 5 })];
    expect(() => segmentDraft(DRAFT, cards)).not.toThrow();
    expect(claimSegs(segmentDraft(DRAFT, cards))).toHaveLength(0);
  });

  it("(e) malformed offsets passed directly to placedSpans never produce a span (none are valid)", () => {
    const cards = [
      card(0, { start: -1, end: 5 }), // negative
      card(1, { start: 5, end: 5 }), // empty
      card(2, { start: 10, end: 8 }), // inverted
      card(3, { start: 0, end: 9999 }), // past end
      card(4, { start: NaN, end: 10 }), // NaN start
      card(5, { start: 0, end: NaN }) // NaN end
    ];
    const spans = placedSpans(DRAFT.length, cards);
    assertWellFormed(spans, DRAFT.length);
    expect(spans).toEqual([]);
  });

  it("(f) overlapping ranges resolve to a non-overlapping, in-bounds, ordered span list", () => {
    const cards = [
      card(0, { start: 0, end: 18 }),
      card(1, { start: 6, end: 30 }), // overlaps claim 0
      card(2, { start: 41, end: 60 })
    ];
    const spans = placedSpans(DRAFT.length, cards);
    assertWellFormed(spans, DRAFT.length);
  });

  it("(g) shuffled/out-of-order input still yields ascending, non-overlapping placedSpans", () => {
    const cards = [
      card(2, { start: 41, end: 60 }),
      card(0, { start: 0, end: 18 }),
      card(1, { start: 20, end: 39 })
    ];
    const spans = placedSpans(DRAFT.length, cards);
    assertWellFormed(spans, DRAFT.length);
    expect(spans.map((s) => s.claimIndex)).toEqual([0, 1, 2]);
  });

  it("(h) single-character text with a [0,1) span segments correctly with no off-by-one throw", () => {
    const text = "A";
    const cards = [card(0, { start: 0, end: 1 })];
    expect(() => segmentDraft(text, cards)).not.toThrow();
    expect(segmentDraft(text, cards)).toEqual([
      { kind: "claim", text: "A", claimIndex: 0, tier: "flag", method: "exact" }
    ]);
  });

  it("(h) single-character text with no claims yields a single one-character text segment", () => {
    expect(segmentDraft("A", [])).toEqual([{ kind: "text", text: "A" }]);
  });

  it("(1) whitespace-only source text yields a single well-formed segment, no throw", () => {
    const whitespace = "   \n  ";
    expect(() => segmentDraft(whitespace, [])).not.toThrow();
    expect(segmentDraft(whitespace, [])).toEqual([{ kind: "text", text: whitespace }]);
  });

  it("(3) an anchor past the end of the source is dropped, not clamped — no fabricated highlight boundary", () => {
    // A clamped span would highlight text the engine never actually placed
    // there; dropping preserves the "never invent a span" contract and
    // leaves the claim visible elsewhere (verdict list / tray).
    const cards = [card(0, { start: 0, end: DRAFT.length + 500 })];
    const segs = segmentDraft(DRAFT, cards);
    expect(claimSegs(segs)).toHaveLength(0);
    expect(segs.map((s) => s.text).join("")).toBe(DRAFT);
  });

  it("(4) a reversed anchor (end before start) is dropped, never inverted into a negative-length span", () => {
    const cards = [card(0, { start: 30, end: 5 })];
    expect(() => placedSpans(DRAFT.length, cards)).not.toThrow();
    expect(placedSpans(DRAFT.length, cards)).toEqual([]);
  });

  it("(5) two anchors starting at the exact same offset resolve deterministically (longer wins)", () => {
    const cards = [
      card(0, { start: 0, end: 10 }),
      card(1, { start: 0, end: 18 }) // same start, longer — wins per the documented tie-break
    ];
    const spans = placedSpans(DRAFT.length, cards);
    expect(spans).toHaveLength(1);
    expect(spans[0].claimIndex).toBe(1);
    expect(spans[0].end).toBe(18);
  });

  it("(7) a placed anchor with null char_start/char_end is unusable and falls back to plain text, no throw", () => {
    const malformed: VerifyClaimVerdict = {
      ...card(0),
      placement: { placed: true, method: "exact", char_start: null, char_end: null }
    };
    expect(() => segmentDraft(DRAFT, [malformed])).not.toThrow();
    const segs = segmentDraft(DRAFT, [malformed]);
    expect(claimSegs(segs)).toHaveLength(0);
    expect(segs.map((s) => s.text).join("")).toBe(DRAFT);
  });

  it("(7) a placed anchor with an undefined char_end is unusable and falls back to plain text, no throw", () => {
    const malformed: VerifyClaimVerdict = {
      ...card(0),
      placement: { placed: true, method: "exact", char_start: 0 }
    };
    expect(() => segmentDraft(DRAFT, [malformed])).not.toThrow();
    expect(claimSegs(segmentDraft(DRAFT, [malformed]))).toHaveLength(0);
  });

  it("(8) an anchor landing mid-surrogate-pair slices on code-unit boundaries without corrupting adjacent text", () => {
    // "\u{1F600}" is a surrogate pair (2 UTF-16 code units). An anchor ending
    // between the high and low surrogate still must not throw or lose text.
    const text = "Alpha \u{1F600} Beta";
    const emojiIndex = text.indexOf("\u{1F600}"); // code-unit index of the high surrogate
    const cards = [card(0, { start: 0, end: emojiIndex + 1 })]; // ends mid-surrogate
    expect(() => segmentDraft(text, cards)).not.toThrow();
    const segs = segmentDraft(text, cards);
    expect(segs.map((s) => s.text).join("")).toBe(text); // lossless regardless of the split
  });

  it("(bonus) a null entry in the cards array is skipped, not thrown on", () => {
    const cards = [null, card(0, { start: 0, end: 18 })] as unknown as VerifyClaimVerdict[];
    expect(() => segmentDraft(DRAFT, cards)).not.toThrow();
    const segs = segmentDraft(DRAFT, cards);
    expect(claimSegs(segs)).toHaveLength(1);
    expect(segs.map((s) => s.text).join("")).toBe(DRAFT);
  });

  it("(regression) known-good two-claim placement output is unchanged by the added guards", () => {
    const cards = [card(0, { start: 0, end: 18 }), card(1, { start: 41, end: 60 })];
    const segs = segmentDraft(DRAFT, cards);
    expect(segs).toEqual([
      { kind: "claim", text: DRAFT.slice(0, 18), claimIndex: 0, tier: "flag", method: "exact" },
      { kind: "text", text: DRAFT.slice(18, 41) },
      { kind: "claim", text: DRAFT.slice(41, 60), claimIndex: 1, tier: "flag", method: "exact" },
      { kind: "text", text: DRAFT.slice(60) }
    ]);
  });
});
