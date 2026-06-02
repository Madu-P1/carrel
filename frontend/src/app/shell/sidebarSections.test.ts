import { describe, expect, it } from "vitest";

import { navLinks } from "./AppShell";
import { SIDEBAR_SECTION_GROUPS, buildSidebarSections } from "./sidebarSections";

describe("buildSidebarSections", () => {
  it("places every navLink into exactly one rendered section (no orphan keys)", () => {
    const sections = buildSidebarSections(navLinks);
    const placed = sections.flatMap((section) => section.items.map((item) => item.key));
    // Every nav key renders somewhere — an orphan key (in navLinks but in no
    // group) is exactly how Verify Draft and Shelf went missing from the rail.
    expect(new Set(placed)).toEqual(new Set(navLinks.map((item) => item.key)));
    // ...and exactly once (no key duplicated across groups).
    expect(placed.length).toBe(navLinks.length);
    expect(new Set(placed).size).toBe(placed.length);
  });

  it("exposes the Cachet V2 surfaces (Verify Draft + Shelf) in the rail", () => {
    const sections = buildSidebarSections(navLinks);
    const hasVerify = sections.some((section) => section.items.some((i) => i.key === "verify"));
    const hasShelf = sections.some((section) => section.items.some((i) => i.key === "shelf"));
    expect(hasVerify).toBe(true);
    expect(hasShelf).toBe(true);
  });

  it("drops empty sections", () => {
    expect(buildSidebarSections([])).toEqual([]);
  });

  it("has no stale group keys (every grouped key is a real navLink key)", () => {
    const navKeys = new Set(navLinks.map((item) => item.key));
    for (const group of SIDEBAR_SECTION_GROUPS) {
      for (const key of group.keys) {
        expect(navKeys.has(key)).toBe(true);
      }
    }
  });
});
