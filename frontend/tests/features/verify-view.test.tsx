import { fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { expect, test, vi } from "vitest";

import { VerifyView } from "../../src/features/verify/VerifyView";
import type { VerifyResponse } from "../../src/services/api/endpoints";
import { mockJson, mockSse, mockSseGapped } from "../support/mockFetch";

/**
 * Build the PR3 stream event sequence that resolves to `verify`, mirroring the
 * backend (`services.verify.verify_draft_stream`): a progress event, a claims
 * skeleton with case_verdicts stripped (never a provisional pass), one
 * cite_verdict per claim, then the canonical result. The settled DOM is driven
 * by the final `result`, so converting a `mockJson("POST","/api/verify",X)` to
 * `mockSse("/api/verify/stream", streamEventsFor(X))` keeps each assertion intact.
 */
function streamEventsFor(verify: VerifyResponse): unknown[] {
  const cards = verify.claim_verdicts ?? [];
  const skeleton = cards.map((c) => ({ ...c, case_verdicts: [] }));
  const events: unknown[] = [
    { type: "progress", phase: "extracting" },
    { type: "claims", claim_verdicts: skeleton }
  ];
  for (const card of cards) {
    const cv =
      (card.case_verdicts ?? [])[0] ??
      {
        claim_index: card.claim_index,
        ok: true,
        verdicts: [],
        error_code: null,
        error_message: null
      };
    events.push({ type: "cite_verdict", claim_index: card.claim_index, case_verdict: cv });
  }
  events.push({ type: "result", verify });
  return events;
}

function mockVerifyStream(verify: VerifyResponse) {
  return mockSse("/api/verify/stream", streamEventsFor(verify));
}

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
  mockVerifyStream(SUCCESS_RESPONSE);

  render(<VerifyView />);

  await submitDraft("Mitochondria produce ATP.");

  await waitFor(() => {
    expect(screen.getByText("Claude")).toBeDefined();
  });
});

test("VerifyView renders the provider-quality gate banner when the backend fail-loud gate fires", async () => {
  mockVerifyStream(PROVIDER_GATE_RESPONSE);

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

test("examining a claim opens the drawer with the resolved span and shows no score", async () => {
  // PR5b: the claim is a flagged statement inline-marked in the document body;
  // clicking the mark opens the Examination drawer with the cited source. Use
  // an unsupported claim so it carries a visible flag mark, and place it in the
  // draft (verbatim) so it pins into the document.
  mockVerifyStream({
    draft_text: "Mitochondria produce ATP.",
    claim_verdicts: [
      {
        claim_index: 0,
        claim_text: "Mitochondria produce ATP.",
        verdict: "unsupported",
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
        unsupported_reason: null,
        placement: { placed: true, method: "exact", char_start: 0, char_end: 25 }
      }
    ],
    summary: { total: 1, verified: 0, unsupported: 1, unknown: 0 },
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

  // The claim is inline-marked; clicking it opens the Examination drawer.
  const claimMark = await screen.findByRole("button", { name: /Statement flagged/i });
  fireEvent.click(claimMark);

  // The drawer is the Examination dialog and shows the resolved span.
  expect(await screen.findByRole("dialog", { name: /Examination/i })).toBeDefined();
  expect(await screen.findByText(/ATP is produced by the mitochondria/i)).toBeDefined();
  // The verify surface shows no confidence score, even though resolve returns one.
  expect(screen.queryByText(/%/)).toBeNull();
});

test("renders the disposition taxonomy with flags surfaced and a problem-first summary", async () => {
  mockVerifyStream({
    draft_text: "Two statements.",
    claim_verdicts: [
      {
        claim_index: 0,
        claim_text: "A grounded statement.",
        verdict: "verified",
        citations: [],
        case_verdicts: [],
        unsupported_reason: null
      },
      {
        claim_index: 1,
        claim_text: "Cites a case that does not exist.",
        verdict: "verified",
        citations: [],
        case_verdicts: [
          {
            claim_index: 1,
            ok: true,
            error_code: null,
            error_message: null,
            verdicts: [
              {
                citation: "999 U.S. 999",
                normalized_citation: null,
                status: 404,
                exists: false,
                case_name: null,
                absolute_url: null,
                court: null,
                date_filed: null,
                error_message: null,
                holding_match: null,
                holding_concern: null,
                holding_excerpt: null,
                holding_error: null
              }
            ]
          }
        ],
        unsupported_reason: null
      }
    ],
    summary: { total: 2, verified: 2, unsupported: 0, unknown: 0 },
    latency_ms: 10,
    model: "claude-sonnet-4-6",
    ok: true,
    provider: "claude"
  });

  render(<VerifyView />);

  await submitDraft("two statements");

  // The fabricated citation surfaces as a flag; the grounded statement is the
  // quiet, unmarked pass; the summary leads with the problem count.
  expect(await screen.findByText("Citation not found")).toBeDefined();
  // "Supported" appears both as the claim badge and as a summary stat label.
  expect(screen.getAllByText("Supported").length).toBeGreaterThan(0);
  expect(screen.getByText(/1 of 2 statements need your review/i)).toBeDefined();
});

test("Export certification opens the exhibit and Save as PDF triggers print", async () => {
  mockVerifyStream({
    draft_text: "A grounded statement.",
    claim_verdicts: [
      {
        claim_index: 0,
        claim_text: "A grounded statement.",
        verdict: "verified",
        citations: [
          {
            node_id: 3,
            document_id: "d1",
            document_name: "Brief.pdf",
            section: null,
            page_num: 12,
            snippet: "",
            content: "",
            score: 0.5,
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
  // Save/restore window.print directly; vi.unstubAllGlobals() would also tear
  // down the global fetch mock installed in setup.ts and break later tests.
  const originalPrint = window.print;
  const printSpy = vi.fn();
  window.print = printSpy;

  render(<VerifyView />);

  await submitDraft("a grounded statement");

  fireEvent.click(await screen.findByRole("button", { name: /Export certification/i }));

  // The exhibit opens as a labelled dialog, carries the human-certified line,
  // and shows no confidence score.
  expect(await screen.findByRole("dialog", { name: /Verification certification/i })).toBeDefined();
  expect(screen.getByText(/Reviewed by/i)).toBeDefined();
  expect(screen.queryByText(/%/)).toBeNull();

  fireEvent.click(screen.getByRole("button", { name: /Save as PDF/i }));
  expect(printSpy).toHaveBeenCalled();

  window.print = originalPrint;
});

test("the certification exhibit is keyboard-dismissable with Escape", async () => {
  mockVerifyStream({
    draft_text: "A grounded statement.",
    claim_verdicts: [
      {
        claim_index: 0,
        claim_text: "A grounded statement.",
        verdict: "verified",
        citations: [],
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

  render(<VerifyView />);

  await submitDraft("a grounded statement");

  fireEvent.click(await screen.findByRole("button", { name: /Export certification/i }));
  expect(await screen.findByRole("dialog", { name: /Verification certification/i })).toBeDefined();

  fireEvent.keyDown(document, { key: "Escape" });

  await waitFor(() => {
    expect(screen.queryByRole("dialog", { name: /Verification certification/i })).toBeNull();
  });
});

test("a dropped stream (no result event) never reads as a pass and surfaces a finish error", async () => {
  // Stream sends the claims skeleton + one cite_verdict, then ends WITHOUT a
  // result event (the truncated-stream case). Invariant #6: the un-checked
  // claim must not render "Supported", and the surface must tell the user the
  // verification did not finish.
  mockSse("/api/verify/stream", [
    { type: "progress", phase: "extracting" },
    {
      type: "claims",
      claim_verdicts: [
        {
          claim_index: 0,
          claim_text: "First statement.",
          verdict: "verified",
          citations: [],
          case_verdicts: [],
          unsupported_reason: null
        },
        {
          claim_index: 1,
          claim_text: "Second statement.",
          verdict: "verified",
          citations: [],
          case_verdicts: [],
          unsupported_reason: null
        }
      ]
    },
    {
      type: "cite_verdict",
      claim_index: 0,
      case_verdict: { claim_index: 0, ok: true, verdicts: [], error_code: null, error_message: null }
    }
    // no { type: "result" }: the stream is truncated here.
  ]);

  render(<VerifyView />);

  await submitDraft("two statements");

  // The finish error is surfaced (errors are not swallowed). Both the banner's
  // ruling label and the engine message carry the phrase, so assert on the
  // alert region rather than a unique text node.
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toMatch(/did not finish/i);
  // Nothing was waved through as supported.
  expect(screen.queryByText("Supported")).toBeNull();
  expect(screen.queryByText(/statements are supported/i)).toBeNull();
});

test("mid-stream: a landed cite_verdict renders its real disposition, never a stale 'Supported' (invariant #6)", async () => {
  // Regression test for the blocker the adversarial review caught: a claim that
  // is grounded (verdict "verified") but whose cited case is fabricated (404)
  // must NOT read "Supported" the instant its cite_verdict lands and the
  // "Checking…" mask drops; it must render the real "Citation not found".
  // We hold the stream open AFTER claim 0's cite_verdict (before the terminal
  // result) so the open-stream frame is actually observed. mockSseGapped emits
  // frames across microtasks; pauseAfter=4 holds back the result event.
  const events = [
    { type: "progress", phase: "extracting" },
    {
      type: "claims",
      claim_verdicts: [
        {
          claim_index: 0,
          claim_text: "Per 999 U.S. 999 the rule is X.",
          verdict: "verified",
          citations: [{ node_id: "c1" }],
          case_verdicts: [],
          unsupported_reason: null
        },
        {
          claim_index: 1,
          claim_text: "A second statement still being checked.",
          verdict: "verified",
          citations: [{ node_id: "c2" }],
          case_verdicts: [],
          unsupported_reason: null
        }
      ]
    },
    {
      // claim 0's cited case does not exist (404): a fabricated citation.
      type: "cite_verdict",
      claim_index: 0,
      case_verdict: {
        claim_index: 0,
        ok: true,
        error_code: null,
        error_message: null,
        verdicts: [
          {
            citation: "999 U.S. 999",
            normalized_citation: null,
            status: 404,
            exists: false,
            case_name: null,
            absolute_url: null,
            court: null,
            date_filed: null,
            error_message: null,
            holding_match: null,
            holding_concern: null,
            holding_excerpt: null,
            holding_error: null
          }
        ]
      }
    }
    // result is withheld (pauseAfter below stops before [DONE]).
  ];
  // Frames: [0]progress [1]claims [2]cite_verdict [3]DONE; pause before DONE so
  // the stream stays open with claim 0 landed and claim 1 still checking.
  const { release } = mockSseGapped("/api/verify/stream", events, 3);

  render(<VerifyView />);
  await submitDraft("two statements");

  // Mid-stream: claim 0's 404 must surface as the fabrication flag, and the
  // word "Supported" must appear nowhere (claim 1 is still "Checking…").
  expect(await screen.findByText("Citation not found")).toBeDefined();
  expect(screen.queryByText("Supported")).toBeNull();
  expect(screen.getByText("Checking…")).toBeDefined();

  release();
});
