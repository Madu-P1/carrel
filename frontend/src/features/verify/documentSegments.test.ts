import { describe, expect, it } from "vitest";

import type { VerifyClaimVerdict } from "@/services/api/endpoints";

import {
  paragraphsFromSegments,
  segmentDraft,
  type ClaimSegment,
  type DocumentSegment
} from "./documentSegments";

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
