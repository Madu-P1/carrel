import { fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  evidence as evidenceApi,
  reader as readerApi,
  type VerifyClaimVerdict
} from "@/services/api/endpoints";

import { SourceInspectorBody } from "./SourceInspector";
import type { ClaimDisposition } from "./claimDisposition";

// C1: "Open in source" opens the cited passage as an overlay (not a route, which
// would unmount VerifyView and lose an unsaved result). Drive the two endpoints
// deterministically and assert the honest 3-state highlight.
vi.mock("@/services/api/endpoints", () => ({
  evidence: { resolve: vi.fn() },
  reader: { fetchNode: vi.fn() }
}));

const mockResolve = vi.mocked(evidenceApi.resolve);
const mockFetchNode = vi.mocked(readerApi.fetchNode);

const QUOTE = "the indemnified party shall bear no liability";
const DISPOSITION = {
  kind: "supported",
  label: "Supported",
  detail: ""
} as unknown as ClaimDisposition;

function cardWithCitation(): VerifyClaimVerdict {
  return {
    claim_index: 0,
    claim_text: "Some claim about liability.",
    verdict: "verified",
    citations: [
      {
        document_id: "doc-1",
        node_id: 42,
        document_name: "Master Services Agreement",
        snippet: QUOTE,
        content: QUOTE,
        page_num: 7,
        section: "§4.2"
      }
    ],
    case_verdicts: []
  } as unknown as VerifyClaimVerdict;
}

function readerNode(verbatim: string) {
  return {
    node_id: 42,
    doc_id: "doc-1",
    filename: "msa.pdf",
    subject_name: null,
    node_type: "body",
    heading_path: "Article 4 > Liability",
    page: 7,
    char_start: 0,
    char_end: verbatim.length,
    verbatim_text: verbatim
  };
}

function resolution() {
  return {
    document_id: "doc-1",
    chunk_id: "42",
    document_name: "Master Services Agreement",
    section: "§4.2",
    page_num: 7,
    quote_text: QUOTE,
    confidence: 1,
    location_kind: "text_offset" as const,
    bbox: null,
    text_offset_start: 0,
    text_offset_end: QUOTE.length
  };
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("SourcePassageOverlay (open in source)", () => {
  it("ink-underlines the validated quote when it is found in the passage", async () => {
    mockResolve.mockResolvedValue(resolution());
    const passage = `Notwithstanding the foregoing, ${QUOTE} for indirect damages.`;
    mockFetchNode.mockResolvedValue(readerNode(passage));

    const card = cardWithCitation();
    render(<SourceInspectorBody card={card} disposition={DISPOSITION} />);

    fireEvent.click(await screen.findByText("Open in source"));

    const mark = await waitFor(() => {
      const el = document.querySelector("mark");
      expect(el).not.toBeNull();
      return el as HTMLElement;
    });
    expect(mark.textContent).toBe(QUOTE);
    expect(
      screen.queryByText("Could not locate the exact cited run in this passage.")
    ).toBeNull();
  });

  it("highlights the exact source run even after a unicode-folding prefix", async () => {
    mockResolve.mockResolvedValue(resolution());
    // "İ".toLowerCase() is two code units (i + combining dot), so a lowercased
    // indexOf plus a length slice would misalign and underline the wrong run.
    // The run must map to the original passage and equal the validated quote.
    const passage = `İ ${QUOTE} thereafter.`;
    mockFetchNode.mockResolvedValue(readerNode(passage));

    const card = cardWithCitation();
    render(<SourceInspectorBody card={card} disposition={DISPOSITION} />);
    fireEvent.click(await screen.findByText("Open in source"));

    const mark = await waitFor(() => {
      const el = document.querySelector("mark");
      expect(el).not.toBeNull();
      return el as HTMLElement;
    });
    expect(mark.textContent).toBe(QUOTE);
  });

  it("shows the passage with an honest note when the quote is not located", async () => {
    mockResolve.mockResolvedValue(resolution());
    mockFetchNode.mockResolvedValue(readerNode("A wholly different clause with no matching run."));

    const card = cardWithCitation();
    render(<SourceInspectorBody card={card} disposition={DISPOSITION} />);
    fireEvent.click(await screen.findByText("Open in source"));

    expect(
      await screen.findByText("Could not locate the exact cited run in this passage.")
    ).toBeTruthy();
    expect(document.querySelector("mark")).toBeNull();
  });

  it("falls back honestly when the source passage cannot be fetched", async () => {
    mockResolve.mockResolvedValue(resolution());
    mockFetchNode.mockRejectedValue(new Error("404"));

    const card = cardWithCitation();
    render(<SourceInspectorBody card={card} disposition={DISPOSITION} />);
    fireEvent.click(await screen.findByText("Open in source"));

    expect(
      await screen.findByText(
        "This source passage is not available to open in place. The cited text:"
      )
    ).toBeTruthy();
    expect(document.querySelector("mark")).toBeNull();
  });
});

describe("SourceInspectorBody could-not-check (no attached source)", () => {
  function cardNoSource(): VerifyClaimVerdict {
    return {
      claim_index: 0,
      claim_text: "The balance of fees, £95,000 plus interest, was to be transferred.",
      verdict: "unknown",
      citations: [],
      case_verdicts: []
    } as unknown as VerifyClaimVerdict;
  }

  function couldNotCheck(detail: string): ClaimDisposition {
    return {
      kind: "could_not_check",
      tier: "refusal",
      label: "Could not verify",
      detail
    } as unknown as ClaimDisposition;
  }

  // The fatal-demo regression: a could-not-check claim with zero attached citations
  // must NOT claim "no source was loaded" when a record IS loaded. It renders the
  // engine's own honest reason instead, and never the "add the documents" CTA.
  it("renders the engine reason, not a fabricated 'no source was loaded'", () => {
    render(
      <SourceInspectorBody
        card={cardNoSource()}
        disposition={couldNotCheck("no matching passage found in your loaded sources")}
      />
    );
    expect(screen.getByText("no matching passage found in your loaded sources")).toBeTruthy();
    expect(screen.queryByText(/no source was loaded/i)).toBeNull();
    expect(screen.queryByText(/add the documents this draft relies on/i)).toBeNull();
  });

  // The genuine no-record reason is the engine's, not the UI's: still surfaced via
  // disposition.detail, so the message tracks the engine in every branch.
  it("surfaces the no-record reason when the engine reports one", () => {
    render(
      <SourceInspectorBody
        card={cardNoSource()}
        disposition={couldNotCheck(
          "This statement carries a checkable value but no source was provided to check it against."
        )}
      />
    );
    expect(
      screen.getByText(
        "This statement carries a checkable value but no source was provided to check it against."
      )
    ).toBeTruthy();
  });
});
