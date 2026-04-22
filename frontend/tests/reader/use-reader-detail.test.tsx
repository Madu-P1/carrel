import { render, screen, waitFor } from "@testing-library/preact";
import { expect, test } from "vitest";

import { useReaderDetail } from "../../src/features/reader/hooks/useReaderDetail";
import { mockJson } from "../support/mockFetch";

function ReaderDetailProbe({ docId }: { docId: string }) {
  const { data, error, loading } = useReaderDetail(docId);

  if (loading.value && !data.value) {
    return <div>loading</div>;
  }

  if (error.value) {
    return <div>error:{error.value.message}</div>;
  }

  if (!data.value) {
    return <div>idle</div>;
  }

  return (
    <div>
      {data.value.document.filename}::{(data.value.chunks ?? []).length}::{(data.value.concepts ?? []).length}
    </div>
  );
}

test("useReaderDetail loads metadata, chunks, and concepts", async () => {
  mockJson("GET", "/api/documents/doc-1", {
    chunks: [
      { content: "Mitosis produces two daughter cells.", id: "chunk-1", page_num: 1, section: "Mitosis" }
    ],
    concept_options: [],
    concepts: [{ description: "Cell division", id: "concept-1", name: "Mitosis" }],
    counts: { cards: 0, chunks: 1, concepts: 1, questions: 0 },
    document: {
      confidence: 0.92,
      filename: "biology.pdf",
      file_type: "pdf",
      id: "doc-1",
      page_count: 3,
      parser_diagnostics: {},
      question_count: 0,
      status: "ready",
      subject_name: "Biology"
    },
    questions: [],
    summary: "Cell cycle notes"
  });

  render(<ReaderDetailProbe docId="doc-1" />);

  expect(await screen.findByText(/biology\.pdf::1::1/i)).toBeDefined();
});

test("useReaderDetail surfaces fetch errors", async () => {
  mockJson("GET", "/api/documents/doc-error", { detail: "boom" }, 500);

  render(<ReaderDetailProbe docId="doc-error" />);

  await waitFor(() => {
    expect(screen.getByText(/error:API 500/i)).toBeDefined();
  });
});
