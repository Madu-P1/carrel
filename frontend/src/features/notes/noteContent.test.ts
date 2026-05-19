import { describe, expect, it } from "vitest";

import {
  noteContentToMarkdown,
  notePreviewText,
  serializeNoteMarkdown
} from "./noteContent";

describe("noteContent", () => {
  it("keeps markdown notes as the editor source of truth", () => {
    expect(noteContentToMarkdown("# Topic\n\n- One\n- Two")).toBe(
      "# Topic\n\n- One\n- Two"
    );
    expect(serializeNoteMarkdown("  # Topic  \n\n")).toBe("# Topic");
  });

  it("converts legacy editor HTML to markdown before editing", () => {
    const markdown = noteContentToMarkdown(`
      <h1>Lecture</h1>
      <p>Keep <strong>bold</strong> and <em>italics</em>.</p>
      <ul><li>First</li><li>Second</li></ul>
      <blockquote>Source line</blockquote>
      <pre>const x = 1;</pre>
    `);

    expect(markdown).toContain("# Lecture");
    expect(markdown).toContain("Keep **bold** and *italics*.");
    expect(markdown).toContain("- First\n- Second");
    expect(markdown).toContain("> Source line");
    expect(markdown).toContain("```\nconst x = 1;\n```");
  });

  it("ignores indentation-only text nodes in legacy HTML", () => {
    expect(
      noteContentToMarkdown(`
        <h1>Topic</h1>
        <p>Keep <strong>bold</strong>.</p>
      `)
    ).toBe("# Topic\n\nKeep **bold**.");
  });

  it("drops executable legacy HTML during conversion", () => {
    const markdown = noteContentToMarkdown(`
      <p>safe</p>
      <img src=x onerror="fetch('//evil')">
      <script>alert(window.__CARREL_LOCAL_API_TOKEN)</script>
    `);

    expect(markdown).toBe("safe");
    expect(markdown).not.toContain("script");
    expect(markdown).not.toContain("onerror");
    expect(markdown).not.toContain("__CARREL_LOCAL_API_TOKEN");
  });

  it("turns markdown into plain note previews", () => {
    expect(notePreviewText("## Topic\n\n- [Claim](javascript:evil)")).toBe(
      "Topic Claim"
    );
    expect(notePreviewText("\n", "Empty note.")).toBe("Empty note.");
  });
});
