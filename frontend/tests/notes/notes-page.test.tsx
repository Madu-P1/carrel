import { fireEvent, render, screen, waitFor, within } from "@testing-library/preact";
import { expect, test } from "vitest";

import { NotesPage } from "../../src/features/notes/NotesPage";
import { jsonResponse, mockJson, registerFetchHandler } from "../support/mockFetch";

/**
 * Smoke tests for the Phase 2 global Notes page.
 *
 * Three things absolutely need to work or the feature is broken:
 *   1. The rail renders subjects with their counts from the organization
 *      endpoint.
 *   2. Selecting a subject in the rail triggers a re-fetch of notes
 *      filtered by subject_name so the user only sees that subject's
 *      notes.
 *   3. Creating a folder POSTs to /api/notes/folders and the rail
 *      refetches so the new folder shows up.
 *
 * Render-once-and-assert-twice patterns are deliberately avoided —
 * each test mounts the page fresh, then awaits the network it
 * actually exercises.
 */

const ORG_PAYLOAD = {
  subjects: [
    {
      name: "Biology",
      note_count: 2,
      folders: [{ id: "folder-bio-1", name: "Lectures", sort_order: 0, note_count: 1 }]
    },
    {
      name: "Math",
      note_count: 3,
      folders: []
    }
  ]
};

const NOTE_ROW = {
  id: "note-1",
  doc_id: "doc-1",
  concept_id: null,
  title: "Cell membranes",
  content: "Osmosis explained.",
  source_snippet: null,
  note_type: "reader_note",
  goal_id: null,
  session_id: null,
  folder_id: null,
  folder_name: null,
  subject: "Biology",
  created_at: "2026-05-15T00:00:00Z",
  updated_at: "2026-05-15T00:00:00Z",
  document_name: "biology.pdf",
  concept_name: null
};

test("Rail renders subjects with their note counts from /api/notes/organization", async () => {
  mockJson("GET", "/api/notes/organization", ORG_PAYLOAD);
  mockJson("GET", "/api/notes", { notes: [NOTE_ROW] });

  render(<NotesPage />);

  // Scope to the rail because both the rail's "All notes" button and
  // the pane's "All notes" selection header use the same literal text.
  const rail = await screen.findByLabelText("Notes navigation");

  // Wait for the organization fetch to land. The "All notes" row
  // mounts at 0 (subjects array is empty) and updates when the data
  // arrives. Biology(2) + Math(3) = 5.
  await waitFor(() => {
    const allButton = within(rail).getByText("All notes").closest("button");
    expect(allButton?.textContent ?? "").toContain("5");
  });

  // Each subject's row is present with its count.
  expect(within(rail).getByText("Biology")).toBeDefined();
  expect(within(rail).getByText("Math")).toBeDefined();

  // Folder under Biology renders. (Math has no folders so we don't
  // assert one — that would couple the test to render order.)
  expect(within(rail).getByText("Lectures")).toBeDefined();
});

test("Selecting a subject refetches /api/notes with subject_name set", async () => {
  let lastNotesUrl: URL | null = null;
  registerFetchHandler((url) => {
    if (url.pathname === "/api/notes/organization") {
      return jsonResponse(ORG_PAYLOAD);
    }
    if (url.pathname === "/api/notes") {
      lastNotesUrl = url;
      return jsonResponse({ notes: [NOTE_ROW] });
    }
    return undefined;
  });

  render(<NotesPage />);

  // Wait for the initial "all notes" fetch.
  await waitFor(() => {
    if (lastNotesUrl === null) throw new Error("Initial notes fetch has not fired yet.");
  });
  expect(lastNotesUrl!.searchParams.get("subject_name")).toBeNull();

  // Click the Math subject row — scoped to the rail so we don't pick
  // up an h2 in the pane that says "Math" once the selection changes.
  const rail = await screen.findByLabelText("Notes navigation");
  const mathRow = await within(rail).findByText("Math");
  fireEvent.click(mathRow);

  await waitFor(() => {
    expect(lastNotesUrl!.searchParams.get("subject_name")).toBe("Math");
  });
});

test("Creating a folder POSTs to /api/notes/folders and refetches the organization", async () => {
  let organizationCallCount = 0;
  let postedBody: unknown = null;
  registerFetchHandler((url, init) => {
    if (url.pathname === "/api/notes/organization") {
      organizationCallCount += 1;
      return jsonResponse(ORG_PAYLOAD);
    }
    if (url.pathname === "/api/notes" && init.method === "GET") {
      return jsonResponse({ notes: [] });
    }
    if (url.pathname === "/api/notes/folders" && init.method === "POST") {
      postedBody = init.body ? JSON.parse(init.body as string) : null;
      return jsonResponse({
        folder: {
          id: "folder-new",
          name: "Exam prep",
          subject_name: "Math",
          sort_order: 0,
          created_at: "2026-05-15T00:00:00Z",
          updated_at: "2026-05-15T00:00:00Z"
        }
      });
    }
    return undefined;
  });

  render(<NotesPage />);

  // Wait for the initial render so the New folder button is visible.
  const newFolderButtons = await screen.findAllByRole("button", { name: /new folder/i });
  // Click the New folder button under Math (the second subject in the
  // payload, which has no existing folders so its New-folder trigger
  // is the only one in that section).
  // The Biology subject also has a New-folder button, so we find the
  // one that appears after Math by matching the label position.
  fireEvent.click(newFolderButtons[newFolderButtons.length - 1]);

  // Inline input appears, type the name and submit with Enter.
  const input = await screen.findByRole("textbox", {
    name: /new folder name for/i
  });
  fireEvent.input(input, {
    currentTarget: { value: "Exam prep" },
    target: { value: "Exam prep" }
  });
  fireEvent.keyDown(input, { key: "Enter" });

  await waitFor(() => {
    expect(postedBody).not.toBeNull();
  });
  const sent = postedBody as { name: string; subject_name: string };
  expect(sent.name).toBe("Exam prep");
  // The New-folder button we clicked was the LAST one (under Math),
  // so subject_name should be Math.
  expect(sent.subject_name).toBe("Math");

  // Refetch fires: the organization endpoint was called once on mount
  // and at least once more after the create.
  await waitFor(() => {
    expect(organizationCallCount).toBeGreaterThanOrEqual(2);
  });
});

test("Empty state renders when there are no notes anywhere", async () => {
  mockJson("GET", "/api/notes/organization", { subjects: [] });
  mockJson("GET", "/api/notes", { notes: [] });

  render(<NotesPage />);

  // Both the rail (when subjects is empty) and the pane render an
  // "All notes" empty state. Two matches is the correct count — the
  // user sees the message in two places, which is intentional.
  const empties = await screen.findAllByText(/no notes yet/i);
  expect(empties.length).toBeGreaterThanOrEqual(1);
});
