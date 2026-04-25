import { fireEvent, render, screen, within } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { ASK_ANCHOR_DRAFTS_STORAGE_KEY } from "../../src/features/ask/anchorDrafts";
import { AnswerSummary } from "../../src/features/ask/components/AnswerSummary";
import { ClaimList } from "../../src/features/ask/components/ClaimList";
import { FallbackAnswer } from "../../src/features/ask/components/FallbackAnswer";
import { DEMO_ANSWER, DEMO_FALLBACK } from "../../src/features/ask/fixtures/grounded-answer.fixture";

const writeText = vi.fn<() => Promise<void>>();

beforeEach(() => {
  writeText.mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText }
  });
  window.localStorage.clear();
});

afterEach(() => {
  window.localStorage.clear();
  writeText.mockReset();
});

test("AnswerSummary renders metadata and utility actions for the grounded answer card", () => {
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

  const drafts = JSON.parse(window.localStorage.getItem(ASK_ANCHOR_DRAFTS_STORAGE_KEY) ?? "[]");
  expect(drafts).toHaveLength(1);
  expect(drafts[0]?.sourceKind).toBe("answer-summary");
});

test("ClaimList renders tiered support copy, source locations, and card utilities", () => {
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

  const drafts = JSON.parse(window.localStorage.getItem(ASK_ANCHOR_DRAFTS_STORAGE_KEY) ?? "[]");
  expect(drafts).toHaveLength(1);
  expect(drafts[0]?.sourceKind).toBe("claim");
  expect(drafts[0]?.citation?.chunkId).toBe("demo-1");
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
