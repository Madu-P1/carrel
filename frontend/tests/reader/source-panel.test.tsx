import { fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { expect, test } from "vitest";

import { appShell } from "../../src/app/shell/useAppShell";
import { OutlineRail } from "../../src/features/reader/components/OutlineRail";
import { SourcePanel } from "../../src/features/reader/components/source-panel/SourcePanel";
import { readerState } from "../../src/features/reader/state";
import type { DocumentDetail } from "../../src/services/api/endpoints";

const detail: DocumentDetail = {
  chunks: [
    { content: "Mitosis creates identical daughter cells.", id: "chunk-1", page_num: 1, section: "Basics" },
    { content: "Checkpoints pause progression when DNA is damaged.", id: "chunk-2", page_num: 2, section: "Regulation" }
  ],
  concept_options: [],
  concepts: [{ description: "Cell division", id: "concept-1", name: "Mitosis" }],
  counts: { cards: 0, chunks: 2, concepts: 1, questions: 0 },
  document: {
    confidence: 0.91,
    filename: "biology.pdf",
    file_type: "pdf",
    id: "doc-1",
    page_count: 2,
    parser_diagnostics: {},
    concept_count: 1,
    question_count: 0,
    status: "ready",
    summary: "",
    subject_name: "Biology",
    updated_at: "2026-04-20T12:00:00Z"
  },
  questions: [],
  summary: "Cell-cycle summary"
};

test("SourcePanel renders metadata, chunks, and concepts", async () => {
  render(<SourcePanel detail={detail} docId="doc-1" />);

  expect(screen.getByText(/biology\.pdf/i)).toBeDefined();
  expect(screen.getByText(/Confidence 91%/i)).toBeDefined();
  expect(screen.getByText(/Chunks \(2\)/i)).toBeDefined();
  expect(screen.getByText(/Concepts \(1\)/i)).toBeDefined();
});

test("clicking a chunk updates the reader route and requested page", async () => {
  render(<SourcePanel detail={detail} docId="doc-1" />);

  fireEvent.click(screen.getByText(/Checkpoints pause progression/i));

  await waitFor(() => {
    expect(appShell.currentRoute.value).toBe("/reader/doc-1?chunk=chunk-2");
    expect(readerState.requestedPage.value).toBe(2);
  });
});

test("OutlineRail renders the tree and routes clicks into page requests", async () => {
  render(
    <OutlineRail
      outline={[
        {
          children: [
            { children: [], pageNumber: 2, title: "Checkpoints" }
          ],
          pageNumber: 1,
          title: "Cell division"
        }
      ]}
    />
  );

  fireEvent.click(screen.getByText(/Cell division/i));

  await waitFor(() => {
    expect(readerState.requestedPage.value).toBe(1);
  });

  // Outline toggle label changed in the premium rebuild to match the
  // Linear-style "Collapse / Expand" pattern used elsewhere in the app.
  fireEvent.click(screen.getByLabelText(/Collapse outline/i));
  expect(screen.queryByText(/Checkpoints/i)).toBeNull();
});
