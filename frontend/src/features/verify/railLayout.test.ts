import { describe, expect, it } from "vitest";

import { layoutRail, type RailAnchor } from "./railLayout";

function top(placements: { key: number; top: number }[], key: number): number {
  return placements.find((p) => p.key === key)!.top;
}

describe("layoutRail — collision-free vertical stacking", () => {
  it("non-overlapping notes keep their exact eye-line", () => {
    const anchors: RailAnchor[] = [
      { key: 0, desiredTop: 0, height: 40 },
      { key: 1, desiredTop: 200, height: 40 }
    ];
    const out = layoutRail(anchors, 16);
    expect(top(out, 0)).toBe(0);
    expect(top(out, 1)).toBe(200);
    expect(out.every((p) => p.displacement === 0)).toBe(true);
  });

  it("overlapping notes push DOWN with the min gap, never up", () => {
    const anchors: RailAnchor[] = [
      { key: 0, desiredTop: 0, height: 50 },
      { key: 1, desiredTop: 20, height: 50 } // wants 20 but 0+50+16=66
    ];
    const out = layoutRail(anchors, 16);
    expect(top(out, 0)).toBe(0);
    expect(top(out, 1)).toBe(66);
    expect(out.find((p) => p.key === 1)!.displacement).toBe(46);
  });

  it("never produces an overlap across a dense cluster", () => {
    const anchors: RailAnchor[] = [
      { key: 0, desiredTop: 0, height: 60 },
      { key: 1, desiredTop: 10, height: 60 },
      { key: 2, desiredTop: 20, height: 60 }
    ];
    const out = layoutRail(anchors, 16).sort((a, b) => a.top - b.top);
    for (let i = 1; i < out.length; i += 1) {
      const prev = anchors.find((a) => a.key === out[i - 1].key)!;
      const gapOk = out[i].top >= out[i - 1].top + prev.height + 16;
      expect(gapOk).toBe(true);
    }
  });

  it("a note can only move down from its eye-line (displacement >= 0)", () => {
    const anchors: RailAnchor[] = [
      { key: 0, desiredTop: 100, height: 80 },
      { key: 1, desiredTop: 120, height: 30 }
    ];
    const out = layoutRail(anchors, 16);
    expect(out.every((p) => p.displacement >= 0)).toBe(true);
  });

  it("is deterministic + order-independent in input order", () => {
    const a: RailAnchor[] = [
      { key: 0, desiredTop: 0, height: 50 },
      { key: 1, desiredTop: 20, height: 50 }
    ];
    const reversed: RailAnchor[] = [a[1], a[0]];
    const out1 = layoutRail(a, 16);
    const out2 = layoutRail(reversed, 16);
    expect(top(out1, 0)).toBe(top(out2, 0));
    expect(top(out1, 1)).toBe(top(out2, 1));
  });

  it("returns placements in INPUT order (stable rendering)", () => {
    const anchors: RailAnchor[] = [
      { key: 5, desiredTop: 300, height: 40 },
      { key: 2, desiredTop: 0, height: 40 }
    ];
    const out = layoutRail(anchors, 16);
    expect(out.map((p) => p.key)).toEqual([5, 2]);
  });

  it("empty input -> empty output", () => {
    expect(layoutRail([], 16)).toEqual([]);
  });

  it("ties on desiredTop break by key, deterministically", () => {
    const anchors: RailAnchor[] = [
      { key: 1, desiredTop: 50, height: 30 },
      { key: 0, desiredTop: 50, height: 30 }
    ];
    const out = layoutRail(anchors, 16);
    // key 0 sorts first -> sits at 50; key 1 pushed to 50+30+16 = 96.
    expect(top(out, 0)).toBe(50);
    expect(top(out, 1)).toBe(96);
  });
});
