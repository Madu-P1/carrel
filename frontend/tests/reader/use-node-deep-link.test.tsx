import { render } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, test } from "vitest";

import { useNodeDeepLink } from "@/features/reader/hooks/useNodeDeepLink";
import { readerState } from "@/features/reader/state";

import { installFetchMock, mockJson, resetFetchMock } from "../support/mockFetch";

function Probe({ docId, nodeId }: { docId: string | null; nodeId: number | null }) {
  useNodeDeepLink(docId, nodeId);
  return null;
}

function _flushMicroAndPaint(): Promise<void> {
  // Pump the microtask queue + a paint frame so the hook's
  // requestAnimationFrame callbacks settle deterministically.
  return new Promise((resolve) => {
    queueMicrotask(() => {
      requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
    });
  });
}

describe("useNodeDeepLink (PR 4.2)", () => {
  beforeEach(() => {
    installFetchMock();
    // Reset reader state so each test starts from a known page.
    readerState.requestedPage.value = 1;
    readerState.currentPage.value = 1;
    readerState.totalPages.value = 50;
  });

  afterEach(() => {
    resetFetchMock();
    document.body.innerHTML = "";
  });

  test("does nothing when nodeId is null", async () => {
    render(<Probe docId="doc-1" nodeId={null} />);
    await _flushMicroAndPaint();
    expect(readerState.requestedPage.value).toBe(1);
  });

  test("requests the node's page after fetching", async () => {
    mockJson("GET", "/api/reader/node/42", {
      node_id: 42,
      doc_id: "doc-1",
      filename: "biology.md",
      subject_name: "Biology",
      node_type: "body",
      heading_path: "Photosynthesis",
      page: 7,
      char_start: 100,
      char_end: 175,
      verbatim_text: "Plants convert sunlight into chemical energy",
    });

    render(<Probe docId="doc-1" nodeId={42} />);
    // Two paint frames + a settle delay to let the async fetch resolve.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(readerState.requestedPage.value).toBe(7);
  });

  test("ignores nodes from a different document", async () => {
    mockJson("GET", "/api/reader/node/42", {
      node_id: 42,
      doc_id: "doc-OTHER",
      filename: null,
      subject_name: null,
      node_type: "body",
      heading_path: "",
      page: 9,
      char_start: 0,
      char_end: 10,
      verbatim_text: "Mismatched doc body",
    });
    render(<Probe docId="doc-1" nodeId={42} />);
    await new Promise((resolve) => setTimeout(resolve, 50));
    // Page should stay at 1 — the node belongs to a different doc, so
    // navigating would be wrong.
    expect(readerState.requestedPage.value).toBe(1);
  });

  test("highlights the verbatim_text when present in the rendered DOM", async () => {
    mockJson("GET", "/api/reader/node/100", {
      node_id: 100,
      doc_id: "doc-bio",
      filename: "biology.md",
      subject_name: "Biology",
      node_type: "body",
      heading_path: "Photosynthesis",
      page: 3,
      char_start: 0,
      char_end: 80,
      verbatim_text: "Photosystem II splits water molecules in the thylakoid membrane",
    });

    // Pre-populate the document with a chunk that contains the
    // verbatim_text. The hook should locate it and wrap with a mark.
    const chunk = document.createElement("p");
    chunk.textContent =
      "Photosystem II splits water molecules in the thylakoid membrane during the light reactions.";
    document.body.appendChild(chunk);

    render(<Probe docId="doc-bio" nodeId={100} />);
    // Wait long enough for fetch + first paint retry to fire.
    await new Promise((resolve) => setTimeout(resolve, 150));
    const mark = document.querySelector("mark.carrel-node-highlight");
    expect(mark).not.toBeNull();
    expect(mark?.textContent).toContain("Photosystem II");
  });

  test("silently degrades when verbatim_text is not in the DOM", async () => {
    mockJson("GET", "/api/reader/node/200", {
      node_id: 200,
      doc_id: "doc-bio",
      filename: null,
      subject_name: null,
      node_type: "body",
      heading_path: "",
      page: 4,
      char_start: 0,
      char_end: 10,
      verbatim_text: "this exact phrase appears nowhere in the document body",
    });
    document.body.appendChild(
      document.createTextNode("Completely different content"),
    );

    render(<Probe docId="doc-bio" nodeId={200} />);
    await new Promise((resolve) => setTimeout(resolve, 150));
    // Page navigation should still happen.
    expect(readerState.requestedPage.value).toBe(4);
    // No highlight added.
    expect(document.querySelector("mark.carrel-node-highlight")).toBeNull();
  });

  test("survives a 404 from the node lookup endpoint", async () => {
    mockJson("GET", "/api/reader/node/999", { detail: "not found" }, 404);
    render(<Probe docId="doc-bio" nodeId={999} />);
    await new Promise((resolve) => setTimeout(resolve, 100));
    // No throw, no highlight, no page change.
    expect(readerState.requestedPage.value).toBe(1);
    expect(document.querySelector("mark.carrel-node-highlight")).toBeNull();
  });
});
