import { fireEvent, render, screen } from "@testing-library/preact";
import { expect, test, vi } from "vitest";

import { ClaimList } from "../src/features/ask/components/ClaimList";
import { FallbackAnswer } from "../src/features/ask/components/FallbackAnswer";
import { UnsupportedSpans } from "../src/features/ask/components/UnsupportedSpans";
import { DEMO_ANSWER, DEMO_FALLBACK } from "../src/features/ask/fixtures/grounded-answer.fixture";

test("claim list renders claims and clicking a citation chip fires the handler", () => {
  const onCitationClick = vi.fn();
  render(<ClaimList claims={DEMO_ANSWER.claims} onCitationClick={onCitationClick} />);

  expect(screen.getByText(/Mitosis creates two genetically identical daughter cells/i)).toBeDefined();

  fireEvent.click(screen.getByRole("button", { name: /Cell division basics/i }));

  expect(onCitationClick).toHaveBeenCalledTimes(1);
  expect(onCitationClick.mock.calls[0]?.[0]?.chunk_id).toBe("demo-1");
});

test("fallback answer renders the visible unavailable state and snippet claims", () => {
  render(<FallbackAnswer claims={DEMO_FALLBACK.claims} error={DEMO_FALLBACK.error ?? undefined} />);

  expect(screen.getByText(/AI synthesis unavailable/i)).toBeDefined();
  expect(screen.getByText(/Cell-cycle checkpoints pause progression/i)).toBeDefined();
});

test("fallback renders the weak_coverage refusal card with the recovery actions", () => {
  const onBroadenScope = vi.fn();
  const onRephrase = vi.fn();
  render(
    <FallbackAnswer
      claims={DEMO_FALLBACK.claims}
      error="weak_coverage"
      onBroadenScope={onBroadenScope}
      onRephrase={onRephrase}
    />
  );

  expect(screen.getByText(/I refused this one/i)).toBeDefined();
  expect(screen.getByText(/Grounded refusal/i)).toBeDefined();
  expect(screen.getByText(/Nearest passages I did find/i)).toBeDefined();

  fireEvent.click(screen.getByRole("button", { name: /Broaden to Library/i }));
  expect(onBroadenScope).toHaveBeenCalledTimes(1);

  fireEvent.click(screen.getByRole("button", { name: /Rephrase question/i }));
  expect(onRephrase).toHaveBeenCalledTimes(1);
});

test("fallback renders the legacy 'AI synthesis unavailable' state for non-refusal errors", () => {
  render(<FallbackAnswer claims={DEMO_FALLBACK.claims} error="claude_call_failed" />);
  expect(screen.getByText(/AI synthesis unavailable/i)).toBeDefined();
  // Recovery buttons are refusal-only; should NOT render for legacy errors.
  expect(screen.queryByRole("button", { name: /Broaden to Library/i })).toBeNull();
});

test("unsupported spans start collapsed and expand on click", () => {
  render(
    <UnsupportedSpans items={["What role do growth factors play in initiating mitosis?"]} />
  );

  expect(screen.queryByText(/growth factors/i)).toBeNull();

  fireEvent.click(screen.getByRole("button", { name: /Not in your sources/i }));

  expect(screen.getByText(/growth factors/i)).toBeDefined();
});
