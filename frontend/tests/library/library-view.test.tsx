import { fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { expect, test, vi } from "vitest";

import { App } from "../../src/app/App";
import { LibraryView } from "../../src/features/library/LibraryView";
import { dispatchMenuCommand } from "../../src/services/native/menu";
import { getFetchCalls, jsonResponse, mockJson, registerFetchHandler } from "../support/mockFetch";

function makeDocument(id: string, filename: string, subject = "Biology") {
  return {
    concept_count: 3,
    confidence: 0.87,
    duplicate_of: null,
    extracted_at: null,
    file_type: "pdf",
    filename,
    id,
    page_count: 4,
    parser_diagnostics: {},
    parser_status: "ready",
    question_count: 5,
    source_hash: null,
    source_kind: "uploaded_file",
    status: "ready",
    storage_name: null,
    subject_name: subject,
    summary: `${filename} summary`,
    updated_at: null,
    upload_date: null
  };
}

/**
 * Fixture for `/api/library/subjects`. The Library home now renders a
 * subject card grid driven by this endpoint; tests need it stubbed even
 * when they care only about drill-down behavior.
 */
function makeSubjectSummaries(
  ...entries: Array<{ subject_name: string; source_count: number }>
): { subjects: unknown[] } {
  return {
    subjects: entries.map((e) => ({
      subject_name: e.subject_name,
      source_count: e.source_count,
      failed_count: 0,
      flashcard_count: 0,
      last_studied_at: null,
      first_failed_doc: null
    }))
  };
}

/** The duplicates endpoint is polled from the Library home too. Always
 *  return a zero-state unless the test specifically cares. */
const EMPTY_DUPLICATES = {
  groups: [],
  total_groups: 0,
  total_duplicates: 0,
  total_cards_in_duplicates: 0
};

test("LibraryView renders a subject grid and drills into a subject on click", async () => {
  mockJson("GET", "/api/documents", [
    makeDocument("doc-1", "mitosis.pdf"),
    makeDocument("doc-2", "atp.pdf", "Chemistry")
  ]);
  mockJson("GET", "/api/library/subjects", makeSubjectSummaries(
    { subject_name: "Biology", source_count: 1 },
    { subject_name: "Chemistry", source_count: 1 }
  ));
  mockJson("GET", "/api/library/duplicates", EMPTY_DUPLICATES);

  render(<LibraryView />);

  // Subject cards render both subject names from the grid.
  expect(await screen.findByText("Biology")).toBeDefined();
  expect(screen.getByText("Chemistry")).toBeDefined();
  // Drill in — files live behind the subject card until clicked.
  fireEvent.click(screen.getByText("Biology"));
  expect(await screen.findByText("mitosis.pdf")).toBeDefined();
});

test("LibraryView shows the empty state when no documents are returned", async () => {
  mockJson("GET", "/api/documents", []);
  mockJson("GET", "/api/library/subjects", makeSubjectSummaries());
  mockJson("GET", "/api/library/duplicates", EMPTY_DUPLICATES);

  render(<LibraryView />);

  expect(await screen.findByText(/No sources yet/i)).toBeDefined();
});

test("LibraryView renders an in-place error state and retry refetches", async () => {
  let attempts = 0;
  registerFetchHandler((url, init) => {
    if (url.pathname === "/api/library/subjects" && init.method === "GET") {
      return jsonResponse(makeSubjectSummaries({ subject_name: "Biology", source_count: 1 }));
    }
    if (url.pathname === "/api/library/duplicates" && init.method === "GET") {
      return jsonResponse(EMPTY_DUPLICATES);
    }
    if (url.pathname !== "/api/documents" || init.method !== "GET") {
      return undefined;
    }
    attempts += 1;
    if (attempts === 1) {
      return jsonResponse({ detail: "boom" }, 500);
    }
    return jsonResponse([makeDocument("doc-1", "mitosis.pdf")]);
  });

  render(<LibraryView />);

  expect(await screen.findByText(/Library failed to load/i)).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: /Retry/i }));
  // After retry, subject grid shows the Biology card.
  expect(await screen.findByText("Biology")).toBeDefined();
});

test("DocumentRow click navigates to the Reader route", async () => {
  mockJson("GET", "/api/documents", [makeDocument("doc-1", "mitosis.pdf")]);
  mockJson("GET", "/api/documents/doc-1", {
    chunks: [],
    concept_options: [],
    concepts: [],
    counts: { cards: 0, chunks: 6, concepts: 0, questions: 0 },
    document: makeDocument("doc-1", "mitosis.pdf"),
    questions: [],
    summary: "Mitosis source"
  });
  mockJson("GET", "/api/library/subjects", makeSubjectSummaries({ subject_name: "Biology", source_count: 1 }));
  mockJson("GET", "/api/library/duplicates", EMPTY_DUPLICATES);

  // Default landing is the Dashboard; jump to /library so the subject
  // card grid is on screen when this test starts interacting.
  window.history.pushState({}, "", "/library");
  render(<App />);

  // Drill into the subject card, then open the document row from inside.
  fireEvent.click(await screen.findByText("Biology"));
  fireEvent.click(await screen.findByRole("button", { name: /Open mitosis\.pdf/i }));

  // After the premium rebuild, the toolbar owns the filename (no separate
  // "PDF reader" badge). The reader is considered loaded once the file-type
  // chip renders inside the toolbar.
  expect(await screen.findByLabelText(/File type: PDF/i)).toBeDefined();
});

test("Delete confirmation opens, deletes the document, and refetches the list", async () => {
  let deleted = false;
  registerFetchHandler((url, init) => {
    if (url.pathname === "/api/documents" && init.method === "GET") {
      return jsonResponse(deleted ? [] : [makeDocument("doc-1", "mitosis.pdf")]);
    }
    if (url.pathname === "/api/documents/doc-1" && init.method === "DELETE") {
      deleted = true;
      return jsonResponse({ deleted: true });
    }
    if (url.pathname === "/api/library/subjects" && init.method === "GET") {
      // Before delete: one Biology source. After delete: empty.
      return jsonResponse(
        deleted
          ? makeSubjectSummaries()
          : makeSubjectSummaries({ subject_name: "Biology", source_count: 1 })
      );
    }
    if (url.pathname === "/api/library/duplicates" && init.method === "GET") {
      return jsonResponse(EMPTY_DUPLICATES);
    }
    return undefined;
  });

  render(<LibraryView />);

  // Drill into Biology, then delete the single document inside.
  fireEvent.click(await screen.findByText("Biology"));
  fireEvent.click(await screen.findByRole("button", { name: "Delete" }));
  expect(screen.getByRole("dialog")).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: /Delete source/i }));

  await waitFor(() => expect(screen.getByText(/No sources yet/i)).toBeDefined());
});

test("Subject rename saves through the API for every document in the section", async () => {
  mockJson("GET", "/api/documents", [makeDocument("doc-1", "mitosis.pdf"), makeDocument("doc-2", "meiosis.pdf")]);
  mockJson("PUT", "/api/documents/doc-1/subject", makeDocument("doc-1", "mitosis.pdf", "Advanced Biology"));
  mockJson("PUT", "/api/documents/doc-2/subject", makeDocument("doc-2", "meiosis.pdf", "Advanced Biology"));
  mockJson("GET", "/api/library/subjects", makeSubjectSummaries({ subject_name: "Biology", source_count: 2 }));
  mockJson("GET", "/api/library/duplicates", EMPTY_DUPLICATES);

  render(<LibraryView />);

  // Drill into Biology so the rename control is visible.
  fireEvent.click(await screen.findByText("Biology"));
  fireEvent.click(await screen.findByRole("button", { name: /Rename subject/i }));
  fireEvent.input(screen.getByLabelText(/Subject name/i), {
    currentTarget: { value: "Advanced Biology" },
    target: { value: "Advanced Biology" }
  });
  fireEvent.click(screen.getByRole("button", { name: /^Save$/i }));

  await waitFor(() => {
    const calls = getFetchCalls().filter((call) => call.method === "PUT");
    expect(calls).toHaveLength(2);
  });
});

test("native file.import menu command triggers the library input click", async () => {
  vi.useFakeTimers();
  mockJson("GET", "/api/documents", []);
  mockJson("GET", "/api/library/subjects", makeSubjectSummaries());
  mockJson("GET", "/api/library/duplicates", EMPTY_DUPLICATES);

  // Default landing is the Dashboard; navigate to /library so the import
  // dropzone is mounted in the page.
  window.history.pushState({}, "", "/library");
  render(<App />);

  await screen.findByRole("button", { name: /Or choose files/i });
  const input = document.getElementById("library-import-input") as HTMLInputElement | null;
  expect(input).not.toBeNull();
  if (!input) {
    vi.useRealTimers();
    return;
  }
  const clickSpy = vi.spyOn(input, "click");

  dispatchMenuCommand("file.import");
  vi.advanceTimersByTime(80);

  expect(clickSpy).toHaveBeenCalledTimes(1);
  vi.useRealTimers();
});

test("LibraryView search filters the document list and announces the match count", async () => {
  mockJson("GET", "/api/documents", [
    makeDocument("doc-1", "mitosis.pdf"),
    makeDocument("doc-2", "atp.pdf", "Chemistry"),
    makeDocument("doc-3", "photosynthesis.pdf")
  ]);
  mockJson("GET", "/api/library/subjects", makeSubjectSummaries(
    { subject_name: "Biology", source_count: 2 },
    { subject_name: "Chemistry", source_count: 1 }
  ));
  mockJson("GET", "/api/library/duplicates", EMPTY_DUPLICATES);

  render(<LibraryView />);

  // Wait for the search input to render (depends on documents fetch completing).
  const input = await screen.findByLabelText(/Search library/i);
  // Typing a filename substring produces a flat "Search results" section.
  fireEvent.input(input, { target: { value: "mito" } });
  expect(await screen.findByText("Search results")).toBeDefined();
  expect(screen.getByText("mitosis.pdf")).toBeDefined();
  // Non-matching docs are hidden while searching.
  expect(screen.queryByText("atp.pdf")).toBeNull();
  expect(screen.queryByText("photosynthesis.pdf")).toBeNull();
  // Match count is announced for AT.
  expect(screen.getByText(/1 match\b/)).toBeDefined();
});

test("LibraryView search shows a zero-result state for no matches", async () => {
  mockJson("GET", "/api/documents", [makeDocument("doc-1", "mitosis.pdf")]);
  mockJson("GET", "/api/library/subjects", makeSubjectSummaries(
    { subject_name: "Biology", source_count: 1 }
  ));
  mockJson("GET", "/api/library/duplicates", EMPTY_DUPLICATES);

  render(<LibraryView />);

  const input = await screen.findByLabelText(/Search library/i);
  fireEvent.input(input, { target: { value: "quantum" } });
  expect(await screen.findByText(/No documents match/)).toBeDefined();
  expect(screen.getByText(/0 matches/)).toBeDefined();
});

test("LibraryView search can also match by subject name", async () => {
  mockJson("GET", "/api/documents", [
    makeDocument("doc-1", "mitosis.pdf", "Biology"),
    makeDocument("doc-2", "atp.pdf", "Chemistry")
  ]);
  mockJson("GET", "/api/library/subjects", makeSubjectSummaries(
    { subject_name: "Biology", source_count: 1 },
    { subject_name: "Chemistry", source_count: 1 }
  ));
  mockJson("GET", "/api/library/duplicates", EMPTY_DUPLICATES);

  render(<LibraryView />);

  const input = await screen.findByLabelText(/Search library/i);
  fireEvent.input(input, { target: { value: "Chem" } });
  expect(await screen.findByText("atp.pdf")).toBeDefined();
  expect(screen.queryByText("mitosis.pdf")).toBeNull();
});
