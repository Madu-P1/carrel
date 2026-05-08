import { fireEvent, render, screen } from "@testing-library/preact";
import { expect, test, vi } from "vitest";

import { AskCard } from "../../src/features/ask/components/AskCard";
import { AskCardList } from "../../src/features/ask/components/AskCardList";
import type { AskCard as AskCardData, AskCardsResponse } from "../../src/services/api/endpoints";

const _card = (overrides: Partial<AskCardData> = {}): AskCardData => ({
  node_id: 1,
  doc_id: "doc-bio",
  filename: "photosynthesis.md",
  subject_name: "Biology",
  node_type: "body",
  heading_path: "Chapter 3 > Photosynthesis",
  page: 472,
  char_start: 1024,
  char_end: 1180,
  verbatim_text:
    "Photosystem II splits water molecules, releasing oxygen and protons into the thylakoid lumen.",
  snippet: "Photosystem II splits water molecules…",
  score: 0.85,
  rerank_score: 0.92,
  sources: ["fts", "vec"],
  ...overrides,
});

const _response = (overrides: Partial<AskCardsResponse> = {}): AskCardsResponse => ({
  query: "photosynthesis",
  cards: [_card()],
  library: { total_nodes: 4 },
  rerank_used: true,
  ...overrides,
});

test("AskCard renders heading_path eyebrow, verbatim quote, and source line", () => {
  render(<AskCard card={_card()} index={0} />);
  expect(screen.getByText(/Chapter 3 > Photosynthesis/)).toBeDefined();
  expect(
    screen.getByText(/Photosystem II splits water molecules/),
  ).toBeDefined();
  expect(screen.getByText(/photosynthesis\.md/)).toBeDefined();
  expect(screen.getByText(/p\. 472/)).toBeDefined();
});

test("AskCard surfaces the rerank confidence badge when rerank_score is set", () => {
  render(<AskCard card={_card({ rerank_score: 0.92 })} index={0} />);
  expect(screen.getByText(/92% match/)).toBeDefined();
});

test("AskCard suppresses the badge when rerank wasn't applied", () => {
  render(<AskCard card={_card({ rerank_score: null })} index={0} />);
  expect(screen.queryByText(/% match/)).toBeNull();
});

test("AskCard Open button fires onOpen with the full card payload", () => {
  const onOpen = vi.fn();
  render(<AskCard card={_card()} index={0} onOpen={onOpen} />);
  fireEvent.click(screen.getByRole("button", { name: /Open .* in reader/i }));
  expect(onOpen).toHaveBeenCalledTimes(1);
  expect(onOpen.mock.calls[0]?.[0]?.node_id).toBe(1);
  expect(onOpen.mock.calls[0]?.[0]?.char_start).toBe(1024);
});

test("AskCard sources hint renders 'matched on keyword + meaning' for both sources", () => {
  render(<AskCard card={_card({ sources: ["fts", "vec"] })} index={0} />);
  expect(screen.getByText(/matched on keyword \+ meaning/)).toBeDefined();
});

test("AskCardList shows the 'library not yet indexed' empty state when total_nodes is zero", () => {
  render(
    <AskCardList
      response={_response({ cards: [], library: { total_nodes: 0 } })}
      pending={false}
      error={null}
    />,
  );
  expect(screen.getByText(/Library not yet indexed/)).toBeDefined();
  expect(screen.getByText(/INGEST_USE_DOCLING/)).toBeDefined();
});

test("AskCardList shows 'no matching passages' when library has nodes but no hits", () => {
  render(
    <AskCardList
      response={_response({ cards: [], library: { total_nodes: 1200 } })}
      pending={false}
      error={null}
    />,
  );
  expect(screen.getByText(/No matching passages/)).toBeDefined();
  expect(screen.getByText(/1,200/)).toBeDefined();
});

test("AskCardList shows the eyebrow + 'reranked' badge when rerank was used", () => {
  render(<AskCardList response={_response()} pending={false} error={null} />);
  expect(screen.getByText(/Most likely answers in your library/i)).toBeDefined();
  expect(screen.getByText(/reranked/i)).toBeDefined();
});

test("AskCardList renders an error state with a retry button", () => {
  const onRetry = vi.fn();
  render(
    <AskCardList
      response={null}
      pending={false}
      error={new Error("network exploded")}
      onRetry={onRetry}
    />,
  );
  expect(screen.getByText(/Could not retrieve cards/i)).toBeDefined();
  expect(screen.getByText(/network exploded/i)).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: /Try again/i }));
  expect(onRetry).toHaveBeenCalledTimes(1);
});

test("AskCardList renders a loading row while pending and no response yet", () => {
  render(<AskCardList response={null} pending={true} error={null} />);
  expect(screen.getByText(/Searching your library/i)).toBeDefined();
});
