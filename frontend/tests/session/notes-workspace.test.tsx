import { fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { expect, test } from "vitest";

import { NotesWorkspace } from "../../src/features/session/components/NotesWorkspace";
import { jsonResponse, mockJson, registerFetchHandler } from "../support/mockFetch";

/**
 * Notes mode lives inside an active session. Three flows to cover:
 *   1. Empty textarea → Save/Expand buttons disabled.
 *   2. Expand with AI → backend returns markdown → textarea updates.
 *   3. Save → POST /api/notes with session_id bound.
 *
 * Error-path coverage is the goal here — the rest of the session view
 * is tested at the backend level; this pins the component's API contract.
 */

test("Save and Expand buttons are disabled until the user types", () => {
  render(<NotesWorkspace sessionId="sess-1" sessionObjective="Cover chapter 8" />);

  const save = screen.getByRole("button", { name: /save note/i });
  const expand = screen.getByRole("button", { name: /expand with ai/i });
  expect((save as HTMLButtonElement).disabled).toBe(true);
  expect((expand as HTMLButtonElement).disabled).toBe(true);

  const textarea = screen.getByRole("textbox", { name: /session notes/i });
  fireEvent.input(textarea, { currentTarget: { value: "a" }, target: { value: "a" } });

  expect((save as HTMLButtonElement).disabled).toBe(false);
  expect((expand as HTMLButtonElement).disabled).toBe(false);
});

test("Expand with AI replaces the textarea content with the backend response", async () => {
  mockJson("POST", "/api/notes/expand", {
    expanded_markdown: "# Expanded\n\n- Key idea"
  });

  render(<NotesWorkspace sessionId="sess-1" sessionObjective="Mitosis" />);
  const textarea = screen.getByRole("textbox", { name: /session notes/i }) as HTMLTextAreaElement;
  fireEvent.input(textarea, {
    currentTarget: { value: "raw notes" },
    target: { value: "raw notes" }
  });
  fireEvent.click(screen.getByRole("button", { name: /expand with ai/i }));

  await waitFor(() => {
    expect(textarea.value).toContain("Expanded");
  });
  expect(await screen.findByText(/expanded — review/i)).toBeDefined();
});

test("Save posts content with session_id bound", async () => {
  let receivedBody: unknown = null;
  registerFetchHandler((url, init) => {
    if (url.pathname === "/api/notes" && init.method === "POST") {
      receivedBody = init.body
        ? JSON.parse(init.body as string)
        : null;
      return jsonResponse({
        note: { id: "note-1", title: "Mitosis", content: "raw notes" }
      });
    }
    return undefined;
  });

  render(<NotesWorkspace sessionId="sess-abc" sessionObjective="Mitosis" />);
  const textarea = screen.getByRole("textbox", { name: /session notes/i }) as HTMLTextAreaElement;
  fireEvent.input(textarea, {
    currentTarget: { value: "raw notes" },
    target: { value: "raw notes" }
  });
  fireEvent.click(screen.getByRole("button", { name: /save note/i }));

  await waitFor(() => {
    expect(receivedBody).not.toBeNull();
  });
  const body = receivedBody as { session_id: string; title: string; content: string };
  expect(body.session_id).toBe("sess-abc");
  expect(body.title).toBe("Mitosis");
  expect(body.content).toBe("raw notes");
  expect(await screen.findByText(/^saved\.$/i)).toBeDefined();
});

test("Expand surfaces backend errors inline (no toast)", async () => {
  registerFetchHandler((url, init) => {
    if (url.pathname === "/api/notes/expand" && init.method === "POST") {
      return jsonResponse({ detail: "LLM unavailable" }, 500);
    }
    return undefined;
  });

  render(<NotesWorkspace sessionId="sess-1" sessionObjective="Notes" />);
  const textarea = screen.getByRole("textbox", { name: /session notes/i }) as HTMLTextAreaElement;
  fireEvent.input(textarea, {
    currentTarget: { value: "a" },
    target: { value: "a" }
  });
  fireEvent.click(screen.getByRole("button", { name: /expand with ai/i }));

  // Error text comes from ApiError.message — the thrown shape is
  // "API 500 Internal Server Error".
  expect(await screen.findByText(/API 500/i)).toBeDefined();
});
