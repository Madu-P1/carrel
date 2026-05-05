import { act, fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { expect, test, vi } from "vitest";

import { SessionView } from "../../src/features/session/SessionView";
import { jsonResponse, mockJson, registerFetchHandler } from "../support/mockFetch";

/**
 * Session start → active → end flow, with the UI-mode prefix round-trip.
 *
 * Premium-UI Ship 4 rebuilt the setup form: the primary CTA renamed
 * to "Start focused study session", subjects moved into the ScopePill
 * popover, mode buttons became radio cards, durations became a
 * radiogroup. Tests below reflect that structure.
 */

test("start session is disabled until objective is provided", async () => {
  mockJson("GET", "/api/sessions/active", { active_session: null });
  mockJson("GET", "/api/library/subjects", { subjects: [] });
  mockJson("GET", "/api/documents", []);

  render(<SessionView />);

  const begin = await screen.findByRole("button", {
    name: /start focused study session/i,
  });
  expect((begin as HTMLButtonElement).disabled).toBe(true);

  const objective = screen.getByPlaceholderText(/cover chapter/i);
  fireEvent.input(objective, {
    currentTarget: { value: "Test objective" },
    target: { value: "Test objective" },
  });

  expect((begin as HTMLButtonElement).disabled).toBe(false);
});

test("starting posts the UI-mode prefix in the objective field", async () => {
  let receivedBody: unknown = null;
  registerFetchHandler((url, init) => {
    if (url.pathname === "/api/sessions/active" && init.method === "GET") {
      return jsonResponse({ active_session: null });
    }
    if (url.pathname === "/api/library/subjects" && init.method === "GET") {
      return jsonResponse({ subjects: [] });
    }
    if (url.pathname === "/api/documents" && init.method === "GET") {
      return jsonResponse([]);
    }
    if (url.pathname === "/api/sessions" && init.method === "POST") {
      receivedBody = init.body ? JSON.parse(init.body as string) : null;
      return jsonResponse({
        id: "sess-new",
        objective: "[ui:pomodoro] Test objective",
        mode: "focus_sprint",
        duration_minutes: 25,
        started_at: new Date().toISOString(),
        status: "active",
      });
    }
    return undefined;
  });

  render(<SessionView />);

  const objective = await screen.findByPlaceholderText(/cover chapter/i);
  fireEvent.input(objective, {
    currentTarget: { value: "Test objective" },
    target: { value: "Test objective" },
  });

  fireEvent.click(
    screen.getByRole("button", { name: /start focused study session/i })
  );

  await waitFor(() => {
    expect(receivedBody).not.toBeNull();
  });
  const body = receivedBody as {
    objective: string;
    mode: string;
    duration_minutes: number;
  };
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
    if (url.pathname === "/api/documents" && init.method === "GET") {
      return jsonResponse([]);
    }
    if (url.pathname === "/api/sessions" && init.method === "POST") {
      receivedBody = init.body ? JSON.parse(init.body as string) : null;
      return jsonResponse({
        id: "sess-flow",
        objective: "[ui:flowtime] Open work",
        mode: "mixed",
        duration_minutes: 0,
        started_at: new Date().toISOString(),
        status: "active",
      });
    }
    return undefined;
  });

  render(<SessionView />);

  // Mode cards expose role=radio with the title as the accessible name.
  fireEvent.click(await screen.findByRole("radio", { name: /flowtime/i }));

  fireEvent.input(screen.getByPlaceholderText(/cover chapter/i), {
    currentTarget: { value: "Open work" },
    target: { value: "Open work" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: /start focused study session/i })
  );

  await waitFor(() => {
    expect(receivedBody).not.toBeNull();
  });
  const body = receivedBody as {
    objective: string;
    mode: string;
    duration_minutes: number;
  };
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
      status: "active",
    },
  });
  mockJson("GET", "/api/library/subjects", { subjects: [] });
  mockJson("GET", "/api/documents", []);

  render(<SessionView />);

  // Prefix stripped in display.
  expect(await screen.findByText(/cover chapter 8/i)).toBeDefined();
  // Must NOT show the raw prefix.
  expect(screen.queryByText(/\[ui:pomodoro\]/)).toBeNull();
  // End button present.
  expect(screen.getByRole("button", { name: /end session/i })).toBeDefined();
});

test("pomodoro auto-completes at the chosen timer and sends a notification", async () => {
  const notificationSpy = vi.fn();
  class TestNotification {
    static permission: NotificationPermission = "granted";
    static requestPermission = vi.fn();

    constructor(title: string, options?: NotificationOptions) {
      notificationSpy(title, options);
    }
  }
  Object.defineProperty(window, "Notification", {
    configurable: true,
    value: TestNotification
  });

  let completeCalls = 0;
  const startedAt = new Date(Date.now() - 61_000).toISOString();
  registerFetchHandler((url, init) => {
    if (url.pathname === "/api/sessions/active" && init.method === "GET") {
      return jsonResponse({
        active_session: {
          id: "sess-timer",
          goal_id: null,
          objective: "[ui:pomodoro] Read chapter 8",
          mode: "focus_sprint",
          duration_minutes: 1,
          difficulty_target: null,
          started_at: startedAt,
          status: "active",
        },
      });
    }
    if (url.pathname === "/api/library/subjects" && init.method === "GET") {
      return jsonResponse({ subjects: [] });
    }
    if (url.pathname === "/api/documents" && init.method === "GET") {
      return jsonResponse([]);
    }
    if (url.pathname === "/api/sessions/sess-timer/complete" && init.method === "POST") {
      completeCalls += 1;
      return jsonResponse({
        session_id: "sess-timer",
        mastery_delta: 0,
        weak_concepts: [],
        unresolved_items: [],
        stretch_question: "Pick one weak area and explain it from source evidence without notes.",
        revision_recommendation: "Run a short review sprint on the next due items.",
        suggested_next_session: "Review next due items",
        due_queue_count: 0,
        duration_seconds: 60,
      });
    }
    return undefined;
  });

  render(<SessionView />);
  expect(await screen.findByText(/Read chapter 8/i)).toBeDefined();

  await act(async () => {
    await Promise.resolve();
  });

  await waitFor(() => expect(completeCalls).toBe(1));
  expect(await screen.findByLabelText(/Session complete/i)).toBeDefined();
  expect(notificationSpy).toHaveBeenCalledWith(
    "Carrel Pomodoro complete",
    expect.objectContaining({ body: expect.stringContaining("Read chapter 8") })
  );
});

test("duration chips form a radiogroup; selecting 45 sends 45 minutes", async () => {
  let receivedBody: unknown = null;
  registerFetchHandler((url, init) => {
    if (url.pathname === "/api/sessions/active" && init.method === "GET") {
      return jsonResponse({ active_session: null });
    }
    if (url.pathname === "/api/library/subjects" && init.method === "GET") {
      return jsonResponse({ subjects: [] });
    }
    if (url.pathname === "/api/documents" && init.method === "GET") {
      return jsonResponse([]);
    }
    if (url.pathname === "/api/sessions" && init.method === "POST") {
      receivedBody = init.body ? JSON.parse(init.body as string) : null;
      return jsonResponse({
        id: "sess-45",
        objective: "[ui:pomodoro] 45 work",
        mode: "focus_sprint",
        duration_minutes: 45,
        started_at: new Date().toISOString(),
        status: "active",
      });
    }
    return undefined;
  });

  render(<SessionView />);

  // The duration radiogroup exposes a labelled container.
  await screen.findByRole("radiogroup", { name: /focus duration/i });
  // Click the "45" chip — it's a radio with the value as accessible name.
  const chip45 = screen.getByRole("radio", { name: /^45/i });
  fireEvent.click(chip45);
  expect(chip45.getAttribute("aria-checked")).toBe("true");

  fireEvent.input(screen.getByPlaceholderText(/cover chapter/i), {
    currentTarget: { value: "45 work" },
    target: { value: "45 work" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: /start focused study session/i })
  );

  await waitFor(() => {
    expect(receivedBody).not.toBeNull();
  });
  expect((receivedBody as { duration_minutes: number }).duration_minutes).toBe(45);
});

test("mode cards form a radiogroup with single selection", async () => {
  mockJson("GET", "/api/sessions/active", { active_session: null });
  mockJson("GET", "/api/library/subjects", { subjects: [] });
  mockJson("GET", "/api/documents", []);

  render(<SessionView />);

  await screen.findByRole("radiogroup", { name: /session mode/i });

  const pomodoro = screen.getByRole("radio", { name: /pomodoro/i });
  const notes = screen.getByRole("radio", { name: /notes/i });

  // Default selection is pomodoro.
  expect(pomodoro.getAttribute("aria-checked")).toBe("true");
  expect(notes.getAttribute("aria-checked")).toBe("false");

  fireEvent.click(notes);
  expect(notes.getAttribute("aria-checked")).toBe("true");
  expect(pomodoro.getAttribute("aria-checked")).toBe("false");
});

test("ArrowRight on the mode radiogroup cycles selection", async () => {
  mockJson("GET", "/api/sessions/active", { active_session: null });
  mockJson("GET", "/api/library/subjects", { subjects: [] });
  mockJson("GET", "/api/documents", []);

  render(<SessionView />);

  const group = await screen.findByRole("radiogroup", { name: /session mode/i });
  // Default is pomodoro (first). ArrowRight should land on flowtime.
  fireEvent.keyDown(group, { key: "ArrowRight" });
  expect(
    screen.getByRole("radio", { name: /flowtime/i }).getAttribute("aria-checked")
  ).toBe("true");
});

test("ArrowRight on the duration radiogroup cycles selection", async () => {
  mockJson("GET", "/api/sessions/active", { active_session: null });
  mockJson("GET", "/api/library/subjects", { subjects: [] });
  mockJson("GET", "/api/documents", []);

  render(<SessionView />);

  const group = await screen.findByRole("radiogroup", { name: /focus duration/i });
  // Default is 25. ArrowRight → 45.
  fireEvent.keyDown(group, { key: "ArrowRight" });
  expect(
    screen.getByRole("radio", { name: /^45/i }).getAttribute("aria-checked")
  ).toBe("true");
});
