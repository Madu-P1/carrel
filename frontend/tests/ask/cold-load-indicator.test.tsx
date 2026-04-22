import { render, screen, waitFor } from "@testing-library/preact";
import { expect, test } from "vitest";

import { ColdLoadIndicator } from "../../src/features/ask/components/ColdLoadIndicator";

/**
 * The cold-load heuristic:
 *   - Only considers local-looking providers (undefined, llama*, ollama).
 *   - Only swaps to the "Warming" state after `coldThresholdMs` of pending.
 *   - Only swaps when last successful call is null or older than keep-alive.
 *
 * Covers the common bad cases: fast ollama response (should NEVER show
 * warming), cloud provider (should NEVER show warming), first pending
 * request (should show warming after threshold).
 */

test("renders the normal skeleton before the cold threshold", () => {
  render(
    <ColdLoadIndicator
      pending
      lastSuccessAt={null}
      lastProvider="llama3.1:8b"
      coldThresholdMs={10_000}
    />
  );
  expect(screen.queryByTestId("ask-cold-load")).toBeNull();
  expect(screen.getByTestId("ask-answer-skeleton")).toBeDefined();
});

test("swaps to the warming state once the threshold is crossed with no prior success", async () => {
  render(
    <ColdLoadIndicator
      pending
      lastSuccessAt={null}
      lastProvider="llama3.1:8b"
      coldThresholdMs={20}
    />
  );
  await waitFor(() => {
    expect(screen.getByTestId("ask-cold-load")).toBeDefined();
  });
  expect(screen.getByText(/warming local model/i)).toBeDefined();
});

test("stays as normal skeleton when last success was recent (warm)", async () => {
  const tenSecAgo = Date.now() - 10_000;
  render(
    <ColdLoadIndicator
      pending
      lastSuccessAt={tenSecAgo}
      lastProvider="llama3.1:8b"
      keepAliveMinutes={30}
      coldThresholdMs={20}
    />
  );
  // Wait past the threshold — still should NOT swap because the model
  // should still be in memory (within keep-alive window).
  await new Promise((resolve) => setTimeout(resolve, 60));
  expect(screen.queryByTestId("ask-cold-load")).toBeNull();
  expect(screen.getByTestId("ask-answer-skeleton")).toBeDefined();
});

test("never shows warming state for cloud providers", async () => {
  render(
    <ColdLoadIndicator
      pending
      lastSuccessAt={null}
      lastProvider="claude-sonnet-4"
      coldThresholdMs={20}
    />
  );
  await new Promise((resolve) => setTimeout(resolve, 60));
  expect(screen.queryByTestId("ask-cold-load")).toBeNull();
});

test("renders nothing when not pending", () => {
  render(
    <ColdLoadIndicator
      pending={false}
      lastSuccessAt={null}
      lastProvider="llama3.1:8b"
    />
  );
  expect(screen.queryByTestId("ask-cold-load")).toBeNull();
  expect(screen.queryByTestId("ask-answer-skeleton")).toBeNull();
});
