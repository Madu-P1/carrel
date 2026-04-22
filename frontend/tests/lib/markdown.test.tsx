import { describe, expect, test } from "vitest";
import { render } from "@testing-library/preact";

import { renderMarkdown } from "../../src/lib/markdown";

// Test helper: render the markdown VNodes to a mount point and return the HTML
// string. Using Testing Library's `render` means Preact resolves the JSX the
// same way it would inside a real feature view.
function html(source: string): string {
  const { container } = render(<div>{renderMarkdown(source)}</div>);
  return container.firstElementChild?.innerHTML ?? "";
}

describe("renderMarkdown — inline", () => {
  test("bold: **foo** renders as <strong>", () => {
    expect(html("**foo**")).toBe("<p><strong>foo</strong></p>");
  });

  test("italic: *foo* renders as <em>", () => {
    expect(html("*foo*")).toBe("<p><em>foo</em></p>");
  });

  test("code: `foo` renders as <code>", () => {
    expect(html("`foo`")).toBe("<p><code>foo</code></p>");
  });

  test("mixed inline: **bold** and *italic* and `code` in one paragraph", () => {
    expect(html("**a** and *b* and `c`")).toBe(
      "<p><strong>a</strong> and <em>b</em> and <code>c</code></p>"
    );
  });

  test("unbalanced emphasis renders literally", () => {
    expect(html("**unclosed")).toBe("<p>**unclosed</p>");
    expect(html("*alone")).toBe("<p>*alone</p>");
  });

  test("nested emphasis is not supported; parser picks valid italic matches left-to-right", () => {
    // We don't support nesting. The parser scans left-to-right and takes
    // whichever delimiter matches first. For `**a*b*c**` the first match
    // that completes is the italic `*a*`, not the bold `**...**`.
    // That's fine — nested emphasis isn't something tutor output produces.
    expect(html("**a*b*c**")).toBe("<p>*<em>a</em>b<em>c</em>*</p>");
  });
});

describe("renderMarkdown — blocks", () => {
  test("paragraph break on blank line", () => {
    expect(html("one\n\ntwo")).toBe("<p>one</p><p>two</p>");
  });

  test("hard break on single newline inside paragraph", () => {
    expect(html("one\ntwo")).toBe("<p>one<br>two</p>");
  });

  test("bullet list with - prefix", () => {
    expect(html("- a\n- b")).toBe("<ul><li>a</li><li>b</li></ul>");
  });

  test("bullet list with * prefix", () => {
    expect(html("* a\n* b")).toBe("<ul><li>a</li><li>b</li></ul>");
  });

  test("ordered list with N. prefix", () => {
    expect(html("1. a\n2. b")).toBe("<ol><li>a</li><li>b</li></ol>");
  });

  test("list items support inline formatting", () => {
    expect(html("- **bold** item")).toBe(
      "<ul><li><strong>bold</strong> item</li></ul>"
    );
  });

  test("paragraph then list then paragraph", () => {
    expect(html("intro\n\n- a\n- b\n\noutro")).toBe(
      "<p>intro</p><ul><li>a</li><li>b</li></ul><p>outro</p>"
    );
  });
});

describe("renderMarkdown — XSS (adversarial)", () => {
  // The safety property: the DOM output must never contain a raw tag from
  // user input. A dangerous-looking SUBSTRING in text content (e.g., the
  // literal characters "script" or "onload=" shown as visible text) is fine,
  // because the browser renders them as inert text, not markup.
  //
  // These tests assert on the final DOM structure: they count real elements
  // and inspect their tag names, rather than pattern-matching the innerHTML
  // string (which contains double-escaped ampersands due to how Preact
  // serializes text).
  const ALLOWED_TAGS = new Set(["P", "STRONG", "EM", "CODE", "BR", "UL", "OL", "LI"]);

  function domOf(source: string): HTMLDivElement {
    const { container } = render(<div>{renderMarkdown(source)}</div>);
    return container.firstElementChild as HTMLDivElement;
  }

  function assertOnlyAllowedTags(root: Element) {
    const offenders: string[] = [];
    const walk = (node: Element) => {
      if (!ALLOWED_TAGS.has(node.tagName)) offenders.push(node.tagName);
      for (const child of Array.from(node.children)) walk(child);
    };
    for (const child of Array.from(root.children)) walk(child);
    expect(offenders).toEqual([]);
  }

  test("raw <script> tag never becomes a script element", () => {
    const root = domOf("<script>alert(1)</script>");
    assertOnlyAllowedTags(root);
    expect(root.querySelectorAll("script")).toHaveLength(0);
    // User sees the source as literal visible text (Preact escapes on render).
    expect(root.textContent).toBe("<script>alert(1)</script>");
  });

  test("img onerror never becomes an image", () => {
    const root = domOf("<img src=x onerror=alert(1)>");
    assertOnlyAllowedTags(root);
    expect(root.querySelectorAll("img")).toHaveLength(0);
  });

  test("script tag inside bold: <strong> wraps literal text, no script element", () => {
    const root = domOf("**<script>alert(1)</script>**");
    assertOnlyAllowedTags(root);
    expect(root.querySelectorAll("strong")).toHaveLength(1);
    expect(root.querySelectorAll("script")).toHaveLength(0);
    expect(root.querySelector("strong")?.textContent).toBe("<script>alert(1)</script>");
  });

  test("markdown link syntax renders as literal punctuation (links unsupported)", () => {
    const root = domOf("[click](javascript:alert(1))");
    assertOnlyAllowedTags(root);
    expect(root.querySelectorAll("a")).toHaveLength(0);
    expect(root.textContent).toBe("[click](javascript:alert(1))");
  });

  test("entity-looking input is not decoded, user sees what they typed", () => {
    const root = domOf("&lt;script&gt;");
    assertOnlyAllowedTags(root);
    // User typed `&lt;script&gt;` — we render it back as those exact visible chars.
    expect(root.textContent).toBe("&lt;script&gt;");
  });

  test("quotes and apostrophes round-trip as text", () => {
    const root = domOf('"hello" and \'world\'');
    expect(root.textContent).toBe('"hello" and \'world\'');
  });

  test("svg onload attempt never becomes an svg element", () => {
    const root = domOf('<svg onload="alert(1)"></svg>');
    assertOnlyAllowedTags(root);
    expect(root.querySelectorAll("svg")).toHaveLength(0);
  });

  test("data URI image payload never becomes img or script", () => {
    const root = domOf('<img src="data:text/html,<script>alert(1)</script>">');
    assertOnlyAllowedTags(root);
    expect(root.querySelectorAll("img")).toHaveLength(0);
    expect(root.querySelectorAll("script")).toHaveLength(0);
  });

  test("iframe attempt never becomes an iframe", () => {
    const root = domOf('<iframe src="evil.html"></iframe>');
    assertOnlyAllowedTags(root);
    expect(root.querySelectorAll("iframe")).toHaveLength(0);
  });

  test("empty input returns empty output", () => {
    expect(html("")).toBe("");
  });
});
