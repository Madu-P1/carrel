import { render, screen, waitFor } from "@testing-library/preact";
import { expect, test } from "vitest";

import { useDocumentsQuery } from "../../src/features/library/hooks/useDocumentsQuery";
import { mockJson } from "../support/mockFetch";

function Harness() {
  const query = useDocumentsQuery();

  return (
    <div>
      <span>{query.loading.value ? "Loading" : "Idle"}</span>
      <span>{query.data.value ? `${query.data.value.length} docs` : "No data"}</span>
      <span>{query.error.value ? "Error" : "No error"}</span>
    </div>
  );
}

test("useDocumentsQuery moves through loading to data", async () => {
  mockJson("GET", "/api/documents", [
    {
      concept_count: 0,
      confidence: 0.92,
      duplicate_of: null,
      extracted_at: null,
      file_type: "pdf",
      filename: "mitosis.pdf",
      id: "doc-1",
      page_count: 3,
      parser_diagnostics: {},
      parser_status: "ready",
      question_count: 0,
      source_hash: null,
      source_kind: "uploaded_file",
      status: "ready",
      storage_name: null,
      subject_name: "Biology",
      summary: "Mitosis notes",
      updated_at: null,
      upload_date: null
    }
  ]);

  render(<Harness />);

  expect(screen.getByText("Loading")).toBeDefined();
  expect(await screen.findByText("1 docs")).toBeDefined();
  await waitFor(() => expect(screen.getByText("Idle")).toBeDefined());
  expect(screen.getByText("No error")).toBeDefined();
});
