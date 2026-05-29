import { fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { expect, test } from "vitest";

import { VerifyView } from "../../src/features/verify/VerifyView";
import type { VerifyResponse } from "../../src/services/api/endpoints";
import { mockJson } from "../support/mockFetch";

const SUCCESS_RESPONSE: VerifyResponse = {
  draft_text: "Some claim.",
  claim_verdicts: [],
  summary: { total: 0, verified: 0, unsupported: 0, unknown: 0 },
  latency_ms: 12,
  model: "claude-sonnet-4-6",
  ok: true,
  provider: "claude",
};

const PROVIDER_GATE_RESPONSE: VerifyResponse = {
  draft_text: "Some claim.",
  claim_verdicts: [],
  summary: { total: 0, verified: 0, unsupported: 0, unknown: 0 },
  latency_ms: 0,
  model: "",
  ok: false,
  error: "provider_below_quality_bar",
  provider: "afm",
};

async function submitDraft(value: string) {
  fireEvent.input(screen.getByLabelText(/Draft/i), {
    currentTarget: { value },
    target: { value },
  });
  fireEvent.click(screen.getByRole("button", { name: /Verify the draft/i }));
}

test("VerifyView renders the ProvenanceBadge on a successful verification", async () => {
  mockJson("POST", "/api/verify", SUCCESS_RESPONSE);

  render(<VerifyView />);

  await submitDraft("Mitochondria produce ATP.");

  await waitFor(() => {
    expect(screen.getByText("Claude")).toBeDefined();
  });
});

test("VerifyView renders the provider-quality gate banner when the backend fail-loud gate fires", async () => {
  mockJson("POST", "/api/verify", PROVIDER_GATE_RESPONSE);

  render(<VerifyView />);

  await submitDraft("Mitochondria produce ATP.");

  expect(
    await screen.findByRole("heading", { name: /Claude is required for verification/i })
  ).toBeDefined();
  expect(screen.getByText("ANTHROPIC_API_KEY")).toBeDefined();
  expect(screen.getByText(/Apple Intelligence/i)).toBeDefined();

  // The verdict summary + claim list should be suppressed so the banner is the only response surface.
  expect(screen.queryByText(/statements need your review/i)).toBeNull();
  expect(screen.queryByText(/supported by the sources/i)).toBeNull();
});
