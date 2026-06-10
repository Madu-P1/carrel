import { describe, expect, it } from "vitest";

import {
  findAnchorPage,
  matchQuoteInItems,
  mergeLineRects,
  normalizeQuote,
  spansToViewportRects,
  type PdfTextItemLike,
  type ViewportLike
} from "./anchor";

function item(
  str: string,
  options: Partial<Omit<PdfTextItemLike, "str">> & { x?: number; y?: number } = {}
): PdfTextItemLike {
  const { x = 0, y = 700, ...rest } = options;
  return {
    str,
    transform: [12, 0, 0, 12, x, y],
    width: rest.width ?? str.length * 6,
    height: rest.height ?? 12,
    hasEOL: rest.hasEOL
  };
}

/** A viewport stub implementing the real bottom-left to top-left y-flip at
 *  scale 2 on a 792pt-tall page, mirroring pdf.js PageViewport semantics. */
const PAGE_HEIGHT = 792;
const SCALE = 2;
const viewport: ViewportLike = {
  convertToViewportRectangle(rect: number[]): number[] {
    const [x1, y1, x2, y2] = rect;
    return [x1 * SCALE, (PAGE_HEIGHT - y1) * SCALE, x2 * SCALE, (PAGE_HEIGHT - y2) * SCALE];
  }
};

describe("normalizeQuote", () => {
  it("collapses whitespace and folds curly quotes and dashes", () => {
    expect(normalizeQuote("The  “Term”\n shall — apply", "spaces")).toBe(
      'the "term" shall - apply'
    );
  });

  it("squash mode keeps alphanumerics only", () => {
    expect(normalizeQuote("agree-\nment, in  FULL.", "squash")).toBe("agreementinfull");
  });

  it("returns empty for unmatchable input", () => {
    expect(normalizeQuote("  \n\t ", "spaces")).toBe("");
    expect(normalizeQuote("—–,.;", "squash")).toBe("");
  });
});

describe("matchQuoteInItems", () => {
  it("matches a quote inside a single item", () => {
    const items = [item("The party shall pay the fee within thirty days.")];
    const match = matchQuoteInItems("shall pay the fee", items);
    expect(match).not.toBeNull();
    expect(match?.mode).toBe("spaces");
    expect(match?.spans).toEqual([{ itemIndex: 0, startChar: 10, endChar: 27 }]);
  });

  it("matches across items when the line break has no trailing space", () => {
    const items = [item("the cap is ninety-nine percent"), item("of the recovered amount")];
    const match = matchQuoteInItems("ninety-nine percent of the recovered amount", items);
    expect(match).not.toBeNull();
    expect(match?.spans.map((s) => s.itemIndex)).toEqual([0, 1]);
  });

  it("tolerates curly quotes and irregular whitespace in the quote", () => {
    const items = [item('the "Effective Date" of this Agreement')];
    const match = matchQuoteInItems("the “Effective\n Date”  of this Agreement", items);
    expect(match).not.toBeNull();
    expect(match?.mode).toBe("spaces");
  });

  it("falls back to squash for hyphenation across a line break", () => {
    const items = [item("the parties reached an agree-"), item("ment on the final terms")];
    const match = matchQuoteInItems("an agreement on the final terms", items);
    expect(match).not.toBeNull();
    expect(match?.mode).toBe("squash");
    expect(match?.spans.map((s) => s.itemIndex)).toEqual([0, 1]);
  });

  it("falls back to squash for a word split across items with no space", () => {
    const items = [item("indem"), item("nification obligations survive")];
    const match = matchQuoteInItems("indemnification obligations", items);
    expect(match).not.toBeNull();
    expect(match?.mode).toBe("squash");
  });

  it("refuses a short squash needle rather than false-anchoring", () => {
    const items = [item("section 1.2 applies")];
    // "1.2" squashes to "12" (2 chars), below the squash floor; spaces mode
    // fails because the source has "1.2" with no spaces around the dot run
    // requested here.
    expect(matchQuoteInItems("§ 1 2", items)).toBeNull();
  });

  it("returns null when the passage is not present", () => {
    const items = [item("entirely unrelated language")];
    expect(matchQuoteInItems("the cited passage", items)).toBeNull();
  });

  it("returns null for an empty or whitespace-only quote", () => {
    const items = [item("some content")];
    expect(matchQuoteInItems("", items)).toBeNull();
    expect(matchQuoteInItems("   \n ", items)).toBeNull();
  });
});

describe("spansToViewportRects", () => {
  it("projects a span with the y-flip and proportional character slicing", () => {
    const items = [item("0123456789", { x: 100, y: 700, width: 100, height: 10 })];
    const rects = spansToViewportRects([{ itemIndex: 0, startChar: 2, endChar: 5 }], items, viewport);
    expect(rects).toHaveLength(1);
    const rect = rects[0];
    // startChar 2 of 10 chars over width 100 => x = 100 + 20 = 120, scaled x2.
    expect(rect.left).toBeCloseTo(240);
    expect(rect.width).toBeCloseTo(60);
    // top of the glyph box: y + height = 710 in PDF space => (792-710)*2 = 164.
    expect(rect.top).toBeCloseTo(164);
    expect(rect.height).toBeCloseTo(20);
  });

  it("merges same-line neighbours and keeps separate lines apart", () => {
    const items = [
      item("first line run", { x: 50, y: 700 }),
      item("continues here", { x: 140, y: 700 }),
      item("second line", { x: 50, y: 680 })
    ];
    const rects = spansToViewportRects(
      [
        { itemIndex: 0, startChar: 0, endChar: 14 },
        { itemIndex: 1, startChar: 0, endChar: 14 },
        { itemIndex: 2, startChar: 0, endChar: 11 }
      ],
      items,
      viewport
    );
    expect(rects).toHaveLength(2);
    expect(rects[0].top).toBeLessThan(rects[1].top);
  });

  it("skips zero-width items without throwing", () => {
    const items = [item("", { width: 0 })];
    expect(spansToViewportRects([{ itemIndex: 0, startChar: 0, endChar: 1 }], items, viewport)).toEqual(
      []
    );
  });
});

describe("mergeLineRects", () => {
  it("unions overlapping rects on one line", () => {
    const merged = mergeLineRects([
      { left: 10, top: 100, width: 50, height: 14 },
      { left: 60, top: 101, width: 40, height: 13 }
    ]);
    expect(merged).toHaveLength(1);
    expect(merged[0].left).toBe(10);
    expect(merged[0].width).toBe(90);
  });
});

describe("findAnchorPage", () => {
  const pages: Record<number, PdfTextItemLike[]> = {
    1: [item("first page text")],
    2: [item("second page where the cited passage lives")],
    3: [item("third page text")]
  };
  const getItems = async (page: number) => pages[page] ?? [];

  it("finds the quote on the preferred page first", async () => {
    const found = await findAnchorPage(getItems, 3, "the cited passage", 2);
    expect(found?.page).toBe(2);
  });

  it("spirals outward when the preferred page misses", async () => {
    const found = await findAnchorPage(getItems, 3, "the cited passage", 3);
    expect(found?.page).toBe(2);
  });

  it("searches the whole document without a preferred page", async () => {
    const found = await findAnchorPage(getItems, 3, "the cited passage", null);
    expect(found?.page).toBe(2);
  });

  it("returns null when the quote is nowhere in the document", async () => {
    const found = await findAnchorPage(getItems, 3, "language that is absent", 1);
    expect(found).toBeNull();
  });
});
