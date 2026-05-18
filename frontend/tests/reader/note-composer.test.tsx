import { fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { expect, test, vi } from "vitest";

import { NoteComposer } from "../../src/features/reader/components/source-panel/NoteComposer";
import { jsonResponse, mockJson, registerFetchHandler } from "../support/mockFetch";

/**
 * NoteComposer is the Reader's doc-bound note-writing surface, relocated
 * here from the session view (which had no business owning notes).
 * Coverage mirrors the old session notes test:
 *   1. Empty body → Save/Expand disabled.
 *   2. Expand with AI → backend markdown replaces the body.
 *   3. Save → POST /api/notes bound to doc_id (not session_id) + onSaved fires.
 *   4. Expand errors surface inline (no toast).
 */

test("Save and Expand are disabled until the user types a body", () => {
  render(<NoteComposer docId="doc-1" onSaved={() => {}} />);

  const save = screen.getByRole("button", { name: /save note/i });
  const expand = screen.getByRole("button", { name: /expand the draft/i });
  expect((save as HTMLButtonElement).disabled).toBe(true);
  expect((expand as HTMLButtonElement).disabled).toBe(true);

  const body = screen.getByRole("textbox", { name: /note body/i });
  fireEvent.input(body, { currentTarget: { value: "a" }, target: { value: "a" } });

  expect((save as HTMLButtonElement).disabled).toBe(false);
  expect((expand as HTMLButtonElement).disabled).toBe(false);
});

test("Expand with AI replaces the body with the backend response", async () => {
  mockJson("POST", "/api/notes/expand", {
    expanded_markdown: "# Expanded\n\n- Key idea"
  });

  render(<NoteComposer docId="doc-1" onSaved={() => {}} />);
  const body = screen.getByRole("textbox", { name: /note body/i }) as HTMLTextAreaElement;
  fireEvent.input(body, {
    currentTarget: { value: "raw notes" },
    target: { value: "raw notes" }
  });
  fireEvent.click(screen.getByRole("button", { name: /expand the draft/i }));

  await waitFor(() => {
    expect(body.value).toContain("Expanded");
  });
  expect(await screen.findByText(/expanded\. review/i)).toBeDefined();
});

test("Save posts content bound to doc_id and fires onSaved", async () => {
  let receivedBody: unknown = null;
  registerFetchHandler((url, init) => {
    if (url.pathname === "/api/notes" && init.method === "POST") {
      receivedBody = init.body ? JSON.parse(init.body as string) : null;
      return jsonResponse({
        note: { id: "note-1", title: "biology.pdf", content: "raw notes" }
      });
    }
    return undefined;
  });
  const onSaved = vi.fn();

  render(<NoteComposer docId="doc-abc" documentName="biology.pdf" onSaved={onSaved} />);
  const body = screen.getByRole("textbox", { name: /note body/i }) as HTMLTextAreaElement;
  fireEvent.input(body, {
    currentTarget: { value: "raw notes" },
    target: { value: "raw notes" }
  });
  fireEvent.click(screen.getByRole("button", { name: /save note/i }));

  await waitFor(() => {
    expect(receivedBody).not.toBeNull();
  });
  const sent = receivedBody as {
    doc_id: string;
    session_id: string | null;
    title: string;
    content: string;
    note_type: string;
  };
  // Bound to the document, not a session — that's the whole point of
  // the relocation.
  expect(sent.doc_id).toBe("doc-abc");
  expect(sent.session_id).toBeNull();
  expect(sent.note_type).toBe("reader_note");
  // Title falls back to the document name when the user leaves it blank.
  expect(sent.title).toBe("biology.pdf");
  expect(sent.content).toBe("raw notes");
  await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
  expect(await screen.findByText(/^saved\.$/i)).toBeDefined();
});

test("Expand surfaces backend errors inline (no toast)", async () => {
  registerFetchHandler((url, init) => {
    if (url.pathname === "/api/notes/expand" && init.method === "POST") {
      return jsonResponse({ detail: "LLM unavailable" }, 500);
    }
    return undefined;
  });

  render(<NoteComposer docId="doc-1" onSaved={() => {}} />);
  const body = screen.getByRole("textbox", { name: /note body/i }) as HTMLTextAreaElement;
  fireEvent.input(body, { currentTarget: { value: "a" }, target: { value: "a" } });
  fireEvent.click(screen.getByRole("button", { name: /expand the draft/i }));

  // Error text comes from ApiError.message — "API 500 Internal Server Error".
  expect(await screen.findByText(/API 500/i)).toBeDefined();
});
