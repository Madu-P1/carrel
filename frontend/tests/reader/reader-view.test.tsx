import { render, screen, waitFor } from "@testing-library/preact";
import { expect, test, vi } from "vitest";

import { mockJson } from "../support/mockFetch";

vi.mock("pdfjs-dist", () => {
  const GlobalWorkerOptions = { workerSrc: "" };
  const page = {
    getTextContent: vi.fn(async () => ({ items: [] })),
    getViewport: vi.fn(({ scale }: { scale: number }) => ({
      clone: () => ({ height: 900 * scale, width: 700 * scale }),
      height: 900 * scale,
      width: 700 * scale
    })),
    render: vi.fn(() => ({ promise: Promise.resolve(undefined) }))
  };
  const pdf = {
    destroy: vi.fn(),
    getDestination: vi.fn(async () => [{ gen: 0, num: 1 }]),
    getOutline: vi.fn(async () => []),
    getPage: vi.fn(async () => page),
    getPageIndex: vi.fn(async () => 0),
    numPages: 3
  };

  return {
    GlobalWorkerOptions,
    TextLayer: class {
      async render() {
        return undefined;
      }
    },
    getDocument: vi.fn(() => ({
      destroy: vi.fn(async () => undefined),
      promise: Promise.resolve(pdf)
    }))
  };
});

import { ReaderView } from "../../src/features/reader/ReaderView";

test("ReaderView without a document id shows the empty placeholder", () => {
  render(<ReaderView />);
  expect(screen.getByText(/No source selected yet\./i)).toBeDefined();
});

test("ReaderView shows a non-PDF placeholder for text sources", async () => {
  mockJson("GET", "/api/documents/text-doc", {
    chunks: [
      {
        content: "Photosynthesis stores light energy in sugars.",
        id: "chunk-1",
        page_num: 1,
        section: "Photosynthesis"
      }
    ],
    concept_options: [],
    concepts: [],
    counts: { cards: 0, chunks: 1, concepts: 0, questions: 0 },
    document: {
      concept_count: 0,
      confidence: 0.91,
      filename: "notes.md",
      file_type: "md",
      id: "text-doc",
      page_count: 1,
      parser_diagnostics: {},
      question_count: 0,
      status: "ready",
      summary: "",
      subject_name: "General"
    },
    questions: [],
    summary: "Markdown note"
  });

  render(<ReaderView id="text-doc" />);
  // Non-PDF hero header: filename + chunk-count + "plain-text rendering"
  // meta sentence. Text shape updated in the premium rebuild.
  expect(await screen.findByText(/plain-text rendering/i)).toBeDefined();
  expect(screen.getByText(/Photosynthesis stores light energy in sugars\./i)).toBeDefined();
});

test("ReaderView shows toolbar and viewer shell for PDFs", async () => {
  mockJson("GET", "/api/documents/pdf-doc", {
    chunks: [],
    concept_options: [],
    concepts: [],
    counts: { cards: 0, chunks: 12, concepts: 0, questions: 0 },
    document: {
      concept_count: 0,
      confidence: 0.97,
      filename: "biology.pdf",
      file_type: "pdf",
      id: "pdf-doc",
      page_count: 12,
      parser_diagnostics: {},
      question_count: 0,
      status: "ready",
      summary: "",
      subject_name: "Biology"
    },
    questions: [],
    summary: "Biology deck"
  });

  render(<ReaderView id="pdf-doc" />);

  // The PDF toolbar owns the filename now (premium rebuild). File-type
  // chip (PDF) + filename both render inside the toolbar.
  expect(await screen.findByText(/biology\.pdf/i)).toBeDefined();
  expect(screen.getByLabelText(/File type: PDF/i)).toBeDefined();

  await waitFor(() => {
    expect(document.querySelector("[data-page-number='1']")).toBeTruthy();
  });
});
