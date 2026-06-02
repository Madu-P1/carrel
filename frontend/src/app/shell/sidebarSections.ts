/**
 * Pure sidebar nav grouping — no render deps, so the no-orphan invariant is
 * unit-tested arithmetic (sidebarSections.test.ts), mirroring the verify
 * feature's pure documentSegments/railLayout modules.
 *
 * The rail renders nav items grouped into ordered sections. Every navLinks
 * key MUST appear in exactly one group; a key in no group never renders in
 * the rail and its route is reachable only by typed URL. That is exactly how
 * the Verify Draft and Shelf buttons went missing (added to navLinks + the
 * key union, but to no section), so the invariant is now locked by a test.
 */

export interface SidebarNavItem {
  label: string;
  commandHint: string;
  icon:
    | "library"
    | "doc"
    | "ask"
    | "study"
    | "dashboard"
    | "sparkle"
    | "command"
    | "search"
    | "graph"
    | "reader"
    | "notes"
    | "flashcards"
    | "session"
    | "plan"
    | "verify"
    | "shelf";
  path: string;
  key:
    | "dashboard"
    | "session"
    | "library"
    | "reader"
    | "ask"
    | "verify"
    | "study"
    | "search"
    | "concepts"
    | "plan"
    | "notes"
    | "shelf";
}

/**
 * Ordered sidebar section groups. Keys are typed to the nav key union, so a
 * typo or a removed key fails typecheck; a key present in navLinks but in no
 * group is caught at runtime by sidebarSections.test.ts.
 */
export const SIDEBAR_SECTION_GROUPS: { label: string; keys: SidebarNavItem["key"][] }[] = [
  { label: "Overview", keys: ["dashboard"] },
  { label: "Study", keys: ["session", "study", "library", "reader", "ask", "notes"] },
  // Cachet V2 surfaces: verify a draft, then it lands on the Shelf. Grouping
  // and label are open to PR6b refinement.
  { label: "Verify", keys: ["verify", "shelf"] },
  { label: "Tools", keys: ["search", "concepts", "plan"] }
];

/**
 * Group nav items into the ordered sidebar sections, dropping any empty
 * section. Items keep their incoming (navLinks) order within a group.
 */
export function buildSidebarSections(
  items: SidebarNavItem[]
): { label: string; items: SidebarNavItem[] }[] {
  return SIDEBAR_SECTION_GROUPS.map((group) => ({
    label: group.label,
    items: items.filter((item) => group.keys.includes(item.key))
  })).filter((section) => section.items.length > 0);
}
