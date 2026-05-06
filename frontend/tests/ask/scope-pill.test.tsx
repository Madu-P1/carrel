import { fireEvent, render, screen } from "@testing-library/preact";
import { expect, test, vi } from "vitest";

import { ScopePill, type AskScopeValue } from "../../src/features/ask/components/ScopePill";
import type { DocumentRow, SrsSubjectSummary } from "../../src/services/api/endpoints";

function doc(id: string, filename: string, subject: string | null = null): DocumentRow {
  return {
    concept_count: 0,
    confidence: 0.9,
    duplicate_of: null,
    extracted_at: null,
    file_type: "pdf",
    filename,
    id,
    page_count: 10,
    parser_diagnostics: {},
    parser_status: "ready",
    question_count: 0,
    source_hash: null,
    source_kind: "uploaded_file",
    status: "ready",
    storage_name: null,
    subject_name: subject,
    summary: "",
    updated_at: null,
    upload_date: null,
  } as unknown as DocumentRow;
}

function subject(name: string, card_count: number, due: number = 0): SrsSubjectSummary {
  return { subject_name: name, card_count, due_count: due };
}

test("ScopePill renders 'Library' by default", () => {
  render(
    <ScopePill
      documents={[]}
      onChange={() => {}}
      subjects={[]}
      value={{ kind: "library", readiness: "ready" }}
    />
  );
  expect(screen.getByRole("button", { name: /Scope: Library/i })).toBeDefined();
});

test("ScopePill renders 'Doc: <filename>' when a document scope is active", () => {
  const value: AskScopeValue = {
    kind: "document",
    docId: "d1",
    docTitle: "mitosis.pdf",
    readiness: "ready",
  };
  render(
    <ScopePill
      documents={[doc("d1", "mitosis.pdf")]}
      onChange={() => {}}
      subjects={[]}
      value={value}
    />
  );
  expect(screen.getByRole("button", { name: /mitosis\.pdf/ })).toBeDefined();
});

test("ScopePill popover opens on click, closes on Escape", () => {
  render(
    <ScopePill
      documents={[doc("d1", "a.pdf")]}
      onChange={() => {}}
      subjects={[subject("Biology", 12)]}
      value={{ kind: "library", readiness: "ready" }}
    />
  );
  fireEvent.click(screen.getByRole("button", { name: /Scope: Library/i }));
  // Popover shows the three root options.
  expect(screen.getByRole("button", { name: /Library/i, pressed: true })).toBeDefined();
  expect(screen.getByRole("button", { name: /Document/i })).toBeDefined();
  expect(screen.getByRole("button", { name: /Subject/i })).toBeDefined();
  fireEvent.keyDown(window, { key: "Escape" });
  // Root options are gone after Escape.
  expect(screen.queryByRole("button", { name: /Document$/i })).toBeNull();
});

test("ScopePill picks a document via the picker and fires onChange", () => {
  const onChange = vi.fn();
  render(
    <ScopePill
      documents={[doc("d1", "atp.pdf", "Chemistry"), doc("d2", "mitosis.pdf", "Biology")]}
      onChange={onChange}
      subjects={[]}
      value={{ kind: "library", readiness: "ready" }}
    />
  );
  fireEvent.click(screen.getByRole("button", { name: /Scope: Library/i }));
  fireEvent.click(screen.getByRole("button", { name: /Document/i }));
  // The picker's list rows contain filenames.
  fireEvent.click(screen.getByText("mitosis.pdf"));
  expect(onChange).toHaveBeenCalledTimes(1);
  const next = onChange.mock.calls[0]![0] as AskScopeValue;
  expect(next.kind).toBe("document");
  expect(next.docId).toBe("d2");
  expect(next.docTitle).toBe("mitosis.pdf");
});

test("ScopePill picks a subject and fires onChange with the subject name", () => {
  const onChange = vi.fn();
  render(
    <ScopePill
      documents={[]}
      onChange={onChange}
      subjects={[subject("Biology", 12), subject("Chemistry", 8)]}
      value={{ kind: "library", readiness: "ready" }}
    />
  );
  fireEvent.click(screen.getByRole("button", { name: /Scope: Library/i }));
  fireEvent.click(screen.getByRole("button", { name: /Subject/i }));
  fireEvent.click(screen.getByText("Chemistry"));
  expect(onChange).toHaveBeenCalledWith(
    expect.objectContaining({ kind: "subject", subjectName: "Chemistry" })
  );
});

test("ScopePill document picker filters by search query", () => {
  render(
    <ScopePill
      documents={[
        doc("d1", "atp.pdf", "Chemistry"),
        doc("d2", "mitosis.pdf", "Biology"),
        doc("d3", "photosynthesis.pdf", "Biology"),
      ]}
      onChange={() => {}}
      subjects={[]}
      value={{ kind: "library", readiness: "ready" }}
    />
  );
  fireEvent.click(screen.getByRole("button", { name: /Scope: Library/i }));
  fireEvent.click(screen.getByRole("button", { name: /Document/i }));
  fireEvent.input(screen.getByLabelText(/Search documents/i), {
    target: { value: "photo" },
  });
  expect(screen.getByText("photosynthesis.pdf")).toBeDefined();
  expect(screen.queryByText("atp.pdf")).toBeNull();
  expect(screen.queryByText("mitosis.pdf")).toBeNull();
});

test("ScopePill disables the Document option when there are no documents", () => {
  render(
    <ScopePill
      documents={[]}
      onChange={() => {}}
      subjects={[subject("Biology", 1)]}
      value={{ kind: "library", readiness: "ready" }}
    />
  );
  fireEvent.click(screen.getByRole("button", { name: /Scope: Library/i }));
  const docOption = screen.getByRole("button", { name: /Document/i });
  expect(docOption).toHaveProperty("disabled", true);
});
