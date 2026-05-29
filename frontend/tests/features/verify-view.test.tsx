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

test("View source opens the side-by-side inspector with the resolved span and shows no score", async () => {
  mockJson("POST", "/api/verify", {
    draft_text: "Mitochondria produce ATP.",
    claim_verdicts: [
      {
        claim_index: 0,
        claim_text: "Mitochondria produce ATP.",
        verdict: "verified",
        citations: [
          {
            node_id: 7,
            document_id: "doc-1",
            document_name: "Cell Biology.pdf",
            section: "Chapter 3",
            page_num: 42,
            snippet: "ATP is produced in the mitochondria.",
            content: "",
            score: 0.8,
            label: "",
            node_type: "body"
          }
        ],
        case_verdicts: [],
        unsupported_reason: null
      }
    ],
    summary: { total: 1, verified: 1, unsupported: 0, unknown: 0 },
    latency_ms: 10,
    model: "claude-sonnet-4-6",
    ok: true,
    provider: "claude"
  });
  mockJson("GET", "/api/evidence/resolve", {
    document_id: "doc-1",
    chunk_id: "7",
    document_name: "Cell Biology.pdf",
    section: "Chapter 3",
    page_num: 42,
    quote_text: "ATP is produced by the mitochondria.",
    confidence: 0.91,
    location_kind: "text_offset",
    bbox: null,
    text_offset_start: 0,
    text_offset_end: 10
  });

  render(<VerifyView />);

  await submitDraft("Mitochondria produce ATP.");

  const viewSource = await screen.findByRole("button", { name: /View source/i });
  fireEvent.click(viewSource);

  // The exact resolved span lands beside the claim.
  expect(await screen.findByText(/ATP is produced by the mitochondria/i)).toBeDefined();
  // The verify surface shows no confidence score, even though resolve returns one.
  expect(screen.queryByText(/%/)).toBeNull();
});
