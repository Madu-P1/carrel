import { fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  evidence as evidenceApi,
  reader as readerApi,
  type VerifyClaimVerdict
} from "@/services/api/endpoints";

import { SourceInspector, SourceInspectorBody } from "./SourceInspector";
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

// Citation with no stored snippet, so there is nothing to fall back to when
// the live resolve is unavailable or comes back empty.
function cardWithBareCitation(): VerifyClaimVerdict {
  return {
    claim_index: 0,
    claim_text: "Some claim about liability.",
    verdict: "verified",
    citations: [
      {
        document_id: "doc-1",
        node_id: 42,
        document_name: "Master Services Agreement",
        snippet: "",
        content: "",
        page_num: 7,
        section: "§4.2"
      }
    ],
    case_verdicts: []
  } as unknown as VerifyClaimVerdict;
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

  it("focuses Close, traps Tab, and restores focus to the opener on close", async () => {
    mockResolve.mockResolvedValue(resolution());
    mockFetchNode.mockResolvedValue(readerNode(`Recitals. ${QUOTE} thereafter.`));

    render(<SourceInspectorBody card={cardWithCitation()} disposition={DISPOSITION} />);

    const openBtn = await screen.findByText("Open in source");
    openBtn.focus();
    fireEvent.click(openBtn);

    const closeBtn = await screen.findByLabelText("Close source passage");
    await waitFor(() => expect(document.activeElement).toBe(closeBtn));

    // The Close button is the only focusable in the panel, so Tab is prevented
    // and focus stays inside (never walks to the drawer behind the scrim).
    const tab = new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true });
    document.dispatchEvent(tab);
    expect(tab.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(closeBtn);

    // Capture-phase Escape peels this overlay; focus returns to the opener.
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(screen.queryByLabelText("Close source passage")).toBeNull());
    expect(document.activeElement).toBe(openBtn);
  });
});

// C3: the cited-source lookup (evidence.resolve) is its own fetch cycle with
// four states — loading, error, no-match, and a resolved match — and the
// honesty invariant applies to it directly: error and no-match must never
// carry the same "located" affordance (the location-kind badge) as a real
// match.
describe("CitationSource (evidence.resolve fetch states)", () => {
  it("LOADING: shows a distinct loading affordance, never stale or final content", async () => {
    mockResolve.mockImplementation(() => new Promise(() => {}));

    render(<SourceInspectorBody card={cardWithCitation()} disposition={DISPOSITION} />);

    expect(await screen.findByText("Resolving the cited span…")).toBeTruthy();
    expect(screen.queryByText("Exact span")).toBeNull();
    expect(screen.queryByText("Approximate passage")).toBeNull();
    expect(screen.queryByText("No matching source span found.")).toBeNull();
    expect(screen.queryByText(`“${QUOTE}”`)).toBeNull();
  });

  it("ERROR (with a stored snippet): shows the fallback quote but never the located-match badge", async () => {
    mockResolve.mockRejectedValue(new Error("network error"));

    render(<SourceInspectorBody card={cardWithCitation()} disposition={DISPOSITION} />);

    expect(
      await screen.findByText("Showed the stored snippet; live resolve failed.")
    ).toBeTruthy();
    // The honesty invariant: an error must never wear the same success badge
    // a resolved match gets.
    expect(screen.queryByText("Exact span")).toBeNull();
    expect(screen.queryByText("Approximate passage")).toBeNull();
    expect(screen.queryByText("No matching source span found.")).toBeNull();
  });

  it("ERROR (no stored snippet): states the source could not be resolved, never falls through to the no-match copy", async () => {
    mockResolve.mockRejectedValue(new Error("network error"));

    render(<SourceInspectorBody card={cardWithBareCitation()} disposition={DISPOSITION} />);

    expect(await screen.findByText("This source could not be resolved.")).toBeTruthy();
    expect(screen.queryByText("Showed the stored snippet; live resolve failed.")).toBeNull();
    expect(screen.queryByText("No matching source span found.")).toBeNull();
    expect(screen.queryByText("Exact span")).toBeNull();
    expect(screen.queryByText("Approximate passage")).toBeNull();
  });

  it("NO-MATCH: source resolved but carried no citable text — explicit no-match state, never the located badge", async () => {
    mockResolve.mockResolvedValue({ ...resolution(), quote_text: "" });

    render(<SourceInspectorBody card={cardWithBareCitation()} disposition={DISPOSITION} />);

    expect(await screen.findByText("No matching source span found.")).toBeTruthy();
    expect(
      screen.getByText("The cited span could not be read from this source.")
    ).toBeTruthy();
    // The honesty invariant: a resolved-but-empty result must never wear the
    // located-match badge either.
    expect(screen.queryByText("Exact span")).toBeNull();
    expect(screen.queryByText("Approximate passage")).toBeNull();
  });

  it("HAPPY PATH: a resolved match shows the quote and the located badge (the positive control the honesty tests diff against)", async () => {
    mockResolve.mockResolvedValue(resolution());

    render(<SourceInspectorBody card={cardWithCitation()} disposition={DISPOSITION} />);

    expect(await screen.findByText(`“${QUOTE}”`)).toBeTruthy();
    expect(screen.getByText("Exact span")).toBeTruthy();
    expect(screen.queryByText("No matching source span found.")).toBeNull();
    expect(screen.queryByText("This source could not be resolved.")).toBeNull();
    expect(screen.queryByText("Showed the stored snippet; live resolve failed.")).toBeNull();
  });
});

// C2: no source loaded — nothing is selected yet, or no document is anchored.
// The panel must say so explicitly instead of rendering an empty/broken-looking shell.
describe("SourceInspector (no source loaded)", () => {
  it("shows the 'No source loaded' empty state when no claim is selected", () => {
    render(<SourceInspector card={null} disposition={null} onClose={() => {}} />);

    expect(screen.getByText("No source loaded")).toBeTruthy();
    expect(
      screen.getByText("Select a claim or anchor a document in the Vault to inspect its source.")
    ).toBeTruthy();
  });

  it("does not show the 'No source loaded' empty state when a source is provided", () => {
    mockResolve.mockResolvedValue(resolution());
    const card = cardWithCitation();
    render(<SourceInspector card={card} disposition={DISPOSITION} onClose={() => {}} />);

    expect(screen.queryByText("No source loaded")).toBeNull();
    expect(screen.getByText(card.claim_text)).toBeTruthy();
  });
});
