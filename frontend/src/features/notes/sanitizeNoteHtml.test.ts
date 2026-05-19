import { describe, expect, it } from "vitest";

import { sanitizeNoteHtml } from "./sanitizeNoteHtml";

describe("sanitizeNoteHtml", () => {
  it("keeps the editor subset and removes executable markup", () => {
    const clean = sanitizeNoteHtml(`
      <p onclick="steal()">Keep <strong>this</strong></p>
      <img src=x onerror="fetch('//evil')">
      <svg onload="alert(1)"><text>bad</text></svg>
      <script>alert(window.__CARREL_LOCAL_API_TOKEN)</script>
      <a href="javascript:alert(1)">link text</a>
      <b>bold</b><i>italic</i>
    `);

    expect(clean).toContain("<strong>this</strong>");
    expect(clean).toContain("link text");
    expect(clean).toContain("<strong>bold</strong>");
    expect(clean).toContain("<em>italic</em>");
    expect(clean).not.toContain("onclick");
    expect(clean).not.toContain("onerror");
    expect(clean).not.toContain("<img");
    expect(clean).not.toContain("<svg");
    expect(clean).not.toContain("<script");
    expect(clean).not.toContain("javascript:");
  });

  it("normalizes empty note bodies to the workspace seed marker", () => {
    expect(sanitizeNoteHtml("")).toBe("\n");
    expect(sanitizeNoteHtml("<br>")).toBe("\n");
  });
});
