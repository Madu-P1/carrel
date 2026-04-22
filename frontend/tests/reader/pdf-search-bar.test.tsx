import { act, fireEvent, render, screen } from "@testing-library/preact";
import { expect, test, vi } from "vitest";

import { PdfSearchBar } from "../../src/features/reader/components/PdfSearchBar";
import { readerState } from "../../src/features/reader/state";

function chunk(id: string, content: string, page = 1) {
  return {
    id,
    content,
    section: null,
    page_num: page,
    doc_id: "doc-1",
  } as unknown as NonNullable<
    import("../../src/services/api/endpoints").DocumentDetail["chunks"]
  >[number];
}

test("PdfSearchBar returns null when closed", () => {
  const { container } = render(
    <PdfSearchBar chunks={[]} onClose={() => {}} open={false} />
  );
  expect(container.querySelector("input")).toBeNull();
});

test("PdfSearchBar typing a substring updates the match counter", async () => {
  const chunks = [
    chunk("c-1", "Meiosis produces four haploid cells.", 12),
    chunk("c-2", "Mitosis is cell division into two diploid cells.", 14),
    chunk("c-3", "Photosynthesis converts light into sugar.", 30),
  ];
  render(<PdfSearchBar chunks={chunks} onClose={() => {}} open />);

  const input = screen.getByLabelText(/Find in document/i) as HTMLInputElement;
  fireEvent.input(input, { target: { value: "cell" } });

  // Two chunks contain "cell" — counter shows "1 of 2".
  expect(screen.getByText(/1 of 2/)).toBeDefined();
  // Highlighted chunk is the first match (order of inputs).
  expect(readerState.highlightedChunkId.value).toBe("c-1");
});

test("PdfSearchBar no-match state announces and doesn't highlight", () => {
  readerState.highlightedChunkId.value = null;
  const chunks = [chunk("c-1", "Nothing relevant here.", 1)];
  render(<PdfSearchBar chunks={chunks} onClose={() => {}} open />);
  fireEvent.input(screen.getByLabelText(/Find in document/i), {
    target: { value: "quantum" },
  });
  expect(screen.getByText("No matches")).toBeDefined();
  expect(readerState.highlightedChunkId.value).toBe(null);
});

test("PdfSearchBar Enter advances to next match; Shift+Enter goes back", () => {
  const chunks = [
    chunk("c-1", "apple", 1),
    chunk("c-2", "apple tree", 2),
    chunk("c-3", "pineapple", 3),
  ];
  render(<PdfSearchBar chunks={chunks} onClose={() => {}} open />);
  const input = screen.getByLabelText(/Find in document/i) as HTMLInputElement;
  fireEvent.input(input, { target: { value: "apple" } });
  expect(screen.getByText(/1 of 3/)).toBeDefined();
  expect(readerState.highlightedChunkId.value).toBe("c-1");

  fireEvent.keyDown(input, { key: "Enter" });
  expect(screen.getByText(/2 of 3/)).toBeDefined();
  expect(readerState.highlightedChunkId.value).toBe("c-2");

  fireEvent.keyDown(input, { key: "Enter", shiftKey: true });
  expect(screen.getByText(/1 of 3/)).toBeDefined();
  expect(readerState.highlightedChunkId.value).toBe("c-1");
});

test("PdfSearchBar Escape calls onClose", () => {
  const onClose = vi.fn();
  render(<PdfSearchBar chunks={[]} onClose={onClose} open />);
  fireEvent.keyDown(screen.getByLabelText(/Find in document/i), {
    key: "Escape",
  });
  expect(onClose).toHaveBeenCalledTimes(1);
});

test("PdfSearchBar prev/next buttons wrap around at the ends", () => {
  const chunks = [chunk("c-1", "alpha"), chunk("c-2", "alpha beta")];
  render(<PdfSearchBar chunks={chunks} onClose={() => {}} open />);
  fireEvent.input(screen.getByLabelText(/Find in document/i), {
    target: { value: "alpha" },
  });
  act(() => {});
  // At match 1 of 2, clicking Previous wraps to 2 of 2.
  fireEvent.click(screen.getByLabelText(/Previous match/i));
  expect(screen.getByText(/2 of 2/)).toBeDefined();
  // Next from 2 of 2 wraps back to 1 of 2.
  fireEvent.click(screen.getByLabelText(/Next match/i));
  expect(screen.getByText(/1 of 2/)).toBeDefined();
});
