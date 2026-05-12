import { cleanup, fireEvent, render, screen } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

const navigateToMock = vi.fn();

vi.mock("@/app/shell/useAppShell", () => ({
  navigateTo: (path: string) => navigateToMock(path),
}));

import { SourceCitation } from "@/features/study/components/SourceCitation";

/*
 * PR 4 of flashcards-focus: source citation on the back face of every
 * SRS flashcard that has a bound anchor. The component is the surface
 * where Carrel's verbatim-source-grounding wedge meets the daily SRS
 * loop — it MUST deep-link to the originating chunk so the student
 * can re-read the passage in context.
 *
 * These tests pin the visible contract: the citation header reads
 * "From {document}, page N", the excerpt renders the verbatim quote,
 * a missing page hides the page label, and click routes through
 * navigateTo with the canonical /reader/{doc}?chunk={chunk} path.
 */
describe("SourceCitation", () => {
  beforeEach(() => {
    navigateToMock.mockClear();
  });

  afterEach(() => {
    cleanup();
    document.body.innerHTML = "";
  });

  test("renders the document name and page in the header", () => {
    render(
      <SourceCitation
        documentId="doc-1"
        documentName="cardio-handbook.pdf"
        chunkId="chunk-42"
        pageNum={7}
        quoteText="Stroke volume rises as preload increases up to a physiologic limit."
      />,
    );
    expect(screen.getByText("From cardio-handbook.pdf, page 7")).toBeTruthy();
  });

  test("renders the verbatim quote as an excerpt", () => {
    render(
      <SourceCitation
        documentId="doc-1"
        documentName="cardio-handbook.pdf"
        chunkId="chunk-42"
        pageNum={7}
        quoteText="Stroke volume rises as preload increases up to a physiologic limit."
      />,
    );
    expect(
      screen.getByText(/Stroke volume rises as preload/),
    ).toBeTruthy();
  });

  test("omits the page label when pageNum is null", () => {
    render(
      <SourceCitation
        documentId="doc-1"
        documentName="lecture-notes.txt"
        chunkId="chunk-42"
        pageNum={null}
        quoteText="Verbatim quote."
      />,
    );
    expect(screen.getByText("From lecture-notes.txt")).toBeTruthy();
    expect(screen.queryByText(/page/i)).toBeNull();
  });

  test("truncates a long quote to ~40 words with an ellipsis", () => {
    const longQuote = Array.from({ length: 80 }, (_, i) => `word${i + 1}`).join(" ");
    render(
      <SourceCitation
        documentId="doc-1"
        documentName="doc.pdf"
        chunkId="chunk-42"
        pageNum={1}
        quoteText={longQuote}
      />,
    );
    // The first 40 words are present, the 41st should be replaced by an
    // ellipsis. Check both ends of the boundary.
    expect(screen.getByText(/word1 word2/)).toBeTruthy();
    expect(screen.getByText(/word40…/)).toBeTruthy();
  });

  test("clicking the row deep-links to /reader/{doc}?chunk={chunk}", () => {
    render(
      <SourceCitation
        documentId="doc-abc"
        documentName="doc.pdf"
        chunkId="chunk-xyz"
        pageNum={3}
        quoteText="Verbatim quote."
      />,
    );
    const button = screen.getByRole("button");
    fireEvent.click(button);
    expect(navigateToMock).toHaveBeenCalledTimes(1);
    expect(navigateToMock).toHaveBeenCalledWith("/reader/doc-abc?chunk=chunk-xyz");
  });

  test("falls back to a generic document label when name is empty", () => {
    render(
      <SourceCitation
        documentId="doc-1"
        documentName=""
        chunkId="chunk-42"
        pageNum={2}
        quoteText="Quote."
      />,
    );
    expect(screen.getByText("From this document, page 2")).toBeTruthy();
  });
});
