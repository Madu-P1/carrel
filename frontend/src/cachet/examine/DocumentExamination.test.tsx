import { act, fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { afterEach, describe, expect, it, vi } from "vitest";

import { registerFetchHandler } from "../../../tests/support/mockFetch";
import { closeExamination, examination, examinationHostMounted, openExamination } from "./examineStore";

/* The examination panes load their engines through the shared setup modules;
 * both are doubled here so the tests exercise the overlay's own logic (state,
 * dispatch, honesty notes) without a real worker or WASM. */

interface FakeTextItem {
  str: string;
  transform: number[];
  width: number;
  height: number;
}

const PAGE_TEXT: Record<number, string> = {
  1: "Preamble of the agreement.",
  2: "The party shall pay the fee within thirty days."
};

function fakeItems(page: number): FakeTextItem[] {
  const str = PAGE_TEXT[page] ?? "";
  return [{ str, transform: [12, 0, 0, 12, 72, 700], width: str.length * 6, height: 12 }];
}

const fakePage = (pageNumber: number) => ({
  getViewport: ({ scale }: { scale: number }) => ({
    width: 612 * scale,
    height: 792 * scale,
    scale,
    convertToViewportRectangle: (rect: number[]) => [
      rect[0] * scale,
      (792 - rect[1]) * scale,
      rect[2] * scale,
      (792 - rect[3]) * scale
    ]
  }),
  getTextContent: async () => ({ items: fakeItems(pageNumber) }),
  render: () => ({ promise: Promise.resolve(), cancel: () => {} })
});

const fakePdf = {
  numPages: 2,
  getPage: async (n: number) => fakePage(n),
  destroy: () => Promise.resolve()
};

vi.mock("@/features/reader/lib/pdfjs-setup", () => ({
  loadPdfJs: async () => ({
    getDocument: () => ({
      promise: Promise.resolve(fakePdf),
      destroy: () => Promise.resolve()
    }),
    TextLayer: class {
      render() {
        return Promise.resolve();
      }
    }
  })
}));

vi.mock("docx-preview", () => ({
  renderAsync: async (_data: ArrayBuffer, container: HTMLElement) => {
    container.innerHTML = "<section><p>The indemnity survives termination of this agreement.</p></section>";
  }
}));

import { DocumentExamination } from "./DocumentExamination";

function mockDocumentFile(docId: string, bytes = new Uint8Array([1, 2, 3])): () => void {
  return registerFetchHandler((url, init) => {
    if (url.pathname === `/api/documents/${docId}/file` && init.method.toUpperCase() === "GET") {
      return new Response(bytes, { status: 200 });
    }
    return undefined;
  });
}

function mockDocumentDetail(docId: string, fileType: string): () => void {
  return registerFetchHandler((url, init) => {
    if (url.pathname === `/api/documents/${docId}` && init.method.toUpperCase() === "GET") {
      return new Response(
        JSON.stringify({ document: { id: docId, filename: "x", file_type: fileType }, summary: "" }),
        { headers: { "content-type": "application/json" }, status: 200 }
      );
    }
    return undefined;
  });
}

afterEach(() => {
  act(() => {
    closeExamination();
  });
});

describe("DocumentExamination", () => {
  it("renders nothing while closed but announces the host", () => {
    const { container } = render(<DocumentExamination />);
    expect(container.firstChild).toBeNull();
    expect(examinationHostMounted.value).toBe(true);
  });

  it("opens a PDF record, lands on the cited page, and anchors the passage", async () => {
    mockDocumentFile("doc-1");
    render(<DocumentExamination />);
    act(() => {
      openExamination({
        docId: "doc-1",
        filename: "contract.pdf",
        fileType: "pdf",
        page: 2,
        quote: "shall pay the fee"
      });
    });

    await screen.findByRole("dialog", { name: /Examining contract\.pdf/ });
    await waitFor(() => {
      expect(screen.getByText("Page 2 of 2")).toBeTruthy();
    });
    await waitFor(() => {
      expect(screen.getByText("Cited passage anchored on this page.")).toBeTruthy();
    });
    expect(screen.getByText("Cited passage")).toBeTruthy();
  });

  it("says so, honestly, when the cited passage is nowhere in the PDF", async () => {
    mockDocumentFile("doc-1");
    render(<DocumentExamination />);
    act(() => {
      openExamination({
        docId: "doc-1",
        filename: "contract.pdf",
        fileType: "pdf",
        page: 1,
        quote: "language that does not exist in this record"
      });
    });

    await screen.findByRole("dialog", { name: /Examining contract\.pdf/ });
    await waitFor(() => {
      expect(screen.getByText("Could not locate the cited passage in this record.")).toBeTruthy();
    });
    expect(screen.queryByText("Cited passage")).toBeNull();
  });

  it("renders a DOCX record and underlines the cited run", async () => {
    mockDocumentFile("doc-2");
    render(<DocumentExamination />);
    act(() => {
      openExamination({
        docId: "doc-2",
        filename: "agreement.docx",
        fileType: "docx",
        quote: "indemnity survives termination"
      });
    });

    const dialog = await screen.findByRole("dialog", { name: /Examining agreement\.docx/ });
    await waitFor(() => {
      expect(screen.getByText("Cited passage anchored below.")).toBeTruthy();
    });
    const mark = dialog.querySelector("mark[data-cachet-anchor]");
    expect(mark?.textContent).toBe("indemnity survives termination");
  });

  it("resolves the file type from the engine when the caller does not know it", async () => {
    mockDocumentDetail("doc-3", "docx");
    mockDocumentFile("doc-3");
    render(<DocumentExamination />);
    act(() => {
      openExamination({ docId: "doc-3", filename: "agreement.docx" });
    });

    const dialog = await screen.findByRole("dialog", { name: /Examining agreement\.docx/ });
    await waitFor(() => {
      expect(dialog.querySelector("mark") !== undefined).toBe(true);
      expect(screen.queryByText(/cannot be displayed in place/)).toBeNull();
    });
  });

  it("refuses honestly on a file type it cannot display", async () => {
    render(<DocumentExamination />);
    act(() => {
      openExamination({ docId: "doc-4", filename: "ledger.xlsx", fileType: "xlsx" });
    });

    await screen.findByRole("dialog", { name: /Examining ledger\.xlsx/ });
    expect(
      screen.getByText(/This record's file type \(xlsx\) cannot be displayed in place\./)
    ).toBeTruthy();
  });

  it("surfaces a missing original file instead of a blank pane", async () => {
    registerFetchHandler((url, init) => {
      if (url.pathname === "/api/documents/doc-5/file" && init.method.toUpperCase() === "GET") {
        return new Response("not found", { status: 404 });
      }
      return undefined;
    });
    render(<DocumentExamination />);
    act(() => {
      openExamination({ docId: "doc-5", filename: "gone.docx", fileType: "docx" });
    });

    await screen.findByRole("dialog");
    await waitFor(() => {
      expect(
        screen.getByText("The original file for this record is no longer in the Vault.")
      ).toBeTruthy();
    });
  });

  it("closes on Escape and clears the examination signal", async () => {
    mockDocumentFile("doc-1");
    render(<DocumentExamination />);
    act(() => {
      openExamination({ docId: "doc-1", filename: "contract.pdf", fileType: "pdf" });
    });
    await screen.findByRole("dialog");

    fireEvent.keyDown(document.body, { key: "Escape" });
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    expect(examination.value).toBeNull();
  });

  it("consumes Escape so the layer beneath (the Examination drawer) stays open", async () => {
    mockDocumentFile("doc-1");
    render(<DocumentExamination />);
    act(() => {
      openExamination({ docId: "doc-1", filename: "contract.pdf", fileType: "pdf" });
    });
    await screen.findByRole("dialog");

    // Stand-in for the drawer's bubble-phase document listener.
    let drawerSawEscape = false;
    const drawerListener = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        drawerSawEscape = true;
      }
    };
    document.addEventListener("keydown", drawerListener);
    fireEvent.keyDown(document.body, { key: "Escape" });
    document.removeEventListener("keydown", drawerListener);

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    expect(drawerSawEscape).toBe(false);
  });
});
