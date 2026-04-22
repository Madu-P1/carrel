import { fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { expect, test } from "vitest";

import { SessionView } from "../../src/features/session/SessionView";
import { jsonResponse, mockJson, registerFetchHandler } from "../support/mockFetch";

/**
 * Session start → active → end flow, with the UI-mode prefix round-trip.
 *
 * The SessionView encodes the chosen UI mode into the objective string
 * (e.g. `[ui:pomodoro] Cover chapter 8`) so refreshing the page restores
 * the right mode-specific body. This test verifies the encode side; the
 * decode side is covered implicitly by the active state rendering the
 * correct mode label.
 */

test("begin session disabled until objective is provided", async () => {
  mockJson("GET", "/api/sessions/active", { active_session: null });
  mockJson("GET", "/api/library/subjects", { subjects: [] });

  render(<SessionView />);

  const begin = await screen.findByRole("button", { name: /begin session/i });
  expect((begin as HTMLButtonElement).disabled).toBe(true);

  const objective = screen.getByPlaceholderText(/cover chapter/i);
  fireEvent.input(objective, {
    currentTarget: { value: "Test objective" },
    target: { value: "Test objective" }
  });

  expect((begin as HTMLButtonElement).disabled).toBe(false);
});

test("begin posts the UI-mode prefix in the objective field", async () => {
  let receivedBody: unknown = null;
  registerFetchHandler((url, init) => {
    if (url.pathname === "/api/sessions/active" && init.method === "GET") {
      return jsonResponse({ active_session: null });
    }
    if (url.pathname === "/api/library/subjects" && init.method === "GET") {
      return jsonResponse({ subjects: [] });
    }
    if (url.pathname === "/api/sessions" && init.method === "POST") {
      receivedBody = init.body ? JSON.parse(init.body as string) : null;
      return jsonResponse({
        id: "sess-new",
        objective: "[ui:pomodoro] Test objective",
        mode: "focus_sprint",
        duration_minutes: 25,
        started_at: new Date().toISOString(),
        status: "active"
      });
    }
    return undefined;
  });

  render(<SessionView />);

  const objective = await screen.findByPlaceholderText(/cover chapter/i);
  fireEvent.input(objective, {
    currentTarget: { value: "Test objective" },
    target: { value: "Test objective" }
  });

  fireEvent.click(screen.getByRole("button", { name: /begin session/i }));

  await waitFor(() => {
    expect(receivedBody).not.toBeNull();
  });
  const body = receivedBody as { objective: string; mode: string; duration_minutes: number };
  expect(body.objective).toBe("[ui:pomodoro] Test objective");
  expect(body.mode).toBe("focus_sprint");
  expect(body.duration_minutes).toBe(25);
});

test("flowtime mode posts duration 0 (open-ended) and mixed backend mode", async () => {
  let receivedBody: unknown = null;
  registerFetchHandler((url, init) => {
    if (url.pathname === "/api/sessions/active" && init.method === "GET") {
      return jsonResponse({ active_session: null });
    }
    if (url.pathname === "/api/library/subjects" && init.method === "GET") {
      return jsonResponse({ subjects: [] });
    }
    if (url.pathname === "/api/sessions" && init.method === "POST") {
      receivedBody = init.body ? JSON.parse(init.body as string) : null;
      return jsonResponse({
        id: "sess-flow",
        objective: "[ui:flowtime] Open work",
        mode: "mixed",
        duration_minutes: 0,
        started_at: new Date().toISOString(),
        status: "active"
      });
    }
    return undefined;
  });

  render(<SessionView />);

  // Select Flowtime mode.
  fireEvent.click(await screen.findByRole("button", { name: /flowtime/i }));

  fireEvent.input(screen.getByPlaceholderText(/cover chapter/i), {
    currentTarget: { value: "Open work" },
    target: { value: "Open work" }
  });
  fireEvent.click(screen.getByRole("button", { name: /begin session/i }));

  await waitFor(() => {
    expect(receivedBody).not.toBeNull();
  });
  const body = receivedBody as { objective: string; mode: string; duration_minutes: number };
  expect(body.mode).toBe("mixed");
  expect(body.duration_minutes).toBe(0);
  expect(body.objective).toBe("[ui:flowtime] Open work");
});

test("active session renders End button and objective with prefix stripped", async () => {
  const startedAt = new Date(Date.now() - 60_000).toISOString(); // 1 min ago
  mockJson("GET", "/api/sessions/active", {
    active_session: {
      id: "sess-live",
      goal_id: null,
      objective: "[ui:pomodoro] Cover chapter 8",
      mode: "focus_sprint",
      duration_minutes: 25,
      difficulty_target: null,
      started_at: startedAt,
      status: "active"
    }
  });
  mockJson("GET", "/api/library/subjects", { subjects: [] });

  render(<SessionView />);

  // Prefix stripped in display.
  expect(await screen.findByText(/cover chapter 8/i)).toBeDefined();
  // Must NOT show the raw prefix.
  expect(screen.queryByText(/\[ui:pomodoro\]/)).toBeNull();
  // End button present.
  expect(screen.getByRole("button", { name: /end session/i })).toBeDefined();
});
