import { fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { expect, test } from "vitest";

import { NotesPage } from "../../src/features/notes/NotesPage";
import { SubjectRail } from "../../src/features/notes/components/SubjectRail";
import { setNotesSelection } from "../../src/features/notes/state";
import { jsonResponse, mockJson, registerFetchHandler } from "../support/mockFetch";

/**
 * Smoke tests for the Phase 2 global Notes page.
 *
 * Architecture note: the Notes-specific rail used to live inside
 * NotesPage. As of the May 16 redesign it lives in the AppShell's
 * WorkspaceSidebar slot (one Carrel logo across the app, content
 * swaps on /notes). Tests that need to exercise the rail mount
 * <SubjectRail /> directly alongside <NotesPage /> — both subscribe
 * to the same module-level signals so behavior is identical.
 *
 * Render-once-and-assert-twice patterns are deliberately avoided —
 * each test mounts fresh, then awaits the network it exercises.
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

function PageWithRail() {
  // Render both surfaces so the rail can be exercised. In production
  // the rail lives inside the AppShell sidebar — for unit tests this
  // co-mount keeps the shared signals subscribed by both consumers.
  return (
    <div data-stillwater="true">
      <SubjectRail />
      <NotesPage />
    </div>
  );
}

test("Rail renders subjects with their note counts from /api/notes/organization", async () => {
  // Reset selection between tests since it's module-scoped.
  setNotesSelection({ kind: "all" });
  mockJson("GET", "/api/notes/organization", ORG_PAYLOAD);
  mockJson("GET", "/api/notes", { notes: [NOTE_ROW] });

  render(<PageWithRail />);

  // Wait for the organization fetch to land. "All notes" badge is in
  // the rail; Biology(2) + Math(3) = 5.
  await waitFor(() => {
    const allButtons = screen.getAllByText("All notes");
    const railAll = allButtons.find((el) =>
      el.closest("button")?.textContent?.includes("5")
    );
    expect(railAll).toBeDefined();
  });

  // "Biology" and "Math" appear in BOTH the rail (as subject rows)
  // AND the pane (as subject-block h2s when notes exist for that
  // subject). Assert presence, not uniqueness.
  expect(screen.getAllByText("Biology").length).toBeGreaterThanOrEqual(1);
  expect(screen.getAllByText("Math").length).toBeGreaterThanOrEqual(1);

  // Folder under Biology renders in the rail AND in any note tile's
  // "Move to folder" dropdown options. Assert presence, not uniqueness.
  expect(screen.getAllByText("Lectures").length).toBeGreaterThanOrEqual(1);
});

test("Selecting a subject refetches /api/notes with subject_name set", async () => {
  setNotesSelection({ kind: "all" });
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

  render(<PageWithRail />);

  await waitFor(() => {
    if (lastNotesUrl === null) throw new Error("Initial notes fetch has not fired yet.");
  });
  expect(lastNotesUrl!.searchParams.get("subject_name")).toBeNull();

  // Click the Math subject row in the rail.
  const mathRow = await screen.findByText("Math");
  fireEvent.click(mathRow);

  await waitFor(() => {
    expect(lastNotesUrl!.searchParams.get("subject_name")).toBe("Math");
  });
});

test("Creating a folder POSTs to /api/notes/folders and refetches the organization", async () => {
  setNotesSelection({ kind: "all" });
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

  render(<PageWithRail />);

  const newFolderButtons = await screen.findAllByRole("button", { name: /new folder/i });
  // The last "New folder" button is under Math (the second subject in
  // the payload, which has no existing folders).
  fireEvent.click(newFolderButtons[newFolderButtons.length - 1]);

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
  expect(sent.subject_name).toBe("Math");

  await waitFor(() => {
    expect(organizationCallCount).toBeGreaterThanOrEqual(2);
  });
});

test("Empty state renders when there are no notes anywhere", async () => {
  setNotesSelection({ kind: "all" });
  mockJson("GET", "/api/notes/organization", { subjects: [] });
  mockJson("GET", "/api/notes", { notes: [] });

  render(<PageWithRail />);

  // The pane's empty hero shows "No notes yet." once the fetches
  // settle. The rail shows "No subjects yet." which is a different
  // string; both surfaces should be distinct now.
  const noNotes = await screen.findByText(/no notes yet/i);
  expect(noNotes).toBeDefined();

  const noSubjects = await screen.findByText(/no subjects yet/i);
  expect(noSubjects).toBeDefined();
});
