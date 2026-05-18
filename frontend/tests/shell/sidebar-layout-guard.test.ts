import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, test } from "vitest";

/*
 * Regression guard for 65ee7401
 * ("fix(shell): pin TODAY/footer and scroll nav so sidebar never overlaps itself").
 *
 * The bug: at short viewport heights the sidebar's nav content rendered
 * at its natural size and painted on top of the TODAY block ("TODAY"
 * overlapping "Plan #6"). Root cause: every flex child of `.sidebar`
 * carried the default flex-shrink:1 and `.nav` was allowed to overflow
 * visibly, so when nav content exceeded its slot it spilled into the
 * today/footer coordinates instead of scrolling.
 *
 * JSDOM has no layout engine, so this cannot be a rendered-box test.
 * Instead it pins the CSS contract that constitutes the fix: `.nav`
 * fills remaining space and scrolls its own overflow, while `.today`
 * and `.footer` never shrink. Same approach as motion-css-guard.test.ts.
 */

const root = resolve(__dirname, "..", "..", "src");

function read(relPath: string): string {
  return readFileSync(resolve(root, relPath), "utf8");
}

function ruleBlock(css: string, selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = css.match(new RegExp(`^${escaped}\\s*\\{([\\s\\S]*?)\\}`, "m"));
  if (!match) throw new Error(`rule "${selector}" not found in CSS`);
  return match[1];
}

describe("sidebar layout guard (regression: 65ee7401)", () => {
  const sidebarCss = read("app/shell/WorkspaceSidebar.module.css");

  test(".nav scrolls its own overflow instead of spilling into siblings", () => {
    const nav = ruleBlock(sidebarCss, ".nav");
    // Fill remaining space, allow shrink past content size, and clip +
    // scroll the overflow. Drop any one of these and nav content paints
    // over the TODAY block again.
    expect(nav).toContain("flex: 1 1 0;");
    expect(nav).toContain("min-height: 0;");
    expect(nav).toContain("overflow-y: auto;");
  });

  test(".today and .footer never yield vertical space to the nav", () => {
    expect(ruleBlock(sidebarCss, ".today")).toContain("flex-shrink: 0;");
    expect(ruleBlock(sidebarCss, ".footer")).toContain("flex-shrink: 0;");
  });
});
