import { describe, expect, it } from "vitest";

import {
  markdownToStructuredDoc,
  structuredDocToMarkdown
} from "./structuredNoteDocument";

describe("structuredNoteDocument", () => {
  it("round-trips the editor markdown subset", () => {
    const markdown = [
      "# Topic",
      "",
      "Keep **bold**, *italic*, and ~~struck~~ text.",
      "",
      "- First",
      "- Second",
      "",
      "1. Alpha",
      "2. Beta",
      "",
      "> Source line",
      "",
      "```",
      "const x = 1;",
      "```"
    ].join("\n");

    expect(structuredDocToMarkdown(markdownToStructuredDoc(markdown))).toBe(
      markdown
    );
  });

  it("preserves safe links and drops executable hrefs", () => {
    const markdown =
      "[good](https://example.com) [bad](javascript:alert(1))";

    expect(structuredDocToMarkdown(markdownToStructuredDoc(markdown))).toBe(
      "[good](https://example.com) bad"
    );
  });
});
