import { render, screen } from "@testing-library/preact";
import { expect, test } from "vitest";

import { NoteEditor } from "../../src/features/notes/NoteEditor";
import { jsonResponse, registerFetchHandler } from "../support/mockFetch";

const ORG_PAYLOAD = { subjects: [] };

const NOTE_ROW = {
  id: "note-1",
  doc_id: "doc-1",
  concept_id: null,
  title: "Legacy note",
  content: `
    <h1 onclick="steal()">Topic</h1>
    <p>Keep <strong>bold</strong>.</p>
    <script>alert(window.__CARREL_LOCAL_API_TOKEN)</script>
  `,
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

function mockEditorEndpoints(onSave?: (body: unknown) => void) {
  registerFetchHandler((url, init) => {
    if (url.pathname === "/api/notes/organization" && init.method === "GET") {
      return jsonResponse(ORG_PAYLOAD);
    }
    if (url.pathname === "/api/notes" && init.method === "GET") {
      return jsonResponse({ notes: [NOTE_ROW] });
    }
    if (url.pathname === "/api/notes" && init.method === "POST") {
      const body = init.body ? JSON.parse(init.body as string) : null;
      onSave?.(body);
      return jsonResponse({
        note: {
          id: "note-1",
          title: body?.title ?? "Legacy note",
          content: body?.content ?? ""
        }
      });
    }
    return undefined;
  });
}

test("NoteEditor converts legacy HTML into markdown before editing", async () => {
  mockEditorEndpoints();

  render(<NoteEditor id="note-1" />);

  const body = (await screen.findByRole(
    "textbox",
    { name: /note body/i },
    { timeout: 6000 }
  )) as HTMLElement;
  expect(body.textContent).toContain("Topic");
  expect(body.textContent).toContain("Keep bold.");
  expect(body.innerHTML).toContain("<strong>bold</strong>");
  expect(body.innerHTML).not.toContain("<script");
  expect(body.innerHTML).not.toContain("__CARREL_LOCAL_API_TOKEN");
});
