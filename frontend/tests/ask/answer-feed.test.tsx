import { fireEvent, render, screen, waitFor, within } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { AnswerSummary } from "../../src/features/ask/components/AnswerSummary";
import { ClaimList } from "../../src/features/ask/components/ClaimList";
import { FallbackAnswer } from "../../src/features/ask/components/FallbackAnswer";
import { DEMO_ANSWER, DEMO_FALLBACK } from "../../src/features/ask/fixtures/grounded-answer.fixture";

const writeText = vi.fn<() => Promise<void>>();
const fetchMock = vi.fn() as unknown as ReturnType<typeof vi.fn> & {
  mockResolvedValue: (value: Response) => void;
  mockReset: () => void;
  mock: { calls: Array<[RequestInfo | URL, RequestInit?]> };
};

beforeEach(() => {
  writeText.mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText }
  });
  fetchMock.mockResolvedValue(
    new Response(
      JSON.stringify({
        anchor: {
          id: "anchor-1",
          document_id: "doc-1",
          chunk_id: "demo-1",
          page_num: 1,
          bbox: null,
          text_offset_start: null,
          text_offset_end: null,
          quote_text: "quote",
          user_question: null,
          claim_text: "claim",
          origin: "ai_answer_citation",
          promotion_state: "weak",
          srs_card_id: null,
          thread_id: null,
          confidence: 0.9,
          created_at: "now",
          updated_at: "now"
        }
      }),
      { status: 200, headers: { "content-type": "application/json" } }
    )
  );
  vi.stubGlobal("fetch", fetchMock);
  window.localStorage.clear();
});

afterEach(() => {
  window.localStorage.clear();
  writeText.mockReset();
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

test("AnswerSummary renders metadata and utility actions for the grounded answer card", async () => {
  const onRetry = vi.fn();

  render(
    <AnswerSummary
      cacheHit
      citations={DEMO_ANSWER.citations}
      latencyMs={DEMO_ANSWER.latency_ms ?? 0}
      model={DEMO_ANSWER.model ?? ""}
      onRetry={onRetry}
      summary={DEMO_ANSWER.answer}
    />
  );

  expect(screen.getByText(/Grounded answer/i)).toBeDefined();
  expect(screen.getByText(/cache hit/i)).toBeDefined();
  expect(screen.getByText(/2 sources/i)).toBeDefined();

  fireEvent.click(screen.getByRole("button", { name: /Retry/i }));
  expect(onRetry).toHaveBeenCalledTimes(1);

  fireEvent.click(screen.getByRole("button", { name: /Save as anchor/i }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/api/anchors");
});

test("ClaimList renders tiered support copy, source locations, and card utilities", async () => {
  render(<ClaimList claims={DEMO_ANSWER.claims} onCitationClick={() => {}} />);

  const firstClaim = screen.getByText(/Mitosis creates two genetically identical daughter cells\./i);
  const firstCard = firstClaim.closest("article");
  expect(firstCard).toBeTruthy();
  const card = within(firstCard as HTMLElement);

  expect(card.getByText(/Supporting passage from cell-division\.md on page 1\./i)).toBeDefined();
  expect(card.getByText(/cell-division\.md · p\.1 · chunk demo-1/i)).toBeDefined();

  fireEvent.click(card.getByRole("button", { name: /Copy/i }));
  expect(writeText).toHaveBeenCalledWith("Mitosis creates two genetically identical daughter cells.");

  fireEvent.click(card.getByRole("button", { name: /Save as anchor/i }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  const init = fetchMock.mock.calls[0]?.[1] as RequestInit | undefined;
  expect(String(init?.body)).toContain("demo-1");
});

test("FallbackAnswer keeps the refusal recovery actions in the summary card", () => {
  const onRetry = vi.fn();
  const onBroadenScope = vi.fn();
  const onRephrase = vi.fn();

  render(
    <FallbackAnswer
      claims={DEMO_FALLBACK.claims}
      error="weak_coverage"
      onBroadenScope={onBroadenScope}
      onRephrase={onRephrase}
      onRetry={onRetry}
    />
  );

  expect(screen.getByText(/Grounded refusal/i)).toBeDefined();
  expect(screen.getByText(/I refused this one/i)).toBeDefined();
  expect(screen.getByText(/Nearest passages I did find/i)).toBeDefined();

  fireEvent.click(screen.getByRole("button", { name: /Retry/i }));
  expect(onRetry).toHaveBeenCalledTimes(1);

  fireEvent.click(screen.getByRole("button", { name: /Broaden to Library/i }));
  expect(onBroadenScope).toHaveBeenCalledTimes(1);

  fireEvent.click(screen.getByRole("button", { name: /Rephrase question/i }));
  expect(onRephrase).toHaveBeenCalledTimes(1);
});
