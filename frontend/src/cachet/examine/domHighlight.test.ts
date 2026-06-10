import { describe, expect, it } from "vitest";

import { clearAnchorMarks, markQuoteInDom } from "./domHighlight";

function container(html: string): HTMLElement {
  const el = document.createElement("div");
  el.innerHTML = html;
  document.body.appendChild(el);
  return el;
}

describe("markQuoteInDom", () => {
  it("wraps a quote inside a single text node", () => {
    const root = container("<p>The party shall pay the fee within thirty days.</p>");
    const marks = markQuoteInDom(root, "shall pay the fee");
    expect(marks).not.toBeNull();
    expect(marks).toHaveLength(1);
    expect(marks?.[0].textContent).toBe("shall pay the fee");
    expect(root.textContent).toBe("The party shall pay the fee within thirty days.");
  });

  it("wraps a quote spanning multiple elements with one mark per node", () => {
    const root = container("<p>The cap is <b>ninety-nine percent</b> of the recovery.</p>");
    const marks = markQuoteInDom(root, "cap is ninety-nine percent of");
    expect(marks).not.toBeNull();
    expect(marks?.length).toBe(3);
    expect(marks?.map((m) => m.textContent).join("")).toBe("cap is ninety-nine percent of");
  });

  it("matches across a mid-word inline split without a synthetic space", () => {
    const root = container("<p><b>Veri</b>fication is deterministic.</p>");
    const marks = markQuoteInDom(root, "Verification is deterministic");
    expect(marks).not.toBeNull();
    expect(marks?.map((m) => m.textContent).join("")).toBe("Verification is deterministic");
  });

  it("tolerates curly quotes and collapsed whitespace", () => {
    const root = container("<p>the “Effective Date” of this Agreement</p>");
    const marks = markQuoteInDom(root, 'the "Effective\n Date" of  this Agreement');
    expect(marks).not.toBeNull();
  });

  it("returns null when the passage is absent, leaving the DOM untouched", () => {
    const root = container("<p>Entirely unrelated language.</p>");
    const before = root.innerHTML;
    expect(markQuoteInDom(root, "the cited passage")).toBeNull();
    expect(root.innerHTML).toBe(before);
  });

  it("returns null for empty or whitespace-only quotes", () => {
    const root = container("<p>Some content.</p>");
    expect(markQuoteInDom(root, "")).toBeNull();
    expect(markQuoteInDom(root, "  \n ")).toBeNull();
  });

  it("re-marking replaces earlier marks instead of nesting them", () => {
    const root = container("<p>alpha beta gamma delta</p>");
    markQuoteInDom(root, "beta gamma");
    const marks = markQuoteInDom(root, "gamma delta");
    expect(marks).toHaveLength(1);
    expect(root.querySelectorAll("mark").length).toBe(1);
    expect(root.textContent).toBe("alpha beta gamma delta");
  });
});

describe("clearAnchorMarks", () => {
  it("restores the original text and merges nodes back", () => {
    const root = container("<p>alpha beta gamma</p>");
    markQuoteInDom(root, "beta");
    clearAnchorMarks(root);
    expect(root.querySelectorAll("mark").length).toBe(0);
    expect(root.textContent).toBe("alpha beta gamma");
    const p = root.querySelector("p");
    expect(p?.childNodes.length).toBe(1);
  });

  it("is safe on a container with no marks", () => {
    const root = container("<p>nothing here</p>");
    expect(() => clearAnchorMarks(root)).not.toThrow();
  });
});
