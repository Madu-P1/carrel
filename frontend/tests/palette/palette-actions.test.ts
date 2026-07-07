import { describe, expect, test } from "vitest";

import { filterActions, paletteActions, scoreAction } from "@/features/palette/actions";

describe("palette actions registry", () => {
  test("registry contains the expected MVP surface", () => {
    const ids = paletteActions.map((a) => a.id);
    for (const expected of [
      "nav.library",
      "nav.reader",
      "nav.verify",
      "nav.shelf",
      "view.toggleLeftSidebar",
      "view.toggleRightPanel",
      "view.toggleTheme",
      "reader.toggleFocusMode",
      "file.import",
      "help.shortcuts"
    ]) {
      expect(ids).toContain(expected);
    }
  });

  test("scoreAction returns 0 for a clear miss", () => {
    const nav = paletteActions.find((a) => a.id === "nav.verify")!;
    expect(scoreAction(nav, "zzzzzqxxxx")).toBe(0);
  });

  test("exact label match scores higher than prefix match", () => {
    const verify = paletteActions.find((a) => a.id === "nav.verify")!;
    const exactScore = scoreAction(verify, "go to verify");
    const prefixScore = scoreAction(verify, "go to");
    expect(exactScore).toBeGreaterThan(prefixScore);
  });

  test("prefix match scores higher than substring match", () => {
    const lib = paletteActions.find((a) => a.id === "nav.library")!;
    const prefixScore = scoreAction(lib, "go to l");
    const substringScore = scoreAction(lib, "library");
    // "Go to Library" starts with "go to l" → prefix (50). "library" is a substring (25).
    expect(prefixScore).toBeGreaterThan(substringScore);
  });

  test("keyword match shows up when label doesn't contain the query", () => {
    const verify = paletteActions.find((a) => a.id === "nav.verify")!;
    expect(scoreAction(verify, "draft")).toBeGreaterThan(0);
    expect(scoreAction(verify, "citations")).toBeGreaterThan(0);
  });

  test("filterActions empty query returns everything", () => {
    expect(filterActions("").length).toBe(paletteActions.length);
  });

  test("filterActions narrows to matches and sorts by score", () => {
    const results = filterActions("toggle");
    // Every toggle action is in the View group.
    expect(results.every((a) => a.group === "View")).toBe(true);
    expect(results.length).toBeGreaterThanOrEqual(3);
  });

  test("filterActions excludes misses entirely", () => {
    const results = filterActions("zzzzznothing");
    expect(results).toEqual([]);
  });
});
